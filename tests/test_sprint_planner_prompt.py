"""Behavior 7: the sprint planner prompt instructs emitting the typed `verification`.

Additive only (clone-prompts-verbatim): a new instruction telling the planner to
populate ``verification: [{description, command, kind}]`` per issue, reusing the
"every criterion MUST map to a command" discipline. No existing prompt line changes.
"""

import pytest

from swe_af.prompts import sprint_planner as sp
from swe_af.reasoners.schemas import Architecture, PRD

pytestmark = pytest.mark.unit


def test_system_prompt_describes_verification_field():
    assert "**verification**" in sp.SYSTEM_PROMPT
    assert "runnable acceptance checks" in sp.SYSTEM_PROMPT
    assert "MUST map to a command" in sp.SYSTEM_PROMPT


def test_rendered_task_prompt_instructs_verification():
    prd = PRD(
        validated_description="Build a lexer",
        acceptance_criteria=["tokens emitted"],
        must_have=[],
        nice_to_have=[],
        out_of_scope=[],
    )
    architecture = Architecture(
        summary="one component",
        components=[],
        interfaces=[],
        decisions=[],
        file_changes_overview="x",
    )
    system, task = sp.sprint_planner_prompts(
        prd=prd,
        architecture=architecture,
        repo_path="/repo",
        prd_path="/prd",
        architecture_path="/arch",
    )
    assert "`verification`" in task
    assert "MUST map to a command" in task
    # The instruction ties the field to the deterministic check rung.
    assert "deterministic check rung" in task
