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
    CriterionResult,
    RetryAdvice,
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
