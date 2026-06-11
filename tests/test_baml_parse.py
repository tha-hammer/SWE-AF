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
import agentfield.harness._schema as _schema

from swe_af.baml_bridge import baml_parse, baml_parse_or_none
from swe_af.execution.schemas import ReplanDecision, RetryAdvice

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent / "fixtures"


def sdk_try_parse(text, schema):
    """The raw SDK ladder, immune to the BAML seam's monkeypatch.

    apply_codex_harness_patch() reassigns _schema.try_parse_from_text to the
    fallback-first wrapper whenever swe_af.reasoners is imported (which happens in
    a full-suite run). Calling the saved original keeps this oracle measuring the
    SDK alone, so the "SDK drops it / BAML rescues it" contract is genuine in both
    isolated and full-suite runs.
    """
    from swe_af.runtime import codex_harness_patch

    original = codex_harness_patch._ORIGINAL_TRY_PARSE_FROM_TEXT
    return (original or _schema.try_parse_from_text)(text, schema)

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
    assert sdk_try_parse(text, RetryAdvice) is None
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
    assert sdk_try_parse(text, RetryAdvice) is None  # SDK can't fix quotes
    got = baml_parse(text, RetryAdvice)
    assert got.should_retry is True
    assert got.diagnosis == "flaky"


# ---------------------------------------------------------------------------
# SB-5: captured / corpus regression
# ---------------------------------------------------------------------------

# Every RetryAdvice-shaped degraded fixture. Real captures dropped into
# tests/fixtures/messy_cli_output_retry_advice*.txt are covered automatically —
# SB-5's positive case folds into this corpus (plan line 410) since no genuine
# malformed-JSON capture exists in-repo yet.
RETRY_ADVICE_CORPUS = sorted(FIXTURES.glob("messy_cli_output_retry_advice*.txt"))

# Genuine captured build logs whose reasoners hit `parsed is None -> fallback`.
# Gitignored .artifacts may be absent in CI; skipif keeps the suite green there.
REAL_CAPTURE_LOG_DIR = (
    Path(__file__).resolve().parents[1] / "examples" / "pyrust" / ".artifacts" / "logs"
)
REAL_CAPTURE_LOGS = (
    sorted(REAL_CAPTURE_LOG_DIR.glob("*.jsonl")) if REAL_CAPTURE_LOG_DIR.is_dir() else []
)


@pytest.mark.parametrize("fixture_path", RETRY_ADVICE_CORPUS, ids=lambda p: p.name)
def test_corpus_sdk_drops_but_baml_parses(fixture_path):
    text = fixture_path.read_text()
    assert sdk_try_parse(text, RetryAdvice) is None
    parsed = baml_parse(text, RetryAdvice)
    assert isinstance(parsed, RetryAdvice)
    assert isinstance(parsed.should_retry, bool)
    assert parsed.diagnosis.strip()


def _captured_error_texts(path: Path) -> list[str]:
    texts: list[str] = []
    for line in path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("event") == "assistant":
            for block in rec.get("content", []):
                if (
                    isinstance(block, dict)
                    and block.get("type") == "text"
                    and "API Error" in (block.get("text") or "")
                ):
                    texts.append(block["text"])
    return texts


@pytest.mark.skipif(not REAL_CAPTURE_LOGS, reason="no captured build logs present")
def test_real_capture_baml_declines_without_crash():
    """Real captured parsed-is-None build logs: BAML DECLINES (None), never crashes.

    These genuine captures are auth-error strings, not schema-shaped JSON, so None
    is the *correct* verdict. The test pins two seam-safety guarantees on real data:
    baml_parse_or_none never raises — even for ReplanDecision, whose untyped
    list[dict] fields are unmappable — and never falsely "rescues" a transport
    failure into a bogus typed object.
    """
    seen = 0
    for log in REAL_CAPTURE_LOGS:
        for text in _captured_error_texts(log):
            seen += 1
            assert sdk_try_parse(text, ReplanDecision) is None
            assert baml_parse_or_none(text, ReplanDecision) is None
    assert seen > 0, "expected at least one captured API-error payload"
