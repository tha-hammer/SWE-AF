from __future__ import annotations

from types import SimpleNamespace

import pytest

from swe_af.execution.schemas import QASynthesisResult
from swe_af.reasoners import execution_agents


def _patch_router_attr(monkeypatch, name: str, value):
    monkeypatch.setitem(execution_agents.router.__dict__, name, value)


def _patch_router(monkeypatch, **attrs):
    attrs.setdefault("note", lambda *args, **kwargs: None)
    for name, value in attrs.items():
        _patch_router_attr(monkeypatch, name, value)


@pytest.mark.asyncio
async def test_code_reviewer_fallback_preserves_exception_text(monkeypatch, tmp_path):
    async def boom(*args, **kwargs):
        raise RuntimeError("schema rejected")

    _patch_router(monkeypatch, harness=boom)

    result = await execution_agents.run_code_reviewer(
        worktree_path=str(tmp_path),
        coder_result={"files_changed": []},
        issue={"name": "ISSUE-1", "title": "T"},
        ai_provider="codex",
    )

    assert result["approved"] is False
    assert result["blocking"] is False
    assert "schema rejected" in result["summary"]


@pytest.mark.asyncio
async def test_qa_synthesizer_codex_uses_harness_not_router_ai(monkeypatch, tmp_path):
    calls = {}

    async def fake_harness(*args, **kwargs):
        calls["harness"] = kwargs
        return SimpleNamespace(
            parsed=QASynthesisResult(action="approve", summary="ok", stuck=False)
        )

    async def fail_ai(*args, **kwargs):
        raise AssertionError("router.ai must not be used for codex synthesizer")

    _patch_router(monkeypatch, harness=fake_harness, ai=fail_ai)

    result = await execution_agents.run_qa_synthesizer(
        qa_result={"passed": True},
        review_result={"approved": True, "blocking": False},
        iteration_history=[],
        worktree_path=str(tmp_path),
        model="gpt-5.4-mini",
        permission_mode="auto",
        ai_provider="codex",
    )

    assert result["action"] == "approve"
    assert calls["harness"]["provider"] == "codex"
    assert calls["harness"]["model"] == "gpt-5.4-mini"
    assert calls["harness"]["cwd"] == str(tmp_path)
    assert calls["harness"]["permission_mode"] == "auto"
    assert calls["harness"]["system_prompt"] == (
        execution_agents.QA_SYNTHESIZER_SYSTEM_PROMPT
    )
    assert calls["harness"].get("tools") in (None, [])


@pytest.mark.asyncio
async def test_qa_synthesizer_claude_keeps_router_ai(monkeypatch):
    calls = {}

    async def fail_harness(*args, **kwargs):
        raise AssertionError("router.harness must not be used for claude synthesizer")

    async def fake_ai(*args, **kwargs):
        calls["ai"] = kwargs
        return SimpleNamespace(
            parsed=QASynthesisResult(action="approve", summary="ok", stuck=False)
        )

    _patch_router(monkeypatch, harness=fail_harness, ai=fake_ai)

    result = await execution_agents.run_qa_synthesizer(
        qa_result={"passed": True},
        review_result={"approved": True, "blocking": False},
        iteration_history=[],
        model="haiku",
        ai_provider="claude",
    )

    assert result["action"] == "approve"
    assert calls["ai"]["model"] == "haiku"
    assert calls["ai"]["system"] == execution_agents.QA_SYNTHESIZER_SYSTEM_PROMPT
    assert calls["ai"]["schema"] is QASynthesisResult
