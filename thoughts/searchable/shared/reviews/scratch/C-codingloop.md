# Review C — coding_loop.py / run_coding_loop — deterministic gate rung

Repo: /home/maceo/Dev/SWE-AF-baml  branch feat/baml-structured-output @ 6517b17 (HEAD confirmed)
File: swe_af/execution/coding_loop.py
Mode: read-only verification

## Per-line verdicts (actual text quoted)

1. **Line 543 — ACCURATE.**
   `    worktree_path = issue.get("worktree_path", dag_state.repo_path)`

2. **Line 564 — ACCURATE.**
   `    guidance = issue.get("guidance") or {}`

3. **Line 602 — this is the loop header (the `for`).**
   `    for iteration in range(start_iteration, max_iterations + 1):`

4. **Line 616 — ACCURATE (coder result assigned).**
   `            coder_result = await _call_with_timeout(`
   (RHS continues across 616–634: `call_fn("{node_id}.run_coder", issue=…, feedback=feedback, iteration=iteration, …)` wrapped in `_call_with_timeout(..., timeout=timeout, label=…)`.)

5. **Line 659 — ACCURATE (coder artifact saved).**
   `        _save_artifact(dag_state.artifacts_dir, iteration_id, "coder", coder_result)`

6. **Line 662 — ACCURATE.**
   `        if needs_deeper_qa:`
   (Preceded at 661 by the comment `# --- 2. PATH BRANCH ---`.)

7. **Lines 730–735 — ACCURATE (`_save_iteration_state` checkpoint).**
   ```
   _save_iteration_state(dag_state.artifacts_dir, issue_name, {
       "iteration": iteration,
       "feedback": summary,
       "files_changed": files_changed,
       "iteration_history": iteration_history,
   }, build_id=dag_state.build_id)
   ```
   Note: checkpoint stores `"feedback": summary` (the raw summary), NOT the rich `feedback` built later at 802. So on resume, the rich fix-feedback tail is lost.

8. **Lines 785–802 — ACCURATE (`feedback_parts` assembled, joined at 802).**
   - 786 `feedback_parts = [summary]`
   - 787–794 appends QA `test_failures`
   - 795–801 appends blocking review `debt_items`
   - 802 `feedback = "\n".join(feedback_parts)`
   Whole block guarded by `if action == "fix":` at 785; `else: feedback = summary` at 803–804.

9. **Lines 516–524 — function signature region. ACCURATE.**
   ```
   async def run_coding_loop(
       issue: dict,
       dag_state: DAGState,
       call_fn: Callable,
       node_id: str,
       config: ExecutionConfig,
       note_fn: Callable | None = None,
       memory_fn: Callable | None = None,
   ) -> IssueResult:
   ```

## Critical analysis A–E

### A. Insert a rung "between 659 and 662"? — REAL and structurally CLEAN.
659 = coder artifact save. 660 = blank. 661 = comment `# --- 2. PATH BRANCH ---`. 662 = `if needs_deeper_qa:`.
Nothing of substance sits between the save and the branch — just a blank line and a comment. `coder_result` is already populated (616–634) and `files_changed` already updated (654–657). Inserting a deterministic-check rung here, AFTER 659 and BEFORE 661/662, is a clean seam: the coder has run + committed, but no reviewer/QA has been called yet. This is exactly where a red gate that wants to short-circuit the reviewer belongs.

### B. Control flow after 662 — reviewer call + action set/consumed. A red gate CANNOT use `continue`.
- The reviewer/QA is invoked inside the path branch: flagged → `_run_flagged_path(...)` (664–681) returns `action, summary, review_result, qa_result, synthesis_result`; default → `_run_default_path(...)` (690–705) returns `action, summary, review_result`. These helper calls ARE the reviewer/QA LLM calls. So to "not call the reviewer this iteration," the rung must short-circuit BEFORE 662 (confirming A).
- `action` is set ONLY by those two path helpers; it's a plain local str ("approve"/"fix"/"block"). It is consumed at: 715 (history), 738/742 (memory write), 748 (approve→return), 765 (block→return), 785 (fix→build feedback).
- **There is NO `continue` or `break` anywhere in the loop body** (grep of lines 602–848: zero hits). The loop re-enters the coder purely by falling off the bottom of the `for` body to the next `iteration`. So a deterministic rung that wants to "set action=fix, skip reviewer, re-enter coder" CANNOT simply `continue` to skip to the next iteration — there is no `continue` idiom in use here, and a bare `continue` inserted at the rung would BYPASS the memory-write (737–745), the history append (713–721), AND the iteration checkpoint (730–735). To re-enter the coder cleanly the rung must instead set `action="fix"` + `feedback`, and then either (a) introduce a `continue` AND replicate the history/checkpoint bookkeeping it skips, or (b) be structured so control still flows through the existing post-branch bookkeeping. Option (b) means the rung sets `action`/`review_result`/`summary` and lets the path branch be skipped — but the path branch is the thing that ASSIGNS those vars, so you'd need an `if det_red: action=... else: <existing branch>`. That is the clean shape.
- The loop (`for iteration in range(start_iteration, max_iterations + 1):`, line 602) has no explicit `continue`/`break`; every exit is a `return IssueResult(...)`.

### C. `iteration` and a parallel `det_check_attempts` counter — FEASIBLE.
`iteration` is the `for`-loop variable (602), bound per iteration from `range(start_iteration, max_iterations+1)`; never manually incremented. `start_iteration` comes from resume state (586/592). A separate `det_check_attempts` counter is feasible: initialize it next to `feedback`/`iteration_history` (around 583–585, before the loop) and increment inside the rung. `det_check_attempts` currently does NOT exist (grep: none). Caveat: it would NOT survive resume unless added to the `_load_iteration_state`/`_save_iteration_state` payloads (590–595 / 730–735).

### D. `feedback_parts` is a list joined into `feedback`, and `feedback` feeds the NEXT coder call — CONFIRMED.
- `feedback_parts` is a `list` (786) joined to `feedback` via `"\n".join(...)` at 802.
- `feedback` is consumed by the coder on the NEXT loop turn at line 621: `feedback=feedback` is a direct kwarg to `call_fn(f"{node_id}.run_coder", …)` (616–634). So appending a deterministic failure tail to `feedback` before falling through WILL reach the next coder invocation.
- Note the checkpoint at 730–735 saves `summary` as "feedback", not this rich `feedback`; a det rung relying on resume continuity should account for that.

### E. `config` type — ExecutionConfig, ATTRIBUTE access (Pydantic BaseModel). Flag MISSING.
- Signature (521): `config: ExecutionConfig`.
- `ExecutionConfig` is `class ExecutionConfig(BaseModel)` (schemas.py:988) with `model_config = ConfigDict(extra="forbid")` (991). So it is attribute-access (`config.max_coding_iterations` used at 545; `config.coder_model`, `config.ai_provider` used in the coder call) — NOT a dict. `config.enable_deterministic_checks` is the correct access *form*.
- **BUT `enable_deterministic_checks` does NOT exist on ExecutionConfig** (full-repo grep for `enable_deterministic`/`deterministic` finds only an unrelated docstring in swe_af/hitl/services.py). Because of `extra="forbid"`, the field must be ADDED to ExecutionConfig (schemas.py ~1002, e.g. `enable_deterministic_checks: bool = False`) before `config.enable_deterministic_checks` will resolve. Reading it without adding the field raises `AttributeError`; constructing a config that passes the flag in raises a Pydantic validation error due to `extra="forbid"`.

## Bottom line
- 659↔662 insertion: REAL and CLEAN — only a blank line + a comment sit between the coder artifact save (659) and `if needs_deeper_qa:` (662); coder_result/files_changed are ready, no reviewer called yet.
- `config` is an attribute-access Pydantic BaseModel (ExecutionConfig), so `config.enable_deterministic_checks` is the right form — but the field MUST be added first (extra="forbid").
- No `continue`/`break` exists in the loop; re-entry is fall-through. A rung that "sets action=fix and skips the reviewer" must short-circuit the path branch (e.g. `if det_red: action="fix"; … else: <existing 662 branch>`) so it still flows through the history/memory/checkpoint bookkeeping at 713–735, rather than `continue`-ing past it.
