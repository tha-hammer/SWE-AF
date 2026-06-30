---
date: 2026-06-28T16:50:54-04:00
researcher: tha-hammer
git_commit: 73a0f8d3a7c2efc0b4ce60a997f2cf7baca71d8e
branch: fix/greenfield-merge-orphan
repository: SWE-AF
topic: "Marketing PRD parallel codex slice builds + seam refactor Implementation Strategy"
tags: [implementation, swe-af, build-factory, marketing-tool, parallel-builds, seams, ownership-manifest, codex, fastapi, nextjs]
status: in_progress
last_updated: 2026-06-28
last_updated_by: tha-hammer
type: implementation_strategy
---

# Handoff: Marketing PRD parallel codex slices (3/5 done, 2 running, integration pending)

## Task(s)
Speed up Monte Carlo AI marketing-tool development by **slicing the PRD and handing slices to parallel codex build-factory runs**. Status:
1. **Seam refactor + ownership manifest** — ✅ COMPLETE, committed `a77f4d8` on `silmari-ai-marketing-tool` master (486 backend tests green).
2. **5 parallel codex slice builds** (isolated clones off the seam baseline):
   - ① **incident** (Play 2 Data-Incident) `exec_20260628_140328_o4gwqpup` — ✅ **SUCCEEDED**, lane-clean.
   - ⑤ **connectors** (real SF/HubSpot) `exec_20260628_140329_ruy9ch2c` — ✅ **SUCCEEDED**, lane-clean (1 tiny test bleed).
   - ② **account_profile** (Account Signal Profile 8.2) `exec_20260628_140328_tvl4f1h2` — ✅ **complete-via-timeout** (6h cap; 32 levels merged, full FE+BE).
   - ④ **narrative** (Narrative Intelligence 8.6) `exec_20260628_190501_vkqyp2uc` — ✅ **SUCCEEDED**, lane-clean (own api/service/7 components; only shared `playwright.config.ts`).
   - ③ **play-builder** (Play Builder 8.4) `exec_20260628_190501_ltjtlnog` — ✅ **SUCCEEDED**, lane-clean (own api/model/5 components, used reserved mig **0301**; only shared `playwright.config.ts`).
3. **Integration pass** — ⏳ **NEXT (all 5 slices done)**: merge 5 disjoint slices → master, wire nav, `alembic merge heads`, union-merge shared FE config, full test/verify.

**ALL 5 slices DONE & lane-verified — zero frozen-file violations across the board. Ready for the integration pass.**

> **Predecessor task (this same session, all ✅ DONE):** greenfield merge-orphan fix shipped (commit `73a0f8d` branch `fix/greenfield-merge-orphan`, image `swe-af-ddd:test/:codex` id `17e7fbdfd75f`, BOTH nodes patched). Contract-upload **PR #50** open into `cosmic-HR04`. Marketing+signalops greenfield merged to their masters. See bd SWE-AF-1c8 (greenfield reconcile, the marketing/signalops master-merges already done via node-root) and the prior handoff `2026-06-27_19-29-08_build-factory-merge-fix-3-builds.md`.

## Critical References
- `/home/maceo/Dev/silmari-ai-marketing-tool/OWNERSHIP_MANIFEST.md` — **the contract** every slice obeys (path lanes, frozen files, reserved Alembic revision namespaces, Next auto-routing). READ FIRST.
- `docs/BUILD_RUNBOOK.md` (SWE-AF) — factory ops; `bd memories swe-af-factory-cancel-and-merge-orphan-fix` for the cancel-doesn't-kill + node mapping.
- Per-slice goals: `/tmp/claude-1000/-home-maceo-Dev-SWE-AF/e932ba0a-c88e-4edd-be54-d1cecc3142d4/scratchpad/goal_{incident,account_profile,connectors,play_builder,narrative}.txt`

## Recent changes
**Seam refactor (commit `edf01f2`) + manifest (`a77f4d8`) on `silmari-ai-marketing-tool` master**, converting 3 shared-edit hotspots to additive seams so parallel slices never touch the same file:
- `backend/app/main.py:44` — routers now **auto-discovered** from `app.api.v1` via `pkgutil.iter_modules` (new surface = drop a module exposing `router`; no main.py edit). Preserved the user's CORS block.
- `backend/app/db/models.py` → **`backend/app/db/models/` package**: `core.py` (baseline 9 models + `__all__`) + `__init__.py` that re-exports core AND auto-imports sibling modules (each slice drops `db/models/<slice>.py`).
- `backend/alembic/env.py:11` — added `import app.db.models` so all (incl. auto-discovered) models register on `Base.metadata`.
- Base = user's smoke-test commit `25938c8 "Wire MVP browser surfaces and tests"` (NOT frontend ownership — it was a smoke test).

## Learnings
- **The seam+manifest design WORKS — proven conflict-free.** ① incident touched ONLY its lane (api/v1/incidents.py, db/models/incidents.py, services/plays/data_incident_play.py, llm/incident_*, app/incidents/, components/incidents/, lib/api/incidents.ts, mig **0101**), ZERO frozen files. ⑤ connectors same (its `_real/` helpers; **base.py untouched**).
- **Frontend SHARED build-config is the one un-seamed hotspot.** account_profile touched `frontend/package.json`/`package-lock.json` (new deps e.g. lucide-react), `tailwind.config.js`, `playwright.config.ts`. The other FE slices (play-builder, narrative) will too → **union-merge these at integration** (the accepted cleanup). Routes/components/api-modules are cleanly disjoint (Next app-router auto-routing).
- **Codex builds self-police the manifest:** account_profile created (unmerged) cleanup branches literally named `issue/00-account-profile-delete-nonowned-scaffold-files` and `...-remove-shared-playwright-wasm-workarounds` — it knew it strayed into shared files.
- **`enable_github_pr:false`** so builds leave work on their integration branch; no PR/push.
- **Resources:** 5 parallel codex builds (planning) + steady-state stayed at **30-33G RAM avail, load <7/16** on the 78G/16-core host — far more comfortable than the runbook's conservative ~24G/2-3-builds estimate. Watcher backs off if avail <8G.
- **timeout ≠ failure** held again: account_profile "failed" on the 6h cap but merged 32 levels with full FE+BE.
- Slice clones use **full `git clone`, NOT worktrees** (worktrees store host-abs `.git` paths that break in the container `/workspaces/dev` mount). PRD docs restored into each clone via `git checkout 412c3b5 -- monte-carlo-ai-marketing-tool/` (PRD is a top-level + 9 domain PRDs, only in bootstrap commit, not on master).

## Artifacts
- Marketing repo `silmari-ai-marketing-tool`: `OWNERSHIP_MANIFEST.md`, seam baseline `a77f4d8` (master).
- Slice clones (each `/home/maceo/Dev/marketing-slice-<name>`), integration branches:
  - `marketing-slice-incident` → branch `6954dcd0-integration` (✅)
  - `marketing-slice-connectors` → branch `ed0f2aa4-integration` (✅)
  - `marketing-slice-account-profile` → branch `2d192002-slice-account-signal-profile` (✅ via timeout)
  - `marketing-slice-narrative` → branch `642b859d-slice-narrative-intelligence` (✅)
  - `marketing-slice-play-builder` → branch `719f2c75-slice/play-builder` (✅, mig 0301)
- Goals + payloads: `…/e932ba0a-…/scratchpad/goal_*.txt`, `payload_slice_*.json`.
- Watchers: all slice watchers have fired (all 5 terminal). No active watchers.
- Prior handoff: `thoughts/searchable/shared/handoffs/general/2026-06-27_19-29-08_build-factory-merge-fix-3-builds.md`.

## Action Items & Next Steps
1. ✅ All 5 slices terminal & lane-verified (done this session). Proceed straight to the integration pass.
2. **Integration pass** (merge all 5 → marketing master, in a branch off `a77f4d8`):
   - Merge the 5 integration branches (disjoint new files → mostly clean).
   - **Union-merge shared FE config**: `frontend/package.json` (combine deps), `package-lock.json` (regen via `npm install`), `tailwind.config.js`, `playwright.config.ts`.
   - Resolve the connectors bleed into `backend/tests/test_domain/test_foundational.py`.
   - **`cd backend && .venv/bin/python -m alembic merge heads`** to unify 0101+0301+0401(+0501?) into one head.
   - Wire **nav links** in `frontend/src/components/AppShell.tsx` for incidents/accounts/play-builder/narrative (the deliberately-deferred integration touch).
   - Run `cd backend && .venv/bin/python -m pytest -q` (was 486 green pre-slices) + the frontend/Playwright tests. Run under `TZ=UTC` (host-TZ flakes on date tests — seen in contract-upload).
   - **Integration branches to merge:** incident `6954dcd0-integration`, connectors `ed0f2aa4-integration`, account_profile `2d192002-slice-account-signal-profile`, narrative `642b859d-slice-narrative-intelligence`, play-builder `719f2c75-slice/play-builder` (each in its `marketing-slice-<name>` clone).
3. **Decide PR/merge target** for the assembled marketing build (greenfield repo, no GitHub remote yet — local master, or add remote).

## Other Notes
- **Build factory live:** control-plane `ddd-build-control-plane-1` (:8080); `ddd-build-swe-agent-codex-1` = `swe-planner-codex` (codex, **PATCHED+fixed image**); `ddd-build-swe-agent-1` = `swe-planner` (claude). Submit to `swe-planner-codex.build`. Monitor only with `docker logs --tail N` (OOM trap).
- **bd:** epic **SWE-AF-106** (this work) open; **SWE-AF-1c8** (greenfield reconcile) open; SWE-AF-1tz/1tp closed (greenfield fix + contract reconcile). `bd list --status=in_progress` → none. Run bd from `/home/maceo/Dev/SWE-AF`.
- **bd memory** `swe-af-factory-cancel-and-merge-orphan-fix` captures: control-plane `/cancel` does NOT kill the in-flight reasoner (docker restart the node to truly stop); node container↔NODE_ID map; the merge-orphan fix details.
- **Codex slice config** (reused from contract payload): runtime=codex, pm/architect=gpt-5.5, coder/qa=gpt-5.4, `enable_github_pr:false`.
- AgentMail: not used this session.
- ⚠️ Primary SWE-AF checkout is parked on branch `fix/greenfield-merge-orphan` (the merge-orphan fix, not merged to main — durable in image+nodes; promote to main when desired).
