"""Behavior 2: ``PlannedIssue.verification`` flows planner -> issue dict -> coder.

A new ``verification: list[AcceptanceCheck] = []`` field survives ``model_dump()``
(as ``dag_executor`` serializes a ``PlannedIssue``) into the issue dict, readable
via ``issue.get("verification", [])``, and round-trips through ``baml_parse``. A
messy-text case proves BAML recovers the ``verification`` block where the SDK
regex ladder drops it (the SB-3 dual-oracle). ``b.parse.*`` makes no LLM call.
"""

import json

import pytest
import agentfield.harness._schema as _schema

from baml_client.sync_client import b
from swe_af.baml_bridge import baml_parse, deserialize, pydantic_to_typebuilder
from swe_af.reasoners.schemas import AcceptanceCheck, PlannedIssue

pytestmark = pytest.mark.unit


def _roundtrip(model, instance_json):
    raw = b.parse.ExtractDynamic(
        json.dumps(instance_json),
        baml_options={"tb": pydantic_to_typebuilder(model)},
    )
    return deserialize(raw, model)


def sdk_try_parse(text, schema):
    """The raw SDK ladder, immune to the BAML seam's monkeypatch (see test_baml_parse)."""
    from swe_af.runtime import codex_harness_patch

    original = codex_harness_patch._ORIGINAL_TRY_PARSE_FROM_TEXT
    return (original or _schema.try_parse_from_text)(text, schema)


def _issue_with_verification() -> PlannedIssue:
    return PlannedIssue(
        name="lexer",
        title="Build lexer",
        description="Tokenize source",
        acceptance_criteria=["tokens emitted"],
        verification=[
            AcceptanceCheck(description="run lexer tests", command="pytest -k lexer", kind="test"),
        ],
    )


def test_verification_defaults_empty():
    issue = PlannedIssue(name="x", title="X", description="d", acceptance_criteria=["a"])
    assert issue.model_dump().get("verification", []) == []


def test_verification_survives_model_dump():
    # dag_executor.py serializes a PlannedIssue via model_dump(); nested checks
    # become nested dicts read as issue.get("verification", []) -> list[dict].
    dumped = _issue_with_verification().model_dump()
    assert dumped["verification"][0]["command"] == "pytest -k lexer"
    assert dumped["verification"][0]["kind"] == "test"


def test_planned_issue_roundtrips_with_verification():
    inst = _issue_with_verification()
    got = _roundtrip(PlannedIssue, inst.model_dump())
    assert got.verification == inst.verification
    assert got.verification[0].command == "pytest -k lexer"


def test_baml_recovers_verification_from_messy_text():
    # Single-quoted inline dict: the SDK ladder returns None; baml_parse recovers it.
    text = (
        "{'name': 'lexer', 'title': 'Build lexer', 'description': 'Tokenize source', "
        "'acceptance_criteria': ['tokens emitted'], "
        "'verification': [{'description': 'run lexer tests', "
        "'command': 'pytest -k lexer', 'kind': 'test'}]}"
    )
    assert sdk_try_parse(text, PlannedIssue) is None  # SDK can't fix single quotes
    got = baml_parse(text, PlannedIssue)
    assert got.verification[0].command == "pytest -k lexer"
