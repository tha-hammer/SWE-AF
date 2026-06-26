# Codex Empty Build Recovery TDD Implementation Plan

## Overview

Fix the Codex build-factory failure mode documented in
`thoughts/searchable/shared/research/2026-06-26-codex-coder-empty-cv-build-debug.md`:
the Contract View build planned issues, then the first coder issue failed five
times with `files_changed=[]`, downstream issues skipped, reviewer/QA/fix paths
also produced fallback output, and the deterministic DB check could not pass in
the running build container.

The Claude runtime is currently completing tasks. Treat Claude as the control
path: keep its runtime defaults, harness adapter mapping, AgentField Write-tool
output contract, and QA synthesizer behavior unchanged unless a regression test
proves the change is safe.

## Current State Analysis

### Key Discoveries

- `ExecutionConfig` defaults to `runtime="claude_code"`, which maps to
  `ai_provider="claude"` and Claude model defaults (`sonnet`, with `haiku` for
  `qa_synthesizer`) in `swe_af/execution/schemas.py:520`.
- Codex is opt-in and maps through `runtime_to_harness_adapter("codex")` to the
  harness provider `"codex"` in `swe_af/runtime/providers.py`.
- `run_coder`, `run_qa`, `run_code_reviewer`, and `generate_fix_issues` already
  use `router.harness(... provider=runtime_to_harness_adapter(ai_provider) ...)`
  at `swe_af/reasoners/execution_agents.py:1086`,
  `swe_af/reasoners/execution_agents.py:1163`,
  `swe_af/reasoners/execution_agents.py:1243`, and
  `swe_af/reasoners/execution_agents.py:1432`.
- `run_qa_synthesizer` does not use the runtime adapter. It calls `router.ai`
  directly at `swe_af/reasoners/execution_agents.py:1325`, so a Codex runtime
  can send raw model ids such as `gpt-5.4-mini` to LiteLLM and fail before a
  synthesizer decision is produced.
- The Codex harness patch intentionally preserves Claude behavior. It only emits
  the Codex-native final-JSON suffix when `active_provider == "codex"`, and
  otherwise returns AgentField's original Write-tool suffix at
  `swe_af/runtime/codex_harness_patch.py:420`.
- `_codex_strict_json_schema` removes defaults, requires object properties, and
  closes normal object schemas at `swe_af/runtime/codex_harness_patch.py:117`,
  but it still leaves open `additionalProperties: true` when the Pydantic schema
  contains bare dict fields.
- Local schema inspection showed the current strictified schemas still contain
  open objects for `CoderResult.agent_retro`, `QAResult.test_failures[]`, and
  `CodeReviewResult.debt_items[]`. Those fields are declared as `dict` or
  `list[dict]` in `swe_af/execution/schemas.py:423`.
- `execute_with_native_structured_output` parses Codex JSONL stdout but, on
  nonzero exit, builds `error_message` only from stderr at
  `swe_af/runtime/codex_harness_patch.py:366`. Codex stderr often contains only
  the banner `Reading prompt from stdin...`, hiding useful JSONL error details.
- `run_code_reviewer` logs the caught exception, then uses `e` after the
  `except` block at `swe_af/reasoners/execution_agents.py:1280`. Python clears
  exception variables after the block, causing `UnboundLocalError` and masking
  the real reviewer error.
- `_run_deterministic_gate` runs planned checks after the coder and feeds any red
  tail back to the coder at `swe_af/execution/coding_loop.py:640`. A planned
  command such as `REQUIRE_TEST_DB=1 npm run test:integration ...` cannot pass
  when the build container has no reachable test DB or `DATABASE_URL_TEST`, but
  that is currently treated like a code failure.
- `docker-compose.yml` passes Codex auth/runtime variables to build nodes, but
  does not pass `DATABASE_URL_TEST` or `host.docker.internal` host-gateway
  support for DB-backed target checks.

## Desired End State

Codex builds should either reach the real coder/reviewer/QA/fix agent work or
fail early with an explicit environment/configuration error. They should not
collapse into five quick fallback iterations with no files changed and no useful
error.

### Observable Behaviors

- Given a Codex-native schema built from coding-loop role outputs, when it is
  strictified, then it contains no `additionalProperties: true` and no bare
  untyped schema branches.
- Given Codex exits nonzero with useful error content in JSONL stdout and only a
  banner on stderr, when AgentField receives the result, then the error message
  includes the structured stdout error detail.
- Given the code reviewer harness raises, when `run_code_reviewer` falls back,
  then it returns a not-approved, non-blocking no-verdict result containing the
  original exception text and does not raise `UnboundLocalError`.
- Given `run_qa_synthesizer(... ai_provider="codex", model="gpt-5.4-mini")`,
  when it invokes the model, then it uses the Codex harness adapter rather than
  `router.ai`/LiteLLM.
- Given `run_qa_synthesizer(... ai_provider="claude")`, when it invokes the
  model, then it keeps the existing `router.ai` path so the successful Claude
  codepath is not perturbed.
- Given a planned deterministic command requires a test DB and the environment
  lacks `DATABASE_URL_TEST`, when the coding loop starts an issue, then it fails
  before spending a coder attempt and reports an environment precondition
  failure instead of feeding the DB connection error back to the coder.
- Given compose-based build nodes are used for DB-backed target checks, when the
  operator sets `DATABASE_URL_TEST`, then `swe-agent` and `swe-fast` receive it
  and can resolve `host.docker.internal` if the DB is exposed on the host.

## What We're Not Doing

- Not implementing the Contract View feature itself.
- Not changing the Claude default runtime, model defaults, or Claude harness
  Write-tool output contract.
- Not replacing AgentField's provider stack.
- Not weakening, skipping, or auto-greenlighting DB-backed integration tests.
- Not hardcoding Cosmic HR database names, Docker networks, credentials, or
  ports into SWE-AF.
- Not making live OpenAI, Claude, or Codex calls in automated unit tests.

## Testing Strategy

- Framework: `pytest` with `pytest-asyncio` (`pyproject.toml` already sets
  `asyncio_mode = "auto"`).
- Test types:
  - Unit tests for schema strictification and Codex error extraction.
  - Async unit tests for execution-agent routing and fallbacks.
  - Functional coding-loop tests for deterministic preflight behavior.
  - Config tests for compose env propagation.
- Mocking:
  - Monkeypatch `router.harness` and `router.ai`; no live LLM calls.
  - Use fake `RawResult`/parsed result objects where AgentField types are awkward.
  - Use the existing injectable `LocalRunner` and scripted `call_fn` patterns in
    `tests/test_coding_loop_deterministic_gate.py`.
- Regression focus:
  - Add Codex-specific assertions without broadening Claude behavior.
  - Run existing Claude-path tests after changes:
    `uv run pytest tests/test_runtime_provider_routing.py tests/test_model_config.py tests/test_codex_harness_patch.py`.

## Behavior 1: Codex Schemas Are Strict

### Test Specification

Given the Pydantic output schemas used by Codex coding-loop roles, when
`_codex_strict_json_schema` prepares them for `codex exec --output-schema`, then
the resulting JSON Schema has no open `additionalProperties: true` nodes and no
bare `{}` union branches.

Edge cases:

- Bare object schema: `{"type":"object","additionalProperties":true}`.
- Array item schema: `{"type":"array","items":{"type":"object","additionalProperties":true}}`.
- Current role schemas: `CoderResult`, `QAResult`, `CodeReviewResult`.
- Fix generator schema after moving the local `FixGeneratorOutput` model to a
  module-level schema.

### TDD Cycle

#### Red: Write Failing Tests

File: `tests/test_codex_harness_patch.py`

Add tests:

```python
def _paths_with_open_additional_properties(schema):
    ...

def test_codex_strict_json_schema_closes_open_dict_objects():
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


def test_codex_role_result_schemas_have_no_open_objects():
    from swe_af.execution.schemas import (
        CodeReviewResult,
        CoderResult,
        FixGeneratorResult,
        QAResult,
    )

    for model in (CoderResult, QAResult, CodeReviewResult, FixGeneratorResult):
        strict = _codex_strict_json_schema(model.model_json_schema())
        assert _paths_with_open_additional_properties(strict) == []
```

This should fail today for `CoderResult.agent_retro`,
`QAResult.test_failures[]`, and `CodeReviewResult.debt_items[]`.

#### Green: Minimal Implementation

Files:

- `swe_af/runtime/codex_harness_patch.py`
- `swe_af/execution/schemas.py`
- `swe_af/reasoners/execution_agents.py`
- `tests/test_baml_bridge.py` if assertions mention the old bare dict fields.

Implementation direction:

- Add a small recursive helper used by `_codex_strict_json_schema` that closes
  any remaining object schema with `additionalProperties is True`.
- Prefer typed nested models where the existing prompt already documents the
  shape:
  - `AgentRetro` for `CoderResult.agent_retro`.
  - `TestFailure` for `QAResult.test_failures`.
  - `DebtItem` for `CodeReviewResult.debt_items`.
  - `FixGeneratorResult`, `FixIssueDraft`, and `FixDebtItem` for
    `generate_fix_issues`.
- Keep runtime dictionaries at the API boundary by relying on `model_dump()`.
  Existing code that calls `.get()` on returned dicts should continue to work.
- Do not mass-convert unrelated pipeline `list[dict]` fields unless a failing
  Codex schema test proves they are part of this failure path.

#### Refactor

- Replace mutable defaults in touched Pydantic models with
  `Field(default_factory=...)` while preserving serialized output.
- Keep the strictifier helper narrow and unit-tested; avoid broad schema
  rewriting outside Codex.

### Success Criteria

Automated:

- `uv run pytest tests/test_codex_harness_patch.py -k 'strict_json_schema or role_result_schemas'`
- `uv run pytest tests/test_baml_bridge.py -k 'dict_bearing_schema or roundtrips'`

Manual:

- Inspect generated `.agentfield_schema.json` from a Codex harness call and
  confirm no `additionalProperties: true` remains.

## Behavior 2: Codex CLI Errors Surface Stdout JSONL Details

### Test Specification

Given Codex exits nonzero and stderr contains only banner noise, when stdout
JSONL contains an error event, then the returned `RawResult.error_message`
contains the JSONL error detail.

Edge cases:

- stderr banner plus structured stdout error.
- stderr real error plus structured stdout detail.
- stdout contains no useful error detail; existing stderr-based message remains.
- git metadata errors still receive the existing actionable hint.

### TDD Cycle

#### Red: Write Failing Tests

File: `tests/test_codex_harness_patch.py`

Add a top-level helper test first so the nested Codex provider replacement is
not hard to exercise:

```python
def test_codex_error_detail_prefers_jsonl_error_over_stdin_banner():
    records = [
        {"type": "event_msg", "message": "Reading prompt from stdin..."},
        {"type": "error", "message": "invalid_json_schema: additionalProperties must be false"},
    ]

    detail = _codex_error_detail(
        stderr="Reading prompt from stdin...\n",
        records=records,
        stdout="",
    )

    assert "invalid_json_schema" in detail
    assert "additionalProperties" in detail
```

Add a second test that monkeypatches `_run_codex_cli_with_stdin` and verifies
`execute_with_native_structured_output` returns `RawResult.is_error=True` with
the same detail in `error_message`.

#### Green: Minimal Implementation

File: `swe_af/runtime/codex_harness_patch.py`

- Extract a testable `_codex_error_detail(stderr, records, stdout) -> str`.
- Search JSONL records recursively for likely error keys:
  `error`, `message`, `msg`, `details`, `detail`, `reason`.
- Ignore known banner-only text when a stronger stdout detail exists.
- On nonzero exit, use:
  - `detail = _codex_error_detail(stderr_clean, records, stdout)`
  - `base_error = detail or stderr_clean or "Codex CLI failed"`
  - `_augment_codex_error_message(base_error, f"{stderr_clean}\n{detail}")`

#### Refactor

- Keep the existing stdout parsing and output-file fallback intact.
- Do not alter Claude auth classification or stdout capture in the same commit.

### Success Criteria

Automated:

- `uv run pytest tests/test_codex_harness_patch.py -k 'codex_error or git_metadata or claude_auth'`

Manual:

- In a failing Codex build log, `Coder agent failed` should include the concrete
  Codex/OpenAI schema or CLI error, not just `Reading prompt from stdin...`.

## Behavior 3: Reviewer Harness Failure Does Not Raise UnboundLocalError

### Test Specification

Given `router.harness` raises inside `run_code_reviewer`, when the fallback
result is returned, then it is not approved, is not blocking, includes the
original exception text, and does not raise `UnboundLocalError`.

### TDD Cycle

#### Red: Write Failing Test

File: `tests/test_execution_agents_runtime.py` (new) or
`tests/test_runtime_provider_routing.py` if the project prefers keeping runtime
agent routing tests together.

```python
@pytest.mark.asyncio
async def test_code_reviewer_fallback_preserves_exception_text(monkeypatch, tmp_path):
    from swe_af.reasoners import execution_agents

    async def boom(*args, **kwargs):
        raise RuntimeError("schema rejected")

    monkeypatch.setattr(execution_agents.router, "harness", boom)

    result = await execution_agents.run_code_reviewer(
        worktree_path=str(tmp_path),
        coder_result={"files_changed": []},
        issue={"name": "ISSUE-1", "title": "T"},
        ai_provider="codex",
    )

    assert result["approved"] is False
    assert result["blocking"] is False
    assert "schema rejected" in result["summary"]
```

This should currently fail with `UnboundLocalError`.

#### Green: Minimal Implementation

File: `swe_af/reasoners/execution_agents.py`

- Introduce `error_text = ""` before the `try`.
- In `except Exception as exc`, set `error_text = str(exc)`.
- Use `error_text or "unknown error"` in the fallback summary.

#### Refactor

- Apply the same pattern only to nearby fallbacks if tests show the same
  out-of-scope exception-variable bug. Do not refactor all reasoners.

### Success Criteria

Automated:

- `uv run pytest tests/test_execution_agents_runtime.py -k reviewer`
- `uv run pytest tests/test_coding_loop.py -k reviewer_crash`

Manual:

- A reviewer crash in the build log remains a fix/no-verdict decision instead
  of becoming a secondary Python exception.

## Behavior 4: QA Synthesizer Uses Codex Harness Without Changing Claude

### Test Specification

Given the QA synthesizer is invoked with `ai_provider="codex"`, when it calls a
model, then it uses `router.harness` with `provider="codex"` and the raw Codex
model id. Given it is invoked with `ai_provider="claude"`, it keeps the current
`router.ai` path.

Edge cases:

- Codex parsed result returns a `QASynthesisResult`.
- Codex harness raises; existing safe fallback still decides from raw QA/review.
- Claude path calls `router.ai` with `system=QA_SYNTHESIZER_SYSTEM_PROMPT`.
- `permission_mode` and `cwd` propagate to the Codex harness path.

### TDD Cycle

#### Red: Write Failing Tests

File: `tests/test_execution_agents_runtime.py`

```python
@pytest.mark.asyncio
async def test_qa_synthesizer_codex_uses_harness_not_router_ai(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from swe_af.execution.schemas import QASynthesisResult
    from swe_af.reasoners import execution_agents

    calls = {}

    async def fake_harness(*args, **kwargs):
        calls["harness"] = kwargs
        return SimpleNamespace(
            parsed=QASynthesisResult(action="approve", summary="ok", stuck=False)
        )

    async def fail_ai(*args, **kwargs):
        raise AssertionError("router.ai must not be used for codex synthesizer")

    monkeypatch.setattr(execution_agents.router, "harness", fake_harness)
    monkeypatch.setattr(execution_agents.router, "ai", fail_ai)

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


@pytest.mark.asyncio
async def test_qa_synthesizer_claude_keeps_router_ai(monkeypatch):
    ...
```

The first test should fail today because `router.ai` is called.

#### Green: Minimal Implementation

File: `swe_af/reasoners/execution_agents.py`

- Branch inside `run_qa_synthesizer`:
  - If `runtime_to_harness_adapter(ai_provider) == "codex"`, call
    `router.harness` with `schema=QASynthesisResult`, `provider="codex"`,
    `model=model`, `cwd=worktree_path or artifacts_dir or "."`,
    `permission_mode=permission_mode or None`, and no write/edit/bash tools.
  - Otherwise keep the existing `router.ai` call.
- Run `check_fatal_harness_error(result)` only on the harness path.
- Preserve the current fallback decision logic.

#### Refactor

- Extract the shared parsed-result handling to a small local helper only if it
  avoids duplication without obscuring the provider branch.

### Success Criteria

Automated:

- `uv run pytest tests/test_execution_agents_runtime.py -k qa_synthesizer`
- `uv run pytest tests/test_runtime_provider_routing.py`

Manual:

- Codex flagged-path builds should no longer log LiteLLM
  `Invalid model spec: 'gpt-5.4-mini'`.
- Claude builds should still use the previously successful synthesizer path.

## Behavior 5: DB-Backed Deterministic Checks Fail As Environment Preconditions

### Test Specification

Given a planned deterministic check requires a test database, when
`DATABASE_URL_TEST` is absent, then the coding loop reports an environment
precondition failure before invoking the coder. Given `DATABASE_URL_TEST` is
present, the normal deterministic gate runs the command through the existing
runner.

The preflight should detect only explicit DB-backed checks, for example:

- Command includes `REQUIRE_TEST_DB=1`.
- Command references `DATABASE_URL_TEST`.

### TDD Cycle

#### Red: Write Failing Tests

File: `tests/test_check_discovery.py`

```python
def test_planned_check_declares_database_requirement():
    from swe_af.execution.deterministic_check import check_requires_test_db

    assert check_requires_test_db("REQUIRE_TEST_DB=1 npm run test:integration")
    assert check_requires_test_db("DATABASE_URL_TEST=postgres://x npm test")
    assert not check_requires_test_db("npm test")
```

File: `tests/test_coding_loop_deterministic_gate.py`

```python
def test_missing_db_precondition_fails_before_coder(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL_TEST", raising=False)
    call_fn = _RecordingCallFn(reviewer_approve=True)
    runner = _SpyRunner([_completed(returncode=0)])
    config = ExecutionConfig(max_coding_iterations=5, agent_timeout_seconds=30)
    issue = _issue(
        verification=_planned("REQUIRE_TEST_DB=1 npm run test:integration")
    )

    result = _run(run_coding_loop(
        issue,
        _dag_state(str(tmp_path)),
        call_fn,
        "node",
        config,
        local_runner=runner,
    ))

    assert result.outcome == IssueOutcome.FAILED_UNRECOVERABLE
    assert "DATABASE_URL_TEST" in result.error_message
    assert call_fn.labels == []
    assert runner.calls == []
```

Add a companion test with `monkeypatch.setenv("DATABASE_URL_TEST", "...")` that
asserts the existing runner path is used.

#### Green: Minimal Implementation

Files:

- `swe_af/execution/deterministic_check.py`
- `swe_af/execution/coding_loop.py`

Implementation direction:

- Add `check_requires_test_db(command: str) -> bool`.
- Add a pure preflight helper, for example:
  `deterministic_preflight(issue, worktree_path, env=os.environ) -> str | None`.
  Return a human-readable error string when a resolved check needs DB access and
  `DATABASE_URL_TEST` is missing.
- In `run_coding_loop`, before the first coder call for an issue, run the
  preflight when deterministic checks are enabled. If it returns an error,
  return `IssueResult(outcome=FAILED_UNRECOVERABLE, error_message=...)` without
  invoking `call_fn` or `local_runner`.
- Keep the existing post-coder deterministic gate for real code/test failures.

#### Refactor

- Keep DB precondition detection explicit and conservative. Do not infer DB
  needs from arbitrary npm script names.
- Document in the error text that this is a build-node environment problem, not
  coder feedback.

### Success Criteria

Automated:

- `uv run pytest tests/test_check_discovery.py -k database`
- `uv run pytest tests/test_coding_loop_deterministic_gate.py -k db_precondition`

Manual:

- A build node lacking `DATABASE_URL_TEST` fails the issue before any `run_coder`
  call and prints a clear remediation.

## Behavior 6: Compose Propagates Optional Test DB Configuration

### Test Specification

Given a compose-launched SWE-AF build node, when `DATABASE_URL_TEST` is set in
the host environment, then the node receives it. Given target DBs are exposed on
the host, the node can resolve `host.docker.internal`.

### TDD Cycle

#### Red: Write Failing Tests

File: `tests/fast/test_docker_config.py`

Add tests for `docker-compose.yml`:

```python
def test_database_url_test_env_in_build_nodes():
    expected = "DATABASE_URL_TEST=${DATABASE_URL_TEST:-}"
    assert expected in _service_environment("swe-agent")
    assert expected in _service_environment("swe-fast")


def test_host_gateway_available_for_db_backed_checks():
    compose = load_docker_compose()
    for service in ("swe-agent", "swe-fast"):
        assert "host.docker.internal:host-gateway" in compose["services"][service].get("extra_hosts", [])
```

If adding support to `docker-compose.local.yml`, add a small helper that loads
that file too and assert the same `DATABASE_URL_TEST` propagation for its
`swe-agent`.

#### Green: Minimal Implementation

Files:

- `docker-compose.yml`
- `docker-compose.local.yml`
- `docs/BUILD_RUNBOOK.md`

Implementation direction:

- Add `DATABASE_URL_TEST=${DATABASE_URL_TEST:-}` to build-node environments.
- Add `extra_hosts: ["host.docker.internal:host-gateway"]` to build-node
  services that may run target DB-backed checks.
- Document the operator contract in `docs/BUILD_RUNBOOK.md`:
  - DB-backed target checks require a throwaway test DB.
  - `DATABASE_URL_TEST` must point to a DB reachable from the build node.
  - SWE-AF does not hardcode target-project DB credentials or external Docker
    network names.
  - For databases in another compose project, expose the test DB on the host or
    attach the build node to that external network explicitly.

#### Refactor

- Avoid duplicating large compose parsing helpers. Reuse existing
  `tests/fast/test_docker_config.py` patterns.

### Success Criteria

Automated:

- `uv run pytest tests/fast/test_docker_config.py -k 'database_url_test or host_gateway'`

Manual:

- `docker compose config` shows `DATABASE_URL_TEST` and `host.docker.internal`
  support on build nodes.

## Behavior 7: Claude Compatibility Stays Green

### Test Specification

Given the Claude runtime is currently completing tasks, when the Codex fixes are
applied, then Claude defaults and output routing remain unchanged.

### TDD Cycle

#### Red: Add Guard Tests Before Refactors

Files:

- `tests/test_runtime_provider_routing.py`
- `tests/test_model_config.py`
- `tests/test_codex_harness_patch.py`

Add or strengthen tests:

```python
def test_runtime_to_harness_adapter_preserves_claude_code():
    assert runtime_to_harness_adapter("claude_code") == "claude-code"


def test_claude_code_defaults_stay_claude():
    cfg = ExecutionConfig(runtime="claude_code")
    assert cfg.ai_provider == "claude"
    assert cfg.coder_model == "sonnet"
    assert cfg.qa_synthesizer_model == "haiku"


def test_claude_active_provider_keeps_agentfield_write_tool_suffix(tmp_path):
    ...
```

Some of these assertions already exist in adjacent form; keep duplication low
by extending existing tests where possible.

#### Green: Minimal Implementation

- The implementation should make these tests pass without special casing beyond
  the explicit Codex branch in `run_qa_synthesizer`.

#### Refactor

- If any shared helper is introduced for provider routing, keep it in
  `swe_af/runtime/providers.py` and use existing names. Do not reintroduce
  inline provider string mappings.

### Success Criteria

Automated:

- `uv run pytest tests/test_runtime_provider_routing.py tests/test_model_config.py tests/test_codex_harness_patch.py`

Manual:

- A Claude build payload using `runtime:"claude_code"` still reaches the
  existing Claude Code harness path and does not receive Codex final-JSON
  instructions.

## Integration Verification

Run after all behavior-level tests pass:

```bash
uv run pytest \
  tests/test_codex_harness_patch.py \
  tests/test_execution_agents_runtime.py \
  tests/test_check_discovery.py \
  tests/test_coding_loop_deterministic_gate.py \
  tests/test_runtime_provider_routing.py \
  tests/test_model_config.py \
  tests/fast/test_docker_config.py
```

If time allows, run a broader smoke:

```bash
uv run pytest tests/test_coding_loop.py tests/test_baml_bridge.py tests/test_local_check.py
```

Manual build validation:

1. Launch a Codex build-node stack with `SWE_DEFAULT_RUNTIME=codex`.
2. Submit a small build that exercises `run_coder` and `run_code_reviewer` but
   does not require a target DB. Confirm Codex reaches real file edits or
   reports a concrete schema/CLI error.
3. Submit or resume a DB-backed target check without `DATABASE_URL_TEST`.
   Confirm it fails before the first coder attempt with an environment
   precondition message.
4. Set `DATABASE_URL_TEST` to a reachable throwaway DB and rerun the same scoped
   DB-backed check. Confirm the deterministic gate runs the command instead of
   preflight-blocking.
5. Run a Claude build or resume path with `runtime:"claude_code"` and verify the
   existing successful behavior still holds.

## Implementation Order

1. Add Claude compatibility guard tests.
2. Add schema strictification tests and fix schema normalization/typed result
   models.
3. Add Codex error-detail tests and fix nonzero-exit error extraction.
4. Add reviewer fallback test and fix exception text capture.
5. Add Codex/Claude QA synthesizer routing tests and implement the Codex-only
   harness branch.
6. Add deterministic DB preflight tests and implement pre-coder environment
   blocking.
7. Add compose/runbook tests and config/docs updates.
8. Run the integration verification command set.

## References

- Debug research:
  `thoughts/searchable/shared/research/2026-06-26-codex-coder-empty-cv-build-debug.md`
- Active beads context: `SWE-AF-x04`
- Codex harness patch: `swe_af/runtime/codex_harness_patch.py`
- Execution agents: `swe_af/reasoners/execution_agents.py`
- Coding loop: `swe_af/execution/coding_loop.py`
- Deterministic gate: `swe_af/execution/deterministic_check.py`
- Runtime/model config: `swe_af/execution/schemas.py`
- Provider mapping: `swe_af/runtime/providers.py`
- Docker config tests: `tests/fast/test_docker_config.py`
