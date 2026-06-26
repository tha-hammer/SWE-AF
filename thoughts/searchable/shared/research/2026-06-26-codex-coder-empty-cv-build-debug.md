---
date: 2026-06-26
author: claude (Opus 4.8) — for handoff to a Codex-backed debugging agent
topic: "Codex build of Contract View produces an EMPTY 'succeeded' build — coder agent writes 0 files"
tags: [swe-af, codex, codex-harness, build-factory, contract-view, coder-failure, deterministic-check]
status: needs-debug
severity: high
---

# Codex coder produces empty builds — debug briefing (Contract View)

## TL;DR for the Codex agent
The **codex runtime** has run the Exploded-Contract-View build **twice** and both times
reported `status: succeeded` while landing **zero implementation** on the integration
branch (only a `.gitignore` change + a "finalize repo" chore commit). The build PLANS
correctly (PRD + 13 issues, right build order) but the **foundation issue `cv-001`
fails `failed_unrecoverable` after 5 coding-loop iterations with `files_changed: []`** —
the **codex coder agent itself fails** (`complete:false`, `"Coder agent failed for
cv-001-contracts-migration-064"`). Because cv-001 is the DAG root (the 064 migration),
its failure cascades: **12 dependent issues SKIPPED, 0 merged**. The build then "succeeds"
by downgrading all 29 unmet acceptance criteria to `accumulated_debt`
(reason: `"Fix generator failed to analyze"`).

**The same plan built on a CLAUDE node would (and for the sibling AOP/Provenance slices,
did) produce real code.** This is codex-runtime-specific. Please debug the codex harness;
a Claude-backed build of the SAME slice has been fired in parallel to unblock the deliverable.

## Reproduction / identifiers
- Control-plane: `http://localhost:8080` (compose `/tmp/ddd-build/compose.yml`).
- Codex node: container `ddd-build-swe-agent-codex-1`, NODE_ID `swe-planner-codex`, :8006,
  image `swe-af-ddd:codex` (== `:test`, hardened prompts, codex-cli 0.142.0).
- **Failing build:** `exec_20260625_235508_tqixapo4` (run `run_20260625_235508_ms4xj7mg`),
  submitted 2026-06-25T23:55Z, completed 2026-06-26T02:50Z, duration ~2h55m.
  Models: pm/architect/tech_lead/sprint_planner/issue_writer/planning_loop=`gpt-5.5`,
  qa/code_reviewer/verifier=`gpt-5.4`, **coder=`gpt-5.4`**, default=`gpt-5.4-mini`.
- **Prior identical-outcome build:** `exec_20260625_200541_82jkpb5y` (coder was `gpt-5.4-mini`).
  Both empty — so NOT a coder-model-strength issue.
- Clone: `/home/maceo/Dev/cosmic-HR04-slice-contract-view`, integration branch
  `5cb4ed20-exploded-contract-view-integration` (will be reset for the Claude run — the
  evidence below is captured independently, you do not need the clone).

## Saved evidence (do not need the build container live)
- **Full result JSON:** `/tmp/slices/cv2_result.json` (the `/api/v1/executions/<id>` body;
  `result.dag_state` has `failed_issues`, `accumulated_debt`, `all_issues`, etc.).
- **Node log tail (1.2MB):**
  `/home/maceo/.claude/projects/-home-maceo-Dev-SWE-AF/4709d3b3-a812-4dad-aef1-3efddbf27f8a/tool-results/bmd2zk3r0.txt`
  (from `docker logs ddd-build-swe-agent-codex-1 --tail 400` — ⚠️ NEVER run `docker logs`
  without `--tail`/`--since`, it OOM-kills the session).

## What the data shows
`result.dag_state`:
- `all_issues: 13`, `completed_issues: 0`, `failed_issues: 1` (**cv-001**),
  `skipped_issues: 12`, `merged_branches: 0`, `unmerged_branches: 0`.
- `replan_count: 1` (replanner chose `continue` → "retry cv-001 as the blocking
  foundation", did not split/drop), then cv-001 exhausted again.
- `accumulated_debt: 29` items, **all** `severity: high`, **all**
  `reason: "Fix generator failed to analyze"`.

`failed_issues[0]` (cv-001-contracts-migration-064):
- `outcome: failed_unrecoverable`, `attempts: 5`, `files_changed: []`,
  `error_message: "Coding loop exhausted after 5 iterations without approval"`.
- `iteration_history` (5 iters), each `files_changed=0`, `qa_passed=false`,
  `review_approved=false`:
  - **it1, it2:** `Deterministic check failed (source=planned): REQUIRE_TEST_DB=1 npm run
    test:integration -- tests/integration/contract-view-migration-064.test.js` → **exit 1**,
    output tail is a **pg-pool connection error** surfacing in an UNRELATED test
    (`tests/integration/contexts/identity/organization-lifecycle.test.js:33` via
    `node_modules/pg-pool/index.js:45`).
  - **it3, it5:** `Synthesizer failed — defaulting to FIX. QA passed=False, review approved=False.`
  - **it4:** `Synthesizer failed and review has blocking issues — blocking.`
- Node log confirms the coder sub-result: `{"complete": false, "files_changed": [],
  "summary": "Coder agent failed for cv-001-contracts-migration-064", "test_summary":
  "Deterministic check failed ... exit code: 1"}`.

## Two distinct codex-harness failure modes to investigate
1. **The codex CODER agent fails to produce/persist file edits** (`complete:false`,
   `files_changed:[]`, "Coder agent failed"). Across all 5 iterations it wrote **nothing**.
   Candidates:
   - codex sandbox dropping file writes. Runbook gotcha: codex `workspace-write`/`bwrap`
     (mount/user namespaces) can be blocked in-container → **silently drops shell commands
     & file writes**. Current setup uses codex `--full-auto` + compose `security_opt:
     [seccomp:unconfined]`; verify `docker exec ddd-build-swe-agent-codex-1 bash -c
     'unshare --user echo ok'` still prints `ok` **under build load**, and that the coder's
     worktree (`.worktrees/issue-5cb4ed20-01-cv-001-...`) is writable from inside the codex
     exec sandbox.
   - codex `exec --json` / structured-output path erroring before any edit. See
     `swe_af/runtime/codex_harness_patch.py` (the monkeypatch that replaces
     `CodexProvider.execute`; `--output-schema`, prompt via stdin). The `Any`-typed-field
     `invalid_json_schema` trap is documented there — confirm the CODER's schema isn't hitting it.
   - Pull the coder sub-reasoner's own exec logs (search the node log for `reasoner_id`
     ~ `run_coder`/`coder` under `run_20260625_235508_ms4xj7mg`, worktree path
     `.../.worktrees/issue-5cb4ed20-01-cv-001-contracts-migration-064`).
2. **The deterministic-check rung requires a test DB the build container lacks.** The
   planned check `REQUIRE_TEST_DB=1 npm run test:integration` fails at the **pg-pool/DB
   connection** layer (not on a migration assertion). If the codex build node has no
   reachable Postgres / no `DATABASE_URL_TEST`, this check can **never pass even with a
   correct coder**, starving the loop of approval. Decide whether deterministic checks that
   need a DB should (a) provision an ephemeral PG in the node, (b) be gated/skipped when no
   DB is wired, or (c) point at the host `cosmichr-pg` (:5432). Also note "**Synthesizer
   failed**" (the qa_synthesizer, a codex agent) on iters 3-5 — a separate codex agent
   failure worth confirming isn't the same root cause.

## Contrast (why this is codex-specific)
The CLAUDE node (`ddd-build-swe-agent-1`, runtime `claude_code`, Opus-plan/Sonnet-code)
built AOP (budget-variance, merged PR #42) and Provenance (PR #41) with real, substantial
implementations on this same control-plane and target repo. Only codex builds come back empty.

## Pointers
- Harness: `swe_af/runtime/codex_harness_patch.py`, `swe_af/execution/` (DAG, verify→fix,
  deterministic-check rung), `swe_af/prompts/coder.py`.
- Runbook: `docs/BUILD_RUNBOOK.md` §6 watchdog, §8 codex gotchas (bwrap, Any-typed schema,
  `~/.codex` mount).
- Spec the build targets: `cosmic-HR04:specs/architecture/contract-view-MAP.md` (A1–A4).
