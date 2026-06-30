---
date: 2026-06-26T15:25:00-04:00
researcher: tha-hammer
git_commit: 42a5cc18caa942858e9d49e4956775a05c0e3d23
branch: main
repository: SWE-AF
topic: "cosmic-HR DDD wave completion + Contract View functional verification + SWE-AF factory build-db"
tags: [swe-af, cosmic-hr, contract-view, ddd, functional-verification, build-db, doppler, seed, codex, mock-vs-reality]
status: complete
last_updated: 2026-06-26
last_updated_by: tha-hammer
type: implementation_strategy
---

# Handoff: cosmic-HR DDD wave done + Contract View made to actually render (functional verify)

## Task(s)
1. **Finish the cosmic-HR04 DDD slice wave** — ✅ COMPLETE. All 8 Frank bounded contexts + 3 future slices merged. AOP (PR #42), Contract View (#43), Provenance (#41), AI Assistant (#40) plus earlier #33–37. Migration chain contiguous **056→067**, no gaps.
2. **SWE-AF factory: built-in test Postgres (`build-db`)** so DB-forcing build checks can pass — ✅ COMPLETE, merged to SWE-AF main (`42a5cc1`).
3. **Diagnose codex empty builds + file upstream issue** — ✅ filed **Agent-Field/SWE-AF#82**.
4. **Consolidate git remotes to only `tha-hammer/SWE-AF`** — ✅ removed `upstream`(Agent-Field) + `tha-hammer`(SWE-AF-anthropic).
5. **Contract View "UI not built" report → functional verification** — ✅ Found it was MERGED-BUT-BROKEN (3 integration bugs from mock-only tests), fixed 2 + added a demo seed, verified in a real browser, **merged PR #44** (`efb3db98` on cosmic-HR04).
   - **OPEN follow-up:** d3 graph layout centers nodes low/cut-off (SVG-height polish; functional but doesn't frame like the mockup). NOT fixed.

## Critical References
- **DDD scope source of truth:** `/home/maceo/Dev/cosmic-HR04/thoughts/searchable/shared/research/2026-06-23-10-54-Future-facingfunctionalities.md` (Deep Decomposition Matrix L927 = 8 contexts; 10 Frank capabilities L538).
- **Contract View build map:** `/home/maceo/Dev/cosmic-HR04/specs/architecture/contract-view-MAP.md` (+ mockup `specs/architecture/contract-view-ui-mockup.html`).
- **SWE-AF ops:** `docs/BUILD_RUNBOOK.md` (now incl. §9 build-db). Memory `~/.claude/projects/-home-maceo-Dev-SWE-AF/memory/cosmic-hr04-ddd-slice-wave.md` (exhaustive running log; READ the last 3 entries first).

## Recent changes
**cosmic-HR04 (Cosmic-HQ/cosmic-HR), all merged:**
- **PR #44** (`efb3db98`): `backend/views/procurementContractView.js:135` — contracts DTO now emits `id`+`totalContractValue` (was only `contractId`/`tcv`; UI reads `id`/`totalContractValue`). `recruiter-ui/components/recruiter/contract/ExplodedCanvas.jsx:54` — filter dangling edges (both endpoints must be in node set) before `d3.forceLink` (was crashing the canvas with "node not found"). New `scripts/seed-contract-explode-demo.cjs` (portable demo seed).
- **PR #42** AOP (migration 066), **#43** Contract View (064/065), **#41** Provenance (067).

**SWE-AF (main, pushed to origin tha-hammer/SWE-AF):**
- `42a5cc1` — `build-db` (postgres:16) + `DATABASE_URL_TEST` wiring in `docker-compose.yml`, `docker-compose.local.yml`, `/tmp/ddd-build/compose.yml`; `BUILD_RUNBOOK.md` §9; codex debug report `thoughts/searchable/shared/research/2026-06-26-codex-coder-empty-cv-build-debug.md`.
- WIP in tree (NOT mine, leave alone): `swe_af/prompts/architect.py`, `architecture_planning_loop.py`, `uv.lock`, `AGENTS.md`, `.beads/*`.

## Learnings
- **"merged + tests pass + build succeeded" ≠ working** — the big lesson. CV passed its build tests because they used MOCKED data with the components' own field names; the real API shape differed in 3 places (id vs contractId, totalContractValue vs tcv, dangling d3 edge). Same false-green class as the codex empty builds. ALWAYS functionally run UI features.
- **The screenshot the user saw is Railway PROD** (auto-deploy of cosmic-HR04). Local `cosmichr` DB is stuck at migration **038** and `.env` has `DATABASE_URL` commented out — there is NO local app running by default.
- **Local run recipe (verified working):** Doppler project is **`nolme-hr`** (NOT cosmic-hr — that stale name 404s). Backend: `doppler run -p nolme-hr -c dev -- bash -c 'cd <clone> && DATABASE_URL=postgres://cosmichr_user:password@localhost:5432/cosmichr_local AUTH_ENABLED=false ALLOW_SUPERUSER_DB=true NODE_ENV=development PORT=3004 node backend/server.js'`. `AUTH_ENABLED=false`→dev-admin maps to the `legacy_default` org (exists in a fresh migrated DB); `ALLOW_SUPERUSER_DB=true` bypasses the RLS-superuser boot guard (`backend/server.js:325`). UI: same doppler + `NEXT_PUBLIC_API_URL=http://localhost:3004` (direct — Next's `/api` rewrite 308-redirects to a trailing slash the express backend 404s) + `NEXT_PUBLIC_LOCAL_VIEW=1`.
- **Clerk frontend gate:** `recruiter-ui/app/(recruiter)/layout.jsx` hard-requires Clerk sign-in + active provisioned org (no dev bypass). To VIEW locally I added a TEMP env-flagged bypass (`NEXT_PUBLIC_LOCAL_VIEW`) — it was REVERTED before commit and must NOT be committed.
- **codex empty builds = real harness bug** (coder writes 0 files; verify-fix "Fix generator failed to analyze"). Use the **claude_code** runtime for builds. build-db only fixed the runtime-agnostic DB-gate cascade. The codex agent's earlier line-level claims did NOT match current main (don't trust them).
- **Seed gotcha:** the agent-written seed used CommonJS `require` in an ESM package → must be `.cjs`. Portable via `SEED_ORG_ID`/`legacy_default` lookup + `SEED_ENGAGEMENT_ID`.

## Artifacts
- Handoff: this file.
- cosmic-HR04 fixes: `backend/views/procurementContractView.js`, `recruiter-ui/components/recruiter/contract/ExplodedCanvas.jsx`, `scripts/seed-contract-explode-demo.cjs` (PR #44, on `cosmic-HR04`).
- Verification clone: `/home/maceo/Dev/cosmic-HR04-slice-contract-view` (branch `cv-local-verify`; the build clones for other slices are siblings `cosmic-HR04-slice-{aop,contract-view,...}`).
- Local DB: `cosmichr_local` on container `cosmichr-pg` (:5432), migrated to 067 + seeded (12 contracts, 25 edges, eng `eng-orgchart-demo`, org `legacy_default` = `05f7e9a8-7fd2-4372-89bb-c4901b6e5f42`).
- SWE-AF: `docs/BUILD_RUNBOOK.md` §9, `thoughts/searchable/shared/research/2026-06-26-codex-coder-empty-cv-build-debug.md`, `/tmp/slices/cv2_result.json` (codex empty-build evidence).
- Upstream issue: github.com/Agent-Field/SWE-AF/issues/82.

## Action Items & Next Steps
1. **(If wanted) Fix the d3 graph centering** in `recruiter-ui/components/recruiter/contract/ExplodedCanvas.jsx` — nodes settle low/cut-off. Root cause: `forceCenter(width/2, height/2)` with `clientWidth/clientHeight` (lines 36–37, 73) measured against an SVG taller than the visible canvas. Likely needs a bounded SVG height (CSS) or ResizeObserver. Verify via the local run recipe above + a temp `(recruiter)/layout.jsx` bypass (revert before commit).
2. **(If wanted) Populate Railway PROD** so the deployed view lights up: run `scripts/seed-contract-explode-demo.cjs` with `DATABASE_URL`=prod (Doppler `nolme-hr` prod-ish config) + `SEED_ORG_ID`=the prod org. OUTWARD-FACING — confirm first.
3. **Clean up local env when done:** stop background dev servers (backend on :3004, recruiter-ui on :3003 — were running tasks); optionally `DROP DATABASE cosmichr_local`.
4. **Verify the rendered fix on prod** after redeploy of #44 (rail TCV + selection + graph).

## Other Notes
- **bd:** `bd list --status=in_progress` → none. Closed this session: SWE-AF-66l (AOP), SWE-AF-x04 (CV build), SWE-AF-hid (build-db). Run bd from `/home/maceo/Dev/SWE-AF` on main. `bd dolt push` has no remote configured (non-fatal; issues persist locally).
- **Infra UP (leave running unless cleaning up):** `cosmichr-pg` (:5432), and the SWE-AF factory `ddd-build-{control-plane,swe-agent,swe-agent-codex,build-db}` (control-plane :8080). No active builds.
- **Field-name fix was additive** (emits both id/contractId, totalContractValue/tcv) — safe, no consumer breakage.
- **Models/runtime policy:** Claude builds = Opus(plan)/Sonnet(code) via `claude_code`; codex currently produces empty builds (avoid for coding until #82 fixed).
- The `cv-render-fixes` and `cv-reconcile` branches were squash-merged + deleted; `cv-local-verify` is the live local clone branch.
