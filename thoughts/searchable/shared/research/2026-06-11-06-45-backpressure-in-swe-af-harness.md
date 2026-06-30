---
date: 2026-06-11T06:45:52-04:00
researcher: maceo
git_commit: ebf00a35e6af11cd085ce4928e589a5b983b2e13
branch: main
repository: SWE-AF
topic: "Does explicit 'backpressure' (deterministic, fail-loud verification loops) exist in the SWE-AF harness — and where could it be added?"
tags: [research, codebase, backpressure, verification-loop, deterministic-checks, llm-as-judge, dag-executor, ci-gate, coder, harness]
status: complete
last_updated: 2026-06-11
last_updated_by: maceo
last_updated_note: "Added Follow-up Research — command discovery (seam #1 blocker) and safe harness-visible Bash"
---

# Research: Backpressure in the SWE-AF Harness

**Date**: 2026-06-11 06:45 -0400
**Researcher**: maceo
**Git Commit**: ebf00a35e6af11cd085ce4928e589a5b983b2e13
**Branch**: main
**Repository**: SWE-AF

## Research Question

The prompting-research documents
([2026-06-11-06-35](thoughts/searchable/shared/research/2026-06-11-06-35-coding-specific-prompting-for-swe-af-agents.md) §2,
[2026-06-11-05-51](thoughts/searchable/shared/research/2026-06-11-05-51-swe-af-prompts-and-prompting-wisdom.md))
name **"backpressure"** as a load-bearing coding-agent concept, sourced from the
AI That Works episode `2026-02-10-agentic-backpressure-deep-dive.md`:

> "Backpressure is any mechanism that gives the model a way to fix its own
> mistakes without dragging you into the loop" — compilers, type checks, unit
> tests that **run automatically, fail loudly, deterministically**, and the model
> reads the failure and tries again. Cheapest-check-first: compiler → type → unit
> → integration → e2e → human. "Compiler errors are the gold standard." It "must
> be deterministic, not LLM-as-judge" — "you can accidentally steer a model; you
> cannot accidentally steer a type checker."

**Two parts:** (1) deduce whether backpressure (by that definition) exists in the
SWE-AF harness today; (2) per the user's explicit request, research how an
**explicit** backpressure layer could be added. Part 1–3 are documentarian (what
IS). [Part 4](#part-4--how-explicit-backpressure-could-be-added-answering-the-explicit-request)
is the requested forward-looking exploration, grounded in existing code seams.

## Summary

- **Backpressure, by the AITW definition, exists in exactly one place in the
  harness: the post-PR CI gate** (`swe_af/execution/ci_gate.py` driven by
  `swe_af/app.py:_run_ci_gate`). It is textbook backpressure — it shells out to
  the `gh` CLI, classifies real GitHub Actions results by **string field
  comparison (no LLM)**, fetches the **real failure logs**, feeds them into a
  **bounded fixer loop**, and re-polls. `run_ci_watcher` is documented in-code as
  "Deterministic — uses the `gh` CLI and does not invoke an LLM"
  ([execution_agents.py:1535](swe_af/reasoners/execution_agents.py#L1535)).
- **Everywhere upstream of the PR, the verification loops are LLM-mediated, not
  deterministic.** The harness has the *shape* of backpressure — a coder→review→fix
  inner loop, an issue-advisor middle loop, a replanner outer loop, and a
  post-DAG verify→fix loop — but every gating verdict in those loops is an
  **LLM-authored boolean**, not a subprocess exit code. By the AITW criterion
  ("must be deterministic, not LLM-as-judge"), these are *observable loops without
  backpressure*.
- **The single most load-bearing signal — "did the tests pass?" — is
  self-attested by the model.** `CoderResult.tests_passed` is annotated in the
  schema as `# Self-reported: did tests pass?`
  ([schemas.py:421](swe_af/execution/schemas.py#L421)), and the coder prompt itself
  says the field is "informational — the reviewer will independently verify"
  ([coder.py:75](swe_af/prompts/coder.py#L75)). The "independent" verifier is
  another LLM agent, not a deterministic runner.
- **The harness never runs the target project's test/build/lint/typecheck as a
  subprocess.** A whole-repo search found the harness shells out only for: git
  operations, the `gh` CLI (CI gate + PR ops), and launching the Codex CLI agent
  session. `pytest`/`go test`/`ruff`/`mypy`/`tsc` etc. appear **only as strings
  inside prompt text** instructing the LLM sub-agent to run them in its own Bash
  tool — whose raw stdout/stderr the harness never sees (it sees only the model's
  free-text `test_summary` and self-reported boolean).
- **Net deduction:** SWE-AF has **one** real backpressure mechanism, and it sits at
  the **end** of the pipeline (after a PR is opened) — i.e. cheapest-check-*last*,
  the inverse of the AITW "cheapest-check-first" ladder. The inner coding loop,
  where a deterministic check would be cheapest and catch the most, has none.

### One-line answer

> **Partial.** Deterministic, fail-loud backpressure exists *once* — the post-PR
> CI gate. The inner per-issue coding loop, the post-DAG verify→fix loop, and the
> integration-test gate are all **LLM-as-judge**, so by the AITW definition they
> are verification *loops* without *backpressure*.

---

## Part 1 — What "backpressure" means here (criteria)

From the AITW deep-dive as recorded in the companion research, a mechanism is
backpressure iff it is:

1. **Automatic** — runs without a human prompting it each time.
2. **Fail-loud** — produces a legible failure the model can read.
3. **Deterministic** — verdict from an exit code / parsed machine field, *not* an
   LLM judgment ("you cannot accidentally steer a type checker").
4. **Looped** — the failure feeds back into another attempt, bounded.
5. **Cheapest-first** — ordered compiler → type → unit → integration → e2e → human.

The rest of this document holds each SWE-AF loop against criteria 3 (deterministic)
and 5 (ordering), since the harness clearly satisfies 1, 2, and 4 structurally.

---

## Part 2 — The loops that exist (structure)

The harness is four nested/sequential loops. All bounds are config-driven
(`ExecutionConfig`/`BuildConfig`, `swe_af/execution/schemas.py`).

| Loop | Location | Bound (default) | Gating verdict | Verdict source |
|---|---|---|---|---|
| Inner coding loop (coder → review → fix) | `coding_loop.py:516` `run_coding_loop` | `max_coding_iterations` = 5 ([schemas.py:705](swe_af/execution/schemas.py#L705)) | `approve` / `fix` / `block` | **LLM** (reviewer / synthesizer) |
| Middle: issue advisor | `dag_executor.py:838` `_execute_single_issue` | `max_advisor_invocations` = 2 ([schemas.py:734](swe_af/execution/schemas.py#L734)) | RETRY_*/SPLIT/ESCALATE/DEBT | **LLM** (`run_issue_advisor`) |
| Outer: replanner | `dag_executor.py:1714` in `run_dag` | `max_replans` = 2 ([schemas.py:695](swe_af/execution/schemas.py#L695)) | CONTINUE/MODIFY/REDUCE/ABORT | **LLM** (`run_replanner`) |
| Post-DAG verify→fix | `app.py:1013-1131` | `max_verify_fix_cycles` = 2 ([schemas.py:697](swe_af/execution/schemas.py#L697)) | `passed` bool | **LLM** (`run_verifier`) |
| Post-PR CI gate | `app.py:209` `_run_ci_gate` | `max_ci_fix_cycles` = 2 ([schemas.py:720](swe_af/execution/schemas.py#L720)) | passed/failed | **Deterministic** (`gh` CLI) |

### Inner coding loop ([coding_loop.py:516-895](swe_af/execution/coding_loop.py#L516))

```
for iteration in range(start, max_iterations + 1):        # coding_loop.py:602
    coder_result = run_coder(issue, feedback=feedback)     # :616
    # default path: reviewer only;  flagged path: QA + reviewer + synthesizer
    action = "approve" | "fix" | "block"
    if action == "approve":  return COMPLETED              # LLM said approved
    if action == "block":    return FAILED_UNRECOVERABLE
    if action == "fix":      feedback = summary + test-failure lines + debt
    if _detect_stuck_loop(history): break                  # :808 (deterministic)
```

The feedback carried into the next coder attempt is the **reviewer's free-text
summary plus structured test-failure lines and blocking-debt items**
([coding_loop.py:802-804](swe_af/execution/coding_loop.py#L802)) — rich text, but
LLM-produced. The one deterministic guard in this loop is `_detect_stuck_loop`
([coding_loop.py:266-279](swe_af/execution/coding_loop.py#L266)): pure Python that
returns `True` when the last 3 iterations are all non-blocking `"fix"` cycles. It
is a **loop-termination** heuristic, not a correctness check — it decides *when to
give up*, not *whether the code works*.

### Post-DAG verify→fix loop ([app.py:1013-1131](swe_af/app.py#L1013))

```
for cycle in range(max_verify_fix_cycles + 1):     # app.py:1013
    verification = run_verifier(...)               # :1015  (LLM agent, Bash tool)
    if verification["passed"]: break               # :1029  (LLM-authored bool)
    failed = _failing_criteria(verification)       # :1033  (filters passed==False)
    fix = generate_fix_issues(failed_criteria=...)  # :1064 (LLM)
    execute(fix_plan)                              # :1118  (re-runs the DAG)
```

Three of the four exit conditions are deterministic Python:
**convergence** (same failing-criteria `frozenset` twice — `_failed_criteria_signature`,
[app.py:479](swe_af/app.py#L479)), **soft deadline**
(`_within_soft_deadline`, [app.py:1099](swe_af/app.py#L1099)), and the **cycle cap**.
But the gate that decides whether a criterion is met at all —
`verification["passed"]` — is the verifier LLM's structured output, and the
per-criterion `evidence` is **model-asserted text**
([verifier.py:72-77](swe_af/prompts/verifier.py#L72)).

---

## Part 3 — Why these loops are *not* backpressure (the determinism gap)

### 3.1 The "tests passed" signal is self-attested

`CoderResult` ([schemas.py:414-425](swe_af/execution/schemas.py#L414)):

```python
class CoderResult(BaseModel):
    files_changed: list[str] = []
    ...
    tests_passed: bool | None = None  # Self-reported: did tests pass?   ← :421
    test_summary: str = ""            # Brief test run output
```

Only `iteration_id` is set by harness code post-call
([execution_agents.py:1026](swe_af/reasoners/execution_agents.py#L1026)); every
other field — including `tests_passed` — is parsed straight from the LLM's
structured output. The coder prompt is explicit that this is not a gate
([coder.py:71-76](swe_af/prompts/coder.py#L71)):

> "Before committing, run the project's test suite… Report `tests_passed` / `test_summary`.
> **This is informational — the reviewer will independently verify.**"

The "independent" verifier is `run_code_reviewer` — another LLM agent
([execution_agents.py:1163](swe_af/reasoners/execution_agents.py#L1163)) — which is
*instructed* to run tests only when `tests_passed` is false/unreported
([code_reviewer.py:25-29](swe_af/prompts/code_reviewer.py#L25)). When the coder
self-reports `true`, the policy is to **trust it**. No subprocess exit code ever
confirms the claim inside the coding loop.

### 3.2 Every in-loop gate is `router.harness`/`router.ai`, not a subprocess

| Reasoner | Gating field | Call | Determinism |
|---|---|---|---|
| `run_coder` | `tests_passed` | `router.harness` ([:1006](swe_af/reasoners/execution_agents.py#L1006)) | LLM self-report |
| `run_qa` | `QAResult.passed` | `router.harness` ([:1083](swe_af/reasoners/execution_agents.py#L1083)) | LLM |
| `run_code_reviewer` | `approved`/`blocking` | `router.harness` ([:1163](swe_af/reasoners/execution_agents.py#L1163)) | LLM |
| `run_qa_synthesizer` | `action`, `stuck` | `router.ai` (no tools) ([:1239](swe_af/reasoners/execution_agents.py#L1239)) | LLM over text |
| `run_verifier` | `VerificationResult.passed` | `router.harness` ([:558](swe_af/reasoners/execution_agents.py#L558)) | LLM |
| `run_integration_tester` | `IntegrationTestResult.passed` | `router.harness` ([:830](swe_af/reasoners/execution_agents.py#L830)) | LLM |
| `run_ci_watcher` | check `bucket` field | `gh` CLI, **no LLM** ([:1526](swe_af/reasoners/execution_agents.py#L1526)) | **Deterministic** |

The QA, reviewer, verifier, and integration-tester agents all *have* a `Bash` tool
and *can* run real commands — but the harness consumes only their final schema
output (a boolean + free text), never the raw exit code or stdout. The agent's
verdict is what the model wrote, which the model could write regardless of what the
subprocess actually returned.

### 3.3 The harness never runs the target's checks itself

Whole-repo search for subprocess execution (excluding tests/thoughts):

- **`swe_af/execution/ci_gate.py`** — `subprocess.run` of `gh pr checks` /
  `gh run view --log-failed` / `gh pr ready`
  ([ci_gate.py:41-50](swe_af/execution/ci_gate.py#L41), [98-110](swe_af/execution/ci_gate.py#L98)).
- **`swe_af/app.py`** — `subprocess.run` of `git` (clone/fetch/checkout/reset/
  merge/push/diff/rev-parse) and `gh` (pr view/edit/api). All git/GitHub plumbing,
  no project test/build.
- **`swe_af/runtime/codex_harness_patch.py`** — `asyncio.create_subprocess_exec`
  to launch the **Codex CLI agent** ([:91-102](swe_af/runtime/codex_harness_patch.py#L91))
  — i.e. starting an LLM coding session, not running checks.
- **`dag_executor.py`, `coding_loop.py`, `execution_agents.py`, `fast/executor.py`** —
  **zero** subprocess calls. All "execution" is `app.call(...)` dispatch to LLM
  reasoners.
- **`swe_af/prompts/**`** — `pytest`/`go test`/`ruff`/`mypy`/`tsc`/`cargo` etc.
  appear only as **instruction strings** inside prompt text.

So the only deterministic machine-truth the harness ingests about code correctness
is the **remote GitHub Actions result**, after a PR exists.

### 3.4 The one real backpressure: the post-PR CI gate

`_run_ci_gate` ([app.py:209-330](swe_af/app.py#L209)) → `watch_pr_checks`
([ci_gate.py:137](swe_af/execution/ci_gate.py#L137)) is genuine backpressure on
all five criteria:

- **Deterministic verdict** — `_classify` returns `"failed"` iff any check's
  `bucket` ∈ `{fail, cancel}`, else `"passed"`; `_is_conclusive` checks for
  `{pending, queued}` ([ci_gate.py:68-82](swe_af/execution/ci_gate.py#L68)). Pure
  string membership over `gh pr checks --json`. No LLM.
- **Real failure logs fed back** — `_fetch_failed_logs` runs
  `gh run view <id> --log-failed`, tails 3000 chars
  ([ci_gate.py:98-110](swe_af/execution/ci_gate.py#L98)), stored in
  `CIFailedCheck.logs_excerpt` and rendered verbatim into the fixer prompt
  ([ci_fixer.py:189-213](swe_af/prompts/ci_fixer.py#L189)).
- **Bounded loop** — `for cycle in range(max_ci_fix_cycles + 1)`
  ([app.py:240](swe_af/app.py#L240)); accumulates `previous_attempts` so the fixer
  sees what's "STILL red" ([ci_fixer.py:168-183](swe_af/prompts/ci_fixer.py#L168)).
- **SHA-anchored, polled** — every `ci_poll_seconds` (30) up to `ci_wait_seconds`
  (1500), anchored to the pushed HEAD SHA
  ([ci_gate.py:231-269](swe_af/execution/ci_gate.py#L231)).

This is the model "reading the failure and trying again" with a deterministic,
fail-loud signal — exactly the AITW pattern. It is also the **only** instance, and
it is **last** in the pipeline (cheapest-check-last).

### 3.5 Merge-conflict state is also deterministic (a second partial signal)

`_attempt_base_merge` ([app.py:1975-2015](swe_af/app.py#L1975)) runs real
`git fetch` / `git merge-base --is-ancestor` / `git merge` and classifies
`clean`/`merged`/`conflict` by exit code, passing `conflicted_files` (from
`git diff --name-only --diff-filter=U`) to `run_pr_resolver`. This is a
deterministic signal, but it gates *PR mergeability*, not code correctness, and
feeds a single LLM resolver pass (no resolver retry loop —
[execution_agents.py:1667-1732](swe_af/reasoners/execution_agents.py#L1667)).

---

## Part 4 — How explicit backpressure could be added (answering the explicit request)

> Documentarian boundary note: Parts 1–3 describe what IS. This part is the
> forward-looking exploration the user explicitly requested ("if not, research how
> we can add an explicit backpressure"). It is options grounded in existing code
> seams, not a committed plan; a `/create_tdd_plan` would formalize a choice.

The gap is narrow and specific: **the harness already has a proven deterministic
backpressure component (`ci_gate.py`) — it is simply applied once, at the end.**
Adding explicit backpressure means moving that *pattern* (deterministic runner →
parsed verdict → real output fed back → bounded loop) earlier and cheaper.

### 4.1 The natural insertion seams

The harness has well-defined joints where a deterministic check could sit between
an LLM attempt and the next gate. Ordered cheapest-first (AITW criterion 5):

| Ladder rung | Where it would attach (existing seam) | Signal it would add |
|---|---|---|
| **Compile / typecheck** | After `run_coder` returns, before the reviewer — `coding_loop.py:616-659` | Run project's build/typecheck as subprocess; non-zero → re-enter coder with raw output as `feedback`, **without spending a reviewer call** |
| **Unit tests** | Replace trust-on-`tests_passed=true` policy ([code_reviewer.py:25-29](swe_af/prompts/code_reviewer.py#L25)) with a harness-level test run | Confirm/deny the coder's self-report deterministically before the reviewer judges quality |
| **Lint** | Same coder-post seam | Cheap fail-loud signal feeding `feedback` |
| **Verifier acceptance** | `app.py:1015-1029` — before/around `run_verifier` | Attach machine-collected build/test output as required evidence, so `passed` is anchored to an exit code, not pure judgment |
| **Integration** | `dag_executor.py:1598-1634` merge gate | Run merged-branch test suite deterministically instead of LLM `IntegrationTestResult.passed` |
| **CI** | Already exists (`ci_gate.py`) | (the proven template) |

### 4.2 The reusable in-repo template

`ci_gate.py` already demonstrates the exact shape an explicit local backpressure
module would take, and it is **already designed for injection**: `CommandRunner`
is an injectable callable type alias
([ci_gate.py:38](swe_af/execution/ci_gate.py#L38)) with `_default_runner` wrapping
`subprocess.run(..., capture_output=True, check=False)`
([ci_gate.py:41-50](swe_af/execution/ci_gate.py#L41)). A local-check module would
mirror this: a runner that executes a configured `test_command`/`build_command`,
a deterministic classifier over the exit code, a tailed-output capture
(`_tail`, [ci_gate.py:92](swe_af/execution/ci_gate.py#L92)), and a bounded
feed-back loop — structurally identical to `watch_pr_checks`, but local and earlier.

### 4.3 Open design questions this would surface (for a follow-on plan)

1. **Where do the commands come from?** The harness is language-agnostic and the
   target repo is cloned at runtime; there is no place today where the harness
   knows the project's test/build command. A backpressure layer needs a source —
   config field, environment-scout output
   ([pipeline.py:240](swe_af/reasoners/pipeline.py#L240) already negotiates
   environment), or a deterministic detector (presence of `pyproject.toml`/`go.mod`/
   `package.json`). This is the central unknown.
2. **Where does it run?** The coder's Bash runs *inside* the provider's agent
   session (claude-code/codex/opencode), not in a harness-visible CWD. A
   harness-level runner needs a working tree it can `cwd` into — the per-issue git
   worktree ([dag_executor.py:1526-1537](swe_af/execution/dag_executor.py#L1526))
   is the candidate.
3. **Sandbox/safety.** Running arbitrary cloned-repo test commands at the harness
   level is a new trust boundary (the Docker container,
   [docker-compose.yml](docker-compose.yml), is the existing isolation).
4. **Feedback format.** The proven pattern is "raw tail into the next prompt as
   `feedback`" (CI fixer does exactly this). The coder loop's `feedback` channel
   ([coding_loop.py:802-804](swe_af/execution/coding_loop.py#L802)) already accepts
   free text, so wiring is low-friction.
5. **Interaction with checkpoint stomp.** The verify→fix loop already overwrites
   checkpoints (memory [[swe-af-replanner-vs-resume]];
   [verify-fix-loop-checkpoint-stomp research](thoughts/searchable/shared/research/2026-06-05-15-00-verify-fix-loop-checkpoint-stomp.md));
   an added deterministic gate would need to respect that recovery work.
6. **`clone-prompts-verbatim` constraint** (companion doc Part C) bounds how much
   the coder/reviewer *prompts* can change; note that adding deterministic
   backpressure is primarily a **harness/code change**, not a prompt change —
   which is itself the AITW thesis ("move control flow into the harness").

---

## Code References

- `swe_af/execution/schemas.py:421` — `CoderResult.tests_passed` `# Self-reported`
- `swe_af/prompts/coder.py:71-76` — "informational — the reviewer will independently verify"
- `swe_af/execution/coding_loop.py:516-895` — inner coding loop; `:266` `_detect_stuck_loop` (deterministic termination)
- `swe_af/execution/coding_loop.py:802-804` — feedback assembled from LLM summary + test lines
- `swe_af/reasoners/execution_agents.py:558,1083,1163,1239` — verifier/QA/reviewer/synthesizer LLM call sites
- `swe_af/reasoners/execution_agents.py:1526-1575` — `run_ci_watcher` ("Deterministic — does not invoke an LLM")
- `swe_af/execution/ci_gate.py:38-110` — injectable `CommandRunner`, `_default_runner`, `_classify`, `_fetch_failed_logs` (the backpressure template)
- `swe_af/app.py:209-330` — `_run_ci_gate` bounded fix loop
- `swe_af/app.py:1013-1131` — post-DAG verify→fix loop (LLM-gated)
- `swe_af/app.py:1975-2015` — deterministic merge-conflict classification
- `swe_af/execution/dag_executor.py:1500-1796` — DAG outer loop; `:838` advisor middle loop; `:1714` replan gate

## Architecture Documentation

- **One deterministic correctness gate (CI), at the end.** Every earlier gate is
  an LLM verdict (`router.harness` agentic call or `router.ai` single call) whose
  boolean output the harness trusts.
- **`router.harness` vs `router.ai`**: `harness` = full agentic session with a tool
  list (incl. `Bash`); `ai` = single tool-less inference. Both return structured
  output the harness consumes as the verdict; neither surfaces subprocess exit
  codes to the harness.
- **Injectable runner pattern** (`ci_gate.CommandRunner`) is the repo's established
  shape for deterministic, testable subprocess gating.
- **Cheapest-check ordering is inverted** relative to the AITW ladder: the only
  deterministic check (CI) is the most expensive/slowest and runs last.

## Historical Context (from thoughts/)

- `thoughts/searchable/shared/research/2026-06-11-06-35-coding-specific-prompting-for-swe-af-agents.md` §2 — frames backpressure as "the product"; this doc is its codebase-grounded counterpart.
- `thoughts/searchable/shared/research/2026-06-11-05-51-swe-af-prompts-and-prompting-wisdom.md` — notes the coder "self-validates then reports tests_passed" and downstream gates are LLM reasoners.
- `thoughts/searchable/shared/research/2026-06-05-15-00-verify-fix-loop-checkpoint-stomp.md` — prior research on the verify→fix loop; raised the `tests_passed`/LLM-as-judge question this doc resolves.
- `thoughts/searchable/shared/plans/2026-06-05-15-25-tdd-verify-loop-checkpoint-recovery.md` (COMPLETE) — verify→fix recovery + checkpoint-stomp guard.
- Memory [[swe-af-replanner-vs-resume]] — replanner handles execution failures only; verify→fix overwrites checkpoints.

## Related Research

- `thoughts/searchable/shared/research/2026-06-11-06-35-coding-specific-prompting-for-swe-af-agents.md`
- `thoughts/searchable/shared/research/2026-06-11-05-51-swe-af-prompts-and-prompting-wisdom.md`
- `thoughts/searchable/shared/research/2026-06-05-15-00-verify-fix-loop-checkpoint-stomp.md`

## Open Questions

1. **Command discovery** — what is the authoritative source for a cloned repo's
   test/build/typecheck command? (config field vs. environment-scout vs. detector)
2. **Execution locus** — harness runs the check in the per-issue worktree, or the
   provider session keeps running them and the harness starts parsing the raw
   output instead of trusting the boolean?
3. **Which rung first?** Compile/typecheck (cheapest, highest signal-per-cost) vs.
   confirming `tests_passed` deterministically (closes the biggest trust gap).
4. **Measurement** — would adding a rung be graded against real build runs (per the
   companion doc's "evals from observed behavior" open question)?

---

## Follow-up Research [2026-06-11 06:55 -0400]

**Prompts:** (1) research the command-discovery question (§4.3 Q1, the seam-#1
blocker) deeper; (2) research how to give a safe harness-visible Bash, suspecting
Docker makes it straightforward; safety is mostly baked in (worktree + container).

### Headline: both blockers are smaller than §4.3 implied

- **Command discovery is *not* greenfield.** The PM prompt already **mandates**
  that acceptance criteria be runnable commands, and the issue-writer already emits
  a structured "Verification Commands" block. The commands are being authored
  today — they are just **trapped in free-text fields** (`list[str]` / `str`), with
  no typed field the harness reads and runs.
- **Harness-visible Bash already exists in all but name.** The harness already
  holds each issue's worktree path in a variable and passes it as `cwd=` to every
  agent. The harness process and the checked-out code share **one container
  filesystem**. `ci_gate.CommandRunner` is a tested, injectable subprocess-runner
  template. A local check = `_default_runner(cmd, worktree_path)` — the CI-gate
  pattern pointed at the worktree instead of `gh`.
- **One genuinely new wrinkle:** the harness installs **no** target-project
  dependencies (left entirely to the agent's Bash session), so a harness-level
  `pytest` would need deps already present in that worktree.

### A. Command discovery — the commands already exist, untyped

**A.1 The planner is already told to produce commands.**
`product_manager.py:57-59` — verified verbatim:

> "**Machine-verifiable acceptance criteria**: Every criterion MUST map to a
> command. Patterns: `cargo test --test <name>`, `stat -f%z <file> <= N`,
> `hyperfine <cmd> --export-json | jq '.results[0].mean < 0.001'`. Never:
> 'performance is acceptable' or 'code is clean.'"

`issue_writer.py:71-83` — the issue-file template already has typed-looking slots:

```
### Run Command
`<exact command to run these tests>`
## Verification Commands
- Build: `<exact command>`
- Test:  `<exact test command>`
- Check: `<command that proves AC passes>`
```

**A.2 …but the schema fields are untyped free text.** The commands land in fields
the harness cannot mechanically extract:
- `PRD.acceptance_criteria: list[str]` ([reasoners/schemas.py:14](swe_af/reasoners/schemas.py#L14))
- `PlannedIssue.acceptance_criteria: list[str]` ([reasoners/schemas.py:84](swe_af/reasoners/schemas.py#L84))
- `PlannedIssue.testing_strategy: str = ""  # Test file paths, framework, coverage`
  ([reasoners/schemas.py:90](swe_af/reasoners/schemas.py#L90))
- The issue-writer "Run Command" / "Verification Commands" go into the **`.md`
  issue file as prose**, with no corresponding typed schema field.

There is **no** `test_command`/`build_command` field in `BuildConfig` or
`ExecutionConfig`, and **no** `SWE_TEST_COMMAND`-style env var
(only `SWE_DEFAULT_RUNTIME/MODEL`, `SWE_AF_GIT_EMAIL/NAME` exist). The one
`run_command` key seen in a real `checkpoint.json` is JSON the planner LLM nested
*inside* the `testing_strategy` string — not a validated field
([examples/pyrust/.artifacts-v2/execution/checkpoint.json:599](examples/pyrust/.artifacts-v2/execution/checkpoint.json#L599)).

**A.3 The environment-scout does not help here.** It reads manifests
(`pyproject.toml`/`go.mod`/`package.json`) but **only** to detect 9 hard-coded
third-party *services* for credential negotiation
([hitl/services.py:56-156](swe_af/hitl/services.py#L56)). It records **zero**
build/test/lint commands and does **no** language detection; `ScoutResult`
([hitl/scout_schema.py:25-59](swe_af/hitl/scout_schema.py#L25)) has no command
field, and its return value is discarded downstream
([app.py:1486-1495](swe_af/app.py#L1486)) — only the injected credentials survive.

**A.4 Three discovery options (increasing structure / decreasing LLM trust):**

| Option | Mechanism | Cost | Determinism |
|---|---|---|---|
| **(a) Parse existing artifacts** | Pull the command out of `testing_strategy` / the issue-file "Run Command" block already being written | Lowest — no schema change; parse free text | Low — format is LLM-authored, brittle |
| **(b) Add a typed planner field** | Add e.g. `verify_command: str` (or `acceptance_criteria` → list of `{text, command}`) to `PlannedIssue`/PRD; the PM/sprint-planner already author the content, so this is mostly a schema + prompt-slot change | Low–medium — schema + one prompt edit | Medium — still LLM-produced, but in a stable slot |
| **(c) Deterministic detector** | Harness inspects manifest files in the worktree (`pyproject.toml`→`pytest`, `go.mod`→`go test ./...`, `package.json` `scripts.test`→`npm test`, `Makefile`→`make test`) | Medium — new detector module | High — pure code, no LLM |

(b) and (c) compose: detector as the deterministic default, planner field as an
override. Note (b) is a schema/prompt change that touches "proven" prompts, so the
`clone-prompts-verbatim` constraint applies; (c) is pure harness code and sidesteps
it (the AITW "harness, not prompt" thesis).

### B. Safe harness-visible Bash — already 90% present

**B.1 The harness already knows the working directory.** Each issue dict carries
`worktree_path`, injected at
[dag_executor.py:194-198](swe_af/execution/dag_executor.py#L194), persisted to
`dag_state.all_issues` ([dag_executor.py:1531-1537](swe_af/execution/dag_executor.py#L1531))
so it survives checkpointing, and passed as `cwd=worktree_path` to **every** agent
call — verified at [execution_agents.py:1013](swe_af/reasoners/execution_agents.py#L1013)
(`run_coder`), and likewise `run_qa` (:1090), `run_code_reviewer` (:1170),
`run_issue_advisor` (:235). The same absolute path is therefore available to a
harness-level `subprocess.run(cmd, cwd=worktree_path)`.

- Path shape: `/workspaces/<repo>-<build_id>/.worktrees/issue-<BUILD_ID>-<NN>-<name>`
  (clone path [app.py:546-548](swe_af/app.py#L546); `worktrees_dir` =
  `repo_path/.worktrees` [dag_executor.py:790](swe_af/execution/dag_executor.py#L790);
  naming [workspace.py:30-31](swe_af/prompts/workspace.py#L30)).
- Stable across coder→reviewer for an issue; the **verifier** uses
  `repo_path` (the merged integration branch), not the per-issue worktree — so a
  verifier-stage check would target `dag_state.repo_path`.

**B.2 The container makes it straightforward — the user's suspicion confirmed.**
The harness Python service (`python -m swe_af`, [Dockerfile:108](Dockerfile#L108),
`WORKDIR /app`) and the cloned code under `/workspaces`
([Dockerfile:97](Dockerfile#L97), `mkdir -p /workspaces`) are the **same container
filesystem** — no cross-container hop, no copy. `git`, `node`/`npm`, `python3.12`,
`uv`, `gh`, `jq` are installed in the image ([Dockerfile:10-90](Dockerfile#L10)).
The harness already runs `subprocess.run(..., cwd=repo_path)` for all git ops
([app.py:599-617](swe_af/app.py#L599)), so a test runner is the identical shape.

**B.3 The runner template is in-repo and tested.** `ci_gate.CommandRunner`
([ci_gate.py:38](swe_af/execution/ci_gate.py#L38)) is an injectable
`Callable[[Sequence[str], str], CompletedProcess]`; `_default_runner` wraps
`subprocess.run(list(cmd), cwd=cwd or None, capture_output=True, text=True,
check=False)` ([ci_gate.py:41-50](swe_af/execution/ci_gate.py#L41)). The
`watch_pr_checks` loop injects `runner` / `sleep` / `now`
([ci_gate.py:137-169](swe_af/execution/ci_gate.py#L137)) and is unit-tested with a
scripted fake runner + fake clock
([tests/test_ci_gate.py:27-81](tests/test_ci_gate.py#L27)). A local check module
reuses this verbatim with `cwd=worktree_path` and a real test command instead of
`gh`. Output capture + `_tail(…, 3000)` ([ci_gate.py:92](swe_af/execution/ci_gate.py#L92))
already produces exactly the failure-tail format a fixer prompt consumes.

**B.4 Safety surface (user is right — mostly baked in).**
- **Worktree isolation**: each issue mutates only its own `.worktrees/issue-…`
  tree; a check there can't corrupt siblings.
- **Container isolation**: the whole build runs in the Docker container
  ([docker-compose.yml](docker-compose.yml)); `/workspaces` is a named volume.
- **Codex already sandboxes**: `--sandbox workspace-write`
  ([codex_harness_patch.py:165-171](swe_af/runtime/codex_harness_patch.py#L165)).
- **Residual notes (not blockers):** the harness and the build share one
  filesystem (harness at `/app`, repo at `/workspaces` — already the status quo, no
  new isolation lost); a runaway/hanging check needs the same `wait_seconds`/
  timeout injection `ci_gate` already provides; arbitrary cloned-repo command
  execution is a trust input, but it is the *same* command the agent's Bash already
  runs unsandboxed today.

**B.5 The one genuinely new wrinkle — dependency setup.** The harness installs
**no** target-project dependencies anywhere (no `pip install`/`npm install`/
`go mod download` in the Dockerfile, `app.py`, or the executor) — it installs only
its *own* deps via `uv pip install --system` ([Dockerfile:86-90](Dockerfile#L86)).
Target-dep setup is left entirely to the agent's Bash session. So a harness-level
`pytest`/`go test` in a worktree would only succeed if deps are already present.
Mitigations to weigh in a plan:
1. Run the check **immediately after the coder agent session** (which just set up
   the env in that worktree) rather than cold.
2. Have the runner **detect+run install first** (the same manifest detector from
   A.4(c): `uv sync`/`pip install -e .`, `npm ci`, `go mod download`).
3. Capture the agent's own setup commands (`agent_retro`/`codebase_learnings`
   already flow to shared memory) and replay them.

### C. Net answer to the follow-up

The seam-#1 "blocker" decomposes into one small schema/detector decision and one
near-trivial wiring task:

- **Command discovery** → not a research gap; it's a **typing** gap. Either parse
  what the planner already writes (A.4a), add a typed slot the planner already has
  content for (A.4b), or detect from manifests (A.4c). Recommend **(c) detector as
  deterministic default + (b) optional planner override** — keeps the gold-standard
  signal deterministic and sidesteps `clone-prompts-verbatim`.
- **Safe harness Bash** → reuse `ci_gate.CommandRunner` with `cwd=worktree_path`;
  the container + worktree already supply the safety the user expected. The only
  real design question is **dependency provisioning** (B.5), best solved by running
  the check right after the coder session and/or a manifest-driven install step.

### Follow-up Code References

- `swe_af/prompts/product_manager.py:57-59` — "Every criterion MUST map to a command"
- `swe_af/prompts/issue_writer.py:71-83` — "Run Command" / "Verification Commands" template (prose, no typed field)
- `swe_af/reasoners/schemas.py:14,84,90` — `acceptance_criteria: list[str]`, `testing_strategy: str` (untyped command homes)
- `swe_af/hitl/scout_schema.py:25-59`, `hitl/services.py:56-156` — scout = credentials only, no commands/lang detection
- `swe_af/reasoners/execution_agents.py:1013` — `cwd=worktree_path` (harness already holds the working dir)
- `swe_af/execution/dag_executor.py:194-198,790,1531-1537` — `worktree_path` injection + persistence; `.worktrees` layout
- `swe_af/app.py:546-548,599-617` — clone path; existing `subprocess.run(cwd=repo_path)` git ops
- `swe_af/execution/ci_gate.py:38-50,137-169` — `CommandRunner` template + injectable loop
- `tests/test_ci_gate.py:27-81` — scripted-runner test seam to copy
- `Dockerfile:10-108` — toolchains, `/workspaces`, single-container layout; no target-dep install
- `swe_af/runtime/codex_harness_patch.py:165-171` — Codex `--sandbox workspace-write`
