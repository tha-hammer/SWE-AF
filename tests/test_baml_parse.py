"""SB-3: BAML parses messy harness output the SDK regex ladder drops.

Dual oracle: the SDK's own ``try_parse_from_text`` returns None on the same
input that ``baml_parse`` parses to the correct typed object — proving BAML is
strictly stronger, not just differently-tuned.

Two helpers, two failure contracts:
  * ``baml_parse``        RAISES ValueError on failure.
  * ``baml_parse_or_none`` returns None on failure (the seam's contract).
"""

import json
from pathlib import Path

import pytest
from agentfield.harness._schema import try_parse_from_text

from swe_af.baml_bridge import baml_parse, baml_parse_or_none
from swe_af.execution.schemas import RetryAdvice

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent / "fixtures"

# Hand-authored oracle for the messy fixture — NOT derived from baml output.
EXPECTED_MESSY = RetryAdvice(
    should_retry=True,
    diagnosis="The integration test failed because the DB migration wasn't applied before the suite ran",
    strategy="Run alembic upgrade head in the setup step, then re-run the suite",
    modified_context="Ensure migrations run before tests; the previous attempt skipped this step",
    confidence=0.82,
)


def test_baml_beats_sdk_ladder_on_messy_fixture():
    text = (FIXTURES / "messy_cli_output_retry_advice.txt").read_text()
    # Dual oracle: the SDK's 3-strategy ladder drops this input.
    assert try_parse_from_text(text, RetryAdvice) is None
    # BAML parses it to the correct typed object.
    assert baml_parse(text, RetryAdvice) == EXPECTED_MESSY


def test_valid_embedded_json_parses():
    J = {
        "should_retry": False,
        "diagnosis": "transient network blip",
        "strategy": "retry as-is",
        "modified_context": "",
        "confidence": 0.3,
    }
    text = f"Here is the result:\n```json\n{json.dumps(J)}\n```\n"
    assert baml_parse(text, RetryAdvice) == RetryAdvice(**J)


def test_unparseable_raises_vs_returns_none():
    garbage = "not json at all, just prose about the weather"
    with pytest.raises(ValueError, match="Could not parse structured response"):
        baml_parse(garbage, RetryAdvice)
    assert baml_parse_or_none(garbage, RetryAdvice) is None


def test_recoverable_malformed_sdk_none_baml_parses():
    """Single-quoted inline JSON: SDK ladder -> None, baml_parse -> object."""
    text = (
        "{'should_retry': True, 'diagnosis': 'flaky', 'strategy': 'rerun', "
        "'modified_context': 'none', 'confidence': 0.6}"
    )
    assert try_parse_from_text(text, RetryAdvice) is None  # SDK can't fix quotes
    got = baml_parse(text, RetryAdvice)
    assert got.should_retry is True
    assert got.diagnosis == "flaky"
