"""The observed-behavior eval net for the planning prompts (SWE-AF-ixn, Phase 0c).

RED-net convention
------------------
The prompt-source checks below use ``xfail(strict=True)`` to mark the *known
offenders* the plan commits to fixing. Today those params fail (expected-fail,
suite stays green); once a later phase brings a prompt under budget / strips the
leaked domain example, the strict marker turns the unexpected pass into a
failure — forcing the marker's removal. That is the intended RED -> GREEN signal,
not a test being weakened. The phase/issue that flips each one green is named in
the ``reason``.

The golden-output checks are the positive guarantees and must stay green. They
``skip`` until Phase 0b captures the fixtures under
``tests/fixtures/prompt_evals/baseline/`` (data-dependent skip, not a weakened
assertion).
"""

from __future__ import annotations

import pytest

from prompt_evals import eval_checks as ec

pytestmark = pytest.mark.unit

_GOLDENS = ["goal_a_version_flag.json", "goal_b_build_metrics.json"]


# --------------------------------------------------------------------------- #
# prompt-source RED net
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "stem",
    [
        "product_manager",
        "architect",
        "tech_lead",
        "architecture_planning_loop",  # Phase 3: tutorial distilled to a heuristic checklist
        "sprint_planner",  # Phase 3: SYSTEM<->task duplication removed (244->212, ceiling 215)
        "issue_writer",
    ],
)
def test_system_prompt_within_line_budget(stem: str) -> None:
    lines = ec.system_prompt_line_count(stem)
    budget = ec.line_budget(stem)
    assert lines <= budget, f"{stem} SYSTEM_PROMPT is {lines} lines (> {budget})"


@pytest.mark.parametrize(
    "stem",
    [
        "product_manager",
        "architect",
        "tech_lead",
        "architecture_planning_loop",  # Phase 3: leaked 'Exploded View' domain example removed
        "sprint_planner",
        "issue_writer",
    ],
)
def test_system_prompt_free_of_domain_leakage(stem: str) -> None:
    leaks = ec.domain_leaks(stem)
    assert not leaks, f"{stem} SYSTEM_PROMPT leaks target-domain tokens: {leaks}"


# --------------------------------------------------------------------------- #
# golden-output positive net
# --------------------------------------------------------------------------- #
def _load_or_skip(fixture: str) -> dict:
    plan_result = ec.load_golden(fixture)
    if plan_result is None:
        pytest.skip(f"golden fixture not captured yet (Phase 0b): {fixture}")
    return plan_result


@pytest.mark.parametrize("fixture", _GOLDENS)
def test_golden_validates_against_plan_result_schema(fixture: str) -> None:
    from swe_af.reasoners.schemas import PlanResult

    plan_result = _load_or_skip(fixture)
    PlanResult.model_validate(plan_result)  # raises on schema violation


@pytest.mark.parametrize("fixture", _GOLDENS)
def test_golden_every_issue_has_runnable_check(fixture: str) -> None:
    plan_result = _load_or_skip(fixture)
    missing = ec.issues_missing_runnable_check(plan_result)
    assert not missing, f"issues with criteria but no runnable verification command: {missing}"


def test_golden_ddd_sprint_has_exactly_one_vertical_slice() -> None:
    plan_result = _load_or_skip("goal_b_build_metrics.json")
    if not ec.planning_artifacts_present(plan_result):
        pytest.skip("goal_b golden has no planning_artifacts; DDD loop did not drive the sprint")
    assert ec.vertical_slice_count(plan_result) == 1
