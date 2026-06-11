"""Behavior 6: the gated deterministic backpressure rung in ``run_coding_loop``.

Real DAGState/ExecutionConfig/artifact-IO; the only mocks are ``call_fn`` (the
agent dispatcher) and ``local_runner`` (the deterministic check runner). A red
check under the retry cap forces ``action="fix"``, **skips the reviewer/QA branch**
(zero LLM calls while red), folds the failure tail into the persisted ``summary``
and the next-iteration ``feedback``, and falls through to the checkpoint/history
machinery. After the cap it downgrades to advisory and lets the LLM path decide.
"""

from __future__ import annotations

import asyncio
import subprocess

import pytest

from swe_af.execution.coding_loop import _load_iteration_state, run_coding_loop
from swe_af.execution.schemas import (
    BuildConfig,
    DAGState,
    ExecutionConfig,
    IssueOutcome,
)

pytestmark = pytest.mark.functional


def _completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


class _SpyRunner:
    """Local runner returning scripted CompletedProcess values; records argv+cwd.

    Pops results in order; reuses the last once exhausted (so "always red" is one
    element). Matches the ``(cmd, cwd) -> CompletedProcess`` LocalRunner contract.
    """

    def __init__(self, results):
        self._results = list(results)
        self.calls: list[tuple[list[str], str]] = []

    def __call__(self, cmd, cwd):
        self.calls.append((list(cmd), cwd))
        if len(self._results) > 1:
            return self._results.pop(0)
        return self._results[0]


class _RecordingCallFn:
    """Scripted async call_fn; records agent labels so reviewer calls can be spied."""

    def __init__(self, reviewer_approve: bool = False):
        self.labels: list[str] = []
        self._coder_calls = 0
        self._reviewer_approve = reviewer_approve

    def __call__(self, agent_name, **kwargs):
        self.labels.append(agent_name)

        async def _invoke():
            if "run_coder" in agent_name:
                self._coder_calls += 1
                return {"files_changed": ["a.py"], "summary": f"did{self._coder_calls}", "complete": True}
            if "run_code_reviewer" in agent_name:
                return {
                    "approved": self._reviewer_approve,
                    "blocking": False,
                    "summary": "approved" if self._reviewer_approve else "needs work",
                }
            if "run_qa_synthesizer" in agent_name:
                return {"action": "approve" if self._reviewer_approve else "fix", "summary": "s", "stuck": False}
            if "run_qa" in agent_name:
                return {"passed": True, "summary": "tp", "test_failures": []}
            return {}

        return _invoke()

    def reviewer_call_count(self) -> int:
        return sum(1 for label in self.labels if "run_code_reviewer" in label)

    def reviewer_called(self) -> bool:
        return self.reviewer_call_count() > 0


def _dag_state(artifacts_dir: str) -> DAGState:
    return DAGState(
        repo_path="/tmp/fake-repo",
        artifacts_dir=artifacts_dir,
        prd_path="",
        architecture_path="",
        issues_dir="",
    )


def _planned(cmd: str = "pytest -k x"):
    return [{"description": "run", "command": cmd, "kind": "test"}]


def _issue(verification=None, **extra) -> dict:
    issue = {
        "name": "ISSUE-1",
        "title": "T",
        "description": "d",
        "acceptance_criteria": ["AC-1"],
        "depends_on": [],
        "provides": [],
        "worktree_path": "/tmp/fake-repo",
        "branch_name": "test/i1",
    }
    if verification is not None:
        issue["verification"] = verification
    issue.update(extra)
    return issue


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_red_under_cap_forces_fix_skips_reviewer_and_checkpoints(tmp_path):
    runner = _SpyRunner([_completed(stdout="AssertionError: boom", returncode=1)])
    call_fn = _RecordingCallFn()
    dag = _dag_state(str(tmp_path))
    config = ExecutionConfig(max_coding_iterations=1, agent_timeout_seconds=30)

    result = _run(run_coding_loop(_issue(verification=_planned()), dag, call_fn, "node", config, local_runner=runner))

    # The gate ran the issue's command as the bash -c argv in the worktree.
    assert runner.calls[0][0] == ["bash", "-c", "pytest -k x"]
    assert runner.calls[0][1] == "/tmp/fake-repo"
    # Reviewer was NOT called while red (zero LLM calls spent).
    assert not call_fn.reviewer_called()
    # The iteration checkpoint WAS still written (fall-through, not continue).
    ckpt = _load_iteration_state(str(tmp_path), "ISSUE-1", build_id=dag.build_id)
    assert ckpt is not None
    assert ckpt["det_check_attempts"] == 1
    assert "AssertionError" in ckpt["feedback"]  # tail folded into persisted summary
    # No crash on the exhausted path; non-blocking + changes -> accept-with-debt.
    assert result.outcome == IssueOutcome.COMPLETED_WITH_DEBT


def test_flag_off_never_runs_gate(tmp_path):
    runner = _SpyRunner([_completed(returncode=1)])  # would be red if ever called
    call_fn = _RecordingCallFn(reviewer_approve=True)
    config = ExecutionConfig(max_coding_iterations=1, agent_timeout_seconds=30, enable_deterministic_checks=False)

    result = _run(run_coding_loop(_issue(verification=_planned()), _dag_state(str(tmp_path)), call_fn, "node", config, local_runner=runner))

    assert not runner.calls  # gate never ran
    assert call_fn.reviewer_called()  # normal path ran, byte-identical to today
    assert result.outcome == IssueOutcome.COMPLETED


def test_no_commands_resolved_skips_gate(tmp_path):
    empty_repo = tmp_path / "repo"
    empty_repo.mkdir()
    runner = _SpyRunner([_completed(returncode=1)])
    call_fn = _RecordingCallFn(reviewer_approve=True)
    config = ExecutionConfig(max_coding_iterations=1, agent_timeout_seconds=30)
    issue = _issue(worktree_path=str(empty_repo))  # no verification, no manifest

    result = _run(run_coding_loop(issue, _dag_state(str(tmp_path / "art")), call_fn, "node", config, local_runner=runner))

    assert not runner.calls
    assert call_fn.reviewer_called()
    assert result.outcome == IssueOutcome.COMPLETED


def test_green_runs_reviewer_and_resets_attempts(tmp_path):
    runner = _SpyRunner([_completed(stdout="ok", returncode=0)])
    call_fn = _RecordingCallFn(reviewer_approve=True)
    dag = _dag_state(str(tmp_path))
    config = ExecutionConfig(max_coding_iterations=1, agent_timeout_seconds=30)

    result = _run(run_coding_loop(_issue(verification=_planned()), dag, call_fn, "node", config, local_runner=runner))

    assert runner.calls  # gate ran
    assert call_fn.reviewer_called()  # green -> reviewer path runs
    assert result.outcome == IssueOutcome.COMPLETED
    ckpt = _load_iteration_state(str(tmp_path), "ISSUE-1", build_id=dag.build_id)
    assert ckpt["det_check_attempts"] == 0


def test_dependency_miss_fed_back_as_red(tmp_path):
    runner = _SpyRunner([_completed(stderr="ModuleNotFoundError: No module named 'foo'", returncode=1)])
    call_fn = _RecordingCallFn()
    dag = _dag_state(str(tmp_path))
    config = ExecutionConfig(max_coding_iterations=1, agent_timeout_seconds=30)

    _run(run_coding_loop(_issue(verification=_planned()), dag, call_fn, "node", config, local_runner=runner))

    assert not call_fn.reviewer_called()
    ckpt = _load_iteration_state(str(tmp_path), "ISSUE-1", build_id=dag.build_id)
    assert "ModuleNotFoundError" in ckpt["feedback"]


def test_cap_reached_downgrades_to_advisory_no_infinite_loop(tmp_path):
    runner = _SpyRunner([_completed(stdout="still red", returncode=1)])  # always red
    call_fn = _RecordingCallFn(reviewer_approve=True)
    config = ExecutionConfig(max_coding_iterations=5, agent_timeout_seconds=30, max_deterministic_check_retries=2)

    result = _run(run_coding_loop(_issue(verification=_planned()), _dag_state(str(tmp_path)), call_fn, "node", config, local_runner=runner))

    # 2 reds blocked (no reviewer), 3rd red downgraded to advisory -> reviewer once.
    assert call_fn.reviewer_call_count() == 1
    assert result.outcome == IssueOutcome.COMPLETED  # terminates, no infinite loop


def test_det_check_attempts_survives_resume(tmp_path):
    dag = _dag_state(str(tmp_path))
    # Pre-seed a checkpoint mid-red-streak: one red already counted.
    from swe_af.execution.coding_loop import _save_iteration_state

    _save_iteration_state(
        str(tmp_path),
        "ISSUE-1",
        {
            "iteration": 1,
            "feedback": "prev red",
            "files_changed": [],
            "iteration_history": [
                {"iteration": 1, "action": "fix", "summary": "red", "qa_passed": None,
                 "review_approved": False, "review_blocking": False, "path": "default"}
            ],
            "det_check_attempts": 1,
        },
        build_id=dag.build_id,
    )
    runner = _SpyRunner([_completed(stdout="red", returncode=1)])  # always red
    call_fn = _RecordingCallFn(reviewer_approve=True)
    config = ExecutionConfig(max_coding_iterations=3, agent_timeout_seconds=30, max_deterministic_check_retries=2)

    result = _run(run_coding_loop(_issue(verification=_planned()), dag, call_fn, "node", config, local_runner=runner))

    # Loaded attempts=1 means only ONE more block (iter2) then advisory at iter3.
    # If the counter had reset to 0, iter2+iter3 would both block and the loop would
    # exhaust at max=3 without ever calling the reviewer.
    assert call_fn.reviewer_called()
    assert result.outcome == IssueOutcome.COMPLETED


def test_config_propagation_build_to_execution():
    d = BuildConfig(enable_deterministic_checks=False).to_execution_config_dict()
    assert d["max_deterministic_check_retries"] == 2
    assert d["deterministic_check_timeout_seconds"] == 600
    # ExecutionConfig has extra="forbid": these keys must be accepted, and the flag
    # must propagate (an omitted dict line would silently default to True).
    assert ExecutionConfig(**d).enable_deterministic_checks is False
