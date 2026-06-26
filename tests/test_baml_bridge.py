"""SB-2: pydantic_to_typebuilder maps a real SWE-AF schema (deterministic).

b.parse.* makes NO LLM call. Oracles are hand-authored pydantic instances,
NOT derived from the mapper's own output.
"""

import json
from enum import Enum
from typing import Optional

import pytest
from pydantic import BaseModel

from baml_client.sync_client import b
from baml_client.type_builder import TypeBuilder
from swe_af.baml_bridge import baml_parse, deserialize, pydantic_to_typebuilder
from swe_af.execution.schemas import (
    AgentRetro,
    CodeReviewResult,
    CoderResult,
    CriterionResult,
    DebtItem,
    MergeResult,
    QAResult,
    RetryAdvice,
    TestFailure as QATestFailure,
    VerificationResult,
)

pytestmark = pytest.mark.unit


def _roundtrip(model, instance_json):
    """parse(json.dumps(J)) via the mapped TypeBuilder, then cast back to model."""
    raw = b.parse.ExtractDynamic(
        json.dumps(instance_json),
        baml_options={"tb": pydantic_to_typebuilder(model)},
    )
    return deserialize(raw, model)


def test_retry_advice_roundtrip():
    J = {
        "should_retry": True,
        "diagnosis": "x",
        "strategy": "y",
        "modified_context": "z",
        "confidence": 0.8,
    }
    assert _roundtrip(RetryAdvice, J) == RetryAdvice(**J)  # hand-authored oracle


def test_nested_model_list_roundtrip():
    """VerificationResult holds list[CriterionResult] + list[str] + str/bool."""
    J = {
        "passed": False,
        "criteria_results": [
            {"criterion": "c1", "passed": True, "evidence": "e1", "issue_name": "i1"},
            {"criterion": "c2", "passed": False, "evidence": "e2"},
        ],
        "summary": "done",
        "suggested_fixes": ["fix a", "fix b"],
    }
    expected = VerificationResult(
        passed=False,
        criteria_results=[
            CriterionResult(criterion="c1", passed=True, evidence="e1", issue_name="i1"),
            CriterionResult(criterion="c2", passed=False, evidence="e2"),
        ],
        summary="done",
        suggested_fixes=["fix a", "fix b"],
    )
    assert _roundtrip(VerificationResult, J) == expected


def test_optional_and_enum_fields():
    class Color(Enum):
        RED = "red"
        BLUE = "blue"

    class Widget(BaseModel):
        name: str
        color: Color
        note: Optional[str] = None
        tags: list[str] = []

    J = {"name": "w", "color": "blue", "note": None, "tags": ["a"]}
    assert _roundtrip(Widget, J) == Widget(name="w", color=Color.BLUE, note=None, tags=["a"])


def test_missing_required_field_raises_value_error():
    # missing diagnosis/strategy/modified_context (confidence has a default → optional)
    incomplete = {"should_retry": True}
    with pytest.raises(ValueError, match="Could not parse structured response"):
        baml_parse(json.dumps(incomplete), RetryAdvice)


def test_unsupported_type_raises_type_error():
    from typing import Any

    class Bad(BaseModel):
        x: Any

    with pytest.raises(TypeError):
        pydantic_to_typebuilder(Bad)


def test_pydantic_to_typebuilder_returns_typebuilder():
    assert isinstance(pydantic_to_typebuilder(RetryAdvice), TypeBuilder)


# ---------------------------------------------------------------------------
# Behavior 0a: bare dict / Any hardening — omit-if-defaulted
# ---------------------------------------------------------------------------
#
# These schemas carry a single unmappable field that has a default:
#   MergeResult.conflict_resolutions: list[dict] = []
#   CoderResult.agent_retro: dict = {}
#   QAResult.test_failures: list[dict] = []
# Before B0a, pydantic_to_typebuilder raised TypeError on them (declined to None
# via baml_parse_or_none — silently never benefitting from BAML). After B0a it
# skips the unmappable *defaulted* field and maps the rest.


@pytest.mark.parametrize("model", [MergeResult, CoderResult, QAResult])
def test_dict_bearing_schema_maps_without_raising(model):
    assert isinstance(pydantic_to_typebuilder(model), TypeBuilder)


def test_merge_result_roundtrips_with_dict_field_at_default():
    inst = MergeResult(
        success=True,
        merged_branches=["feat/a"],
        failed_branches=[],
        needs_integration_test=False,
        summary="ok",
    )
    # conflict_resolutions defaults to [] and is omitted from the BAML type;
    # _strip_none + the Pydantic default restore it on model_validate.
    assert _roundtrip(MergeResult, inst.model_dump()) == inst


def test_coder_result_roundtrips_with_dict_field_at_default():
    inst = CoderResult(files_changed=["x.py"], summary="did", iteration_id="i1")
    assert _roundtrip(CoderResult, inst.model_dump()) == inst  # agent_retro back at {}


def test_qa_result_roundtrips_with_dict_field_at_default():
    inst = QAResult(passed=True, summary="green", iteration_id="i1")
    assert _roundtrip(QAResult, inst.model_dump()) == inst  # test_failures back at []


def test_coder_result_roundtrips_with_agent_retro_content():
    inst = CoderResult(
        files_changed=["x.py"],
        summary="did",
        agent_retro=AgentRetro(
            worked_well=["small tests"],
            got_stuck_on=["schema"],
            tips_for_next_time=["check output schema first"],
        ),
    )

    assert _roundtrip(CoderResult, inst.model_dump()) == inst


def test_qa_and_review_nested_items_roundtrip_non_default_content():
    qa = QAResult(
        passed=False,
        test_failures=[
            QATestFailure(
                test_name="test_x",
                file="tests/test_x.py",
                error="boom",
                expected="green",
                actual="red",
            )
        ],
    )
    review = CodeReviewResult(
        approved=False,
        debt_items=[
            DebtItem(
                severity="should_fix",
                title="Missing edge case",
                file_path="x.py",
                description="Cover empty input",
            )
        ],
    )

    assert _roundtrip(QAResult, qa.model_dump()) == qa
    assert _roundtrip(CodeReviewResult, review.model_dump()) == review


def test_required_bare_dict_field_still_raises():
    """We only omit *defaulted* unmappable fields — a required one must still raise,
    so required data is never silently dropped."""

    class RequiredDict(BaseModel):
        payload: dict  # required, bare dict → unmappable, no default

    with pytest.raises(TypeError):
        pydantic_to_typebuilder(RequiredDict)
