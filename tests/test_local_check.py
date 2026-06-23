"""Behavior 4: deterministic local runner ``run_local_check``.

Wraps a shell pipeline as the argv ``["bash", "-c", command]`` and runs it through
an injectable runner (the same ``(cmd, cwd) -> CompletedProcess`` contract as
``ci_gate.CommandRunner``), reusing ``shell=False``. Returns a ``CheckResult``
whose ``passed`` is ``exit_code == 0``. It owns its **own** timeout (``ci_gate``
has none to inherit): a runner that raises ``TimeoutExpired``/``OSError`` maps to a
red ``CheckResult(exit_code=-1)`` so a hung command cannot stall the build.
"""

from __future__ import annotations

import subprocess

import pytest

from swe_af.execution.deterministic_check import CheckResult, run_local_check

pytestmark = pytest.mark.unit


def _completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


class _FakeRunner:
    """Records argv+cwd; returns a scripted CompletedProcess or raises."""

    def __init__(self, result=None, raises=None):
        self.result = result
        self.raises = raises
        self.calls: list[tuple[list[str], str]] = []

    def __call__(self, cmd, cwd):
        self.calls.append((list(cmd), cwd))
        if self.raises is not None:
            raise self.raises
        return self.result


def test_nonzero_exit_is_red_with_tail():
    fake = _FakeRunner(result=_completed(stdout="boom", returncode=1))
    res = run_local_check("x", "/tmp", runner=fake)
    assert isinstance(res, CheckResult)
    assert res.passed is False
    assert res.exit_code == 1
    assert "boom" in res.output_tail


def test_zero_exit_is_green():
    fake = _FakeRunner(result=_completed(returncode=0))
    res = run_local_check("true", "/tmp", runner=fake)
    assert res.passed is True
    assert res.exit_code == 0


def test_wraps_command_as_bash_dash_c_argv():
    fake = _FakeRunner(result=_completed())
    run_local_check("pytest -k lexer | tee out", "/work", runner=fake)
    assert fake.calls[0][0] == ["bash", "-c", "pytest -k lexer | tee out"]
    assert fake.calls[0][1] == "/work"


def test_combines_stdout_and_stderr_in_tail():
    fake = _FakeRunner(result=_completed(stdout="out-text", stderr="err-text", returncode=2))
    res = run_local_check("x", "/tmp", runner=fake)
    assert "out-text" in res.output_tail and "err-text" in res.output_tail


def test_timeout_expired_is_red_exit_minus_one():
    fake = _FakeRunner(raises=subprocess.TimeoutExpired(cmd="bash", timeout=1))
    res = run_local_check("sleep 999", "/tmp", runner=fake)
    assert res.passed is False
    assert res.exit_code == -1


def test_oserror_is_red_exit_minus_one():
    fake = _FakeRunner(raises=OSError("bash not found"))
    res = run_local_check("x", "/tmp", runner=fake)
    assert res.passed is False
    assert res.exit_code == -1
    assert "bash not found" in res.output_tail


def test_empty_command_is_defensive_red_without_running():
    fake = _FakeRunner(result=_completed(returncode=0))
    res = run_local_check("   ", "/tmp", runner=fake)
    assert res.passed is False
    assert not fake.calls  # validator blocks this upstream; never reaches the runner


def test_passed_iff_exit_zero_property():
    for rc in (0, 1, 2, 127, -1):
        fake = _FakeRunner(result=_completed(returncode=rc))
        assert run_local_check("x", "/tmp", runner=fake).passed is (rc == 0)


# --- real subprocess smoke: the default runner exercises the bash -c argv wrap ---


def test_real_pipeline_passes(tmp_path):
    res = run_local_check("echo hi | grep hi", str(tmp_path))
    assert res.passed is True
    assert "hi" in res.output_tail


def test_real_exit_one_fails(tmp_path):
    res = run_local_check("exit 1", str(tmp_path))
    assert res.passed is False
    assert res.exit_code == 1
