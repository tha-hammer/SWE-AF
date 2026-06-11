from __future__ import annotations

import asyncio
import contextvars
import json
import os
from pathlib import Path
from typing import Any

# BAML Schema-Aligned Parser fallback. Imported at module scope so the wrapped
# try_parse_from_text resolves it as a module global — tests spy on
# ``codex_harness_patch.baml_parse_or_none`` (the SAME bound name the wrapper
# invokes). Guarded so a missing/ungenerated baml_client degrades gracefully to
# the SDK-only parse path instead of breaking reasoner import.
try:
    from swe_af.baml_bridge import baml_output_format, baml_parse_or_none
except Exception:  # pragma: no cover - baml client not generated / baml-py absent
    baml_parse_or_none = None  # type: ignore[assignment]
    baml_output_format = None  # type: ignore[assignment]

_PATCHED = False

# When True (set from BuildConfig/ExecutionConfig.enable_baml_output_format during
# the measured rollout), the claude/opencode prompt suffix renders the output shape
# via BAML output_format (~85% smaller) instead of raw JSON Schema. OFF by default;
# an unmappable schema or any render failure falls back to JSON Schema. codex is
# never affected (it uses its native --output-schema path).
baml_output_format_enabled: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "swe_af_baml_output_format_enabled", default=False
)

# Set by the wrapped Agent.harness for the duration of a harness call.
# Read by the dispatching build_prompt_suffix so that claude_code / open_code
# calls keep the original AgentField "use Write tool" instruction and only
# codex calls get the Codex-native structured-output instruction.
active_provider: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "swe_af_codex_active_provider", default=None
)

_ORIGINAL_BUILD_PROMPT_SUFFIX: Any = None
_ORIGINAL_TRY_PARSE_FROM_TEXT: Any = None


def _codex_strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return schema
    strict = dict(schema)
    schema_type = strict.get("type")
    if schema_type == "object":
        properties = strict.get("properties")
        if isinstance(properties, dict):
            cleaned: dict[str, Any] = {}
            for key, value in properties.items():
                if isinstance(value, dict):
                    child = dict(value)
                    child.pop("default", None)
                    cleaned[key] = _codex_strict_json_schema(child)
                else:
                    cleaned[key] = value
            strict["properties"] = cleaned
            strict["required"] = list(cleaned.keys())
            strict["additionalProperties"] = False
    if schema_type == "array":
        items = strict.get("items")
        if isinstance(items, dict):
            strict["items"] = _codex_strict_json_schema(items)
    for key in ("allOf", "anyOf", "oneOf"):
        branch = strict.get(key)
        if isinstance(branch, list):
            strict[key] = [
                _codex_strict_json_schema(item) if isinstance(item, dict) else item
                for item in branch
            ]
    defs = strict.get("$defs")
    if isinstance(defs, dict):
        strict["$defs"] = {
            key: _codex_strict_json_schema(value) if isinstance(value, dict) else value
            for key, value in defs.items()
        }
    definitions = strict.get("definitions")
    if isinstance(definitions, dict):
        strict["definitions"] = {
            key: _codex_strict_json_schema(value) if isinstance(value, dict) else value
            for key, value in definitions.items()
        }
    return strict


def _augment_codex_error_message(message: str, detail: str) -> str:
    lower = f"{message}\n{detail}".lower()
    hints = (
        ".git/index.lock",
        ".git/refs",
        "repository metadata is read-only",
    )
    if any(token in lower for token in hints):
        return (
            f"{message}\n\n"
            "Codex tried to mutate git metadata under workspace-write; "
            "git must be host-managed."
        )
    return message


async def _run_codex_cli_with_stdin(
    cmd: list[str],
    prompt_for_codex: str,
    *,
    env: dict[str, str] | None,
    cwd: str | None,
) -> tuple[str, str, int]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=cwd,
    )
    stdout_bytes, stderr_bytes = await proc.communicate(prompt_for_codex.encode("utf-8"))
    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    return stdout, stderr, int(proc.returncode)


def apply_codex_harness_patch() -> None:
    global _PATCHED, _ORIGINAL_BUILD_PROMPT_SUFFIX, _ORIGINAL_TRY_PARSE_FROM_TEXT
    if _PATCHED:
        return
    try:
        from agentfield.agent import Agent
        from agentfield.harness import _runner, _schema
        from agentfield.harness._cli import (
            estimate_cli_cost,
            extract_final_text,
            parse_jsonl,
            strip_ansi,
        )
        from agentfield.harness._result import FailureType, Metrics, RawResult
        from agentfield.harness.providers.codex import CodexProvider
    except Exception:
        return

    _ORIGINAL_BUILD_PROMPT_SUFFIX = _schema.build_prompt_suffix

    def build_prompt_suffix_with_schema_file(schema: Any, cwd: str) -> str:
        """Use Codex-native structured output instead of AgentField's Write-tool suffix.

        AgentField's default suffix asks the model to create
        ``.agentfield_output.json`` with a Write tool. Codex CLI executions may
        run under read-only sandboxing and do not have AgentField's Write tool,
        so that instruction causes no final output. The Codex provider below
        passes ``--output-schema`` and ``--output-last-message`` to the CLI; this
        suffix only needs to create the schema file and ask for final JSON.
        """
        schema_json = json.dumps(
            _codex_strict_json_schema(_schema.schema_to_json_schema(schema)),
            indent=2,
        )
        _schema.write_schema_file(schema_json, cwd)
        schema_path = _schema.get_schema_path(cwd)
        return (
            "\n\n---\n"
            "CRITICAL CODEX STRUCTURED OUTPUT REQUIREMENTS:\n"
            f"Return a single final JSON object conforming to: {schema_path}\n"
            "Do not use markdown fences, comments, or surrounding prose.\n"
            "Do not try to create .agentfield_output.json yourself; the Codex "
            "CLI will persist your final JSON response for AgentField."
        )

    async def execute_with_native_structured_output(self: Any, prompt: str, options: dict[str, object]) -> Any:
        cwd = str(options.get("cwd")) if isinstance(options.get("cwd"), str) else None
        model = options.get("model")
        permission_mode = options.get("permission_mode")
        env_value = options.get("env")
        merged_env = {**os.environ}
        if isinstance(env_value, dict):
            merged_env.update({str(k): str(v) for k, v in env_value.items() if isinstance(k, str)})

        cmd = [self._bin, "exec", "--json", "--skip-git-repo-check"]
        if cwd:
            cmd.extend(["-C", cwd])
        if model:
            cmd.extend(["-m", str(model)])

        if permission_mode == "auto":
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
        elif permission_mode in {"read-only", "workspace-write", "danger-full-access"}:
            cmd.extend(["--sandbox", str(permission_mode)])
        else:
            cmd.extend(["--sandbox", "workspace-write"])

        prompt_for_codex = prompt
        if cwd:
            schema_path = _schema.get_schema_path(cwd)
            output_path = _schema.get_output_path(cwd)
            if Path(schema_path).exists():
                cmd.extend(["--output-schema", schema_path])
                cmd.extend(["--output-last-message", output_path])
                prompt_for_codex += (
                    "\n\n---\n"
                    "CODEX STRUCTURED OUTPUT CONTRACT:\n"
                    f"The Codex CLI will save your final response to: {output_path}\n"
                    f"Your final response MUST be a single JSON object conforming to: {schema_path}\n"
                    "Return the JSON object as your final answer. Do not write "
                    "the output file yourself or make the output file the task."
                )

        try:
            start = asyncio.get_running_loop().time()
            timeout_seconds = options.get("timeout_seconds")
            if isinstance(timeout_seconds, (int, float)) and timeout_seconds > 0:
                stdout, stderr, returncode = await asyncio.wait_for(
                    _run_codex_cli_with_stdin(cmd, prompt_for_codex, env=merged_env, cwd=cwd),
                    timeout=float(timeout_seconds),
                )
            else:
                stdout, stderr, returncode = await _run_codex_cli_with_stdin(
                    cmd, prompt_for_codex, env=merged_env, cwd=cwd
                )
            duration_ms = int((asyncio.get_running_loop().time() - start) * 1000)
        except FileNotFoundError as exc:
            return RawResult(
                result="",
                messages=[],
                metrics=Metrics(
                    duration_api_ms=0,
                    num_turns=1,
                    total_cost_usd=0.0,
                    session_id="",
                ),
                is_error=True,
                error_message=str(exc),
                failure_type=FailureType.CRASH,
                returncode=-1,
            )
        except asyncio.TimeoutError:
            return RawResult(
                result="",
                messages=[],
                metrics=Metrics(
                    duration_api_ms=0,
                    num_turns=1,
                    total_cost_usd=0.0,
                    session_id="",
                ),
                is_error=True,
                error_message="Codex CLI timed out",
                failure_type=FailureType.TIMEOUT,
                returncode=-1,
            )

        stderr_clean = strip_ansi(stderr or "")
        records = parse_jsonl(stdout or "")
        result_text = extract_final_text(records) or ""

        if not result_text and cwd:
            output_path = _schema.get_output_path(cwd)
            output_file = Path(output_path)
            if output_file.exists():
                try:
                    result_text = output_file.read_text(encoding="utf-8")
                except Exception:
                    result_text = ""

        is_error = returncode != 0
        error_message = ""
        failure_type = FailureType.NONE
        if is_error:
            base_error = stderr_clean or "Codex CLI failed"
            error_message = _augment_codex_error_message(base_error, base_error)
            failure_type = FailureType.CRASH

        return RawResult(
            result=result_text,
            messages=records if isinstance(records, list) else [],
            metrics=Metrics(
                duration_api_ms=duration_ms,
                num_turns=1,
                total_cost_usd=estimate_cli_cost(
                    model=str(options.get("model", "")),
                    prompt=prompt_for_codex,
                    result_text=result_text,
                ),
                session_id="",
            ),
            is_error=is_error,
            error_message=error_message,
            failure_type=failure_type,
            returncode=returncode,
        )

    def build_prompt_suffix_with_baml_output_format(schema: Any, cwd: str) -> str:
        """claude/opencode suffix using BAML output_format instead of JSON Schema.

        Same Write-tool contract as the AgentField base suffix, but the output shape
        is the compact ``ctx.output_format`` render. Raises (caller falls back) if the
        schema is unmappable.
        """
        render = baml_output_format(schema)  # may raise TypeError on unmappable schema
        output_path = _schema.get_output_path(cwd)
        return (
            "\n\n---\n"
            "CRITICAL OUTPUT REQUIREMENTS:\n"
            f"You MUST use your Write tool to create this file: {output_path}\n"
            "The file MUST contain ONLY valid JSON matching the schema below.\n"
            "Do NOT output the JSON in your response text — write it to the file.\n\n"
            f"{render}\n\n"
            "Write ONLY valid JSON to the file. No markdown fences, no comments, no extra text."
        )

    def build_prompt_suffix_dispatching(schema: Any, cwd: str) -> str:
        """Route to codex-native suffix only when the active call is for codex.

        Without this gate, every claude_code / open_code harness call would
        also receive the codex-specific instruction "Do not try to create
        .agentfield_output.json yourself; the Codex CLI will persist your
        final JSON response" — which is wrong for those providers and forces
        their runner into the slower stdout-parse fallback path.

        For claude/opencode, when ``baml_output_format_enabled`` is set and the
        schema is mappable, use the compact BAML output_format render; any failure
        (unmappable schema, missing baml client) falls back to the JSON-Schema suffix.
        """
        if active_provider.get() == "codex":
            return build_prompt_suffix_with_schema_file(schema, cwd)
        if baml_output_format_enabled.get() and baml_output_format is not None:
            try:
                return build_prompt_suffix_with_baml_output_format(schema, cwd)
            except Exception:
                pass  # unmappable / render failure → fall back to JSON Schema
        return _ORIGINAL_BUILD_PROMPT_SUFFIX(schema, cwd)

    # --- BAML fallback-first parse wrap ---------------------------------------
    # Run the SDK's 3-strategy try_parse_from_text first; only on its None does
    # BAML's Schema-Aligned Parser get a shot. The happy path stays byte-identical.
    _ORIGINAL_TRY_PARSE_FROM_TEXT = _runner.try_parse_from_text

    def try_parse_from_text_fallback_first(text: Any, schema: Any) -> Any:
        result = _ORIGINAL_TRY_PARSE_FROM_TEXT(text, schema)
        if result is not None:
            return result
        # Module-global lookup at call time so tests can spy on
        # codex_harness_patch.baml_parse_or_none (the bound name used here).
        if baml_parse_or_none is None:
            return None
        return baml_parse_or_none(text, schema)

    _orig_agent_harness = Agent.harness

    async def _harness_with_provider_context(
        self: Any, prompt: str, *args: Any, **kwargs: Any
    ) -> Any:
        provider_value = kwargs.get("provider")
        token = active_provider.set(str(provider_value) if provider_value else None)
        try:
            return await _orig_agent_harness(self, prompt, *args, **kwargs)
        finally:
            active_provider.reset(token)

    _schema.build_prompt_suffix = build_prompt_suffix_dispatching
    _runner.build_prompt_suffix = build_prompt_suffix_dispatching
    # Assign the BAML wrap to BOTH bindings. _runner.try_parse_from_text is the
    # load-bearing one: _runner.py imported the symbol by name, so the live call
    # sites (_runner.py:141,355,466) bind the _runner module reference, NOT
    # _schema's. Patching _schema alone would be a no-op for the parse path.
    _runner.try_parse_from_text = try_parse_from_text_fallback_first
    _schema.try_parse_from_text = try_parse_from_text_fallback_first
    CodexProvider.execute = execute_with_native_structured_output
    Agent.harness = _harness_with_provider_context
    _PATCHED = True
