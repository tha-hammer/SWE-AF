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
import shlex
import subprocess
from collections.abc import Callable, Mapping, Sequence
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
_SHELL_ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


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
class ResolvedCheck:
    """A command the rung will run, tagged with where it came from.

    ``source`` is ``"planned"`` (a typed ``AcceptanceCheck`` the planner authored)
    or ``"manifest"`` (the deterministic project-level fallback).
    """

    command: str
    source: str


def resolve_issue_commands(issue: dict, worktree_path: str) -> list[ResolvedCheck]:
    """Resolve the checks to run for *issue*, typed-first then manifest-fallback.

    Resolution order (pure function of ``(issue, worktree contents)``):
      1. Typed planner checks — ``issue["verification"][*].command`` (each with a
         non-empty command) → ``source="planned"``. Present-and-valid planned checks
         win outright; the manifest is ignored, honoring per-issue specificity (a
         targeted ``pytest -k lexer`` beats a whole-suite ``pytest``).
      2. Else the manifest fallback from ``detect_project_commands`` — the ``test``
         command then the ``build`` command → ``source="manifest"``.
      3. Else ``[]`` — the rung is skipped.

    Whitespace/empty planned commands (Behavior 1 should preclude these) are treated
    as absent, so a degenerate ``verification`` block falls back to the manifest.
    """
    verification = issue.get("verification") or []
    planned = [
        ResolvedCheck(command=entry["command"], source="planned")
        for entry in verification
        if isinstance(entry, dict) and str(entry.get("command") or "").strip()
    ]
    if planned:
        return planned

    commands = detect_project_commands(worktree_path)
    return [
        ResolvedCheck(command=commands[kind], source="manifest")
        for kind in ("test", "build")
        if commands.get(kind)
    ]


def _split_shell_tokens(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return command.split()


def _leading_env_assignments(command: str) -> dict[str, str]:
    tokens = _split_shell_tokens(command)
    if tokens and tokens[0] == "env":
        tokens = tokens[1:]

    assignments: dict[str, str] = {}
    for token in tokens:
        match = _SHELL_ASSIGNMENT.match(token)
        if match is None:
            break
        assignments[match.group(1)] = match.group(2)
    return assignments


def command_supplies_test_db(command: str) -> bool:
    """Return True when *command* assigns DATABASE_URL_TEST inline."""
    return bool(_leading_env_assignments(command).get("DATABASE_URL_TEST"))


def check_requires_test_db(command: str) -> bool:
    """Return True for commands that explicitly declare test-DB dependency."""
    assignments = _leading_env_assignments(command)
    if assignments.get("REQUIRE_TEST_DB") == "1":
        return True
    if "DATABASE_URL_TEST" in command:
        return True
    return False


def deterministic_preflight(
    issue: dict,
    worktree_path: str,
    env: Mapping[str, str],
) -> str | None:
    """Return an environment precondition error for unrunnable DB-backed checks."""
    for check in resolve_issue_commands(issue, worktree_path):
        if (
            check_requires_test_db(check.command)
            and not command_supplies_test_db(check.command)
            and not env.get("DATABASE_URL_TEST")
        ):
            return (
                "Build-node environment precondition failed: deterministic check "
                "requires DATABASE_URL_TEST, but the build environment does not "
                "provide it. Set DATABASE_URL_TEST to a throwaway test database "
                "or provide it inline in the check command. "
                f"Command: `{check.command}`"
            )
    return None


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


@dataclass(frozen=True)
class GateOutcome:
    """Result of the deterministic backpressure gate for one coder iteration.

    ``red`` — a resolved check failed (and was not a benign skip).
    ``tail`` — the formatted failure tail to feed back to the coder.
    ``ran`` — whether any command actually executed (``False`` = nothing resolved,
    so the rung is a transparent no-op and the bound should not be reset).
    """

    red: bool
    tail: str
    ran: bool


# pytest exits 5 when it collected no tests — common in early-TDD issues before any
# test exists. Treat as not-red (skip), not a build-blocking failure.
_PYTEST_NO_TESTS_COLLECTED = 5


def _is_benign_skip(check: ResolvedCheck, result: CheckResult) -> bool:
    first_token = check.command.strip().split(maxsplit=1)[0] if check.command.strip() else ""
    return result.exit_code == _PYTEST_NO_TESTS_COLLECTED and first_token == "pytest"


def _format_gate_tail(check: ResolvedCheck, result: CheckResult) -> str:
    return (
        f"Deterministic check failed (source={check.source}): `{check.command}`\n"
        f"exit code: {result.exit_code}\n"
        f"--- output tail ---\n{result.output_tail}"
    )


def _run_deterministic_gate(
    issue: dict,
    worktree_path: str,
    timeout: float = DET_CHECK_TIMEOUT_SECONDS,
    runner: LocalRunner | None = None,
) -> GateOutcome:
    """Run *issue*'s resolved checks in *worktree_path*; the first real failure reds.

    Deep module: the coding loop calls this and reads a simple ``GateOutcome``. A
    pytest "no tests collected" (exit 5) is a benign skip — an early-TDD issue with
    no tests yet does not block. No commands resolved → ``ran=False`` (no-op rung).
    """
    resolved = resolve_issue_commands(issue, worktree_path)
    if not resolved:
        return GateOutcome(red=False, tail="", ran=False)
    for check in resolved:
        result = run_local_check(check.command, worktree_path, runner=runner, timeout=timeout)
        if result.passed or _is_benign_skip(check, result):
            continue
        return GateOutcome(red=True, tail=_format_gate_tail(check, result), ran=True)
    return GateOutcome(red=False, tail="", ran=True)
