"""SB-4: the patched seam unmasks a degrading reasoner end-to-end.

Drives the REAL agentfield HarnessRunner via a fake provider that returns the
SB-3 messy fixture text. With the fallback-first wrap installed on
``_runner.try_parse_from_text`` (the binding the call sites actually invoke),
the retry advisor returns the model's real advice instead of the
``should_retry=False`` fallback.

No real LLM call: the provider is faked and ``_ai_schema_repair`` is stubbed.
"""

import os

os.environ.setdefault("AGENTFIELD_SERVER", "http://localhost:9999")

from pathlib import Path  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402
from agentfield import Agent  # noqa: E402
from agentfield.harness import _runner as _runner_mod  # noqa: E402
from agentfield.harness._result import Metrics, RawResult  # noqa: E402

import swe_af.runtime.codex_harness_patch as codex_harness_patch  # noqa: E402
from swe_af.reasoners import router  # noqa: E402
from swe_af.reasoners.execution_agents import run_retry_advisor  # noqa: E402

pytestmark = pytest.mark.functional

FIXTURE = (
    Path(__file__).parent / "fixtures" / "messy_cli_output_retry_advice.txt"
).read_text()

CLEAN_JSON = (
    '{"should_retry": false, "diagnosis": "clean", "strategy": "s", '
    '"modified_context": "m", "confidence": 0.4}'
)
FALLBACK_DIAGNOSIS = "Retry advisor agent failed to produce a valid analysis."


class _FakeProvider:
    """Returns a fixed text as the harness result; never writes an output file."""

    def __init__(self, text: str):
        self._text = text

    async def execute(self, prompt, options):  # noqa: ANN001
        return RawResult(result=self._text, is_error=False, metrics=Metrics())


@pytest.fixture
def attached_router():
    """Attach the main router to a real Agent so router.harness hits the runner."""
    agent = Agent(node_id="seam-test", agentfield_server=os.environ["AGENTFIELD_SERVER"])
    agent.include_router(router)
    try:
        yield
    finally:
        object.__setattr__(router, "_agent", None)


@pytest.fixture(autouse=True)
def _no_ai_repair(monkeypatch):
    """Keep the test deterministic/offline: the AI-repair tier is out of scope."""

    async def _none(text, schema, options):  # noqa: ANN001
        return None

    monkeypatch.setattr(_runner_mod, "_ai_schema_repair", _none)


async def _run_advisor(repo_path):
    return await run_retry_advisor(
        issue={"name": "demo"},
        error_message="boom",
        error_context="ctx",
        attempt_number=1,
        repo_path=str(repo_path),
    )


async def test_seam_unmasks_degrading_retry_advisor(
    attached_router, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        _runner_mod, "build_provider", lambda cfg: _FakeProvider(FIXTURE)
    )
    out = await _run_advisor(tmp_path)
    # SDK-alone would yield parsed=None -> should_retry=False fallback.
    assert out["should_retry"] is True
    assert out["diagnosis"] != FALLBACK_DIAGNOSIS
    assert "migration" in out["diagnosis"].lower()


async def test_happy_path_baml_not_invoked(attached_router, tmp_path, monkeypatch):
    # Spy at the SAME bound name the wrapper invokes (codex_harness_patch global).
    spy = MagicMock(
        side_effect=AssertionError("baml_parse_or_none must not run on the happy path")
    )
    monkeypatch.setattr(codex_harness_patch, "baml_parse_or_none", spy)
    monkeypatch.setattr(
        _runner_mod, "build_provider", lambda cfg: _FakeProvider(CLEAN_JSON)
    )
    out = await _run_advisor(tmp_path)
    assert out["should_retry"] is False
    assert out["diagnosis"] == "clean"
    spy.assert_not_called()


async def test_baml_also_fails_preserves_fallback(
    attached_router, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        _runner_mod,
        "build_provider",
        lambda cfg: _FakeProvider("totally unparseable prose, definitely no json here"),
    )
    out = await _run_advisor(tmp_path)
    assert out["should_retry"] is False
    assert out["diagnosis"] == FALLBACK_DIAGNOSIS
