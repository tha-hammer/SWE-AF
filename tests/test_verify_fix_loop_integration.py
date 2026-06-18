"""Integration tests for the verify/fix loop wiring inside swe_af.app.build().

Drives build() with a substring-routed mock app.call (pattern:
tests/fast/test_app.py:260). Asserts the loop wires the recovery helpers:
snapshot written, convergence break, accept-partial debt, namespaced fix
checkpoints, soft-deadline short-circuit, and cross-cycle history.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("AGENTFIELD_SERVER", "http://localhost:9999")

import swe_af.app as app_mod


def _passthrough_unwrap(raw, name):
    if isinstance(raw, dict) and "result" in raw and "status" in raw:
        return raw["result"]
    return raw


def _make_plan_result(artifacts: str) -> dict:
    return {
        "prd": {"validated_description": "d", "acceptance_criteria": ["C1"]},
        "architecture": {},
        "review": {},
        "issues": [{"name": "i0"}],
        "levels": [["i0"]],
        "file_conflicts": [],
        "artifacts_dir": artifacts,
        "rationale": "r",
    }


def _make_dag_result(n: int = 3) -> dict:
    return {
        "all_issues": [{"name": f"i{i}"} for i in range(n)],
        "completed_issues": [{"name": "i0"}],
        "failed_issues": [],
        "skipped_issues": [],
        "accumulated_debt": [],
    }


def _verification(passed: bool, criteria: list[str]) -> dict:
    return {
        "passed": passed,
        "summary": "v",
        "criteria_results": [
            {"criterion": c, "passed": False, "evidence": f"{c}-evidence"} for c in criteria
        ],
    }


def _git_repo(tmp_path) -> str:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    return str(repo)


def _router(verifications, recorder, fix_issues=True):
    """Build a substring-routed async mock app.call.

    ``verifications`` is a list popped per run_verifier call.
    ``recorder`` accumulates (target, kwargs) tuples.
    """

    async def mock_call(target: str, **kwargs):
        recorder.append((target, kwargs))
        if ".run_git_init" in target:
            return {"success": False, "error_message": "no git in test"}
        if ".run_verifier" in target:
            return verifications.pop(0)
        if ".generate_fix_issues" in target:
            return {
                "fix_issues": [{"name": "fix-c1", "title": "fix"}] if fix_issues else [],
                "debt_items": [],
                "summary": "",
            }
        if target.endswith(".execute"):
            return _make_dag_result()
        if ".run_repo_finalize" in target:
            return {"success": True, "summary": "done"}
        return {}

    return mock_call


async def _run_build(tmp_path, verifications, recorder, config, monkeypatch, fix_issues=True):
    monkeypatch.delenv("HAX_API_KEY", raising=False)
    repo = _git_repo(tmp_path)
    artifacts = os.path.join(os.path.abspath(repo), ".artifacts")
    plan_result = _make_plan_result(artifacts)

    config = {"git_init_max_retries": 1, "git_init_retry_delay": 0.0, **config}
    mock_call = _router(verifications, recorder, fix_issues=fix_issues)
    # Inject the plan_result through the .plan route via a closure variable.
    async def routed(target, **kwargs):
        if target.endswith(".plan"):
            recorder.append((target, kwargs))
            return plan_result
        return await mock_call(target, **kwargs)

    with (
        patch.object(app_mod.app, "call", side_effect=routed),
        patch.object(app_mod.app, "note", return_value=None),
        patch.object(app_mod, "_unwrap", side_effect=_passthrough_unwrap),
    ):
        return await app_mod.build(goal="g", repo_path=repo, config=config)


@pytest.mark.asyncio
async def test_convergence_breaks_and_records_debt(tmp_path, monkeypatch):
    """Same failing criterion across cycles → converge, debt, one fix execute."""
    recorder: list = []
    # cycle 0 fail C1, cycle 1 fail C1 (identical) → convergence at cycle 1.
    verifications = [_verification(False, ["C1"]), _verification(False, ["C1"])]
    result = await _run_build(
        tmp_path, verifications, recorder,
        config={"max_verify_fix_cycles": 2}, monkeypatch=monkeypatch,
    )

    assert result["success"] is False
    debt = result["dag_state"]["accumulated_debt"]
    assert any(d["type"] == "unmet_acceptance_criterion" and d["criterion"] == "C1" for d in debt)

    fix_executes = [
        kw for t, kw in recorder if t.endswith(".execute") and "checkpoint_label" in kw
    ]
    assert len(fix_executes) == 1                       # converged before a 2nd fix
    assert fix_executes[0]["checkpoint_label"] == "fix-1"

    snap = Path(tmp_path) / "repo" / ".artifacts" / "execution" / "main-dag-result.json"
    assert snap.exists()
    assert len(json.loads(snap.read_text())["all_issues"]) == 3


@pytest.mark.asyncio
async def test_history_passed_to_fix_generator(tmp_path, monkeypatch):
    """Cycle 2's generate_fix_issues receives prior cycle's failed criteria."""
    recorder: list = []
    # Distinct criteria each cycle so the loop does NOT converge; runs to cap.
    verifications = [
        _verification(False, ["C1"]),
        _verification(False, ["C2"]),
        _verification(False, ["C3"]),
    ]
    await _run_build(
        tmp_path, verifications, recorder,
        config={"max_verify_fix_cycles": 2}, monkeypatch=monkeypatch,
    )

    gen_calls = [kw for t, kw in recorder if ".generate_fix_issues" in t]
    assert len(gen_calls) == 2
    assert gen_calls[0]["previously_failed_criteria"] == []          # cycle 0: no history
    prior = [c["criterion"] for c in gen_calls[1]["previously_failed_criteria"]]
    assert "C1" in prior                                              # cycle 1: C1 carried

    fix_labels = [
        kw["checkpoint_label"] for t, kw in recorder
        if t.endswith(".execute") and "checkpoint_label" in kw
    ]
    assert fix_labels == ["fix-1", "fix-2"]


@pytest.mark.asyncio
async def test_soft_deadline_short_circuits_second_cycle(tmp_path, monkeypatch):
    """Elapsed ≥ budget before the 2nd launch → stop, debt; first fix still ran."""
    recorder: list = []
    verifications = [
        _verification(False, ["C1"]),
        _verification(False, ["C2"]),
        _verification(False, ["C3"]),
    ]
    # Drive elapsed time from loop progress (patching the shared time module
    # affects every monotonic() caller, so make the value depend on state, not a
    # fixed call count): 0 until the first fix DAG has launched, then over-budget.
    def fake_monotonic():
        launched = sum(
            1 for t, k in recorder
            if t.endswith(".execute") and "checkpoint_label" in k
        )
        return 0.0 if launched == 0 else 5000.0

    monkeypatch.setattr(app_mod.time, "monotonic", fake_monotonic)

    result = await _run_build(
        tmp_path, verifications, recorder,
        config={"max_verify_fix_cycles": 5, "verify_fix_soft_deadline_seconds": 3600},
        monkeypatch=monkeypatch,
    )

    assert result["success"] is False
    fix_executes = [
        kw for t, kw in recorder if t.endswith(".execute") and "checkpoint_label" in kw
    ]
    assert len(fix_executes) == 1                       # second launch gated by deadline
    assert fix_executes[0]["checkpoint_label"] == "fix-1"
    debt = result["dag_state"]["accumulated_debt"]
    assert any(d["type"] == "unmet_acceptance_criterion" for d in debt)
