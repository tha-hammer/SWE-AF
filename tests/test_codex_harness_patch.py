from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from swe_af.runtime.codex_harness_patch import (
    _CapturedStdoutStream,
    _augment_codex_error_message,
    _codex_strict_json_schema,
    _codex_error_detail,
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


def _paths_with_open_additional_properties(schema, path="$"):
    paths = []
    if isinstance(schema, dict):
        if schema.get("additionalProperties") is True:
            paths.append(path)
        for key, value in schema.items():
            paths.extend(_paths_with_open_additional_properties(value, f"{path}.{key}"))
    elif isinstance(schema, list):
        for index, value in enumerate(schema):
            paths.extend(_paths_with_open_additional_properties(value, f"{path}[{index}]"))
    return paths


def test_codex_strict_json_schema_closes_open_dict_objects() -> None:
    schema = {
        "type": "object",
        "properties": {
            "payload": {"type": "object", "additionalProperties": True},
            "items": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
        },
    }

    strict = _codex_strict_json_schema(schema)

    assert _paths_with_open_additional_properties(strict) == []
    assert strict["properties"]["payload"]["additionalProperties"] is False
    assert strict["properties"]["items"]["items"]["additionalProperties"] is False


def test_fix_generator_result_is_public_schema_contract() -> None:
    from swe_af.execution.schemas import FixGeneratorResult

    assert FixGeneratorResult.model_json_schema()["type"] == "object"


def test_codex_role_result_schemas_have_no_open_objects() -> None:
    from swe_af.execution.schemas import (
        CodeReviewResult,
        CoderResult,
        FixGeneratorResult,
        QAResult,
    )

    for model in (CoderResult, QAResult, CodeReviewResult, FixGeneratorResult):
        strict = _codex_strict_json_schema(model.model_json_schema())
        assert _paths_with_open_additional_properties(strict) == []


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


def test_codex_schema_output_paths_are_invocation_scoped(tmp_path) -> None:
    from agentfield.harness import _schema
    from swe_af.runtime.codex_harness_patch import (
        _begin_codex_invocation_paths,
        _current_codex_invocation_paths,
        _reset_codex_invocation_paths,
    )

    apply_codex_harness_patch()

    token = active_provider.set("codex")
    first_token = None
    second_token = None
    try:
        first_token = _begin_codex_invocation_paths(str(tmp_path))
        first_suffix = _schema.build_prompt_suffix(
            {"type": "object", "properties": {"summary": {"type": "string"}}},
            str(tmp_path),
        )
        first_paths = _current_codex_invocation_paths()

        second_token = _begin_codex_invocation_paths(str(tmp_path))
        second_suffix = _schema.build_prompt_suffix(
            {"type": "object", "properties": {"approved": {"type": "boolean"}}},
            str(tmp_path),
        )
        second_paths = _current_codex_invocation_paths()
    finally:
        if second_token is not None:
            _reset_codex_invocation_paths(second_token)
        if first_token is not None:
            _reset_codex_invocation_paths(first_token)
        active_provider.reset(token)

    assert first_paths.schema_path != second_paths.schema_path
    assert first_paths.output_path != second_paths.output_path
    assert first_paths.schema_path in first_suffix
    assert second_paths.schema_path in second_suffix
    assert Path(first_paths.schema_path).exists()
    assert Path(second_paths.schema_path).exists()


@pytest.mark.asyncio
async def test_codex_provider_uses_invocation_scoped_schema_and_output_paths(
    monkeypatch, tmp_path
) -> None:
    from agentfield.harness import _schema
    from agentfield.harness.providers.codex import CodexProvider
    from swe_af.runtime import codex_harness_patch as chp

    apply_codex_harness_patch()
    commands: list[list[str]] = []

    async def fake_run(cmd, prompt_for_codex, *, env, cwd, timeout_seconds):
        commands.append(list(cmd))
        return chp.CodexCLIResult(
            stdout=json.dumps({"type": "result", "result": '{"ok": true}'}) + "\n",
            stderr="",
            returncode=0,
            timed_out=False,
        )

    monkeypatch.setattr(chp, "_run_codex_cli_with_timeout", fake_run)

    async def invoke(schema: dict):
        provider_token = active_provider.set("codex")
        path_token = chp._begin_codex_invocation_paths(str(tmp_path))
        try:
            _schema.build_prompt_suffix(schema, str(tmp_path))
            return await CodexProvider().execute("prompt", {"cwd": str(tmp_path)})
        finally:
            chp._reset_codex_invocation_paths(path_token)
            active_provider.reset(provider_token)

    await asyncio.gather(
        invoke({"type": "object", "properties": {"first": {"type": "string"}}}),
        invoke({"type": "object", "properties": {"second": {"type": "string"}}}),
    )

    schema_paths = [
        cmd[cmd.index("--output-schema") + 1]
        for cmd in commands
        if "--output-schema" in cmd
    ]
    output_paths = [
        cmd[cmd.index("--output-last-message") + 1]
        for cmd in commands
        if "--output-last-message" in cmd
    ]
    assert len(schema_paths) == len(output_paths) == 2
    assert len(set(schema_paths)) == 2
    assert len(set(output_paths)) == 2
    assert all(Path(path).name.startswith(".agentfield_schema.") for path in schema_paths)
    assert all(Path(path).name.startswith(".agentfield_output.") for path in output_paths)


def test_codex_error_detail_prefers_jsonl_error_over_stdin_banner() -> None:
    records = [
        {"type": "event_msg", "message": "Reading prompt from stdin..."},
        {
            "type": "error",
            "message": "invalid_json_schema: additionalProperties must be false",
        },
    ]

    detail = _codex_error_detail(
        stderr="Reading prompt from stdin...\n",
        records=records,
        stdout="",
    )

    assert "invalid_json_schema" in detail
    assert "additionalProperties" in detail


@pytest.mark.asyncio
async def test_codex_provider_nonzero_exit_surfaces_stdout_jsonl_error(
    monkeypatch, tmp_path
) -> None:
    from agentfield.harness.providers.codex import CodexProvider
    from swe_af.runtime import codex_harness_patch as chp

    apply_codex_harness_patch()

    async def fake_run(cmd, prompt_for_codex, *, env, cwd, timeout_seconds):
        return chp.CodexCLIResult(
            stdout=json.dumps(
                {
                    "type": "error",
                    "message": "invalid_json_schema: additionalProperties must be false",
                }
            )
            + "\n",
            stderr="Reading prompt from stdin...\n",
            returncode=1,
            timed_out=False,
        )

    monkeypatch.setattr(chp, "_run_codex_cli_with_timeout", fake_run)

    raw = await CodexProvider().execute("prompt", {"cwd": str(tmp_path)})

    assert raw.is_error is True
    assert "invalid_json_schema" in (raw.error_message or "")
    assert "additionalProperties" in (raw.error_message or "")


@pytest.mark.asyncio
async def test_codex_cli_timeout_kills_and_reaps_child(monkeypatch) -> None:
    from swe_af.runtime.codex_harness_patch import _run_codex_cli_with_timeout

    events = []

    class FakeProc:
        returncode = None
        stdin = object()
        stdout = object()
        stderr = object()

        async def communicate(self, _payload):
            await asyncio.sleep(999)

        def kill(self):
            events.append("kill")
            self.returncode = -9

        async def wait(self):
            events.append("wait")

    async def fake_create_subprocess_exec(*args, **kwargs):
        events.append("spawn")
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await _run_codex_cli_with_timeout(
        ["codex", "exec"],
        "prompt",
        env={},
        cwd=None,
        timeout_seconds=0.01,
    )

    assert result.returncode == -1
    assert result.timed_out is True
    assert events == ["spawn", "kill", "wait"]


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
