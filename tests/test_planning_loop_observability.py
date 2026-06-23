"""Behavior 8: planning events and observability are emitted."""

from __future__ import annotations

import json

from swe_af.reasoners.pipeline import publish_planning_event
from swe_af.reasoners.schemas import PlanningEvent


def test_planning_loop_records_events(tmp_path):
    ev = PlanningEvent(
        event_name="PlanningArtifactsValidated",
        event_version="v1",
        source_context="DDD Planning",
        correlation_id="plan-123",
        payload={"errors": 0},
    )
    publish_planning_event(
        artifacts_dir=str(tmp_path / ".artifacts"),
        event=ev,
        now="2026-06-23T00:00:00Z",
    )
    log = tmp_path / ".artifacts" / "plan" / "planning-events.jsonl"
    content = log.read_text()
    assert "PlanningArtifactsValidated" in content
    # injected clock is recorded deterministically
    record = json.loads(content.strip().splitlines()[-1])
    assert record["occurred_at"] == "2026-06-23T00:00:00Z"


def test_planning_events_are_appended(tmp_path):
    for name in ("PlanRequested", "ArchitectureApproved"):
        publish_planning_event(
            artifacts_dir=str(tmp_path / ".artifacts"),
            event=PlanningEvent(event_name=name),
            now="2026-06-23T00:00:00Z",
        )
    lines = (tmp_path / ".artifacts" / "plan" / "planning-events.jsonl").read_text().splitlines()
    assert len(lines) == 2
