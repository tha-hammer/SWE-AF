---
date: 2026-06-11
reviewer: claude (review_plan)
plan: thoughts/searchable/shared/plans/2026-06-11-07-43-tdd-baml-typed-deterministic-backpressure.md
plan_branch: feat/baml-structured-output
verified_against: /home/maceo/Dev/SWE-AF-baml @ 6517b17
status: RESOLVED — all 3 critical + 6 warnings folded into the plan (2026-06-11)
---

> **Resolution (2026-06-11):** every finding below has been applied to the plan in place.
> Critical fixes: B4 now reuses the argv `CommandRunner` via `["bash","-c",cmd]` (no
> `shell=True`) and adds its own `deterministic_check_timeout_seconds` (default 600) with
> `TimeoutExpired→exit_code=-1`; B6's rung now gates the reviewer branch and **falls through**
> (never `continue`), folds the tail into the persisted `summary`, and persists
> `det_check_attempts` across resume. Warnings: `_tail` re-export noted, BAML `@check`
> reworded to `tb.add_baml` raw, PlannedIssue/verification switched to named anchors, config
> triplication reframed with `extra="forbid"` semantics + a propagation test, manifest
> false-red (pytest exit 5) documented in B5. The sections below are retained as the
> point-in-time review of the original draft.

# Plan Review Report: BAML-Typed Deterministic Backpressure — REVIEW

All file:line citations were verified against the actual implementation tree
(`/home/maceo/Dev/SWE-AF-baml` @ `6517b17`, branch `feat/baml-structured-output`),
**not** `main` — the BAML bridge this plan stacks on exists only on that branch.

## Review Summary

| Category | Status | Issues |
|----------|--------|--------|
| Contracts | ❌ | 2 critical (runner type, timeout), 1 warning |
| Interfaces | ⚠️ | 1 warning (BAML `@check` API absent) |
| Promises | ❌ | 1 critical (control-flow `continue`), 2 warnings (checkpoint, counter resume) |
| Data Models | ✅ | 1 minor (insertion anchors drift) |
| APIs / Producer | ✅ | clean — schema+prompt is sufficient |

**Verdict: the plan is well-researched and the seams are real, but three
load-bearing claims are wrong as written. None require redesign — all are precise
corrections to specific behaviors.**

---

## Contract Review

### Well-Defined
- ✅ **Insertion seam (Behavior 6) is real and clean.** Lines 659→662 are separated
  only by a blank line + a `# --- 2. PATH BRANCH ---` comment. `coder_result` and
  `files_changed` are populated; no reviewer/QA has run. Inserting a gate here that
  decides before `if needs_deeper_qa:` (662) genuinely costs zero LLM calls.
- ✅ **Config propagation chain exists end-to-end.** `cfg.to_execution_config_dict()`
  (app.py:931) → `ExecutionConfig(**effective_config)` (app.py:1572) → `run_dag` →
  `run_coding_loop(config=config)` where `config: ExecutionConfig` (coding_loop.py:521,
  attribute-access Pydantic model). `config.enable_deterministic_checks` is the right
  *form*.
- ✅ **`dag_executor.py:741-742` `model_dump()`** is accurate and recursive — a new
  `verification: list[AcceptanceCheck]` survives into the issue dict as `list[dict]`,
  readable via `issue.get("verification", [])`.

### Critical
- ❌ **`CommandRunner` is argv-shaped — it cannot run shell pipelines (Behavior 4).**
  The plan's Current State says *"The runner template exists and is injectable + tested"*
  and cites `ci_gate.CommandRunner`. But the actual type is
  `Callable[[Sequence[str], str], CompletedProcess[str]]` — **arg1 is an argv list, not a
  command string** — and `_default_runner` does `subprocess.run(list(cmd), …, shell=False)`
  with **no `timeout`**. Behavior 4 wants `subprocess.run(command, shell=True)` on a
  command *string* with pipes (`… | jq …`). Passing a string to the existing runner
  shreds it into one-char argv entries (`list("pytest")` → `['p','y',…]`). **The runner
  template is the wrong shape and cannot be reused as cited.**
  - *Impact:* Behavior 4 silently produces garbage commands, or the type alias is reused
    incorrectly and pipelines never run.
  - *Recommendation:* Either (a) keep the argv contract and wrap pipelines as
    `["bash", "-lc", command]` — this **reuses the existing `CommandRunner` type, keeps
    `shell=False`, and avoids introducing a brand-new `shell=True` pattern** (there is
    currently **zero** `shell=True` in the repo); or (b) define a *distinct*
    `ShellRunner = Callable[[str, str], CompletedProcess[str]]` and do not claim it is the
    existing template. Option (a) is cleaner and preserves the "injectable + tested"
    claim. Pick one explicitly in Behavior 4.

- ❌ **The timeout the plan "mirrors" does not exist (Behavior 4).** Behavior 4 says a
  runner that "raises / times out → `passed=False`, exit_code sentinel -1 (mirrors
  `ci_gate` timeout handling)." `ci_gate._default_runner` has **no `timeout=`**, and
  ci_gate's only timeout is a wall-clock *poll cap* in `watch_pr_checks` — there is **no
  per-subprocess timeout and no -1 sentinel** to mirror.
  - *Impact:* This is load-bearing for the plan's central promise. A cold worktree running
    `pytest`/`npm test` can hang indefinitely (network wait, watch mode, interactive
    prompt). With no timeout, **one hung command blocks the entire build forever** —
    directly defeating "bounded, then downgrade to advisory."
  - *Recommendation:* Behavior 4 must specify its **own** timeout: `subprocess.run(...,
    timeout=DET_CHECK_TIMEOUT_SECONDS)` (add the constant), and map `TimeoutExpired` →
    `CheckResult(passed=False, exit_code=-1, output_tail="<timeout>")`. Make the timeout a
    config value (it belongs with the other deterministic-check knobs in Behavior 6's
    config triplication). Do not describe it as "mirroring" ci_gate.

### Warning
- ⚠️ **`_tail` promotion to `_proc.py` is fine — but keep ci_gate re-exporting it.**
  `_tail` (sig `_tail(text, max_chars=_LOG_TAIL_CHARS) -> str`, ci_gate.py:92-95) and
  `_LOG_TAIL_CHARS=3000` (ci_gate.py:31) are used only in `ci_gate.py` and imported by
  `tests/test_ci_gate.py` **from `ci_gate`**. Promoting to `swe_af/execution/_proc.py`
  works only if `ci_gate` continues to re-export `_tail`, or `test_ci_gate.py`'s import
  breaks. Behavior 4's Refactor step should state this re-export requirement.

---

## Interface Review

### Well-Defined
- ✅ **BAML bridge mapping handles `list[AcceptanceCheck]`.** `_map_type` handles `list[X]`
  (baml_bridge.py:70-72) and nested `BaseModel` (108-112), both accurate.
  `pydantic_to_typebuilder(model) -> TypeBuilder` (132-137) is reflective over
  `model_fields`, so a new nested model flows through unchanged.
- ✅ **Fallback-first seam is exactly as described.** `baml_parse_or_none` is wired only via
  `codex_harness_patch.py:301-309` (SDK native parse first, BAML on its `None`).
  `baml_parse` (raising) has **no production caller** (tests only). The plan's conclusion —
  *the validity guarantee must live in Pydantic, not BAML asserts* — is correct, because
  BAML never runs on the happy path.

### Warning
- ⚠️ **BAML `@check`/`@assert` has no fluent API for dynamic fields (Behavior 0/1).**
  `add_property()` returns `ClassPropertyBuilder` exposing only `.alias()` / `.description()`
  — **no `.assert_()` / `.check()` / `.constraint()`** (confirmed in `baml_py.pyi`). The
  only escape hatch is `TypeBuilder.add_baml(raw_baml_str)`. Behavior 1's Refactor step
  ("extend `pydantic_to_typebuilder` to attach the BAML `@check` echo") implies an API that
  does not exist.
  - *Severity is low* because Behavior 0 is explicitly a spike and the plan declares the
    BAML check "not load-bearing" (Pydantic is the guarantee). This is **de-risked by
    design.**
  - *Recommendation:* Reword Behavior 1's Refactor to: "*if* B0 proves feasible, attach the
    echo via `tb.add_baml('dynamic class … { command string @check(...) }')` — there is no
    `.check()` builder method." Keep it optional, as the plan already intends.

---

## Promise Review

### Well-Defined
- ✅ **Feedback reaches the next coder iteration.** `feedback_parts` (coding_loop.py:786) is
  joined into `feedback` (802) under `if action == "fix":`, and `feedback` is consumed by the
  next coder call at L621 (`feedback=feedback`). Appending the failure tail there works —
  *provided the rung sets `action="fix"`* (see critical below).

### Critical
- ❌ **The loop has no `continue`/`break` — a raw `continue` would corrupt bookkeeping
  (Behavior 6).** Behavior 6's Green step says "*skip path branch, append tail to
  `feedback_parts`, **continue***." Verified: there is **zero** `continue`/`break` in the
  `for iteration in range(...)` body (602-760). Re-entry to the coder is plain fall-through.
  The reviewer/QA *is* `_run_flagged_path`/`_run_default_path` (664/690), which **set
  `action`, `summary`, and review artifacts**. A `continue` inserted at 659–662 would jump
  past: the iteration-history append, the **checkpoint** `_save_iteration_state` (730-735),
  and the **memory write** (737-745).
  - *Impact:* resume breaks (no checkpoint for the red iteration), history is lost, and —
    because `feedback` is built at 802 *inside the path branch's downstream* — the tail may
    never be joined. This also **contradicts the plan's own Behavior 6 checkpoint edge-case**
    ("folded into summary/iteration_history *before* `_save_iteration_state`"), which is only
    possible if you do **not** `continue`.
  - *Recommendation:* Replace "skip path branch + continue" with: **set `action="fix"` and
    `summary=<tail>` directly, bypass the `if needs_deeper_qa:` branch (so no reviewer runs),
    then fall through to the existing history/checkpoint/memory/feedback machinery.** Concretely:
    `if gate.blocks: action, summary, review_result = "fix", gate.tail, None  else: <existing
    662 branch>`. The plan's own helper-extraction Refactor (`_run_deterministic_gate`) is the
    right shape — just gate the *branch*, never `continue`.

### Warning
- ⚠️ **Checkpoint persists `summary`, not `feedback` (Behavior 6).** `_save_iteration_state`
  stores `{"feedback": summary, …}` (coding_loop.py:730-735) — the **rich** `feedback` from
  802 is *not* checkpointed. The plan correctly says the rung's result must be "folded into
  summary/iteration_history before `_save_iteration_state`," but the Green step routes the
  tail into `feedback_parts`/`feedback`, which is **not** the persisted field. Make it
  explicit: the deterministic failure tail must go into **`summary`** (and/or
  `iteration_history`) so resume replays the red, since `feedback` is ephemeral.
- ⚠️ **`det_check_attempts` won't survive resume (Behavior 6).** The bound is enforced by a
  per-issue counter the plan threads "alongside `iteration`." But `iteration` is the loop
  variable (`range(start_iteration, …)`), and resume restarts from `start_iteration` via the
  checkpoint. If `det_check_attempts` is not added to the `_save_iteration_state` payload and
  the load path, a resume mid-red-streak **resets the bound to 0**, allowing more reds than
  intended (or, with flaky checks, a longer-than-bounded loop across resumes). Add it to the
  checkpoint dict and the loader.

---

## Data Model Review

### Well-Defined
- ✅ **`AcceptanceCheck` and `verification` are clean net-new adds** — zero existing
  occurrences of either name; no collision (`VerificationResult` is unrelated).
- ✅ **`CoderResult.tests_passed` self-attestation is real** (schemas.py:421,
  `tests_passed: bool | None = None  # Self-reported: did tests pass?`) — the motivating gap
  is accurately cited.
- ✅ **Config triplication is real** (BuildConfig field → ExecutionConfig field →
  hand-written allow-list in `to_execution_config_dict`, schemas.py:822-848). Accurately
  flagged as pre-existing.

### Minor (mechanical, but will bite)
- ⚠️ **Insertion anchors are wrong/fragile.** `class PlannedIssue` is at **line 78**;
  `guidance` is at **92**, `target_repo` at **93**. Behavior 2 says add `verification` "at
  line 92/93, grouped with guidance" — that **lands on top of `guidance`/`target_repo`**.
  Correct anchor: **insert after the `guidance` field (line 92)**. Also, once `AcceptanceCheck`
  is inserted "before line 78" (Behavior 1), **every absolute line below shifts** — the plan's
  "92/93", "before 78", etc. all drift on the first edit.
  - *Recommendation:* Restate Behaviors 1–2 with **named anchors** ("immediately before
    `class PlannedIssue`", "after the `guidance` field") rather than absolute line numbers.

### Promise on the config wiring
- ⚠️ **Reframe the triplication failure mode + add a propagation test (Behavior 6).**
  `to_execution_config_dict` is a hand-written allow-list, and `ExecutionConfig` has
  `model_config = ConfigDict(extra="forbid")`. So the failure modes are **asymmetric**:
  - Adding a dict key without the matching ExecutionConfig field → **raises loudly** (good).
  - Omitting the `to_execution_config_dict` line → the flag **silently defaults to the
    ExecutionConfig default**, and the BuildConfig value is ignored (the real trap).
  Behavior 6's tests set `config.enable_deterministic_checks=True` **directly on
  ExecutionConfig**, which **bypasses the triplication entirely** — so the wiring that the
  plan flags as risky is the one thing left untested. Add one test:
  `BuildConfig(enable_deterministic_checks=False).to_execution_config_dict()` →
  `ExecutionConfig(**d).enable_deterministic_checks is False`. Note all three edits must land
  in the same change or `ExecutionConfig(**d)` raises (`extra="forbid"`).

---

## API / Producer Review

### Well-Defined
- ✅ **Producer path is clean — schema + prompt is sufficient (Behavior 7).** There is **no
  hand-written `PlannedIssue(...)` construction**. Issues are produced by schema-driven
  auto-deserialization: `pipeline.py:495-547` declares `SprintPlanOutput.issues:
  list[PlannedIssue]`, passes `schema=SprintPlanOutput` to `router.harness(...)`, and returns
  `result.parsed.issues`. Adding `verification` to `PlannedIssue` + the additive prompt
  instruction **populates end-to-end with no intermediate wiring.** *Caveat (already honored
  by the plan): keep `AcceptanceCheck` a typed nested `BaseModel`; an untyped `dict`/`Any`
  field is unmappable by the bridge and would silently restrict to the SDK-native path.*
- ✅ **PM "MUST map to a command" guidance is real** (product_manager.py:57-59, under
  `## Execution Model Awareness`, with `cargo test`/`stat`/`hyperfine` patterns). Behavior 7's
  "reuse the already-present guidance" is grounded.
- ✅ **Manifest detector is genuinely new.** No `detect_project_commands` and no literal
  manifest string-checks exist in non-prompt code; detection appears only as prompt text
  (`git_init.py:46`, `environment_scout.py:33-36`). Behavior 3 is net-new with no duplication.
- ✅ **Test doubles to copy exist.** `_ScriptedRunner`/`_FakeClock`/`_no_sleep`
  (test_ci_gate.py:43-81, returns `CompletedProcess`, scripts on `cmd[:3]` argv slice) and
  `_roundtrip(model, instance_json)` (test_baml_bridge.py:26-32). *Note:* `_ScriptedRunner`
  keys on an **argv slice** — it will need adapting if Behavior 4 settles on a string-command
  runner (another reason to prefer the `["bash","-lc",cmd]` argv reconciliation).

### Warning (semantics)
- ⚠️ **Whole-suite manifest fallback can red on unrelated/empty test states (Behaviors 3/5/6).**
  The manifest fallback emits broad commands (`pytest`, `npm test`, `go test ./...`). Two
  false-red modes:
  1. A broad `pytest` reds on **pre-existing or flaky failures** unrelated to the issue's own
     code — blocking an issue whose change is correct.
  2. `pytest` with **no tests collected** exits **5** (non-zero) → treated as red, even though
     nothing ran — likely in early-TDD issues before tests exist.
  The typed per-issue command (`pytest -k lexer`) avoids this, and "planned-over-manifest" +
  the advisory cap bound the damage. But the manifest fallback is exactly the path used when
  the planner omits `verification`.
  - *Recommendation:* Document this in Behavior 5; consider treating pytest exit 5 ("no tests
    collected") as **not-red** (or skip), and note that the advisory downgrade is what
    protects against unrelated-failure blocking.

---

## Critical Issues (Must Address Before Implementation)

1. **Runner contract mismatch (Behavior 4).** `CommandRunner` is argv-shaped; it cannot run
   shell pipelines. *Fix:* wrap as `["bash","-lc",command]` argv (reuses the existing
   `CommandRunner` type + `shell=False`) **or** define a distinct `ShellRunner` and stop
   calling it "the existing template." Decide explicitly.

2. **Timeout is borrowed from a non-existent pattern (Behavior 4).** ci_gate has no
   per-subprocess timeout/-1 sentinel. *Fix:* specify `subprocess.run(timeout=…)` +
   `TimeoutExpired → passed=False, exit_code=-1`, with the timeout as a config knob. Without
   it, a hung command blocks the build forever and the "bounded" promise is false.

3. **`continue` corrupts the iteration bookkeeping (Behavior 6).** The loop has no
   `continue`/`break`; a raw `continue` skips checkpoint (730), memory (737-745), and history.
   *Fix:* gate the `if needs_deeper_qa:` *branch* — set `action="fix"`, `summary=<tail>`,
   `review_result=None`, then **fall through** to the existing machinery. Never `continue`.
   (This also resolves the plan's internal contradiction with its own checkpoint edge-case.)

## Suggested Plan Amendments

```diff
# Behavior 4 (Deterministic local runner)
~ Do NOT reuse ci_gate.CommandRunner for a shell string. Either invoke
+   runner(["bash","-lc", command], cwd)   # reuses argv CommandRunner, shell=False
+ or define ShellRunner = Callable[[str, str], CompletedProcess[str]] explicitly.
+ Add DET_CHECK_TIMEOUT_SECONDS; subprocess.run(..., timeout=DET_CHECK_TIMEOUT_SECONDS);
+ map TimeoutExpired/OSError -> CheckResult(passed=False, exit_code=-1, output_tail=err).
- "mirrors ci_gate timeout handling"  (ci_gate has no per-subprocess timeout)
+ In Refactor: ci_gate must keep re-exporting _tail after the _proc.py promotion
+   (tests/test_ci_gate.py imports _tail from ci_gate).

# Behavior 6 (gated rung)
- "skip path branch ... continue"
+ if gate.blocks and det_check_attempts < cap:
+     action, summary, review_result = "fix", gate.tail, None   # bypass 662 branch
+ else:
+     <existing 'if needs_deeper_qa:' branch>
+ Fold gate.tail into `summary` (persisted by _save_iteration_state), not only `feedback`.
+ Add det_check_attempts to the _save_iteration_state payload AND the resume loader.
+ Add a propagation test: BuildConfig(enable_deterministic_checks=False)
+   -> to_execution_config_dict() -> ExecutionConfig(**d).enable_deterministic_checks is False.
+ Land all 3 config edits together (ExecutionConfig extra="forbid" rejects orphan keys).

# Behaviors 1 & 2 (schema)
~ Use named anchors, not absolute lines:
+   AcceptanceCheck: immediately before `class PlannedIssue` (currently line 78)
+   verification:    after the `guidance` field (currently line 92), NOT "at 92/93"
~ Behavior 1 Refactor: BAML @check has no .check()/.assert_() builder;
+   if used at all, inject via tb.add_baml(raw). Keep optional (B0 decides).

# Behavior 5 (resolution)
+ Document false-red risk of broad manifest fallback (unrelated/flaky failures;
+   pytest exit 5 = "no tests collected"). Consider exit-5 as not-red.
```

## Approval Status

- [x] **Ready for Implementation** — all 3 critical + 6 warnings folded into the plan
  (2026-06-11). The architecture, seams, and producer path were sound and verified; the
  applied fixes were localized to Behaviors 4 and 6 plus anchor/wording cleanups in 0, 1, 2, 5.
- [ ] ~~Needs Minor-to-Moderate Revision~~ (original verdict — now resolved)
- [ ] Needs Major Revision

**Note on dependency:** this plan stacks on the **unmerged** `feat/baml-structured-output`
branch. All anchors above are valid at `6517b17`; if that branch is rebased/merged before
implementation, re-validate the schema and bridge line numbers (another reason to switch to
named anchors).
