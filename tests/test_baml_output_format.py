"""Behavior 6b: BAML ``output_format`` as the prompt's output-shape section.

``baml_output_format`` renders the same type far more compactly than raw JSON
Schema, via ``b.request`` (builds the request without sending — no LLM call). The
``codex_harness_patch`` seam uses it for claude/opencode when the flag is on and the
schema is mappable, else falls back to the SDK's JSON-Schema injection. codex's
native ``--output-schema`` path is untouched.
"""

import json

import pytest
from pydantic import BaseModel

from swe_af.baml_bridge import baml_output_format
from swe_af.execution.schemas import RetryAdvice, VerificationResult
from swe_af.reasoners.schemas import AcceptanceCheck

pytestmark = pytest.mark.unit


class _RequiredDict(BaseModel):
    payload: dict  # required + bare dict -> unmappable (pydantic_to_typebuilder raises)


@pytest.mark.parametrize(
    "model,fields",
    [
        (AcceptanceCheck, ["description", "command", "kind"]),
        (RetryAdvice, ["should_retry", "diagnosis", "strategy", "modified_context", "confidence"]),
        (VerificationResult, ["passed", "criteria_results", "summary", "suggested_fixes"]),
    ],
)
def test_render_is_smaller_and_contains_all_field_names(model, fields):
    render = baml_output_format(model)
    for field in fields:
        assert field in render, f"{field} missing from render"
    assert len(render) < len(json.dumps(model.model_json_schema()))


def test_nested_render_is_inline_not_ref():
    render = baml_output_format(VerificationResult)
    assert "criterion" in render  # nested CriterionResult fields rendered inline
    assert "$ref" not in render and "$defs" not in render


def test_unmappable_required_dict_raises():
    with pytest.raises(TypeError):
        baml_output_format(_RequiredDict)


def test_render_makes_no_llm_call(monkeypatch):
    import swe_af.baml_bridge as bridge

    def _fail(*a, **k):
        raise AssertionError("baml_output_format made an LLM call (b.ExtractDynamic)")

    # b.request.ExtractDynamic builds only; the LLM-calling b.ExtractDynamic must
    # never fire. raising=False keeps the test valid if the attr name shifts.
    monkeypatch.setattr(bridge.b, "ExtractDynamic", _fail, raising=False)
    assert "command" in baml_output_format(AcceptanceCheck)


# ---------------------------------------------------------------------------
# Seam: codex_harness_patch.build_prompt_suffix dispatching
# ---------------------------------------------------------------------------


def _patched():
    from swe_af.runtime import codex_harness_patch

    codex_harness_patch.apply_codex_harness_patch()
    import agentfield.harness._schema as _schema

    return codex_harness_patch, _schema


def test_seam_flag_off_is_byte_identical_json_schema(tmp_path):
    chp, _schema = _patched()
    suffix = _schema.build_prompt_suffix(AcceptanceCheck, str(tmp_path))
    original = chp._ORIGINAL_BUILD_PROMPT_SUFFIX(AcceptanceCheck, str(tmp_path))
    assert suffix == original


def test_seam_flag_on_uses_compact_baml_render(tmp_path):
    chp, _schema = _patched()
    token = chp.baml_output_format_enabled.set(True)
    try:
        suffix = _schema.build_prompt_suffix(AcceptanceCheck, str(tmp_path))
    finally:
        chp.baml_output_format_enabled.reset(token)
    original = chp._ORIGINAL_BUILD_PROMPT_SUFFIX(AcceptanceCheck, str(tmp_path))
    assert suffix != original
    assert "Answer in JSON using this schema" in suffix  # the output_format render
    assert len(suffix) < len(original)


def test_seam_flag_on_unmappable_falls_back_no_raise(tmp_path):
    chp, _schema = _patched()
    token = chp.baml_output_format_enabled.set(True)
    try:
        suffix = _schema.build_prompt_suffix(_RequiredDict, str(tmp_path))  # must not raise
    finally:
        chp.baml_output_format_enabled.reset(token)
    original = chp._ORIGINAL_BUILD_PROMPT_SUFFIX(_RequiredDict, str(tmp_path))
    assert suffix == original  # fell back to JSON Schema injection


def test_seam_codex_path_untouched(tmp_path):
    chp, _schema = _patched()
    prov = chp.active_provider.set("codex")
    fmt = chp.baml_output_format_enabled.set(True)  # even with the flag on
    try:
        suffix = _schema.build_prompt_suffix(AcceptanceCheck, str(tmp_path))
    finally:
        chp.active_provider.reset(prov)
        chp.baml_output_format_enabled.reset(fmt)
    assert "CODEX STRUCTURED OUTPUT" in suffix
