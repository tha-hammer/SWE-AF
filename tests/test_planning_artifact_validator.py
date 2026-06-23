"""Behavior 2: deterministic planning-artifact validator enforces the loop guardrails."""

from __future__ import annotations

from swe_af.reasoners.pipeline import validate_planning_artifacts


def test_validator_accepts_complete_artifacts(complete_planning_artifacts):
    assert validate_planning_artifacts(complete_planning_artifacts) == []


def test_validator_rejects_context_without_domain_events(complete_planning_artifacts):
    complete_planning_artifacts.bounded_contexts[0].domain_events = []
    errors = validate_planning_artifacts(complete_planning_artifacts)
    assert any("domain event" in error.lower() for error in errors)


def test_validator_rejects_missing_current_diagram(complete_planning_artifacts):
    complete_planning_artifacts.current_diagram.mermaid = ""
    errors = validate_planning_artifacts(complete_planning_artifacts)
    assert any("current diagram" in e.lower() for e in errors)


def test_validator_requires_migration_justification_for_non_in_process(complete_planning_artifacts):
    complete_planning_artifacts.event_backbone.default_transport = "kafka"
    complete_planning_artifacts.event_backbone.migration_justification = ""
    errors = validate_planning_artifacts(complete_planning_artifacts)
    assert any("migration_justification" in e for e in errors)


def test_validator_accepts_non_in_process_with_justification(complete_planning_artifacts):
    complete_planning_artifacts.event_backbone.default_transport = "kafka"
    complete_planning_artifacts.event_backbone.migration_justification = "high throughput needed"
    assert validate_planning_artifacts(complete_planning_artifacts) == []


def test_validator_rejects_read_model_without_source_events(complete_planning_artifacts):
    complete_planning_artifacts.read_models[0].source_events = []
    errors = validate_planning_artifacts(complete_planning_artifacts)
    assert any("read model" in e.lower() for e in errors)


def test_validator_rejects_guardrail_without_enforcement(complete_planning_artifacts):
    complete_planning_artifacts.guardrails[0].enforcement = ""
    errors = validate_planning_artifacts(complete_planning_artifacts)
    assert any("enforcement" in e.lower() for e in errors)


def test_validator_rejects_vertical_slice_without_events(complete_planning_artifacts):
    complete_planning_artifacts.vertical_slice.domain_events = []
    errors = validate_planning_artifacts(complete_planning_artifacts)
    assert any("vertical slice" in e.lower() for e in errors)


def test_validator_accepts_dict_input(complete_planning_artifacts):
    # M3: plan() passes a dict (app.call returns model_dump()), so the production
    # path is dict-shaped. Validate it directly, not just the model.
    assert validate_planning_artifacts(complete_planning_artifacts.model_dump()) == []
