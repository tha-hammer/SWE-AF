"""Behaviors 5 & 6: Sprint Planner + Issue Writer consume DDD planning artifacts."""

from __future__ import annotations

import inspect

from swe_af.prompts.issue_writer import issue_writer_task_prompt
from swe_af.prompts.sprint_planner import sprint_planner_task_prompt


# --- Behavior 5: Sprint Planner -------------------------------------------------


def test_sprint_planner_prompt_accepts_planning_artifacts():
    sig = inspect.signature(sprint_planner_task_prompt)
    assert "planning_artifacts" in sig.parameters


def test_sprint_planner_prompt_requires_vertical_slice_and_context_fields(
    complete_planning_artifacts,
):
    prompt = sprint_planner_task_prompt(
        goal="g", prd={}, architecture={}, planning_artifacts=complete_planning_artifacts
    )
    assert "bounded_context" in prompt
    assert "contract_refs" in prompt
    assert "slice_role" in prompt
    assert "vertical slice" in prompt.lower()


def test_sprint_planner_prompt_lists_bounded_context_names(complete_planning_artifacts):
    prompt = sprint_planner_task_prompt(
        goal="g", prd={}, architecture={}, planning_artifacts=complete_planning_artifacts
    )
    assert "Plan Intake" in prompt  # summarized, not dumped as raw JSON


def test_sprint_planner_prompt_omits_block_when_no_artifacts():
    prompt = sprint_planner_task_prompt(goal="g", prd={}, architecture={})
    assert "DDD Planning Artifacts" not in prompt


# --- Behavior 6: Issue Writer ---------------------------------------------------


def test_issue_writer_prompt_accepts_no_new_required_param():
    # issue metadata travels on the issue itself; signature stays backward compatible
    sig = inspect.signature(issue_writer_task_prompt)
    assert "issue" in sig.parameters


def test_issue_writer_prompt_renders_planning_context(enriched_issue):
    prompt = issue_writer_task_prompt(
        issue=enriched_issue.model_dump(),
        prd_summary="",
        architecture_summary="",
        issues_dir="/tmp",
    )
    assert "Bounded Context" in prompt
    assert "Domain Events" in prompt
    assert "Read Models" in prompt
    assert "Observability" in prompt


def test_issue_writer_prompt_omits_ddd_sections_without_metadata():
    plain_issue = {
        "name": "n", "title": "t", "description": "d", "acceptance_criteria": [],
    }
    prompt = issue_writer_task_prompt(
        issue=plain_issue, prd_summary="", architecture_summary="", issues_dir="/tmp"
    )
    assert "Bounded Context" not in prompt
