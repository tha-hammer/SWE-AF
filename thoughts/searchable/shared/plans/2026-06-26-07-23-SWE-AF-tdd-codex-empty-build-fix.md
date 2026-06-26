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

## Review Resolution

This plan incorporates the review in
`thoughts/searchable/shared/plans/2026-06-26-07-23-SWE-AF-tdd-codex-empty-build-fix-REVIEW.md`.
The review found five implementation-blocking gaps; this revised plan addresses
all of them before the original Codex fixes:

- Codex structured-output files must be invocation-scoped so flagged QA and
  reviewer calls can run concurrently in the same worktree without racing on
  `.agentfield_schema.json` or `.agentfield_output.json`.
- DB preflight must distinguish a command that merely references
  `DATABASE_URL_TEST` from a command that supplies it inline, e.g.
  `DATABASE_URL_TEST=postgres://x npm test`.
- Fatal harness errors raised by concurrent flagged-path QA/reviewer calls must
  remain fatal, not be converted into ordinary fix-loop feedback.
- `FixGeneratorResult` and all new nested result models must be module-level,
  typed, defaulted contracts before tests import or assert against them.
- Codex CLI timeout handling must kill and reap the child process before
  returning a timeout result.

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
- The Codex structured-output patch uses fixed cwd-relative files
  `.agentfield_schema.json` and `.agentfield_output.json`. The flagged path runs
  QA and reviewer concurrently in the same worktree, so two Codex harness calls
  can overwrite each other's schema or output file before either call finishes.
- `execute_with_native_structured_output` applies `asyncio.wait_for` outside the
  subprocess helper. On timeout it returns a timeout `RawResult` but does not
  kill and reap the still-running Codex child process.
- `_run_flagged_path` uses `asyncio.gather(..., return_exceptions=True)` for QA
  and reviewer. That converts `FatalHarnessError` into an ordinary value, so
  auth/config/environment failures can become normal fix-loop feedback instead
  of aborting as fatal.
- `docker-compose.yml` now includes a throwaway `build-db` default for
  `swe-agent`, and `docker-compose.local.yml` has the same pattern for its
  `swe-agent`. The plan must preserve or deliberately replace that contract.
  Today `swe-fast` still lacks matching `DATABASE_URL_TEST` and
  `host.docker.internal` wiring, while `docs/BUILD_RUNBOOK.md` claims both build
  nodes receive the DB URL.

## Desired End State

Codex builds should either reach the real coder/reviewer/QA/fix agent work or
fail early with an explicit environment/configuration error. They should not
collapse into five quick fallback iterations with no files changed and no useful
error.

### Observable Behaviors

- Given a Codex-native schema built from coding-loop role outputs, when it is
  strictified, then it contains no `additionalProperties: true` and no bare
  untyped schema branches.
- Given two Codex harness calls run concurrently in the same worktree, when they
  build schema/output files, then each call uses invocation-scoped paths and
  cannot read another call's schema or output.
- Given Codex exits nonzero with useful error content in JSONL stdout and only a
  banner on stderr, when AgentField receives the result, then the error message
  includes the structured stdout error detail.
- Given Codex CLI times out, when SWE-AF returns a timeout result, then the
  child process has been killed and reaped.
- Given the code reviewer harness raises, when `run_code_reviewer` falls back,
  then it returns a not-approved, non-blocking no-verdict result containing the
  original exception text and does not raise `UnboundLocalError`.
- Given flagged-path QA or reviewer raises `FatalHarnessError`, when
  `_run_flagged_path` gathers concurrent results, then the fatal error is
  re-raised instead of converted into an ordinary QA/review result.
- Given `run_qa_synthesizer(... ai_provider="codex", model="gpt-5.4-mini")`,
  when it invokes the model, then it uses the Codex harness adapter rather than
  `router.ai`/LiteLLM.
- Given `run_qa_synthesizer(... ai_provider="claude")`, when it invokes the
  model, then it keeps the existing `router.ai` path so the successful Claude
  codepath is not perturbed.
- Given a planned deterministic command requires a test DB, lacks an inline
  `DATABASE_URL_TEST=...` assignment, and the process environment lacks
  `DATABASE_URL_TEST`, when the coding loop starts or resumes an issue, then it
  fails before spending a coder attempt and reports an environment precondition
  failure instead of feeding the DB connection error back to the coder.
- Given compose-based build nodes are used for DB-backed target checks, when the
  operator relies on the repo's default throwaway `build-db` or overrides
  `DATABASE_URL_TEST`, then `swe-agent` and `swe-fast` receive the same DB
  contract and can resolve `host.docker.internal` for host-exposed DBs.

## What We're Not Doing

- Not implementing the Contract View feature itself.
- Not changing the Claude default runtime, model defaults, or Claude harness
  Write-tool output contract.
- Not replacing AgentField's provider stack.
- Not weakening, skipping, or auto-greenlighting DB-backed integration tests.
- Not hardcoding target-project schemas or production database credentials into
  SWE-AF. Compose may keep overrideable throwaway `build-db` defaults, but the
  contract must be documented as a generic build-node test DB and overridable by
  environment.
- Not making live OpenAI, Claude, or Codex calls in automated unit tests.

## Testing Strategy

- Framework: `pytest` with `pytest-asyncio` (`pyproject.toml` already sets
  `asyncio_mode = "auto"`).
- Test types:
  - Unit tests for invocation-scoped Codex schema/output paths and subprocess
    timeout cleanup.
  - Unit tests for schema strictification and Codex error extraction.
  - Async unit tests for execution-agent routing and fallbacks.
  - Functional coding-loop tests for flagged-path fatal-error propagation.
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

## Behavior 0: Codex Structured-Output Files Are Invocation-Scoped

### Test Specification

Given two Codex harness calls run concurrently in the same cwd, when each call
builds its schema file and invokes `codex exec --output-schema`, then each call
uses a unique schema path and a unique output path. Neither call can overwrite or
read the other's `.agentfield_schema*.json` or `.agentfield_output*.json` file.

Edge cases:

- Two provider-context calls in the same asyncio event loop and same cwd.
- Non-Codex providers still use AgentField's original Write-tool output suffix.
- Codex output files are cleaned up or overwritten only within their own
  invocation scope.
- Existing manual inspection remains possible because generated paths have a
  recognizable `.agentfield_schema.<token>.json` /
  `.agentfield_output.<token>.json` shape.

### TDD Cycle

#### Red: Write Failing Tests

File: `tests/test_codex_harness_patch.py`

Add tests:

```python
def test_codex_schema_output_paths_are_invocation_scoped(tmp_path):
    from agentfield.harness import _schema

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
```

Add an async test that monkeypatches `_run_codex_cli_with_stdin`, invokes the
patched Codex provider twice with the same cwd via `asyncio.gather`, and asserts
the two recorded command lines contain different `--output-schema` and
`--output-last-message` paths.

#### Green: Minimal Implementation

File: `swe_af/runtime/codex_harness_patch.py`

- Add a small `CodexInvocationPaths` dataclass with `schema_path` and
  `output_path`.
- Add a `ContextVar[CodexInvocationPaths | None]` that is set for the duration
  of each Codex provider execution.
- Add small private helpers used by tests and the harness wrapper:
  `_begin_codex_invocation_paths(cwd)`, `_current_codex_invocation_paths()`,
  and `_reset_codex_invocation_paths(token)`.
- Generate paths under the same cwd with an invocation token:
  `.agentfield_schema.<token>.json` and `.agentfield_output.<token>.json`.
- In `_harness_with_provider_context`, when `provider == "codex"` and a string
  `cwd` is available, set both `active_provider` and the invocation-path
  context for the whole `_orig_agent_harness(...)` call. This is the load-bearing
  point because prompt suffix construction happens inside AgentField harness
  before `CodexProvider.execute` reads the schema path.
- In `build_prompt_suffix_with_schema_file`, use the current invocation paths
  when present instead of `_schema.get_schema_path(cwd)`.
- In `execute_with_native_structured_output`, use the current invocation paths
  for `--output-schema`, `--output-last-message`, and output-file fallback.
  If a Codex provider is invoked directly without the harness wrapper, create a
  local invocation context before checking paths.
- Keep the old fixed filenames as fallback only when no invocation context is
  present, so non-Codex and low-level tests remain debuggable.

#### Refactor

- Keep invocation path state local to the Codex patch. Do not change
  AgentField's upstream `_schema` helpers globally.
- Prefer a short token such as `uuid.uuid4().hex[:12]` so filenames stay
  inspectable in build logs.

### Success Criteria

Automated:

- `uv run pytest tests/test_codex_harness_patch.py -k 'invocation_scoped or prompt_suffix'`
- `uv run pytest tests/test_coding_loop.py -k flagged`

Manual:

- In a flagged Codex build, QA and reviewer logs show distinct
  `.agentfield_schema.<token>.json` and `.agentfield_output.<token>.json` paths
  even when both agents run in the same worktree.

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
- Fix generator schema after moving the local `FixGeneratorOutput` model to the
  module-level public `FixGeneratorResult` schema.
- Non-default nested output content round-trips through BAML instead of being
  silently omitted as an unmappable defaulted bare dict.

### TDD Cycle

#### Red: Write Failing Tests

File: `tests/test_codex_harness_patch.py`

Add tests:

```python
def test_fix_generator_result_is_public_schema_contract():
    from swe_af.execution.schemas import FixGeneratorResult

    assert FixGeneratorResult.model_json_schema()["type"] == "object"


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
`QAResult.test_failures[]`, and `CodeReviewResult.debt_items[]`. If
`FixGeneratorResult` has not been moved to `swe_af.execution.schemas`, the first
test should fail on that public-contract gap before schema strictness assertions
run.

File: `tests/test_baml_bridge.py`

Add non-default round-trip coverage:

```python
def test_coder_result_roundtrips_with_agent_retro_content():
    from swe_af.execution.schemas import AgentRetro, CoderResult

    inst = CoderResult(
        files_changed=["x.py"],
        summary="did",
        agent_retro=AgentRetro(
            worked_well=["small tests"],
            got_stuck_on=["schema"],
            tips_for_next_time=["check output schema first"],
        ),
    )

    assert _roundtrip(CoderResult, inst.model_dump()) == inst


def test_qa_and_review_nested_items_roundtrip_non_default_content():
    from swe_af.execution.schemas import CodeReviewResult, DebtItem, QAResult, TestFailure

    qa = QAResult(
        passed=False,
        test_failures=[
            TestFailure(
                test_name="test_x",
                file="tests/test_x.py",
                error="boom",
                expected="green",
                actual="red",
            )
        ],
    )
    review = CodeReviewResult(
        approved=False,
        debt_items=[
            DebtItem(
                severity="should_fix",
                title="Missing edge case",
                file_path="x.py",
                description="Cover empty input",
            )
        ],
    )

    assert _roundtrip(QAResult, qa.model_dump()) == qa
    assert _roundtrip(CodeReviewResult, review.model_dump()) == review
```

#### Green: Minimal Implementation

Files:

- `swe_af/runtime/codex_harness_patch.py`
- `swe_af/execution/schemas.py`
- `swe_af/reasoners/execution_agents.py`
- `tests/test_baml_bridge.py` if assertions mention the old bare dict fields.

Implementation direction:

- Add a small recursive helper used by `_codex_strict_json_schema` that closes
  any remaining object schema with `additionalProperties is True`.
- Add typed nested models in `swe_af/execution/schemas.py` with explicit
  defaults:
  - `AgentRetro`: `worked_well: list[str] = Field(default_factory=list)`,
    `got_stuck_on: list[str] = Field(default_factory=list)`,
    `tips_for_next_time: list[str] = Field(default_factory=list)`.
  - `TestFailure`: `test_name: str = ""`, `file: str = ""`,
    `error: str = ""`, `expected: str = ""`, `actual: str = ""`.
  - `DebtItem`: `severity: str = ""`, `title: str = ""`,
    `file_path: str = ""`, `description: str = ""`.
  - `FixIssueDraft`: `name: str = ""`, `title: str = ""`,
    `description: str = ""`,
    `acceptance_criteria: list[str] = Field(default_factory=list)`,
    `files_to_modify: list[str] = Field(default_factory=list)`,
    `target_repo: str = ""`.
  - `FixDebtItem`: `criterion: str = ""`, `reason: str = ""`,
    `severity: str = "high"`.
  - `FixGeneratorResult`: `fix_issues: list[FixIssueDraft]`,
    `debt_items: list[FixDebtItem]`, and `summary: str = ""`, with list
    fields using `Field(default_factory=list)`.
- Update `CoderResult.agent_retro`,
  `QAResult.test_failures`, `CodeReviewResult.debt_items`, and
  `generate_fix_issues(... schema=FixGeneratorResult)` to use those models.
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

Add a second test that monkeypatches `_run_codex_cli_with_stdin`, calls
`apply_codex_harness_patch()`, instantiates the patched AgentField
`CodexProvider`, and verifies `provider.execute(...)` returns
`RawResult.is_error=True` with the same detail in `error_message`. Do not import
`execute_with_native_structured_output` directly unless the implementation first
extracts it to a module-level helper; it is currently a nested replacement
installed onto `CodexProvider.execute`.

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

## Behavior 3: Codex CLI Timeout Kills And Reaps Child Process

### Test Specification

Given a Codex CLI subprocess exceeds the configured timeout, when SWE-AF returns
a timeout `RawResult`, then the child process has been killed and awaited. No
timed-out Codex process should continue writing to the same worktree or
invocation-scoped output file after the harness reports failure.

Edge cases:

- Timeout while the process is still running.
- Process exits between cancellation and `kill()`.
- Kill/await raises `ProcessLookupError`; the timeout result still returns.
- Existing `FileNotFoundError` and non-timeout nonzero-exit behavior is
  unchanged.

### TDD Cycle

#### Red: Write Failing Tests

File: `tests/test_codex_harness_patch.py`

Add a testable helper around subprocess execution:

```python
@pytest.mark.asyncio
async def test_codex_cli_timeout_kills_and_reaps_child(monkeypatch):
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
```

If the implementation keeps `_run_codex_cli_with_stdin` as the public helper,
adapt the test names to the final helper shape, but preserve the observable
contract: timeout causes kill and wait.

#### Green: Minimal Implementation

File: `swe_af/runtime/codex_harness_patch.py`

- Move timeout handling into the subprocess helper so the helper owns the child
  process lifecycle.
- Return a small structured result, for example:
  `CodexCLIResult(stdout: str, stderr: str, returncode: int, timed_out: bool)`.
- On timeout:
  - cancel/exit the `communicate()` wait,
  - if the process is still running, call `proc.kill()`,
  - always `await proc.wait()` with `ProcessLookupError` tolerated,
  - return `timed_out=True`, `returncode=-1`, and any captured output if
    available.
- Preserve `FileNotFoundError` handling in `execute_with_native_structured_output`.

#### Refactor

- Keep child-process cleanup isolated in the Codex helper. Do not alter Claude
  subprocess transport behavior in this change.

### Success Criteria

Automated:

- `uv run pytest tests/test_codex_harness_patch.py -k 'timeout or codex_error'`

Manual:

- A timed-out Codex build logs `Codex CLI timed out` and `pgrep -af 'codex exec'`
  does not show the timed-out child still running for the worktree.

## Behavior 4: Reviewer Harness Failure Does Not Raise UnboundLocalError

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

## Behavior 5: Flagged Path Propagates Fatal Harness Errors

### Test Specification

Given flagged-path QA or reviewer raises `FatalHarnessError`, when
`_run_flagged_path` awaits the concurrent QA/reviewer work, then the fatal error
is re-raised. It must not be converted into a normal `{"passed": False}` or
`{"approved": False}` feedback result.

Edge cases:

- QA raises `FatalHarnessError`; reviewer returns normally.
- Reviewer raises `FatalHarnessError`; QA returns normally.
- Both raise, and at least one fatal error is propagated.
- Non-fatal exceptions continue to use the existing safe fallback behavior.

### TDD Cycle

#### Red: Write Failing Tests

File: `tests/test_coding_loop.py` or `tests/test_execution_agents_runtime.py`

Add tests:

```python
@pytest.mark.asyncio
async def test_flagged_path_propagates_fatal_harness_error_from_qa(tmp_path):
    from swe_af.execution.coding_loop import _run_flagged_path
    from swe_af.execution.fatal_error import FatalHarnessError
    from swe_af.execution.schemas import ExecutionConfig

    def call_fn(agent_name, **kwargs):
        async def _invoke():
            if agent_name.endswith(".run_qa"):
                raise FatalHarnessError("auth failed")
            if agent_name.endswith(".run_code_reviewer"):
                return {"approved": False, "blocking": False, "summary": "no verdict"}
            return {}

        return _invoke()

    with pytest.raises(FatalHarnessError, match="auth failed"):
        await _run_flagged_path(
            call_fn=call_fn,
            node_id="node",
            worktree_path=str(tmp_path),
            coder_result={"files_changed": []},
            issue={"name": "ISSUE-1", "title": "T"},
            iteration=1,
            iteration_id="i1",
            iteration_history=[],
            project_context={},
            memory_context={},
            config=ExecutionConfig(),
            timeout=30,
            issue_name="ISSUE-1",
        )
```

Add the symmetric reviewer-fatal test.

#### Green: Minimal Implementation

File: `swe_af/execution/coding_loop.py`

- After `asyncio.gather(..., return_exceptions=True)`, inspect gathered results
  before ordinary exception fallback conversion.
- If any gathered value is `FatalHarnessError`, re-raise it immediately.
- Preserve the existing fallback conversion for non-fatal exceptions so normal
  QA/review crashes still produce no-verdict fix feedback.

#### Refactor

- Keep this handling local to `_run_flagged_path`. Do not alter the individual
  agent functions' `FatalHarnessError` behavior.

### Success Criteria

Automated:

- `uv run pytest tests/test_coding_loop.py -k fatal_harness`
- `uv run pytest tests/test_execution_agents_runtime.py -k fatal`

Manual:

- A flagged-path auth/config failure aborts the issue with the fatal error
  instead of entering another fix iteration.

## Behavior 6: QA Synthesizer Uses Codex Harness Without Changing Claude

### Test Specification

Given the QA synthesizer is invoked with `ai_provider="codex"`, when it calls a
model, then it uses `router.harness` with `provider="codex"` and the raw Codex
model id. Given it is invoked with `ai_provider="claude"`, it keeps the current
`router.ai` path.

Edge cases:

- Codex parsed result returns a `QASynthesisResult`.
- Codex harness raises; existing safe fallback still decides from raw QA/review.
- Claude path calls `router.ai` with `system=QA_SYNTHESIZER_SYSTEM_PROMPT`.
- Codex path calls `router.harness` with
  `system_prompt=QA_SYNTHESIZER_SYSTEM_PROMPT`.
- `permission_mode` and `cwd` propagate to the Codex harness path.
- Codex synthesizer gets no write/edit/bash tools.

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
    assert calls["harness"]["system_prompt"] == execution_agents.QA_SYNTHESIZER_SYSTEM_PROMPT
    assert calls["harness"].get("tools") in (None, [])


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
    `system_prompt=QA_SYNTHESIZER_SYSTEM_PROMPT`, `model=model`,
    `cwd=worktree_path or artifacts_dir or "."`,
    `permission_mode=permission_mode or None`, and `tools=[]` or omitted tools.
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

## Behavior 7: DB-Backed Deterministic Checks Fail As Environment Preconditions

### Test Specification

Given a planned deterministic check requires a test database, when neither the
command nor the environment supplies `DATABASE_URL_TEST`, then the coding loop
reports an environment precondition failure before invoking the coder. Given
`DATABASE_URL_TEST` is present in the process environment, or the command itself
assigns `DATABASE_URL_TEST=...`, the normal deterministic gate runs the command
through the existing runner.

The preflight should detect only explicit DB-backed checks, for example:

- Command includes `REQUIRE_TEST_DB=1`.
- Command references `DATABASE_URL_TEST` without assigning it inline.
- Command assigns `DATABASE_URL_TEST=postgres://...` inline; this declares and
  satisfies the DB URL precondition for that command.

### TDD Cycle

#### Red: Write Failing Tests

File: `tests/test_check_discovery.py`

```python
def test_planned_check_declares_database_requirement():
    from swe_af.execution.deterministic_check import (
        check_requires_test_db,
        command_supplies_test_db,
    )

    assert check_requires_test_db("REQUIRE_TEST_DB=1 npm run test:integration")
    assert check_requires_test_db("DATABASE_URL_TEST=postgres://x npm test")
    assert command_supplies_test_db("DATABASE_URL_TEST=postgres://x npm test")
    assert not command_supplies_test_db("REQUIRE_TEST_DB=1 npm test")
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

Add an inline-env companion test:

```python
def test_inline_db_url_precondition_runs_existing_gate(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL_TEST", raising=False)
    call_fn = _RecordingCallFn(reviewer_approve=True)
    runner = _SpyRunner([_completed(returncode=0)])
    config = ExecutionConfig(max_coding_iterations=1, agent_timeout_seconds=30)
    issue = _issue(
        verification=_planned("DATABASE_URL_TEST=postgres://x npm test")
    )

    result = _run(run_coding_loop(
        issue,
        _dag_state(str(tmp_path)),
        call_fn,
        "node",
        config,
        local_runner=runner,
    ))

    assert result.outcome == IssueOutcome.COMPLETED
    assert runner.calls
```

Add a resume companion test by seeding `_save_iteration_state(...)` and asserting
a resumed DB-required issue still preflights before the next coder call.

#### Green: Minimal Implementation

Files:

- `swe_af/execution/deterministic_check.py`
- `swe_af/execution/coding_loop.py`

Implementation direction:

- Add `check_requires_test_db(command: str) -> bool`.
- Add `command_supplies_test_db(command: str) -> bool` that recognizes explicit
  inline shell assignments such as `DATABASE_URL_TEST=postgres://x npm test`.
- Add a pure preflight helper, for example:
  `deterministic_preflight(issue, worktree_path, env: Mapping[str, str]) -> str | None`.
  Do not use `env=os.environ` as a default argument. Return a human-readable
  error string only when a resolved check needs DB access, does not supply
  `DATABASE_URL_TEST` inline, and `env` lacks `DATABASE_URL_TEST`.
- In `run_coding_loop`, before the first coder call for an issue, run the
  preflight when deterministic checks are enabled. Run it after checkpoint load
  as well, so resumed issues fail before the next coder call. If it returns an
  error, return `IssueResult(outcome=FAILED_UNRECOVERABLE, error_message=...)`
  without invoking `call_fn` or `local_runner`.
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

## Behavior 8: Compose Propagates Build-Time Test DB Configuration

### Test Specification

Given a compose-launched SWE-AF build node, when the operator relies on the
repo's default throwaway `build-db` or overrides `DATABASE_URL_TEST` from the
host environment, then both build nodes receive the same DB URL contract. Given
target DBs are exposed on the host for advanced setups, both build nodes can
resolve `host.docker.internal`.

This plan preserves the current repo direction: compose ships a generic
throwaway Postgres service named `build-db` with overrideable defaults. It does
not revert to a blank optional env var. The fix is to make `swe-fast`,
`docker-compose.local.yml`, tests, and `docs/BUILD_RUNBOOK.md` agree with that
contract.

### TDD Cycle

#### Red: Write Failing Tests

File: `tests/fast/test_docker_config.py`

Add tests for `docker-compose.yml`:

```python
def test_database_url_test_env_in_build_nodes():
    expected = (
        "DATABASE_URL_TEST=${DATABASE_URL_TEST:-"
        "postgres://cosmichr_user:password@build-db:5432/cosmichr_buildtest}"
    )
    assert expected in _service_environment("swe-agent")
    assert expected in _service_environment("swe-fast")


def test_host_gateway_available_for_db_backed_checks():
    compose = load_docker_compose()
    for service in ("swe-agent", "swe-fast"):
        assert "host.docker.internal:host-gateway" in compose["services"][service].get("extra_hosts", [])


def test_build_nodes_wait_for_build_db_when_using_default_url():
    compose = load_docker_compose()
    for service in ("swe-agent", "swe-fast"):
        depends_on = compose["services"][service].get("depends_on", {})
        assert "build-db" in depends_on
```

If adding support to `docker-compose.local.yml`, add a small helper that loads
that file too and assert the same default `DATABASE_URL_TEST`,
`host.docker.internal`, and `build-db` dependency for its `swe-agent`.

#### Green: Minimal Implementation

Files:

- `docker-compose.yml`
- `docker-compose.local.yml`
- `docs/BUILD_RUNBOOK.md`

Implementation direction:

- Preserve the current overrideable throwaway default on `swe-agent`:
  `DATABASE_URL_TEST=${DATABASE_URL_TEST:-postgres://cosmichr_user:password@build-db:5432/cosmichr_buildtest}`.
- Add the same `DATABASE_URL_TEST` value to `swe-fast`.
- Add `extra_hosts: ["host.docker.internal:host-gateway"]` to both
  `docker-compose.yml` build-node services and keep it in
  `docker-compose.local.yml`.
- Add `build-db` dependency/health gating for `swe-fast`, matching `swe-agent`,
  because the default DB URL points at the compose service.
- Document the operator contract in `docs/BUILD_RUNBOOK.md`:
  - DB-backed target checks require a throwaway test DB.
  - By default compose provides `build-db`; operators can override
    `BUILD_DB_USER`, `BUILD_DB_PASSWORD`, `BUILD_DB_NAME`, or the whole
    `DATABASE_URL_TEST`.
  - SWE-AF does not know or hardcode target-project schemas, production
    credentials, or external Docker network names.
  - For databases in another compose project, expose the test DB on the host or
    attach the build node to that external network explicitly.

#### Refactor

- Avoid duplicating large compose parsing helpers. Reuse existing
  `tests/fast/test_docker_config.py` patterns.

### Success Criteria

Automated:

- `uv run pytest tests/fast/test_docker_config.py -k 'database_url_test or host_gateway'`

Manual:

- `docker compose config` shows matching `DATABASE_URL_TEST`,
  `host.docker.internal`, and `build-db` dependency support on `swe-agent` and
  `swe-fast`.

## Behavior 9: Claude Compatibility Stays Green

### Test Specification

Given the Claude runtime is currently completing tasks, when the Codex fixes are
applied, then Claude defaults and output routing remain unchanged.

### TDD Cycle

#### Red: Add Guard Tests Before Refactors

Files:

- `tests/test_runtime_provider_routing.py`
- `tests/test_model_config.py`
- `tests/test_codex_harness_patch.py`
- `tests/fast/test_fast_init_executor_planner_verifier_routing.py`

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


def test_fast_runtime_provider_helper_uses_shared_mapping():
    import inspect
    import swe_af.fast.app as fast_app

    source = inspect.getsource(fast_app._runtime_to_provider)
    assert "runtime_to_harness_provider" in source
```

Some of these assertions already exist in adjacent form; keep duplication low
by extending existing tests where possible.

#### Green: Minimal Implementation

- The implementation should make these tests pass without special casing beyond
  the explicit Codex branch in `run_qa_synthesizer`.
- Update `swe_af/fast/app.py::_runtime_to_provider` to delegate to
  `runtime_to_harness_provider` from `swe_af.runtime.providers`, preserving the
  existing `claude_code -> claude`, `open_code -> opencode`, and
  `codex -> codex` results while removing the inline fallback mapper.

#### Refactor

- If any shared helper is introduced for provider routing, keep it in
  `swe_af/runtime/providers.py` and use existing names. Do not reintroduce
  inline provider string mappings in planner or fast-node code.

### Success Criteria

Automated:

- `uv run pytest tests/test_runtime_provider_routing.py tests/test_model_config.py tests/test_codex_harness_patch.py`
- `uv run pytest tests/fast/test_fast_init_executor_planner_verifier_routing.py -k runtime_to_provider`

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
  tests/test_coding_loop.py \
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
3. Submit a flagged-path Codex build that runs QA and reviewer concurrently.
   Confirm the two agent logs use different invocation-scoped
   `.agentfield_schema.<token>.json` and `.agentfield_output.<token>.json`
   paths.
4. Force or simulate a Codex timeout and confirm the timed-out `codex exec`
   child process is not left running.
5. Submit or resume a DB-backed target check without `DATABASE_URL_TEST` and
   without an inline `DATABASE_URL_TEST=...` assignment.
   Confirm it fails before the first coder attempt with an environment
   precondition message.
6. Set `DATABASE_URL_TEST` to a reachable throwaway DB, or provide it inline in
   the deterministic command, and rerun the same scoped DB-backed check. Confirm
   the deterministic gate runs the command instead of preflight-blocking.
7. Run a Claude build or resume path with `runtime:"claude_code"` and verify the
   existing successful behavior still holds.

## Implementation Order

1. Add Claude compatibility and fast runtime-provider guard tests.
2. Add invocation-scoped Codex schema/output path tests and implement the
   ContextVar-backed path contract.
3. Add schema strictification tests and fix schema normalization/typed result
   models, including `FixGeneratorResult` and BAML non-default round trips.
4. Add Codex error-detail tests and fix nonzero-exit error extraction.
5. Add Codex timeout cleanup tests and move timeout handling into the subprocess
   lifecycle helper.
6. Add reviewer fallback test and fix exception text capture.
7. Add flagged-path `FatalHarnessError` propagation tests and preserve fatal
   errors across `asyncio.gather`.
8. Add Codex/Claude QA synthesizer routing tests and implement the Codex-only
   harness branch with the preserved system prompt and no tools.
9. Add deterministic DB preflight tests and implement pre-coder/resume
   environment blocking without false-blocking inline `DATABASE_URL_TEST=...`.
10. Add compose/runbook tests and config/docs updates that make `swe-agent`,
    `swe-fast`, and `docker-compose.local.yml` agree on the build-db contract.
11. Run the integration verification command set.

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
