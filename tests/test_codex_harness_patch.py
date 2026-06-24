from __future__ import annotations

from swe_af.runtime.codex_harness_patch import (
    _CapturedStdoutStream,
    _augment_codex_error_message,
    _codex_strict_json_schema,
    _format_claude_auth_error,
    _is_claude_auth_error,
    _stdout_tail,
    active_provider,
    apply_codex_harness_patch,
)


def test_codex_strict_json_schema_requires_all_object_properties() -> None:
    schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "default": ""},
            "files_changed": {"type": "array", "items": {"type": "string"}},
        },
    }

    strict = _codex_strict_json_schema(schema)

    assert strict["required"] == ["summary", "files_changed"]
    assert strict["additionalProperties"] is False
    assert "default" not in strict["properties"]["summary"]


def test_codex_strict_json_schema_recurses_into_defs() -> None:
    schema = {
        "$defs": {
            "Item": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "count": {"type": "integer", "default": 1},
                },
                "required": ["name"],
            }
        },
        "type": "object",
        "properties": {
            "items": {"type": "array", "items": {"$ref": "#/$defs/Item"}},
        },
    }

    strict = _codex_strict_json_schema(schema)

    item = strict["$defs"]["Item"]
    assert item["required"] == ["name", "count"]
    assert item["additionalProperties"] is False
    assert "default" not in item["properties"]["count"]


def test_codex_strict_json_schema_coerces_typeless_union_branches() -> None:
    """A Pydantic `Any | None` field renders the Any arm as a bare {}; OpenAI strict
    structured outputs (codex --output-schema) reject any union branch without a type,
    so the strict-ifier must give such arms a concrete type."""
    schema = {
        "type": "object",
        "properties": {
            # mirrors AskUserFormField.default_value: Any | None
            "default_value": {"anyOf": [{}, {"type": "null"}]},
        },
    }

    strict = _codex_strict_json_schema(schema)

    branches = strict["properties"]["default_value"]["anyOf"]
    # the bare {} (Any) arm must now carry a concrete type; the null arm is untouched
    assert all("type" in branch for branch in branches)
    assert {"type": "string"} in branches
    assert {"type": "null"} in branches


def test_codex_git_metadata_error_gets_actionable_hint() -> None:
    message = _augment_codex_error_message(
        "fatal: cannot create .git/index.lock",
        "fatal: cannot create .git/index.lock",
    )

    assert "Codex tried to mutate git metadata under workspace-write" in message
    assert "git must be host-managed" in message


def test_codex_unrelated_error_is_unchanged() -> None:
    assert _augment_codex_error_message("plain error", "plain error") == "plain error"


def test_claude_auth_error_is_classified_with_actionable_message() -> None:
    raw = 'API Error: 401 {"type":"authentication_error"} Please run /login'

    assert _is_claude_auth_error(raw)
    classified = _format_claude_auth_error(raw)
    assert classified.startswith("AuthError: Claude Code authentication failed")
    assert "Please run /login" in classified


def test_claude_stdout_capture_retains_non_json_error_banner() -> None:
    class FakeStream:
        async def __aiter__(self):
            for line in [
                'API Error: 401 {"type":"authentication_error"}\n',
                "Please run /login\n",
            ]:
                yield line

    from types import SimpleNamespace

    owner = SimpleNamespace()

    async def consume() -> list[str]:
        return [line async for line in _CapturedStdoutStream(FakeStream(), owner)]

    import asyncio

    assert asyncio.run(consume()) == [
        'API Error: 401 {"type":"authentication_error"}\n',
        "Please run /login\n",
    ]
    captured = _stdout_tail(owner)
    assert "API Error: 401" in captured
    assert "Please run /login" in captured


def test_codex_prompt_suffix_uses_final_json_not_write_tool(tmp_path) -> None:
    from agentfield.harness import _schema

    apply_codex_harness_patch()

    token = active_provider.set("codex")
    try:
        suffix = _schema.build_prompt_suffix(
            {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
            },
            str(tmp_path),
        )
    finally:
        active_provider.reset(token)

    assert "Return a single final JSON object" in suffix
    assert "Write tool" not in suffix
    assert (tmp_path / ".agentfield_schema.json").exists()


def test_non_codex_prompt_suffix_keeps_agentfield_write_tool_default(tmp_path) -> None:
    """For claude_code / open_code calls, build_prompt_suffix must return the
    original AgentField suffix that instructs the agent to use its Write tool.

    Without this gate the codex-native suffix would leak into every harness
    call, forcing claude/opencode runs onto the slower stdout-parse fallback.
    """
    from agentfield.harness import _schema

    apply_codex_harness_patch()

    # No active provider set ⇒ default suffix.
    suffix = _schema.build_prompt_suffix(
        {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
        },
        str(tmp_path),
    )

    assert "Write tool" in suffix
    assert "Codex CLI" not in suffix
