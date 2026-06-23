"""Behavior 3: Architect-owned planning loop reasoner produces DDD artifacts."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def attached_reasoners_router():
    """Attach the planning ``router`` to a mock agent so router.note/harness work.

    Mirrors conftest's ``attach_fast_router`` — direct reasoner calls delegate
    note()/harness() to the attached agent via __getattr__. Yields the mock agent
    so tests can configure ``agent.harness``; restores the prior agent afterwards.
    """
    from swe_af.reasoners import router as reasoners_router

    prior = object.__getattribute__(reasoners_router, "_agent")
    agent = MagicMock()
    agent.note = MagicMock()
    object.__setattr__(reasoners_router, "_agent", agent)
    try:
        yield agent
    finally:
        object.__setattr__(reasoners_router, "_agent", prior)


def _prd() -> dict:
    return {
        "validated_description": "Build it",
        "acceptance_criteria": [],
        "must_have": [],
        "nice_to_have": [],
        "out_of_scope": [],
    }


def _architecture() -> dict:
    return {
        "summary": "A",
        "components": [],
        "interfaces": [],
        "decisions": [],
        "file_changes_overview": "",
    }


@pytest.mark.asyncio
async def test_architecture_planning_loop_uses_schema_and_writes_artifact(
    tmp_path, complete_planning_artifacts, attached_reasoners_router
):
    from swe_af.reasoners.pipeline import run_architecture_planning_loop

    real_fn = run_architecture_planning_loop._original_func
    response = MagicMock(is_error=False, parsed=complete_planning_artifacts)
    attached_reasoners_router.harness = AsyncMock(return_value=response)

    result = await real_fn(
        prd=_prd(),
        architecture=_architecture(),
        repo_path=str(tmp_path),
        artifacts_dir=".artifacts",
    )

    # called the harness with the typed schema
    assert attached_reasoners_router.harness.call_args.kwargs["schema"].__name__ == (
        "ArchitecturePlanningArtifacts"
    )
    # returns a model-dump dict
    assert result["event_backbone"]["default_transport"] == "in_process"
    # wrote the artifact markdown
    assert (tmp_path / ".artifacts" / "plan" / "architecture-planning.md").exists()


@pytest.mark.asyncio
async def test_architecture_planning_loop_passes_validation_feedback_into_prompt(
    tmp_path, complete_planning_artifacts, attached_reasoners_router
):
    from swe_af.reasoners.pipeline import run_architecture_planning_loop

    real_fn = run_architecture_planning_loop._original_func
    response = MagicMock(is_error=False, parsed=complete_planning_artifacts)
    attached_reasoners_router.harness = AsyncMock(return_value=response)

    await real_fn(
        prd=_prd(),
        architecture=_architecture(),
        repo_path=str(tmp_path),
        validation_feedback=["bounded context 'X' has no domain event"],
    )

    prompt = attached_reasoners_router.harness.call_args.kwargs["prompt"]
    assert "no domain event" in prompt
