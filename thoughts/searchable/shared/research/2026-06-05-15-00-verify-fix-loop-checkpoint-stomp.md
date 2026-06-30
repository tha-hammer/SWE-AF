---
date: 2026-06-05T15:00:07-04:00
researcher: tha-hammer
git_commit: ebf00a35e6af11cd085ce4928e589a5b983b2e13
branch: main
repository: SWE-AF
topic: "Verify→fix loop termination and DAG checkpoint stomping — claim verification"
tags: [research, codebase, verify-fix-loop, dag-executor, checkpoint, fix-generator]
status: complete
last_updated: 2026-06-05
last_updated_by: tha-hammer
---

# Research: Verify→fix loop & checkpoint stomping — claim verification

**Date**: 2026-06-05T15:00:07-04:00
**Researcher**: tha-hammer
**Git Commit**: ebf00a35e6af11cd085ce4928e589a5b983b2e13
**Branch**: main
**Repository**: SWE-AF

## Research Question

Confirm a two-part research claim against current source: (P1) the verify→fix
loop has no recovery for "can't verify acceptance criteria"; (P2) fix-DAG
execution stomps the main DAG checkpoint. Verify every `file:line` citation and
flag any that do not match the code as it exists today.

## Summary

Both root causes are **confirmed against source**, and the seven structural
citations that matter (loop bounds, the single guard, the inner `execute`, the
checkpoint path, the seven save sites, the resume path) are all accurate. Three
secondary details in the original write-up are slightly off and are corrected
below:

1. **Gap 2 parenthetical is wrong.** "still-failing criteria recorded as debt …
   only happens when `fix_issues` is empty, line 1033" — line 1033 is an `else:`
   that only logs (`app.note`); it appends no debt. The only debt append is
   `app.py:1003-1010`, which records the generator's `debt_items`, not the
   `failed_criteria`, and runs before the `fix_issues` branch. The *core* claim
   (terminal exhaustion at line 968 breaks before recording the still-failing
   criteria as debt) is correct.
2. **`fix_generator.py:20` → `:25`.** The "attempted and failed repeatedly →
   Record as debt" line is `prompts/fix_generator.py:25`. Line 20 is the start
   of the enclosing "Analyze feasibility" bullet.
3. **`execution_agents.py:1297` → `:1298`.** `async def generate_fix_issues` is
   at line 1298 (decorator `@router.reasoner()` at 1296).

One recoverability nuance (P2): the "9-issue `dag_result` survives in memory"
claim is true **only while the process is killed mid-`execute(fix_plan)`** (the
`await` at `app.py:1024` has not returned). The code comment at `app.py:944-946`
explicitly states the loop "can overwrite `dag_result` with fix-execution
results" — i.e. once the fix `execute` returns, line 1024 reassigns `dag_result`
to the fix result. The 2-hour scenario (burn *inside* `execute(fix_plan)`) is
consistent with the in-memory claim precisely because the `await` never returned.

## Detailed Findings

### P1 — Verify→fix loop (`swe_af/app.py:951-1037`)

The loop is `for cycle in range(cfg.max_verify_fix_cycles + 1)` at
`app.py:952`. Confirmed structure:

| Claim | Citation | Verified |
|---|---|---|
| Loop bounds / body | `app.py:952-1035` | ✅ exact |
| Single termination guard = cycle count | `app.py:968` (`verification.get("passed") or cycle >= cfg.max_verify_fix_cycles`) | ✅ only guard |
| `max_verify_fix_cycles` default 1 | `execution/schemas.py:697` (`max_verify_fix_cycles: int = 1`) | ✅ exact |
| Inner full DAG run per cycle | `app.py:1024` (`await app.call(f"{NODE_ID}.execute", plan_result=fix_plan, …)`) | ✅ exact |
| Per-agent coding-loop cost | `execution/schemas.py:1005` (`agent_timeout_seconds: int = 2700  # 45 min`) | ✅ (also defined at `schemas.py:730`) |

The "the cost is the loop body, not the loop count" insight holds: `execute` at
`app.py:1024` is the same node called for the main build at `app.py:933`, so one
fix cycle is a full DAG run subject to `agent_timeout_seconds` (2700s) × retries
× advisor. `max_verify_fix_cycles=1` bounds cycles to 2 (cycle 0 + cycle 1) but
does not bound wall-clock.

**Gap 1 — no convergence detection.** `failed_criteria` is recomputed fresh each
cycle at `app.py:972-975` from `verification["criteria_results"]`. Nothing stores
or compares the prior cycle's set. The fix-generator entry point
`generate_fix_issues` (`reasoners/execution_agents.py:1298`) and the prompt
builder `fix_generator_task_prompt` (`prompts/fix_generator.py:55-66`) take
`failed_criteria`, `dag_state_summary`, `prd` only — **no cross-cycle history
parameter**. The prompt instructs "attempted and failed repeatedly → Record as
debt" (`prompts/fix_generator.py:25`), but the agent is never given the data to
know what repeated. ✅ Confirmed.

**Gap 2 — no accept-partial terminal.** On the terminal cycle, `cycle >=
cfg.max_verify_fix_cycles` is true at `app.py:968` and the loop `break`s
**before** reaching the `failed_criteria` computation (972) or any debt append.
`success = verification.get("passed", False)` at `app.py:1037` is therefore
`False`, and the still-failing criteria are never recorded as debt. ✅ Core claim
confirmed. ⚠️ Correction: the original parenthetical attributing debt recording
to `line 1033` is wrong — `app.py:1033-1034` (`else:`) only emits an `app.note`;
the actual debt append is `app.py:1003-1010` and records the generator's
`debt_items`, not `failed_criteria`.

**Gap 3 — no time-budget awareness.** A repo-wide grep for
`monotonic|time.time|deadline|elapsed` in `swe_af/app.py` returns **nothing** —
there are zero time checks in the loop (or the file). ✅ Confirmed. The 7200s cap
is external (AgentField, not in this repo).

### P2 — Checkpoint stomping (`swe_af/execution/dag_executor.py`)

| Claim | Citation | Verified |
|---|---|---|
| Single fixed checkpoint path | `dag_executor.py:683-685` (`os.path.join(dag_state.artifacts_dir, "execution", "checkpoint.json")`) | ✅ exact, depends only on `artifacts_dir` |
| Unconditional overwrite | `dag_executor.py:694` (`with open(path, "w") as f:`) — no existence/size guard | ✅ exact |
| `_save_checkpoint` def | `dag_executor.py:688` | ✅ exact |
| 7 save sites | `dag_executor.py:1436, 1505, 1517, 1557, 1676, 1734, 1799` | ✅ exactly 7, all match |
| Fix plan reuses `artifacts_dir` | `app.py:1021` (`"artifacts_dir": plan_result.get("artifacts_dir", artifacts_dir)`) | ✅ exact |
| Fix `execute` passes no `build_id` | `app.py:1024-1031` (no `build_id` kwarg; contrast main `execute` at `app.py:940` which passes `build_id=build_id`) | ✅ confirmed |
| `resume_build` reads same hardcoded path | `app.py:2014` (`plan_path = os.path.join(base, "execution", "checkpoint.json")`) | ✅ exact |

Mechanism confirmed end-to-end: the fix `execute` (`app.py:1024`) → `run_dag`
(`dag_executor.py:1352`) → `_init_dag_state` (`dag_executor.py:709`) defaults
`build_id=""`, and the checkpoint path ignores `build_id` (only `artifacts_dir`),
so the smaller fix-DAG's `_save_checkpoint` writes over the parent's
`checkpoint.json` via the unconditional `open(path, "w")`. `resume_build`
(`app.py:1999`) then reconstructs a plan from that stomped checkpoint
(`app.py:2025-2040`), i.e. resumes the fix-DAG.

**Recoverability.**
- *In memory*: the outer `build()` local `dag_result` holds the real (9-issue)
  results **only until** `app.py:1024` returns — at which point it is reassigned
  to the fix-execution result. The comment at `app.py:944-946` documents this
  overwrite. A kill *during* `execute(fix_plan)` leaves the 9-issue `dag_result`
  intact in memory (await never returned); a completed fix cycle does not.
- *On disk*: no backup, no namespacing, no history — the parent `DAGState` is
  gone once stomped. Git branches and issue `.md` files are written elsewhere and
  survive; the DAG record (completed/failed/debt/replan/merge state) does not.

## Code References

- `swe_af/app.py:952` - `for cycle in range(cfg.max_verify_fix_cycles + 1)` — verify→fix loop head
- `swe_af/app.py:968` - the loop's only termination guard (passed OR cycle ≥ max)
- `swe_af/app.py:972-975` - `failed_criteria` recomputed fresh each cycle
- `swe_af/app.py:1003-1010` - debt append from generator `debt_items` (the only debt write in the loop)
- `swe_af/app.py:1024-1031` - inner fix `execute`, no `build_id`, reused `artifacts_dir`
- `swe_af/app.py:1033-1034` - `else:` log-only branch (no debt append — corrects original claim)
- `swe_af/app.py:944-946` - comment: loop "can overwrite `dag_result` with fix-execution results"
- `swe_af/app.py:1037` - `success = verification.get("passed", False)`
- `swe_af/app.py:2014` - `resume_build` hardcoded checkpoint path
- `swe_af/execution/schemas.py:697` - `max_verify_fix_cycles: int = 1`
- `swe_af/execution/schemas.py:1005` - `agent_timeout_seconds: int = 2700`
- `swe_af/execution/dag_executor.py:683-685` - `_checkpoint_path` (artifacts_dir-only)
- `swe_af/execution/dag_executor.py:688-697` - `_save_checkpoint`, unconditional `open("w")`
- `swe_af/execution/dag_executor.py:1436,1505,1517,1557,1676,1734,1799` - 7 `_save_checkpoint` sites
- `swe_af/reasoners/execution_agents.py:1298` - `generate_fix_issues` (corrects 1297)
- `swe_af/prompts/fix_generator.py:25` - "failed repeatedly → Record as debt" (corrects line 20)
- `swe_af/prompts/fix_generator.py:55-66` - `fix_generator_task_prompt` signature (no cross-cycle history)

## Architecture Documentation

- The verify→fix loop and the DAG executor communicate through one mutable
  `dag_result` dict in `build()` and one fixed-path JSON checkpoint on disk.
- `execute` is a single reusable node target (`{NODE_ID}.execute`) invoked for
  both the main build and each fix cycle; the only call-site difference relevant
  here is that the fix invocation omits `build_id` and `execute_fn_target` /
  `workspace_manifest` is the same dict.
- Checkpoint identity is keyed solely on `artifacts_dir`; there is no per-DAG or
  per-cycle namespacing, and no read-before-write guard.

## Open Questions

- Whether any external caller (AgentField) sets `max_verify_fix_cycles > 1` in
  practice — not determinable from this repo.
- Exact kill timing of the observed 2-hour run (mid-`execute` vs. completed fix
  cycle) determines which in-memory state the downstream/PR steps actually saw;
  not recoverable from source alone.
