"""Unit tests for the lean-prompt scaffolding helpers (SWE-AF-23z, Phase 1).

These cover only the additive helpers; the existing renderers in
``swe_af/prompts/_utils.py`` are exercised by ``test_workspace_context_block.py``.
"""

from __future__ import annotations

import pytest

from swe_af.prompts._utils import (
    criterion_command_discipline,
    lean_role,
    xml_block,
)

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# lean_role
# --------------------------------------------------------------------------- #
def test_lean_role_is_a_single_line_with_domain_and_function() -> None:
    role = lean_role("a multi-repo build pipeline", "technical reviewer")
    assert role == "You are a technical reviewer for a multi-repo build pipeline."
    assert "\n" not in role


def test_lean_role_trims_whitespace() -> None:
    assert lean_role("  product features  ", "  product manager  ") == (
        "You are a product manager for product features."
    )


def test_lean_role_avoids_seniority_persona() -> None:
    role = lean_role("the planning pipeline", "architect").lower()
    for persona_word in ("senior", "staff", "principal", "expert", "years of experience"):
        assert persona_word not in role


# --------------------------------------------------------------------------- #
# xml_block
# --------------------------------------------------------------------------- #
def test_xml_block_wraps_content_in_named_tag() -> None:
    assert xml_block("prd", "Ship the thing.") == "<prd>\nShip the thing.\n</prd>"


def test_xml_block_normalizes_surrounding_newlines() -> None:
    # Leading/trailing newlines in content collapse to exactly one each side.
    assert xml_block("architecture", "\n\nbody\n\n") == "<architecture>\nbody\n</architecture>"


def test_xml_block_handles_empty_content() -> None:
    assert xml_block("prior_responses", "") == "<prior_responses>\n\n</prior_responses>"


def test_xml_block_is_parseable_xml() -> None:
    import xml.etree.ElementTree as ET

    element = ET.fromstring(xml_block("prd", "Ship the thing."))
    assert element.tag == "prd"
    assert element.text.strip() == "Ship the thing."


# --------------------------------------------------------------------------- #
# criterion_command_discipline
# --------------------------------------------------------------------------- #
def test_criterion_command_discipline_states_the_rule() -> None:
    text = criterion_command_discipline()
    assert "acceptance criterion" in text
    assert "command" in text
    assert "exit code" in text.lower()


def test_criterion_command_discipline_is_a_stable_single_source() -> None:
    # Idempotent / deterministic — it is a constant the prompts can rely on.
    assert criterion_command_discipline() == criterion_command_discipline()
    assert criterion_command_discipline().strip() == criterion_command_discipline()
