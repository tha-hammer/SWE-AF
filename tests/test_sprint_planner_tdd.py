"""The sprint planner decomposes test-first (TDD aspects + worked example).

These pin the TDD framing added so the planner's acceptance_criteria become the
coder's first failing tests and its testing_strategy scripts Red→Green→Refactor.
Content tests, like tests/fast/test_prompts.py does for the fast planner.
"""

import pytest

from swe_af.prompts.sprint_planner import (
    SYSTEM_PROMPT,
    sprint_planner_task_prompt,
)
from swe_af.reasoners.schemas import PRD, Architecture

pytestmark = pytest.mark.unit


class TestSystemPromptTddAspects:
    def test_names_red_green_refactor_cycle(self):
        for marker in ("🔴", "🟢", "🔵"):
            assert marker in SYSTEM_PROMPT
        assert "Red" in SYSTEM_PROMPT and "Green" in SYSTEM_PROMPT
        assert "Refactor" in SYSTEM_PROMPT

    def test_requires_given_when_then_acceptance_criteria(self):
        assert "Given / When / Then" in SYSTEM_PROMPT
        assert "observable behavior" in SYSTEM_PROMPT.lower()

    def test_behavior_first_not_function_first(self):
        assert "Behavior-first" in SYSTEM_PROMPT
        assert "smallest" in SYSTEM_PROMPT and "observable behaviors" in SYSTEM_PROMPT

    def test_calls_for_property_tests(self):
        lowered = SYSTEM_PROMPT.lower()
        assert "property-based test" in lowered or "property test" in lowered
        assert "parse(serialize(x)) == x" in SYSTEM_PROMPT  # named invariant

    def test_orders_behaviors_simplest_first(self):
        assert "simplest-first" in SYSTEM_PROMPT
        # the simplest→hardest ladder is spelled out
        assert "edge cases" in SYSTEM_PROMPT and "error handling" in SYSTEM_PROMPT

    def test_declares_blast_radius(self):
        assert "blast radius" in SYSTEM_PROMPT
        assert "change amplification" in SYSTEM_PROMPT


class TestWorkedExample:
    def test_has_a_concrete_tdd_framed_example(self):
        assert "Example: A TDD-Framed Issue" in SYSTEM_PROMPT

    def test_example_acceptance_criteria_use_given_when_then(self):
        # The lexer example pins each AC as an observable behavior.
        assert "Given an empty string, when the lexer runs, then" in SYSTEM_PROMPT
        assert "raises a LexError" in SYSTEM_PROMPT  # error-handling behavior

    def test_example_testing_strategy_scripts_the_cycle(self):
        assert "tests/test_lexer.py" in SYSTEM_PROMPT
        assert "Red→Green→Refactor" in SYSTEM_PROMPT
        assert "Hypothesis" in SYSTEM_PROMPT  # property test in the example


class TestActiveTaskPromptReinforcesTdd:
    def _task(self) -> str:
        prd = PRD(
            validated_description="Build a thing",
            acceptance_criteria=["does the thing"],
            must_have=[],
            nice_to_have=[],
            out_of_scope=[],
        )
        arch = Architecture(
            summary="one module",
            components=[],
            interfaces=[],
            decisions=[],
            file_changes_overview="",
        )
        return sprint_planner_task_prompt(
            goal="Build a thing",
            prd=prd,
            architecture=arch,
            repo_path="/repo",
        )

    def test_mission_includes_test_first_section(self):
        task = self._task()
        assert "Decompose Test-First (TDD)" in task

    def test_mission_names_cycle_and_given_when_then(self):
        task = self._task()
        assert "Red → Green → Refactor" in task
        assert "Given / When / Then" in task
        assert "property-based test" in task.lower()
