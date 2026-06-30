---
date: 2026-06-17T15:51:51-04:00
researcher: tha-hammer
git_commit: e5ee2350bfbd2f9dee8fbe67cb7810abcf6f4525
branch: fix/scope-build-verification
repository: SWE-AF
topic: "BAML SWE-AF builds for cosmic-HR + SWE-AF-4of verification-scope fix + cosmic-HR test hygiene"
tags: [swe-af, baml, orchestration, verification-scope, test-hygiene, react-19, cosmic-hr]
status: complete
last_updated: 2026-06-17
last_updated_by: tha-hammer
type: implementation_strategy
---

# Handoff: BAML builds + SWE-AF-4of fix + cosmic-HR test hygiene

## Task(s)
All COMPLETED this session:
1. **Ran 3 BAML SWE-AF builds against cosmic-HR** (Opus=plan / Sonnet=QA·review·fix / Haiku=code, Max-plan OAuth):
   - Meetings surface specs 19/20 → pushed `feature/2c1e6176-complete-meetings-tdd` (later prod-build-fixed).
   - Org-chart actionable-data (M1–M9) → salvaged + pushed `baml/orgchart-actionable-data`.
   - Meetings-detail query-param refactor (Option B1) → salvaged + pushed `baml/meetings-detail-refactor`.
2. **Diagnosed + fixed Max-OAuth staleness** that killed builds mid-run (durable `claude setup-token`).
3. **Filed + verified harness bugs** SWE-AF-vvk, SWE-AF-wtp (fixed in commit `27cb8a8`, 60 tests green) — both CLOSED.
4. **Fixed cosmic-HR prod-build breaks** (postcss try/catch, missing `generateStaticParams`, Radix `<Select.Item value="">`).
5. **Implemented SWE-AF-4of** (verification scoping) + **rebuilt `swe-af-baml:smoke`** — CLOSED.
6. **cosmic-HR test hygiene**: gated 50 pre-existing known-bad failures + added a React-19 vitest project → `chore/gate-known-bad-tests` (pushed, suite green).

## Critical References
- Memory: `~/.claude/projects/-home-maceo-Dev-SWE-AF/memory/swe-af-4of-and-cosmic-hr-test-hygiene.md` (the authoritative record of the fix).
- Memory: `swe-af-baml-meetings-build.md`, `swe-af-baml-orgchart-build.md` (build exec IDs, nodes, outcomes).
- Memory: `swe-af-max-plan-auth.md` (durable token; do NOT mount the creds file — it goes stale via atomic-rename).
- Memory: `docker-logs-oom-hazard.md` (NEVER `docker logs <container>` without `--tail`; it OOM-killed a session).

## Recent changes
**SWE-AF (this repo) — verification scoping (SWE-AF-4of):**
- `swe_af/prompts/sprint_planner.py` — two "Early Verification" sections: forbid "full/existing suite passes" acceptance criteria; require scoping to feature test files.
- `swe_af/prompts/qa.py:32` — "Run the feature's tests" (not whole repo); pre-existing failures not blocking.
- `swe_af/prompts/coder.py:71` — run feature's tests; don't fix pre-existing failures.
- Committed on `fix/scope-build-verification` (`e5ee235`) AND `feat/baml-structured-output` worktree at `/home/maceo/Dev/SWE-AF-baml` (`e746f26` — this is the branch the BAML image builds from).

**cosmic-HR `chore/gate-known-bad-tests` (off cosmic-HR04, pushed):**
- 9 DB integration test files → `describe.skipIf(process.env.REQUIRE_TEST_DB !== '1')` (commit `0115989`).
- `vitest.config.js:136` exclude block → 5 Stripe import-throwers gated on `REQUIRE_TEST_DB` (commit `0115989`).
- `recruiter-ui/vitest.config.js` (new), `recruiter-ui/vitest.setup.js` (new), `recruiter-ui/package.json` (+4 React-19 testing devDeps + `test` script) — React-19 vitest project (commit `5494570`).

**cosmic-HR feature branches (pushed earlier this session):**
- `baml/orgchart-actionable-data` (`a5f9099`) — incl. `recruiter-ui/components/recruiter/org-chart/OrgChartToolbar.jsx` Radix Select sentinel fix.
- `baml/meetings-detail-refactor` (`aaa1eb1`).
- `feature/2c1e6176-complete-meetings-tdd` (`ba53c2c`) — postcss revert + generateStaticParams placeholder.

## Learnings
- **swe-af-baml:smoke is built from the `feat/baml-structured-output` worktree (`/home/maceo/Dev/SWE-AF-baml`), NOT main.** Apply harness changes to BOTH. Rebuild: `cd /home/maceo/Dev/SWE-AF-baml && docker build -t swe-af-baml:smoke .` (Docker root = `/work_dev/docker`, 267G free; host `/` at 90% does NOT block builds).
- **Recurring failure mode (hit 3×):** builds finish all issues fine but the final `integration-verification` / `run_integration_tester` phase runs the FULL suite, loops on PRE-EXISTING failures (DB `ECONNREFUSED`, Stripe, React 18/19), and burns to the 6h cap → `status=failed`, no PR. Salvage = `docker restart <node>` to kill the spin (commits persist on bind mount), verify SCOPED tests, push the branch. SWE-AF-4of + cosmic-HR gating together prevent this going forward.
- **Max OAuth**: pass the durable `setup-token` as `CLAUDE_CODE_OAUTH_TOKEN`, empty `ANTHROPIC_API_KEY`, and do NOT bind-mount `.credentials.json` (single-file mount freezes on the old inode through atomic-rename refresh → 401 mid-build).
- **cosmic-HR repo uses vitest, not jest.** recruiter-ui prod = Next 16 Turbopack + `output:'export'`, served by Express per-path-or-404 (`backend/server.js:231-250`) → no SPA fallback (deep links to dynamic routes 404).
- **React 18/19 dual-version**: recruiter-ui is React 19; root vitest renders via React 18 → radix children rejected ("Objects are not valid as a React child"). Fix = recruiter-ui-local vitest project (dedupe to React 19 + `@testing-library/react@16`), proven on meetings branch `5e74bfd` (cosmic-hr-ka1e).
- **In-container git**: `.git` has root-owned files (builds run as root) → host commits fail "Permission denied". Commit/push from inside the node container with `git -c user.x=...` + token URL `https://x-access-token:${GH_TOKEN}@github.com/Cosmic-HQ/cosmic-HR.git`.

## Artifacts
- Handoff: this file.
- Memories (all under `~/.claude/projects/-home-maceo-Dev-SWE-AF/memory/`): `swe-af-4of-and-cosmic-hr-test-hygiene.md`, `swe-af-baml-meetings-build.md`, `swe-af-baml-orgchart-build.md`, `docker-logs-oom-hazard.md`, `swe-af-max-plan-auth.md`.
- Pushed branches on `Cosmic-HQ/cosmic-HR`: `chore/gate-known-bad-tests`, `baml/orgchart-actionable-data`, `baml/meetings-detail-refactor`, `feature/2c1e6176-complete-meetings-tdd`.
- SWE-AF branch `fix/scope-build-verification` (local; SWE-AF push is 403-blocked for tha-hammer) + `feat/baml-structured-output` worktree commit `e746f26`.

## Action Items & Next Steps
1. **Open PRs** on Cosmic-HQ/cosmic-HR for the 4 pushed branches (links printed via `…/pull/new/<branch>`). For `chore/gate-known-bad-tests`, merge to cosmic-HR04 so future builds/feature branches inherit the clean suite + React-19 project.
2. **Re-run a BAML build** on the rebuilt `swe-af-baml:smoke` against a cosmic-HR clone that includes `chore/gate-known-bad-tests` — confirm the verification phase no longer loops and the build opens its own PR (validates SWE-AF-4of end-to-end; not yet observed on a live run).
3. **Optional follow-ups** (not blocking): drop the out-of-scope commit `bf03e6e` (pipeline-test mocks) from `baml/meetings-detail-refactor` for a pure-scoped PR; consider the heavier baseline-diff (approach B) for SWE-AF-4of if scoping proves insufficient; real fix for the 5 Stripe import-throwers (lazy-init Stripe or mock).
4. **SWE-AF push**: `fix/scope-build-verification` is local-only (tha-hammer lacks write to the SWE-AF remote) — needs a maintainer with write access to push, or merge the same edits onto the canonical BAML branch.

## Other Notes
- **Beads**: no issues in_progress. Closed this session: SWE-AF-vvk, SWE-AF-wtp (in `27cb8a8`), SWE-AF-4of (this session). SWE-AF-gnm (P2, coder-broke-prod-build) remains OPEN. Run `bd dolt push && bd dolt pull` to sync.
- **Running infra**: control-plane (Go, healthy) at `localhost:8090`; idle BAML nodes `swe-baml-meetings`, `swe-baml-orgchart` (durable token); leave `swe-af-anthropic-swe-agent-1`/`swe-baml-agentplane` alone (another agent's Elixir-port work). Postgres `cosmichr-pg` is up if you set `DATABASE_URL_TEST` for integration runs.
- **Isolated clones**: `/home/maceo/Dev/cosmic-HR04-test-hygiene` (chore branch, deps installed), `-baml-orgchart`, `-baml-meetings`.
- Build exec IDs (cancelled/timed-out, salvaged): orgchart `exec_20260617_104254_cx7tcf9g`, refactor `exec_20260617_112503_20a6y8ai`, meetings `exec_20260616_185315_cw5dy0db`.
