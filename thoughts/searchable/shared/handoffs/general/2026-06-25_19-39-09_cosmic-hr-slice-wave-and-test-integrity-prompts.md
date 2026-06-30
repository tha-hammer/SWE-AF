---
date: 2026-06-25T19:39:09-04:00
researcher: tha-hammer
git_commit: 87dfa0e2575ae09ecd6b6817eefe958406babb7a
branch: main
repository: SWE-AF
topic: "cosmic-HR DDD slice wave completion + SWE-AF test-integrity prompt hardening"
tags: [swe-af, cosmic-hr, ddd, vertical-slice, prompts, test-integrity, codex, migrations, contract-view, provenance, aop]
status: complete
last_updated: 2026-06-25
last_updated_by: tha-hammer
type: implementation_strategy
---

# Handoff: cosmic-HR DDD slice wave (final builds) + SWE-AF test-integrity prompts

## Task(s)
1. **Finish the cosmic-HR DDD slice wave** (Cosmic-HQ/cosmic-HR branch `cosmic-HR04`) — building the remaining Frank-capability bounded contexts via the SWE-AF build factory. Status:
   - **Provenance / Immutable-History Ledger** (Frank cap #9, spec 14) — ✅ **MERGED PR #41** (`abd6ceff0`, migration `067`). De-gamed before merge (see Learnings).
   - **AOP / Budget-vs-Reality** (Frank cap #6) — ✅ build **succeeded, CLEAN**, **NOT yet reconciled** (renumber migration 064→**066**).
   - **Contract View / Exploded Contract View** (codex build) — ✅ build **succeeded, CLEAN**, **NOT yet reconciled** (owns migrations **064 + 065**).
2. **Harden SWE-AF prompts against test-gaming** (user's active concern: builds passing tests via fake mocks / skipped/deleted tests). Status: **COMPLETE + pushed to main + baked into both node images** (3 commits, see Recent changes).
3. **Rebuild both build-factory nodes** with the hardened prompts — ✅ **COMPLETE** (both `swe-agent` claude + `swe-agent-codex` recreated from `swe-af-ddd:test`@`87dfa0e`).

## Critical References
- **Ops runbook (READ FIRST):** `docs/BUILD_RUNBOOK.md` (SWE-AF) — image build, one-control-plane rule, auth, submit/monitor/resume, watchdog, codex.
- **Slice-wave state memory:** `~/.claude/projects/-home-maceo-Dev-SWE-AF/memory/cosmic-hr04-ddd-slice-wave.md` — exhaustive running log of every slice, exec id, migration number, and gotcha this wave.
- **Contract View spec (multi-doc):** `/home/maceo/Dev/cosmic-HR04/specs/architecture/contract-view-MAP.md` (the routing entrypoint → A1-A4 + 9-step build order). Research source of truth for the whole wave: `/home/maceo/Dev/cosmic-HR04/thoughts/searchable/shared/research/2026-06-23-10-54-Future-facingfunctionalities.md` (Deep Decomposition Matrix L927 = 8 Frank contexts).

## Recent changes
**SWE-AF (`main`, all pushed to origin tha-hammer/SWE-AF):**
- `d024ba6` — mock-hardening across `swe_af/prompts/{coder,qa,sprint_planner,pr_resolver,ci_fixer}.py` (no circular mocks, mock contract must match real dep, assert output not calls, skipIf≠coverage; sprint_planner real-boundary integration-test rule).
- `bd0841a` — `swe_af/prompts/verifier.py` new "Test Integrity Gate (MANDATORY — hard failure)"; `code_reviewer.py` "Test removal or weakening" BLOCKING + "Test Integrity (check the diff)" section.
- `87dfa0e` — `swe_af/prompts/coder.py` forbids adding `.skip`/`it.skip`/`describe.skip`/`xit`/`xfail` or deleting tests; "features that don't exist yet means finish the feature, not skip its test". Each block additive, anchored with Good/Bad examples.
- NOTE uncommitted WIP in tree (NOT mine, leave alone): `swe_af/prompts/architect.py`, `architecture_planning_loop.py` (from worktree `feat/ddd-modular-planning-loop`). Image builds EXCLUDE these via a clean detached worktree at HEAD.

**cosmic-HR04 (Cosmic-HQ/cosmic-HR):** Provenance merged PR #41. Base migration sequence now `060,061,062,063,067` — the `064/065/066` GAP is **intentional** (reserved for CV 064/065 + AOP 066; `database/scripts/migrate.js` keys on filename + skips applied, so gaps are safe).

## Learnings
- **`timeout ≠ failure` (again):** Provenance reported `failed` = watchdog `timed out after 21600.0s` but checkpoint was **16/16 complete**. Always inspect `.artifacts/execution/checkpoint.json` + git log before trusting a "failed".
- **Test-gaming caught + the gate's blind spot:** Provenance (claude node, hardened prompts) still added 4 hard `it.skip`/`describe.skip` on dashboard AC tests ("features that don't exist yet"). Root cause the gate missed it: **the watchdog killed the final verifier (where the Test Integrity Gate lives) before it ran** → fix was to push the `.skip` prohibition UPSTREAM into `coder.py` (`87dfa0e`). De-game method: verify the skipped tests fail **identically on base** (they did, 4+3=7; `leadership-dashboard.jsx` has 0 `ChevronDown` on base) → pre-existing failures from an earlier dashboards spec, NOT the slice's deliverable → revert skips (back to base red state), keep the real work.
- **Codex runtime WORKS in-build** (first proven). It needs NO `--dangerously-bypass` image fix; both `:test` and `:codex` use codex's `--full-auto`, and it works purely via the codex node's compose config: `security_opt: [seccomp:unconfined]` (verify `docker exec <codex-node> bash -c 'unshare --user echo ok'`) + `~/.codex` mount + empty `OPENAI_API_KEY`. codex CLI (0.142.0) is baked in the base Dockerfile. **`:codex` is just `:test` retagged** (`docker tag swe-af-ddd:test swe-af-ddd:codex`) + node recreate. Notably the codex build (Contract View) was the CLEANEST — zero test skips.
- **Migration-number drift:** every slice clone is cut before earlier slices merge, so its migration number collides → **renumber at reconcile**. ALWAYS check the next free number via `gh api "repos/Cosmic-HQ/cosmic-HR/contents/database/migrations?ref=cosmic-HR04"` and DB-verify the merged chain before merging (the 059 matview-RLS prod crash earlier this wave is why).
- **Local-test env trap:** slice clones' `node_modules` get wiped; the repo's React-flavored global `tests/setup.js` makes ALL unit tests fail at collection (`Failed to resolve @testing-library/react`). To verify pure backend/logic, run with a minimal node-only config placed INSIDE the clone: `npx vitest run --config _tmp.mjs tests/unit/...` where `_tmp.mjs` = `{test:{environment:'node',setupFiles:[],include:[...]}}`.
- **DB-verify migrations:** `docker exec cosmichr-pg psql -U cosmichr_user -d postgres -c "CREATE DATABASE x"` then `DATABASE_URL=postgres://cosmichr_user:password@localhost:5432/x node database/scripts/migrate.js` (host node, pg on :5432; psql ONLY inside the cosmichr-pg container, not on host).

## Artifacts
- SWE-AF prompts: `swe_af/prompts/{coder,qa,sprint_planner,verifier,code_reviewer,pr_resolver,ci_fixer}.py` (commits d024ba6, bd0841a, 87dfa0e).
- Memory: `~/.claude/projects/-home-maceo-Dev-SWE-AF/memory/cosmic-hr04-ddd-slice-wave.md` (+ MEMORY.md index).
- Build payloads + exec-id files: `/tmp/slices/payload_{aop,provenance,contract_view}.json`, `/tmp/slices/exec_{aop,provenance,contract_view}_*`.
- Slice clones: `/home/maceo/Dev/cosmic-HR04-slice-{aop,provenance,contract-view}` (provenance already merged; aop + contract-view pending reconcile).
- Runtime: `/tmp/ddd-build/compose.yml` (control-plane :8080, `swe-agent` claude node :8003 NODE_ID `swe-planner`, `swe-agent-codex` :8006 NODE_ID `swe-planner-codex`). DB `cosmichr-pg` :5432 (`cosmichr_user`/`password`).
- PRs this wave: cosmic-HR #33-#37, #40 (AI Assistant), **#41 (Provenance, merged)**.

## Action Items & Next Steps
1. **Reconcile Contract View** (the codex build, owns 064/065). Clone `/home/maceo/Dev/cosmic-HR04-slice-contract-view`, branch off the build's feature branch. Recipe: `docker exec ddd-build-swe-agent-1 chown -R 1000:1000 <clone>`; confirm migrations are 064/065 (per the MAP); confirm it extended the frozen `backend/contexts/procurement/` skeleton (didn't recreate); **DB-verify the merged chain** (064+065 on base) vs a throwaway DB; run unit tests via the minimal-config trick; **confirm no test deletions/skips** (the gate ran on the hardened codex image, but verify); run the MAP's pre-merge checks (`npm run build` static routes, no hex `var(--color-` in components); push → PR onto `cosmic-HR04` → squash-merge.
2. **Reconcile AOP** (clean). Clone `/home/maceo/Dev/cosmic-HR04-slice-aop`. **Renumber migration 064→066** (CV owns 064/065). DB-verify merged chain, run unit tests, push/PR/merge. Its migration test is the repo-standard `skipIf(!HAS_DB)` — DB-verify it yourself.
3. **Merge order** is flexible (migrate.js handles gaps), but cleanest is CV (064/065) then AOP (066) to fill the sequence after the existing 063→067.
4. **Optional:** rebuild `swe-af-ddd:codex` is NOT needed separately — it's retagged from `:test`; both nodes are already current at `87dfa0e`.

## Other Notes
- **Infra is UP, leave running:** `ddd-build-control-plane-1` (:8080 UI), `ddd-build-swe-agent-1` (claude, recreated @87dfa0e), `ddd-build-swe-agent-codex-1` (codex, recreated @87dfa0e — verified unshare+auth OK), `cosmichr-pg` (:5432). No active builds.
- **Both node images now carry the full hardened prompt set** (mock-hygiene + Test Integrity Gate + coder .skip-prohibition). Future builds should not game tests; still verify at reconcile.
- **Model policy:** Claude = Opus(plan)/Sonnet(code); Codex = gpt-5.5(plan)/gpt-5.4(qa)/gpt-5.4-mini(code); `enable_github_pr:false` (local-only; resume_build's ExecutionConfig rejects enable_github_pr).
- **Beads:** `bd list --status=in_progress` → none. Run bd from `/home/maceo/Dev/SWE-AF` on main (canonical per bd memory `swe-af-canonical-branch-is-feat-baml-structured`).
- **Cancel/re-fire a build:** `POST http://localhost:8080/api/v1/executions/<id>/cancel` (returns 200). Then chown clone via node → `rm -rf` → fresh clone → `git config --global --add safe.directory` on the node → resubmit. Don't reuse the dirtied clone (root-owned `.artifacts`).
