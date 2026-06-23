"""Behavior 1: typed ``AcceptanceCheck`` + always-on ``command`` validator.

The Pydantic ``@field_validator`` is the *always-on* validity guarantee: it runs
on every parse — both the agentfield SDK path and the BAML fallback path (through
``model_validate`` inside ``deserialize``) — because the bridge is fallback-first
(Behavior 0 verdict). ``b.parse.*`` makes no LLM call; oracles are hand-authored.
"""

import json

import pytest
from pydantic import ValidationError

from baml_client.sync_client import b
from swe_af.baml_bridge import baml_parse, deserialize, pydantic_to_typebuilder
from swe_af.reasoners.schemas import AcceptanceCheck

pytestmark = pytest.mark.unit


def _roundtrip(model, instance_json):
    """parse(json.dumps(J)) via the mapped TypeBuilder, then cast back to model."""
    raw = b.parse.ExtractDynamic(
        json.dumps(instance_json),
        baml_options={"tb": pydantic_to_typebuilder(model)},
    )
    return deserialize(raw, model)


def test_piped_command_roundtrips():
    J = {
        "description": "perf budget under 1ms",
        "command": "hyperfine x --export-json out.json | jq '.results[0].mean < 0.001'",
        "kind": "check",
    }
    assert _roundtrip(AcceptanceCheck, J) == AcceptanceCheck(**J)  # hand-authored oracle


def test_default_kind_is_check():
    assert AcceptanceCheck(description="d", command="pytest").kind == "check"


def test_empty_command_raises_validation_error():
    with pytest.raises(ValidationError):
        AcceptanceCheck(description="d", command="")


def test_whitespace_only_command_raises_validation_error():
    with pytest.raises(ValidationError):
        AcceptanceCheck(description="d", command="   ")


def test_piped_command_accepted_metachars_not_rejected():
    # Commands are pipelines by design — the validator guarantees presence/shape,
    # NOT safety, so it must not reject pipes/quotes/redirects/&&.
    c = AcceptanceCheck(description="d", command="pytest -k lexer | tee /tmp/out && echo ok")
    assert "| tee" in c.command and "&& echo" in c.command


def test_overlong_command_raises_validation_error():
    with pytest.raises(ValidationError):
        AcceptanceCheck(description="d", command="x " * 1500)  # 3000 chars > 2000 bound


def test_baml_parse_enforces_validator_on_fallback_path():
    # The validator runs through model_validate inside deserialize, so an empty
    # command is rejected on the BAML path too (surfaced as ValueError by the seam).
    with pytest.raises(ValueError, match="Could not parse structured response"):
        baml_parse(json.dumps({"description": "d", "command": "   "}), AcceptanceCheck)
