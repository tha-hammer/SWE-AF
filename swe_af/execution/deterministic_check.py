"""Deterministic project-command detection (pure — no LLM, no network).

Supplies a project-level fallback build/test command for the deterministic
backpressure rung when the planner did not author a per-issue ``AcceptanceCheck``.
Detection is a pure function of the worktree's manifest files: same directory
contents always yield the same dict (idempotent).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from swe_af.execution._proc import _tail

# Default per-check timeout (seconds). Load-bearing: ci_gate has no per-subprocess
# timeout to inherit, so without this a hung command (cold-worktree pytest blocked
# on the network, a watch-mode runner) would stall the build forever. Overridable
# per call and via the deterministic_check_timeout_seconds config knob (Behavior 6).
DET_CHECK_TIMEOUT_SECONDS: int = 600

# Injectable runner contract — identical to ci_gate.CommandRunner: argv list + cwd.
LocalRunner = Callable[[Sequence[str], str], "subprocess.CompletedProcess[str]"]

# A Makefile target line for the conventional ``test`` target: "test:" / "test :"
# (optionally with prerequisites). Anchored at line start so "pytest:" / "test_x:"
# do not match.
_MAKE_TEST_TARGET = re.compile(r"^test\s*:")


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _package_json_commands(path: str) -> dict[str, str]:
    """npm commands gated on the presence of the matching ``scripts`` entry."""
    try:
        data = json.loads(_read_text(path))
    except (OSError, ValueError):
        return {}
    scripts = data.get("scripts") if isinstance(data, dict) else None
    scripts = scripts if isinstance(scripts, dict) else {}
    commands: dict[str, str] = {}
    if scripts.get("build"):
        commands["build"] = "npm run build"
    if scripts.get("test"):
        commands["test"] = "npm test"
    return commands


def _makefile_commands(path: str) -> dict[str, str]:
    """``make test`` only when the Makefile actually declares a ``test`` target."""
    try:
        text = _read_text(path)
    except OSError:
        return {}
    if any(_MAKE_TEST_TARGET.match(line) for line in text.splitlines()):
        return {"test": "make test"}
    return {}


# Manifest -> command-builder, in precedence order (first present manifest wins
# when several coexist). The first tuple element is a manifest filename or a tuple
# of equivalent alternatives. Adding a fixed-command language is a one-line entry.
_DETECTORS: tuple[tuple[object, object], ...] = (
    ("Cargo.toml", lambda _p: {"build": "cargo build", "test": "cargo test"}),
    ("go.mod", lambda _p: {"build": "go build ./...", "test": "go test ./..."}),
    (("pyproject.toml", "setup.py"), lambda _p: {"test": "pytest"}),
    ("package.json", _package_json_commands),
    ("Makefile", _makefile_commands),
)


def detect_project_commands(worktree_path: str) -> dict[str, str]:
    """Return ``{kind: command}`` for the highest-precedence manifest present.

    Precedence: ``Cargo.toml`` > ``go.mod`` > ``pyproject.toml``/``setup.py`` >
    ``package.json`` > ``Makefile``. The first manifest that exists determines the
    result (content-dependent manifests — ``package.json``, ``Makefile`` — may yield
    an empty dict, e.g. a ``package.json`` with no ``test`` script). No manifest /
    unreadable path → ``{}`` (the rung is then skipped).
    """
    for names, builder in _DETECTORS:
        candidates = (names,) if isinstance(names, str) else names
        for name in candidates:
            candidate = os.path.join(worktree_path, name)
            if os.path.isfile(candidate):
                return builder(candidate)
    return {}


@dataclass(frozen=True)
class CheckResult:
    """Outcome of running one deterministic check command.

    ``passed`` is exactly ``exit_code == 0``. ``exit_code`` is ``-1`` for a
    timeout / OS error (the command never produced a real exit code).
    """

    passed: bool
    exit_code: int
    output_tail: str


def _default_local_runner(
    cmd: Sequence[str], cwd: str, timeout: float = DET_CHECK_TIMEOUT_SECONDS
) -> "subprocess.CompletedProcess[str]":
    """Real runner: ``shell=False`` (the pipeline is interpreted by ``bash -c``)."""
    return subprocess.run(
        list(cmd),
        cwd=cwd or None,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def run_local_check(
    command: str,
    cwd: str,
    runner: LocalRunner | None = None,
    timeout: float = DET_CHECK_TIMEOUT_SECONDS,
) -> CheckResult:
    """Run *command* in *cwd* and return a ``CheckResult`` (passed iff exit 0).

    The command is wrapped as the argv ``["bash", "-c", command]`` so shell
    pipelines (``| jq``, ``>``, ``&&``) run while keeping ``shell=False`` — the same
    trust boundary as the agent's own Bash (worktree + container). The default
    runner enforces *timeout*; a ``TimeoutExpired``/``OSError`` becomes a red
    ``CheckResult(exit_code=-1)`` so a hung command cannot stall the build. An empty
    command (Behavior 1's validator blocks it upstream) is a defensive red and never
    reaches the runner.
    """
    if not command.strip():
        return CheckResult(passed=False, exit_code=-1, output_tail="empty command")

    argv: list[str] = ["bash", "-c", command]
    try:
        if runner is None:
            completed = _default_local_runner(argv, cwd, timeout)
        else:
            completed = runner(argv, cwd)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return CheckResult(passed=False, exit_code=-1, output_tail=_tail(str(exc) or "timeout"))

    output = (completed.stdout or "") + (completed.stderr or "")
    return CheckResult(
        passed=completed.returncode == 0,
        exit_code=completed.returncode,
        output_tail=_tail(output),
    )
