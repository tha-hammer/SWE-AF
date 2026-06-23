"""Behavior 1: DDD planning-artifact schemas are typed and backward compatible."""

from __future__ import annotations


def test_plan_result_defaults_without_planning_artifacts():
    from swe_af.reasoners.schemas import PlanResult

    result = PlanResult(
        prd={
            "validated_description": "T",
            "acceptance_criteria": [],
            "must_have": [],
            "nice_to_have": [],
            "out_of_scope": [],
        },
        architecture={
            "summary": "A",
            "components": [],
            "interfaces": [],
            "decisions": [],
            "file_changes_overview": "",
        },
        review={"approved": True, "feedback": "", "summary": "ok"},
        issues=[],
        levels=[],
        artifacts_dir="/tmp",
        rationale="r",
    )
    assert result.planning_artifacts is None


def test_complete_planning_artifacts_round_trip(complete_planning_artifacts):
    # W3: lock the EXACT field names validate_planning_artifacts depends on, so the
    # schema and validator cannot drift apart. The schema is the source of truth.
    dumped = complete_planning_artifacts.model_dump()
    assert dumped["current_diagram"]["mermaid"].startswith("flowchart")
    assert dumped["future_diagram"]["mermaid"].startswith("flowchart")
    bc = dumped["bounded_contexts"][0]
    assert bc["aggregates"][0]["name"] == "PlanRequest"
    assert bc["domain_services"] and bc["domain_events"]
    assert dumped["event_backbone"]["default_transport"] == "in_process"
    assert dumped["internal_event_schema"]["event_version"]
    assert dumped["read_models"][0]["source_events"]
    assert dumped["data_ownership"]
    assert dumped["guardrails"][0]["enforcement"]
    assert dumped["observability"]
    vs = dumped["vertical_slice"]
    assert vs["bounded_context"] and vs["domain_events"]
    assert dumped["extraction_strategy"]["gated_on"] == "tested_slice"


def test_planning_event_schema_round_trip():
    # W5: SWE-AF's OWN planner observability event (distinct from the target
    # project's internal_event_schema above — see W4 note in Behavior 8).
    from swe_af.reasoners.schemas import PlanningEvent

    ev = PlanningEvent(
        event_name="PlanningArtifactsValidated",
        event_version="v1",
        occurred_at="2026-06-23T00:00:00Z",
        source_context="DDD Planning",
        correlation_id="plan-123",
        payload={"errors": 0},
    )
    assert ev.model_dump()["event_name"] == "PlanningArtifactsValidated"


def test_planned_issue_carries_ddd_metadata():
    from swe_af.reasoners.schemas import PlannedIssue

    issue = PlannedIssue(
        name="n",
        title="t",
        description="d",
        acceptance_criteria=[],
        bounded_context="Plan Intake",
        contract_refs=["PlanRequest.submit"],
        domain_events=["PlanRequested"],
        read_models=["PlanStatusView"],
        guardrails=["no-cross-context-import"],
        observability=["emit PlanRequested"],
        slice_role="vertical-slice",
    )
    dumped = issue.model_dump()
    assert dumped["bounded_context"] == "Plan Intake"
    assert dumped["slice_role"] == "vertical-slice"
    # backward-compat: the BAML-added verification field still defaults cleanly
    assert dumped["verification"] == []
