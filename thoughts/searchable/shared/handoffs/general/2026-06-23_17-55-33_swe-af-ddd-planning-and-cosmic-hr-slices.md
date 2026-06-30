---
date: 2026-06-23T17:55:33-04:00
researcher: tha-hammer
git_commit: e88ee813d2ed9099bf8a33fb3dc1e6d76e452b89
branch: main
repository: SWE-AF
topic: "DDD modular planning loop + build-timer fix + cosmic-HR vertical-slice builds"
tags: [swe-af, ddd, planning-loop, build-watchdog, cosmic-hr, vertical-slice, baml, railway]
status: complete
last_updated: 2026-06-23
last_updated_by: tha-hammer
type: implementation_strategy
---

# Handoff: DDD planning loop + timer fix (merged to main) + cosmic-HR slices (slice 2 building)

## Task(s)
1. **Implement DDD modular planning loop (SWE-AF-cl2)** — COMPLETE. TDD, 9 behaviors (B1–B9). Built on branch `feat/ddd-modular-planning-loop`, **merged to `main`** (merge commit `e88ee81`).
2. **Fix build watchdog turning green builds into "failed" (SWE-AF-m2d)** — COMPLETE. `build()` now owns a wall-clock budget + finalizes green; merged into `feat/ddd-modular-planning-loop` (commit `e2b8c5a`), so it's in `main` too.
3. **cosmic-HR Transcript Intake vertical slice (slice 1)** — COMPLETE: built by the live factory, verified (202/205 tests), pushed to `Cosmic-HQ/cosmic-HR` branch `feature/5b74e958-transcript-intake`.
4. **cosmic-HR Interview Extraction vertical slice (slice 2)** — **IN PROGRESS / RUNNING**. `exec_20260623_212916_vm76ovo3`, currently in the new DDD planning-loop phase. Background monitor task `bg5ry34ig` will fire on completion.

## Critical References
- Plan: `thoughts/searchable/shared/plans/2026-06-23-07-38-SWE-AF-tdd-ddd-modular-planning-loop.md` (+ `…-REVIEW.md`)
- Research (cosmic-HR domain, 10 bounded contexts): `/home/maceo/Dev/cosmic-HR04/thoughts/searchable/shared/research/2026-06-23-10-54-Future-facingfunctionalities.md`

## Recent changes
**SWE-AF (`main` @ `e88ee81`) — see `git log main` for exact lines; key files:**
- `swe_af/reasoners/schemas.py` — 17 DDD models + `PlanningEvent` (defined before `Architecture`); additive `Architecture.planning_artifacts`, `PlanResult.planning_artifacts`, `PlannedIssue.{bounded_context,contract_refs,domain_events,read_models,guardrails,observability,slice_role}`.
- `swe_af/reasoners/pipeline.py` — `validate_planning_artifacts` (pure, dict-or-model), `run_architecture_planning_loop` reasoner, `render_planning_artifacts_markdown`, `publish_planning_event` (JSONL).
- `swe_af/prompts/architecture_planning_loop.py` (NEW) — DDD loop prompt.
- `swe_af/app.py` — `plan()` runs the loop before Sprint Planner via `_run_architecture_planning_loop_until_valid` (retry + force-accept); `build()` budget: `_effective_build_budget_seconds` + `_build_budget_exhausted`, the verify-loop budget gate (records `verification_incomplete` debt → `completed_with_debt`), and a `CancelledError` backstop.
- `swe_af/prompts/_utils.py` (`planning_artifacts_context_block`), `prompts/sprint_planner.py`, `prompts/issue_writer.py`, `prompts/replanner.py` — thread/render artifacts.
- `swe_af/execution/schemas.py` — `BuildConfig.build_budget_seconds`/`build_budget_buffer_seconds`; `DAGState.planning_artifacts`. `dag_executor.py:_init_dag_state` populates it.
- `Dockerfile` + `docker-compose.yml` — `default_execution_timeout=21600` (watchdog headroom).
- New tests: `tests/test_planning_artifacts_schema.py`, `test_planning_artifact_validator.py`, `test_planning_artifact_prompts.py`, `test_architecture_planning_loop_reasoner.py`, `test_replanner_planning_artifact_context.py`, `test_planning_loop_observability.py`, `test_planning_artifacts_docs.py`, `test_build_budget_finalize.py`; updated `test_planner_pipeline.py`, `test_mock_fixture_cross_feature_integration.py`, `test_conftest_malformed_planner_execute_nodeids_integration.py`.

## Learnings
- **Build watchdog is agentfield's, not SWE-AF's**: `agentfield/async_config.py:default_execution_timeout=7200` (max 21600). It cancels the `build` reasoner at 2h active time → control-plane marks execution `failed` even when all issues are green (observed slice-1 `exec_20260623_172701`: 10/10 done, verifier "no blocking issues", WATCHDOG_FIRING @7202s). Fix = build owns its budget + finalizes (SWE-AF-m2d).
- **Auth gotcha**: the durable token at `/home/maceo/Dev/silmari-agent-memory/.env` is **mislabeled `ANTHROPIC_API_KEY`** but is actually a **Claude Code OAuth token** (`sk-ant-oat…`). It MUST go in `CLAUDE_CODE_OAUTH_TOKEN` with `ANTHROPIC_API_KEY` empty; setting it as `ANTHROPIC_API_KEY` makes the `claude_code` provider fast-fail ("ClaudeCodeProvider error… PM failed to produce a valid PRD"). The earlier per-session Max OAuth access token (from `~/.claude/.credentials.json`) expires ~6h — use the durable one for long builds.
- **`resume_build` only re-runs execution, not verification** (`app.py:~2391` → calls `execute` with `resume=True`); there is NO standalone verify reasoner. To re-verify a finished slice, run its feature tests directly.
- **cosmic-HR RLS test artifact**: migration `056` correctly uses `FORCE ROW LEVEL SECURITY` + `app.current_org` GUC policies. The 3 RLS failures were because the test DB user `cosmichr_user` is a **superuser (`rolbypassrls=t`)** which bypasses RLS; proving it via a non-super role is blocked because pre-existing migration `048` needs superuser `SET ROLE`. Not a slice bug.
- **Live build launch** = `docker compose -f /tmp/ddd-build/compose.yml up -d` (control-plane `agentfield/control-plane:latest` :8080 + node `swe-af-ddd:test` :8003) then `POST http://localhost:8080/api/v1/execute/async/swe-planner.build` with `{"input":{goal, repo_path, config}}`. Status: `GET /api/v1/executions/<exec_id>`. Logs: `docker logs --tail N` ONLY (debug JSON is huge — OOM hazard otherwise).

## Artifacts
- Plan + review: `thoughts/searchable/shared/plans/2026-06-23-07-38-SWE-AF-tdd-ddd-modular-planning-loop{,-REVIEW}.md`
- This handoff.
- SWE-AF origin (`tha-hammer/SWE-AF`) branches: `main` @ `e88ee81` (pushed), `feat/ddd-modular-planning-loop` @ `e2b8c5a`, `fix/build-budget-finalize` @ `e2b8c5a`. Worktrees: `/home/maceo/Dev/SWE-AF` (main), `/home/maceo/Dev/SWE-AF-ddd-planning` (feat/ddd…), `/home/maceo/Dev/SWE-AF-baml`.
- cosmic-HR slice 1: pushed to `Cosmic-HQ/cosmic-HR` branch `feature/5b74e958-transcript-intake` (PR-create link printed on push).
- Build clone: `/home/maceo/Dev/cosmic-HR-ddd-build` (on slice-1 branch; slice-1 artifacts preserved at `.artifacts-slice1-transcript-intake`; slice-2 build writes fresh `.artifacts`).
- Stack config: `/tmp/ddd-build/` (`compose.yml`, `.env` [OAuth token], `build_payload.json`, `build_payload_slice2.json`).
- Smoke driver (focused loop test): `/tmp/ddd_loop_smoke.py`.

## Action Items & Next Steps
1. **Watch slice-2 build** `exec_20260623_212916_vm76ovo3` (monitor task `bg5ry34ig`). On completion: inspect `/home/maceo/Dev/cosmic-HR-ddd-build/.artifacts/plan/architecture-planning.md` + git log of the new integration branch; run the slice's feature tests (vitest unit pass without DB; integration needs `cosmichr-pg` + a test DB — see Learnings re superuser/RLS). If green, push the branch to `Cosmic-HQ/cosmic-HR` for Railway (confirm branch name with user first).
2. **Remaining 8 bounded contexts** as future slices (Identity & Tenant, ATS Core, Workforce Graph, Engagement Roster, Outreach Orchestration, Voice Conversations, AI Assistant, Analytics & Insights). Base dependent slices on prior branches.
3. **SWE-AF follow-ups (deferred, not blocking)**: (a) budget gates only the *verify* phase — a very long *execute* phase is one uninterruptible `app.call`, so execute-phase budgeting is a separate enhancement; (b) make `resume_build` able to continue a budget/watchdog-finalized build through verification. Consider a PR for the `main` merge if desired.

## Other Notes
- **Beads (run from `/home/maceo/Dev/SWE-AF-baml` — shared DB; no dolt remote configured, so no `bd dolt push`)**: closed this session — SWE-AF-cl2 (DDD loop), SWE-AF-m2d (watchdog), SWE-AF-x7m (plan-review fixes). `bd list --status=in_progress` = none. Run `bd` from the `-baml` worktree to avoid a stray `.beads/issues.jsonl` export on main.
- **Running infra (leave up)**: `ddd-build-control-plane-1` (:8080), `ddd-build-swe-agent-1` (:8003, image `swe-af-ddd:test` rebuilt WITH the watchdog fix + durable OAuth token + watchdog=21600), `cosmichr-pg` (postgres:16, :5432, creds `cosmichr_user`/`password`/db `cosmichr`). Node→host gateway from container = `172.18.0.1`.
- **Verification verdict for slice 1**: unit 114/114, integration 88/91 (3 RLS env-artifacts), slice sound.
- Model policy used for builds: Opus for `pm/architect/tech_lead/sprint_planner/issue_writer`, Sonnet for everything else; `enable_github_pr:false` (local-only).
