---
date: 2026-06-26
reviewer: codex (review-plan)
plan: thoughts/searchable/shared/plans/2026-06-26-07-23-SWE-AF-tdd-codex-empty-build-fix.md
codebase: /home/maceo/Dev/SWE-AF
related_issue: SWE-AF-e7e
amendment_issue: SWE-AF-llt
status: RESOLVED - all critical issues folded into the plan (2026-06-26)
---

# Plan Review Report: Codex Empty Build Recovery - REVIEW

> Resolution (2026-06-26): the plan has been amended in place. It now includes
> invocation-scoped Codex structured-output files, timeout child-process cleanup,
> flagged-path FatalHarnessError propagation, explicit typed result models with
> BAML coverage, inline DATABASE_URL_TEST handling, consistent build-db compose
> expectations, and fast-node shared runtime-provider mapping. The original
> findings are retained below as the point-in-time review of the pre-amendment
> draft.

This review checked the plan against the current repository state and the
referenced debug artifact. The plan identifies several real Codex failure
paths, but it is not ready for implementation as written: it misses one
load-bearing Codex concurrency bug and contains stale DB/compose assumptions
that would send implementers in the wrong direction.

## Review Summary

| Category | Status | Issues Found |
|----------|--------|--------------|
| Contracts | Critical | 3 critical, 2 warnings |
| Interfaces | Critical | 1 critical, 4 warnings |
| Promises | Critical | 3 critical, 2 warnings |
| Data Models | Warning | 3 warnings |
| APIs / Config | Critical | 1 critical, 2 warnings |

Approval status: Needs Major Revision. Address the critical findings before
implementation starts.

## Contract Review

### Well-Defined

- The core Codex error boundary is real: `execute_with_native_structured_output`
  parses stdout JSONL at `swe_af/runtime/codex_harness_patch.py:353` but builds
  nonzero-exit errors from stderr at `swe_af/runtime/codex_harness_patch.py:370`.
- The reviewer fallback bug is accurately identified: `run_code_reviewer`
  catches `Exception as e` at `swe_af/reasoners/execution_agents.py:1270` and
  later references `e` outside the `except` block at
  `swe_af/reasoners/execution_agents.py:1280`.
- The QA synthesizer provider boundary is precise: the current code calls
  `router.ai` unconditionally at `swe_af/reasoners/execution_agents.py:1325`,
  while the other coding-loop agents already use `runtime_to_harness_adapter`.

### Critical

- The DB preflight contract false-positives on inline environment assignment.
  The plan treats `DATABASE_URL_TEST=postgres://x npm test` as a command that
  requires host `DATABASE_URL_TEST`, but the current runner executes checks via
  `bash -c` at `swe_af/execution/deterministic_check.py:187`, where that inline
  assignment already satisfies the command. If implemented as written, the new
  preflight can block a runnable command before coder work.

- The compose DB contract conflicts with current files and the plan invariant.
  The plan says not to hardcode target DB names/credentials and expects
  `DATABASE_URL_TEST=${DATABASE_URL_TEST:-}`, but `docker-compose.yml:43`,
  `docker-compose.local.yml:31`, and `docs/BUILD_RUNBOOK.md:196` already
  default to a `build-db` URL. Meanwhile `swe-fast` still lacks the DB env in
  its `docker-compose.yml:70` environment block. The plan must choose the real
  contract: preserve the repo's build-db default and add the missing fast-node
  wiring, or deliberately revert to optional blank env and update the runbook.

- Fatal harness errors are swallowed in the flagged QA/reviewer path. Agents
  re-raise `FatalHarnessError` at `swe_af/reasoners/execution_agents.py:1186`
  and `swe_af/reasoners/execution_agents.py:1268`, but
  `asyncio.gather(..., return_exceptions=True)` at
  `swe_af/execution/coding_loop.py:428` converts them to values and the code
  handles them as ordinary QA/review failures at
  `swe_af/execution/coding_loop.py:432` and `:439`. This contradicts the plan's
  "fail early with explicit environment/configuration error" goal.

### Warnings

- DB preflight resume behavior is underspecified. The loop loads checkpoint
  state at `swe_af/execution/coding_loop.py:595` before invoking the next coder
  at `:623`; the plan should state whether a resumed issue with a DB-required
  check re-runs preflight before the resumed coder attempt.
- The preflight helper should avoid `env=os.environ` as a default argument.
  Existing deterministic helpers keep inputs explicit, e.g.
  `detect_project_commands(worktree_path)` at
  `swe_af/execution/deterministic_check.py:79` and
  `resolve_issue_commands(issue, worktree_path)` at `:109`.

## Interface Review

### Well-Defined

- `run_qa_synthesizer` already exposes the parameters needed for a Codex-only
  harness branch at `swe_af/reasoners/execution_agents.py:1289`, and the coding
  loop forwards `worktree_path`, `permission_mode`, and `ai_provider` at
  `swe_af/execution/coding_loop.py:469`.
- Shared runtime mapping exists in `swe_af/runtime/providers.py:30` and is
  covered in `tests/test_model_config.py:411`.

### Critical

- `FixGeneratorResult` is planned as a public import before it exists. The red
  test imports `FixGeneratorResult` from `swe_af.execution.schemas`, but current
  schemas only define `CoderResult`, `QAResult`, `CodeReviewResult`, and
  `QASynthesisResult` at `swe_af/execution/schemas.py:423`, `:437`, `:447`,
  and `:465`. The fix-generator schema is local inside `generate_fix_issues`
  at `swe_af/reasoners/execution_agents.py:1427`. The plan should first add a
  module-level `FixGeneratorResult` contract, or split the red test so it fails
  on schema strictness rather than import absence.

### Warnings

- The Codex error-path test names `execute_with_native_structured_output` as if
  it were importable, but the function is nested at
  `swe_af/runtime/codex_harness_patch.py:265` and installed as
  `CodexProvider.execute` at `:508`. The test plan should explicitly exercise
  the patched provider or extract a testable helper.
- The QA synthesizer Codex test should assert the no-tools contract. The plan
  requires no write/edit/bash tools, but its assertions do not check `tools`.
- The Codex QA synthesizer branch should explicitly preserve
  `QA_SYNTHESIZER_SYSTEM_PROMPT`; the current `router.ai` path passes it at
  `swe_af/reasoners/execution_agents.py:1328`.
- `swe_af/fast/app.py:49` still has an inline `_runtime_to_provider` mapper.
  If this plan touches runtime/provider mapping, it should either leave fast
  routing intentionally out of scope or amend it to use the shared provider API.

## Promise Review

### Well-Defined

- Deterministic command ordering is clear: planned checks win at
  `swe_af/execution/deterministic_check.py:130`, and manifest fallback orders
  test before build at `:134`.
- The Codex patch has an idempotent patch guard and restores `active_provider`
  in `finally` at `swe_af/runtime/codex_harness_patch.py:217` and `:457`.

### Critical

- Codex QA/reviewer parallelism can race on shared structured-output files. The
  flagged path starts QA and reviewer concurrently at
  `swe_af/execution/coding_loop.py:388` and gathers them at `:428`. Both agents
  use the same `worktree_path` as `cwd` at
  `swe_af/reasoners/execution_agents.py:1173` and `:1253`. Codex writes fixed
  `.agentfield_schema.json` and `.agentfield_output.json` files in that cwd at
  `swe_af/runtime/codex_harness_patch.py:254`, `:295`, and `:299`. One agent can
  overwrite the other's schema/output file before the CLI uses or reads it.

- Codex CLI timeout has no child-process cleanup. The subprocess is created in
  `_run_codex_cli_with_stdin` at `swe_af/runtime/codex_harness_patch.py:201`
  and awaited at `:209`; the timeout wrapper is outside that helper at `:313`.
  On timeout, the handler at `:337` returns an error result without killing or
  reaping the child process.

- Fatal harness errors in flagged QA/reviewer concurrency are not propagated,
  as noted in Contract Review. This is also a promise violation: non-retryable
  failures no longer stay non-retryable in the flagged path.

### Warnings

- The plan should add a concrete test for the Codex structured-output race:
  either make Codex schema/output paths invocation-scoped or serialize the
  Codex flagged QA/reviewer path.
- The manual validation should include a flagged-path Codex build, not only a
  default reviewer-only build, because the race occurs only when QA and reviewer
  run concurrently in the same worktree.

## Data Model Review

### Well-Defined

- The strict schema target is real and scoped. Current role result schemas have
  bare dict/list-of-dict fields at `swe_af/execution/schemas.py:433`, `:442`,
  and `:453`, while `_codex_strict_json_schema` only closes object schemas with
  `properties` today at `swe_af/runtime/codex_harness_patch.py:122`.
- Keeping runtime dictionaries at the API boundary through `model_dump()` is the
  right compatibility direction. Existing consumers call `.get()` on dumped
  dict items, e.g. `swe_af/execution/coding_loop.py:840`.

### Warnings

- `AgentRetro` is named but not schema-complete. The prompt only says
  "`agent_retro`: briefly note what worked well..." at `swe_af/prompts/coder.py:135`,
  while current `agent_retro` is a bare dict at `swe_af/execution/schemas.py:433`.
  Define exact fields and defaults before implementation.
- `TestFailure`, `DebtItem`, `FixIssueDraft`, and `FixDebtItem` need exact
  optional/default semantics. Current consumers tolerate partial dicts via
  `.get(...)`; new Pydantic nested models can accidentally reject partial agent
  output unless defaults are explicit.
- BAML coverage should expand. Existing tests in `tests/test_baml_bridge.py:108`
  rely on omitted/restored defaulted bare dict fields. Once these fields become
  typed nested models, add non-default round-trip tests for `agent_retro`,
  `test_failures`, and `debt_items`.

## API / Config Review

### Well-Defined

- The external AgentField API surface is not part of this change. The app nodes
  still construct `Agent(... version="1.0.0", api_key=...)` in `swe_af/app.py`
  and `swe_af/fast/app.py`.
- Existing Codex runtime/model config tests already cover the default runtime
  and provider mapping in `tests/test_model_config.py`.

### Critical

- The compose/runbook API is stale in the plan. The plan's current-state claim
  that compose does not pass `DATABASE_URL_TEST` is no longer true for
  `swe-agent`, but remains true for `swe-fast`. The test expectation in the plan
  should match the intended current contract rather than the old one.

### Warnings

- The plan should update `docs/BUILD_RUNBOOK.md` consistently with whichever DB
  env contract it chooses. Current docs claim both build nodes receive the DB URL
  at `docs/BUILD_RUNBOOK.md:191`, but `swe-fast` does not.
- Add `extra_hosts` only if the intended contract includes host-exposed DBs. If
  the repo keeps `build-db` as the default, `host.docker.internal` support is an
  optional operator path, not the primary compose path.

## Critical Issues To Address Before Implementation

1. Codex structured-output file race in flagged QA/reviewer path.
   Impact: Codex can still produce schema errors, fallback output, or empty
   results even after the planned schema/routing fixes.
   Recommendation: add a new behavior before implementation. Either make
   Codex schema/output paths invocation-scoped, or serialize QA and reviewer
   when `config.ai_provider == "codex"` and test that contract.

2. DB preflight detection blocks valid inline env commands and the compose
   DB contract is stale.
   Impact: implementation can fail before coder on checks that supply their own
   `DATABASE_URL_TEST`, or regress the existing build-db default.
   Recommendation: distinguish "requires DB" from "host env missing" and treat
   inline `DATABASE_URL_TEST=...` as satisfying the precondition. Revise compose
   tests to preserve the selected build-db/optional-env contract.

3. Non-retryable fatal harness errors are still swallowed by flagged-path
   concurrency.
   Impact: environment/auth/config failures can degrade into normal fix loops,
   the same class of misleading fallback behavior the plan is meant to remove.
   Recommendation: add a flagged-path test where QA or reviewer raises
   `FatalHarnessError`, and propagate it instead of converting it to a normal
   QA/review result.

4. `FixGeneratorResult` and nested result models are not fully specified.
   Impact: tests can fail on missing imports rather than schema strictness, and
   typed model migration can break BAML or `.get()`-based consumers.
   Recommendation: define module-level result models with explicit fields,
   defaults, and non-default BAML round-trip tests.

5. Codex CLI timeout cleanup is unspecified.
   Impact: timed-out Codex subprocesses can continue running against the same
   worktree and fixed output paths after SWE-AF has already returned an error.
   Recommendation: move timeout handling into the subprocess helper or ensure
   cancellation kills and awaits the child process.

## Suggested Plan Amendments

```diff
+ Add Behavior 0: Codex structured-output paths are invocation-scoped, or Codex
+ flagged QA/reviewer execution is serialized to avoid shared
+ .agentfield_schema.json / .agentfield_output.json races.
+
+ Add tests where flagged Codex QA and reviewer run in the same worktree and
+ cannot overwrite each other's schema/output files.
+
~ Modify Behavior 1: create module-level FixGeneratorResult, FixIssueDraft,
~ FixDebtItem, AgentRetro, TestFailure, and DebtItem schemas with explicit
~ defaults before importing them in strict-schema tests.
+
+ Add BAML round-trip tests for non-default typed nested content.
+
~ Modify Behavior 4: pass system_prompt=QA_SYNTHESIZER_SYSTEM_PROMPT on the
~ Codex harness path and assert tools are absent or empty.
+
+ Add flagged-path FatalHarnessError propagation tests.
+
~ Modify Behavior 5: check_requires_test_db should not require host
~ DATABASE_URL_TEST when the command itself assigns DATABASE_URL_TEST=...
+
~ Modify Behavior 6: preserve the current build-db default or explicitly replace
~ it; make swe-agent, swe-fast, docker-compose.local.yml, and BUILD_RUNBOOK agree.
+
+ Add Codex subprocess timeout cleanup tests.
```

## Review Checklist

### Contracts

- [x] Component boundaries reviewed
- [x] Input/output contracts reviewed
- [ ] Error contracts complete
- [ ] Preconditions complete
- [x] Invariants identified

### Interfaces

- [ ] All public methods/models defined with signatures
- [x] Naming mostly follows codebase conventions
- [ ] Interface matches existing patterns
- [ ] Extension points fully considered
- [x] Visibility modifiers appropriate

### Promises

- [ ] Behavioral guarantees complete
- [ ] Async timeout/cancellation handling complete
- [ ] Resource cleanup specified
- [x] Idempotency addressed where identified
- [ ] Ordering/concurrency guarantees documented

### Data Models

- [ ] All fields have types
- [ ] Required vs optional is clear
- [x] Relationships are documented enough for this scope
- [x] Migration strategy is additive
- [x] Serialization format is specified through `model_dump()`

### APIs

- [x] Endpoints/external APIs not materially changed
- [ ] Config request/response/env formats fully specified
- [ ] Error responses fully documented
- [x] Authentication requirements are preserved
- [x] Versioning not applicable
