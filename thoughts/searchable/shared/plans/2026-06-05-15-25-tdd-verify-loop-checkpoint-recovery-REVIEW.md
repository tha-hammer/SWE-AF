# Plan Review Report: Verify→Fix Loop Recovery & Checkpoint Stomp Protection

**Plan**: `thoughts/searchable/shared/plans/2026-06-05-15-25-tdd-verify-loop-checkpoint-recovery.md`
**Reviewed**: 2026-06-05 · against `git_commit ebf00a3` (current HEAD)
**Method**: every `file:line` citation, signature, and structural claim in the plan was read against live source. No claim taken on trust.

---

## Review Summary

| Category | Status | Issues Found |
|----------|--------|--------------|
| Citation accuracy | ✅ | 0 — all 30+ line refs verified exact |
| Contracts | ⚠️ | 2 (B1 guard heuristic, B5 dedupe key) |
| Interfaces | ✅ | 0 — all signatures match; additive params backward-compatible |
| Promises (timing/behavior) | ❌ | 1 critical clarity gap (B6 between-cycles semantics) |
| Data Models | ✅ | 0 — DAGState / BuildConfig fields confirmed present |
| APIs / wiring | ✅ | 0 — call sites and forwarding verified |

**Verdict: Needs Minor Revision.** The plan is unusually well-grounded — every citation is accurate and the TDD cycles are concrete and runnable. The issues are about *expectation framing* and two guard heuristics, not broken design.

---

## Citation Verification (all ✅)

| Plan claim | Verified at source |
|---|---|
| Verify loop `app.py:952-1035`, guard `:968` | ✅ exact |
| `failed_criteria` recomputed `:972-975` | ✅ exact |
| `generate_fix_issues` call `:988-998` | ✅ exact |
| Existing debt append `:1003-1010` (keys `criterion`/`reason`/`severity`) | ✅ exact |
| Fix `execute` `:1024-1031`, reused `artifacts_dir` `:1021`, no `build_id` | ✅ exact |
| `app.py` does **not** import `time` (imports: asyncio, os, subprocess, uuid) | ✅ confirmed |
| `execute` sig `:1542-1552` (`resume`, `build_id`, `workspace_manifest`), `run_dag` call `:1586` | ✅ exact |
| `resume_build` `:1998-2044`, hardcoded `checkpoint.json` `:2014` | ✅ exact |
| `_checkpoint_path` `:683-685`; `_save_checkpoint` `:688-697`, early-return `:691`, `open("w")` `:694` | ✅ exact |
| `_load_checkpoint` `:700-706`; resume load path `:1413-1416` | ✅ exact |
| 7 save sites `1436,1505,1517,1557,1676,1734,1799` | ✅ **exactly 7, all match** |
| `run_dag` sig `:1352-1364` (`build_id`, `workspace_manifest` present) | ✅ exact |
| `DAGState` `:276`; `all_issues:292`, `build_id:316`, `accumulated_debt:323`, `completed_issues:296` | ✅ all present |
| `BuildConfig` `:684`, `extra="forbid":687`, `max_verify_fix_cycles:697`, `agent_timeout_seconds:730` | ✅ exact |
| `generate_fix_issues` `:1297`(deco)/`:1298`(def); `fix_generator_task_prompt` call `:1318-1322` | ✅ exact |
| `fix_generator_task_prompt` sig `:55-59`; debt instruction `:25`; "Existing Technical Debt" section `:89-95` | ✅ exact |
| `import json` / `Callable` already imported in `dag_executor.py` (`:6`, `:10`) | ✅ B1 helper has its deps |

**Bonus verification not asserted by the plan but load-bearing for B6:**
- `to_execution_config_dict()` (`schemas.py:822-848`) is an **explicit whitelist** of 20 keys. A new `BuildConfig` field is *not* auto-forwarded to `ExecutionConfig`. **B6's central assumption is confirmed** — `verify_fix_soft_deadline_seconds` will not trip `ExecutionConfig`'s `extra="forbid"`. ✅

---

## ❌ Critical: B6 timing promise is mis-framed (clarify before implementing)

The Overview motivates the work with: *"A single fix cycle is a full DAG run that can consume the entire external 7200s budget."* A reader expects B6 (soft deadline) to bound that. **It does not.**

B6's own Test Spec is precise and correct: it gates *"when the loop is **about to launch** a fix DAG."* That is a **between-cycles** check, evaluated at `elapsed = time.monotonic() - verify_loop_start` **before** the `execute` call at `app.py:1024`. Consequences:

1. **The first fix cycle is never gated** — `elapsed ≈ 0` at first launch, so the very DAG that burns ~2 hours is launched unconditionally. B6 cannot interrupt an in-flight `execute`.
2. **Under the shipped default `max_verify_fix_cycles = 1`**, there is only ever one fix DAG. With one fix cycle, B6 has no *subsequent* launch to block, so **B6 is inert by default** — even when `verify_fix_soft_deadline_seconds` is set.
3. The actual wall-clock bound on a single fix DAG remains the inner `agent_timeout_seconds` (2700s) × retries × advisor — which the plan correctly scopes out ("Not changing the external 7200s cap").

**This is not a code defect — the helper and wiring are correct.** It is an expectation/Promise gap: B6 caps *cumulative cycles*, and only matters when `max_verify_fix_cycles ≥ 2`. Same dormancy applies to **B4 (convergence)** and **B7 (history)** — both require ≥2 fix cycles to ever fire; under the default config they never execute.

**Recommendation (pick one, document in the plan):**
- Add to "What We're NOT Doing": *"B4/B6/B7 are dormant under the default `max_verify_fix_cycles=1`; they bound cumulative cycles for operators who raise that knob. No behavior here interrupts an in-flight fix DAG — the 2-hour single-cycle burn is bounded only by `agent_timeout_seconds`."*
- And note the coupling explicitly: **B6 is only meaningful when paired with `max_verify_fix_cycles > 1`.** Shipping B6 with a non-zero default while leaving cycles at 1 would have zero effect.

Without this, the plan reads as if it solves the headline 2-hour scenario. What it actually delivers by default is: **no checkpoint stomp (B1+B3), a forensic main-DAG snapshot (B2), and still-failing criteria recorded as debt (B5).** That is genuinely valuable — but it's *recoverability*, not *time reduction*. Make that explicit.

---

## ⚠️ Contract Issues (address, non-blocking)

### B1 — the "don't shrink" guard is a count heuristic with a cross-build false-positive
`_existing_issue_count` compares `len(all_issues)` only. Two real edge cases the plan's spec doesn't cover:

- **Stale checkpoint from a prior, larger build in a reused `artifacts_dir`.** The checkpoint path keys on `artifacts_dir` alone (confirmed — `build_id` is *not* in the path). If a fresh, smaller build runs in an `artifacts_dir` that still holds a bigger previous `checkpoint.json`, the guard **refuses to write the legitimate new checkpoint**, and `resume_build` would later resume the *wrong* (old) plan. The plan's fail-open covers *corrupt* files, not *valid-but-stale* ones.
- **Count collision**: two unrelated DAGs with equal `all_issues` counts pass the guard and can still overwrite each other (count ≠ identity).

In practice B3's namespacing makes the in-run main-vs-fix stomp moot, so B1 is defense-in-depth. But document the assumption: **B1 is safe only because `artifacts_dir` is unique per build.** If that's true, state it (and ideally assert it). If `artifacts_dir` can be reused across builds, B1 needs a build-identity check or a "clear checkpoint at build start" step, or it will block legitimate writes.

**Recommendation:** Add an edge case to B1's spec: "existing checkpoint from a different build (same `artifacts_dir`, unrelated `build_id`)" — and decide the intended behavior. Add one test seeding a larger stale checkpoint and asserting the chosen semantics.

### B5 — dedupe key and reason-source need to be pinned in the spec
The existing append (`app.py:1003-1010`) records the generator's `debt_items` keyed on `criterion`; B5 appends `_criteria_to_debt(failed_criteria)` also keyed on `criterion`. The plan says "dedupe ... compare on `criterion`" — good — but two sub-points should be explicit:
- `_criteria_to_debt` sources `reason` from `c.get("evidence","")`. This is correct (verifier `criteria_results` dicts carry `evidence`, confirmed at `fix_generator.py:74`), but state it so the contract is unambiguous.
- The terminal cycle-cap break at `app.py:968` fires **before** `failed_criteria` is computed (`:972`). The plan already flags this and says to reuse the `:972-975` comprehension via a `_failing_criteria(verification)` helper. ✅ Good — just make sure the Red test for B5's build() integration actually exercises the `:968` path (cycle-cap exhaustion), not only the no-fix `:1033` path, since they're different break sites.

---

## Notes (✅ verified, no action — recorded for the implementer)

- **B3 side effect is the desired fix, and is correct.** After namespacing, `checkpoint.json` holds the main DAG's final state and fix DAGs write `checkpoint-fix-N.json`. `resume_build` then resumes the *main* DAG. Caveat to note: `resume_build` only re-enters `execute`, **not** the verify/fix loop — so resume recovers execution, not verification. That's consistent with "Not making fix-DAGs resumable," but worth a one-line mention so nobody expects resume to re-verify.
- **B2 call-site placement is sound** — inserting after `app.py:942` captures the main `dag_result` before the loop can reassign it at `:1024`. The `manifest` refresh at `:947-948` sits between but doesn't touch `dag_result`'s issue set.
- **No real concurrency hazard** on the guard's read-then-write: the 7 save sites within a single `run_dag` are sequential, and main/fix DAGs run sequentially (fix `execute` awaits after main returns). With B3, they target different files anyway. TOCTOU is benign here.
- **B7 accumulation semantics** ("track `prior_failed_criteria` accumulated across cycles") should specify dedupe-by-`criterion` to avoid the prompt section growing with repeats. Minor — and dormant under default config (≥2 cycles required).
- **Backward compatibility is clean throughout**: every new param defaults to today's behavior (`checkpoint_label=""`, `verify_fix_soft_deadline_seconds=0`, `previously_failed_criteria=None`). `extra="forbid"` on `BuildConfig` accepts new *declared* fields fine.

---

## Suggested Plan Amendments

```diff
# Overview / What We're NOT Doing
+ Add: "B4 (convergence), B6 (soft deadline), and B7 (history) are DORMANT under
+       the default max_verify_fix_cycles=1 — each requires ≥2 fix cycles to fire.
+       They bound CUMULATIVE cycles, not the duration of a single in-flight fix DAG.
+       The 2-hour single-cycle burn is bounded only by agent_timeout_seconds; this
+       plan's default-config contribution is no-stomp (B1+B3), snapshot (B2), and
+       debt recording (B5)."
+ Add: "B6 is only meaningful when paired with max_verify_fix_cycles > 1."

# Behavior 1: Test Specification → Edge Cases
+ Add edge case: "existing checkpoint from a DIFFERENT build at the same
+   artifacts_dir (larger all_issues) — decide: block (assumes unique artifacts_dir)
+   vs. overwrite (key guard on build_id). Add a test for the chosen semantics."
+ Add precondition note: "B1 is safe iff artifacts_dir is unique per build()."

# Behavior 5: Test Specification
+ Clarify: reason is sourced from criterion['evidence']; dedupe key is 'criterion'.
+ Ensure the build() integration Red test exercises the app.py:968 cycle-cap break
+   specifically (not only the :1033 no-fix break).

# Behavior 7: Green
+ Specify: prior_failed_criteria is deduped by 'criterion' before rendering.
```

---

## Approval Status

- [ ] Ready for Implementation
- [x] **Needs Minor Revision** — clarify B6/B4/B7 default-config dormancy (the one critical framing gap), pin B1's unique-`artifacts_dir` assumption, and tighten B5's dedupe/reason contract. No code design is broken; the TDD cycles are accurate and runnable as written.

**Bottom line:** This is a high-quality, citation-accurate plan. Every line reference checks out — rare. The single thing that must change before implementation is honest framing: under default settings the plan delivers *checkpoint integrity + forensics + debt*, not *time savings*. Say that plainly so operators know they must raise `max_verify_fix_cycles` and set a soft deadline for B6 to do anything.

---

## Resolution (applied to the plan — 2026-06-05)

All issues folded into `2026-06-05-15-25-tdd-verify-loop-checkpoint-recovery.md`:

- **❌ B6/B4/B7 dormancy** → New **"Scope & timing semantics"** block in the
  Overview + three bullets in "What We're NOT Doing"; per-behavior dormancy
  callouts on B4, B6, B7; integration tests retagged `[cycles=2]` vs
  `[default cycles=1]`. The plan now states plainly that nothing interrupts an
  in-flight fix DAG and that B6 requires `max_verify_fix_cycles > 1`.
- **⚠️ B1 guard** → **Upgraded the recommendation after verification.** The review
  suggested pinning a "unique `artifacts_dir`" precondition; reading `build()`
  showed that assumption is **false** when the caller passes an explicit local
  `repo_path` (`app.py:503` — `artifacts_dir` is reused). So B1 was made
  **`build_id`-aware** instead (`_existing_checkpoint_meta` reads `build_id`;
  refuse-to-shrink only on same `build_id`, fail-open cross-build). `build_id` is
  unique per build (`app.py:488`, verified) and is a serialized `DAGState` field
  (`schemas.py:316`). Added `test_save_checkpoint_refuses_to_shrink_same_build` and
  `test_save_checkpoint_fail_open_cross_build`; removed the incorrect "preserve
  stale" test.
- **⚠️ B5 contract** → Pinned `reason ← criterion["evidence"]` and dedupe key
  `criterion`; integration test now required to exercise the `app.py:968`
  cycle-cap break (plus a second assertion for the `:1033` no-fix break).
- **B7 dedupe** → Specified dedupe-by-`criterion` for accumulated history.
- **Resume scope** → B3 downstream note now states `resume_build` re-enters
  `execute` only, not the verify/fix loop.

**Updated status: Ready for Implementation.** No open design questions remain; the
TDD cycles are runnable as written.

### Follow-up decision (operator request): wire in non-zero defaults

Per explicit request, the plan now ships the protection **active by default**
instead of opt-in:
- `max_verify_fix_cycles`: **1 → 2** (gives B4/B6/B7 a second cycle to act on).
- `verify_fix_soft_deadline_seconds`: **0 → 3600** (`0` still disables).

Rationale: the deadline gates the *start* of a cycle, so worst-case total fix time
≈ `deadline + one_full_cycle` ≈ `3600 + 2700` = 6300s, under the external 7200s
cap. Regression risk verified low: `grep max_verify_fix_cycles tests/` finds only
*forbidden-identifier* source guards (`test_verifier.py:79-83`), which a
default-value change does not affect — no test asserts the default is 1 or counts
exactly one fix cycle. The B4/B6/B7 dormancy callouts in the plan were flipped to
"active under the new default," and the config-default test now asserts `==2` /
`==3600`. Operators can restore old behavior with `max_verify_fix_cycles=1` or
disable the budget with `verify_fix_soft_deadline_seconds=0`.

Trade-off recorded in the plan: a build that fails verification may now attempt a
*second* fix cycle it previously would not have (more time/spend on hard builds),
bounded by the soft deadline.
