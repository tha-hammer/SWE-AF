"""Behavior 7: planning context survives the plan-to-execution handoff."""

from __future__ import annotations

from swe_af.execution.dag_executor import _init_dag_state


def _plan_result_with_artifacts(complete_planning_artifacts_dict) -> dict:
    return {
        "prd": {"validated_description": "g"},
        "architecture": {"summary": "a"},
        "issues": [],
        "levels": [],
        "rationale": "r",
        "artifacts_dir": "/tmp/.artifacts",
        "planning_artifacts": complete_planning_artifacts_dict,
    }


def test_init_dag_state_preserves_planning_artifacts(tmp_path, complete_planning_artifacts_dict):
    plan_result = _plan_result_with_artifacts(complete_planning_artifacts_dict)
    state = _init_dag_state(plan_result, repo_path=str(tmp_path))
    assert state.planning_artifacts is not None
    assert state.planning_artifacts["event_backbone"]["default_transport"] == "in_process"


def test_init_dag_state_without_planning_artifacts_defaults_none(tmp_path):
    plan_result = {
        "prd": {"validated_description": "g"},
        "architecture": {"summary": "a"},
        "issues": [],
        "levels": [],
        "rationale": "r",
        "artifacts_dir": "/tmp/.artifacts",
    }
    state = _init_dag_state(plan_result, repo_path=str(tmp_path))
    assert state.planning_artifacts is None


def test_replanner_prompt_includes_planning_summary(complete_planning_artifacts_dict):
    from swe_af.execution.schemas import DAGState
    from swe_af.prompts.replanner import replanner_task_prompt

    state = DAGState(repo_path="/tmp", planning_artifacts=complete_planning_artifacts_dict)
    prompt = replanner_task_prompt(state, failed_issues=[])
    assert "Plan Intake" in prompt  # bounded context names summarized for recovery
