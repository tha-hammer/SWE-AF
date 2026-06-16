import json, os
from pathlib import Path

from swe_af.app import (
    _criteria_to_debt,
    _dump_main_dag_result,
    _failed_criteria_signature,
    _within_soft_deadline,
)
from swe_af.execution.schemas import BuildConfig


# --- Behavior 2: main-DAG snapshot -----------------------------------------

def test_dump_main_dag_result_writes_snapshot(tmp_path):
    artifacts = str(tmp_path / ".artifacts")
    dag_result = {"all_issues": [{"name": f"i{i}"} for i in range(9)],
                  "completed_issues": []}
    _dump_main_dag_result(artifacts, dag_result)
    snap = Path(artifacts) / "execution" / "main-dag-result.json"
    assert snap.exists()
    assert len(json.loads(snap.read_text())["all_issues"]) == 9


def test_dump_main_dag_result_noop_without_artifacts(tmp_path):
    _dump_main_dag_result("", {"all_issues": []})  # must not raise


# --- Behavior 4: convergence signature -------------------------------------

def test_signature_is_order_independent():
    a = [{"criterion": "X"}, {"criterion": "Y"}]
    b = [{"criterion": "Y"}, {"criterion": "X"}]
    assert _failed_criteria_signature(a) == _failed_criteria_signature(b)


def test_signature_differs_on_content():
    a = [{"criterion": "X"}]
    b = [{"criterion": "Z"}]
    assert _failed_criteria_signature(a) != _failed_criteria_signature(b)


def test_signature_empty():
    assert _failed_criteria_signature([]) == frozenset()


# --- Behavior 5: accept-partial debt ---------------------------------------

def test_criteria_to_debt_shape():
    out = _criteria_to_debt([{"criterion": "X", "evidence": "e"}])
    assert out == [{"type": "unmet_acceptance_criterion", "criterion": "X",
                    "reason": "e", "severity": "high"}]


def test_criteria_to_debt_empty():
    assert _criteria_to_debt([]) == []


# --- Behavior 6: soft time budget ------------------------------------------

def test_config_defaults():
    cfg = BuildConfig(repo_url="https://x/y")
    assert cfg.max_verify_fix_cycles == 2                 # raised from 1
    assert cfg.verify_fix_soft_deadline_seconds == 3600   # budget on by default


def test_soft_deadline_zero_disables():
    assert _within_soft_deadline(10_000, 0) is True       # 0 still disables


def test_soft_deadline_blocks_when_exceeded():
    assert _within_soft_deadline(100, 60) is False
    assert _within_soft_deadline(30, 60) is True
