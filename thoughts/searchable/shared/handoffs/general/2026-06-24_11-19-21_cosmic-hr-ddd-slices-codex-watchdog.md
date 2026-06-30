---
date: 2026-06-24T11:19:21-04:00
researcher: tha-hammer
git_commit: cdc0e4d39e124332f1144c62b68ed6161fe6a749
branch: main
repository: SWE-AF
topic: "cosmic-HR DDD slices 3+ build wave: watchdog env bug fixed, codex runtime enabled, reconciliation PR + ops runbook"
tags: [swe-af, cosmic-hr, ddd, vertical-slice, watchdog, codex, agentfield, runbook, reconciliation]
status: complete
last_updated: 2026-06-24
last_updated_by: tha-hammer
type: implementation_strategy
---

# Handoff: cosmic-HR DDD slice wave + watchdog fix + codex enablement + ops runbook

## Task(s)
1. **Reconcile slices 1+2 + the 3 refactors into one branch → cosmic-HR04** — COMPLETE. PR #31 (state-machine substrate + config-extraction P1+2 + transcript-intake + interview-extraction) reconciled in `cosmic-HR04-integration`, 261/264 tests green, merged. Hotfix **PR #32** (recruiter-ui `lib/env.js` client-bundle crash) merged. Both on `Cosmic-HQ/cosmic-HR` branch `cosmic-HR04`.
2. **Build the next independent DDD slices** (procurement, identity, ATS, voice) — **MIXED**:
   - **procurement** (Vendor Blueprint, Claude) — ✅ succeeded.
   - **identity** (Claude) — ✅ **COMPLETE 11/11** on `feature/f022bc58-identity-tenant-context` (watchdog "failed" was bogus; see below). Restored, intact, NOT pushed.
   - **ats + voice** (Claude) — ▶ RUNNING on the corrected 6h watchdog (started ~14:58 UTC).
3. **Fix the watchdog-timeout-on-green-builds bug (SWE-AF)** — COMPLETE (commit `8a987d6`). Root cause = env var name mismatch (below).
4. **Enable the `codex` runtime (2 slices were meant for Codex A/B)** — **PARTIAL**. bwrap-sandbox fix built into image; **not yet proven in a real build** (PM still fails; needs a clean test).
5. **Author a build-factory ops runbook** — COMPLETE (commit `cdc0e4d`).

## Critical References
- **Ops runbook (READ FIRST):** `docs/BUILD_RUNBOOK.md` (SWE-AF) — image build, one-control-plane rule, auth, submit/monitor/resume, watchdog trap, codex, gotchas. Linked from repo-root `CLAUDE.md`.
- Domain research (slice source of truth): `/home/maceo/Dev/cosmic-HR04/thoughts/searchable/shared/research/2026-06-23-10-54-Future-facingfunctionalities.md` — 10 bounded contexts; pipeline order at L575.
- No single multi-slice plan exists; each build self-plans. Slice-1 plan example: `/home/maceo/Dev/cosmic-HR-ddd-build/.artifacts-slice1-transcript-intake/plan/`.

## Recent changes
**SWE-AF (`main`):**
- `Dockerfile` ENV — added `AGENTFIELD_ASYNC_DEFAULT_EXECUTION_TIMEOUT=21600` + `AGENTFIELD_ASYNC_MAX_EXECUTION_TIMEOUT=21600` alongside the unprefixed `default_execution_timeout` (the watchdog fix); plus `COPY --from=agentfield_sdk` + `--reinstall-package agentfield` (build from local SDK).
- `docker-compose.yml` / `docker-compose.local.yml` — `additional_contexts: agentfield_sdk: ../agentfield/sdk/python` on swe-agent + swe-fast build blocks.
- `docs/BUILD_RUNBOOK.md` (NEW), `CLAUDE.md` (links runbook).
- Budget logic referenced: `swe_af/app.py:619 _effective_build_budget_seconds`; role keys `swe_af/execution/schemas.py:478 ROLE_TO_MODEL_FIELD`.

**agentfield (`/home/maceo/Dev/agentfield`, branch main):**
- `c35737f4 fix(codex)` — `harness/providers/codex.py` codex flags + `harness/_cli.py` stdin DEVNULL. Then a follow-up (debugger window) changed codex.py to `--dangerously-bypass-approvals-and-sandbox --skip-git-repo-check` (bwrap is blocked by container kernel). Local SDK is 0.1.90rc3.

**cosmic-HR04:** PR #31 (reconcile) + PR #32 (env hotfix) merged to branch `cosmic-HR04`.

## Learnings
- **THE WATCHDOG BUG (root cause):** agentfield's watchdog (`agentfield/async_config.py AsyncConfig.from_environment`) reads ONLY the **`AGENTFIELD_ASYNC_`-prefixed** env. The Dockerfile/compose only set the unprefixed `default_execution_timeout=21600`, which `swe_af/app.py:_effective_build_budget_seconds` reads for the *finalize budget*. So budget=6h but the real watchdog stayed at its 7200s default → build budgeted past the 2h kill → green builds reported "failed". Fix = set BOTH names = 21600. Verify: `docker exec <node> python -c "from agentfield.async_config import AsyncConfig; print(AsyncConfig.from_environment().default_execution_timeout)"` → 21600.0.
- **`timeout ≠ failure`:** identity "failed" at the watchdog but its checkpoint is **11/11, level 7/7, all issues merged** — the watchdog fired during the final verify AFTER all work was done. ALWAYS inspect `.artifacts/execution/checkpoint.json` + git log before treating a timeout as a real failure.
- **codex runtime:** the original "PM failed to produce a valid PRD" was NOT auth and NOT the model — it was `bwrap` (codex's sandbox) blocked by the container kernel. `--sandbox workspace-write` still invokes bwrap; `--dangerously-bypass-approvals-and-sandbox` does not (safe — the build container is already sandboxed). The stdout "Reading prompt from stdin" banner was a red herring (it's on stderr; parse_jsonl skips it).
- **Stale-artifact trap:** a build's `.artifacts` is root-owned; a non-root `rm` silently fails, leaving a stale `prd.md` that gives a FALSE "PRD-WRITTEN" signal. Chown/wipe via the container as root before re-testing.
- **One control-plane, N nodes:** never spawn a 2nd control-plane (isolated storage = fragmented UI on a new port — the user was explicit). Scale via extra nodes with distinct `NODE_ID`s on the same :8080 CP (e.g. `swe-planner-codex`).
- Codex auth = mount `~/.codex` + leave `OPENAI_API_KEY` empty → uses ChatGPT subscription. Models: planner `gpt-5.5`, qa/review `gpt-5.4`, coder `gpt-5.4-mini`.

## Artifacts
- `docs/BUILD_RUNBOOK.md`, `CLAUDE.md` (SWE-AF).
- Memories: `swe-af-watchdog-env-name-bug`, `swe-af-codex-runtime-broken`, `swe-af-one-shared-control-plane`, `cosmic-hr04-config-extraction-build` (in `~/.claude/projects/-home-maceo-Dev-SWE-AF/memory/`).
- Build payloads + exec-id files: `/tmp/slices/` (payload_{procurement,identity,ats,voice}{,_claude,_codex}.json).
- Runtime stack: `/tmp/ddd-build/compose.yml` (control-plane :8080, `swe-agent` claude node :8003, `swe-agent-codex` :8006). Codex derived image build: `/tmp/codex-img/`.
- Slice clones: `/home/maceo/Dev/cosmic-HR04-slice-{procurement,identity,ats,voice}` (each cloned off `cosmic-HR04`). Integration clone: `/home/maceo/Dev/cosmic-HR04-integration`.
- PRs: Cosmic-HQ/cosmic-HR #31 (reconcile, merged), #32 (env hotfix, merged).

## Action Items & Next Steps
1. **Watch ats + voice** (Claude, running): `exec_20260624_145850_wvln21cp` (ats), `exec_20260624_145850_ks8e785r` (voice) via `curl :8080/api/v1/executions/<id>`. Poller `bzlsqcos0`. On done: inspect checkpoint + run the slice's tests; if green, reconcile + PR to `cosmic-HR04` (same pattern as PR #31).
2. **Clean codex test** — bwrap fix is in `swe-af-ddd:codex` (node `swe-planner-codex`, :8006) but UNPROVEN in-build. Test on a **fresh throwaway clone** (NOT a real slice — I dirtied the identity clone doing this, since fixed). Submit to `swe-planner-codex.build`; wipe `.artifacts` as root first. If green, the 2 codex-intended slices (ats/voice) can move to codex.
3. **Verify + push the done slices**: procurement (✅) and **identity (11/11, `feature/f022bc58-identity-tenant-context`)** are complete but NOT pushed — run their tests, then reconcile into `cosmic-HR04`.
4. **Remaining DDD slices** — independent batch was procurement/identity/ats/voice (all in motion/done). **Dependent chain still pending** (sequence, each needs the prior): Graph/Roster/Dashboards → AI Assistant → Analytics & Insights. Procurement (slice 3) is the prerequisite for Graph/Dashboards.

## Other Notes
- **Infra is UP (leave running):** `ddd-build-control-plane-1` (:8080 UI), `ddd-build-swe-agent-1` (claude node, NOW has the AGENTFIELD_ASYNC watchdog env), `ddd-build-swe-agent-codex-1` (:8006), `cosmichr-pg` (:5432, creds `cosmichr_user`/`password`). Throwaway test DBs: create per-run, never use the live DB (integration tests truncate). `cosmichr_user` is superuser → RLS tests fail as env artifact, not bug.
- **Beads:** run from `/home/maceo/Dev/SWE-AF-baml` worktree (shared DB; no dolt remote). Not queried this session.
- **Model policy for builds:** Claude = Opus(plan)/Sonnet(code); Codex = gpt-5.5(plan)/gpt-5.4(qa)/gpt-5.4-mini(code); `enable_github_pr:false` (local-only; `resume_build`'s ExecutionConfig REJECTS `enable_github_pr`).
- A user debugger is/was running in another window on the agentfield codex provider — coordinate before rebuilding `swe-af-ddd:codex`.
