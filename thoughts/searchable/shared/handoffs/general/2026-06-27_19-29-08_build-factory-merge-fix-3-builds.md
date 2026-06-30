---
date: 2026-06-27T19:29:08-04:00
researcher: tha-hammer
git_commit: a7048cd85db9620716c2882b1a54e9a3e22d51d3
branch: main
repository: SWE-AF
topic: "Build-factory greenfield merge-orphan fix + 3 concurrent PRD/plan builds"
tags: [swe-af, build-factory, dag-executor, merge-bug, codex, claude_code, contract-upload, signalops, marketing, greenfield]
status: in_progress
last_updated: 2026-06-27
last_updated_by: tha-hammer
type: implementation_strategy
---

# Handoff: build-factory greenfield merge-orphan fix + 3 builds (2 running, 1 held)

## Task(s)
1. **Run 3 builds on the SWE-AF build factory** (control-plane :8080, nodes `swe-planner`=claude / `swe-planner-codex`=codex):
   - **contract-upload (codex)** — `exec_20260627_191706_43hba8yk` on `swe-planner-codex`, clone `/home/maceo/Dev/cosmic-HR04-contract-upload`. **RUNNING, healthy, 7/8, 0 failed** — real commits landing (existing repo → immune to the bug below). Completion watcher `b1d54teht`.
   - **signalops (greenfield Python port)** — first run was codex (`exec_…205136`, **CANCELLED** after hitting the merge bug). **Re-fired on claude_code** as the fix CANARY: `exec_20260627_232602_o2bsuc56` on `swe-planner`, in-place `/home/maceo/Dev/silmari-signalops`. **RUNNING.** Fix-validation watcher `bodzhmo3b`.
   - **marketing tool (PRD, claude_code)** — `exec_…221009` **CANCELLED** (greenfield, would have orphaned on the unpatched node). **HELD** — to be re-fired on `swe-planner` once the canary proves the fix. Repo `/home/maceo/Dev/silmari-ai-marketing-tool`, greenfield, initial commit `412c3b5`.
2. **Fix the greenfield merge-orphaning bug in the build orchestrator** — ✅ IMPLEMENTED + hot-patched live on the claude node; ⚠️ **NOT committed, NOT in the image, codex node NOT patched.**

## Critical References
- `docs/BUILD_RUNBOOK.md` — factory ops (auth, submit, watchdog, codex traps, build-db). READ FIRST.
- `swe_af/execution/dag_executor.py` — the orchestrator + **the fix** (uncommitted working-tree change).
- Plans/PRD driving the builds:
  - `/home/maceo/Dev/cosmic-HR04/thoughts/searchable/shared/plans/2026-06-27-13-33-ENG-contract-upload-hitl-tdd.md`
  - `/home/maceo/Dev/silmari-signalops/thoughts/searchable/shared/plans/2026-06-27-silmari-signalops-port-plan.md`
  - `/home/maceo/Dev/silmari-ai-marketing-tool/monte-carlo-ai-marketing-tool/PRD.md` (+ chosen techstack baked into `payload_marketing.json`)

## Recent changes
**THE FIX — `swe_af/execution/dag_executor.py`** (working tree on `main`, `py_compile` OK):
- `:9` `import subprocess`.
- `:41 _git()`, `:49 _branch_is_merged()` (`git merge-base --is-ancestor`), `:54 _deterministic_merge()` (checkout integration + `git merge --no-ff`, abort on conflict).
- `:317` in `_merge_level_branches` (single-repo path), after the LLM merger call: **verify each completed branch actually landed; if not, merge it deterministically**; then `merge_result["merged_branches"]/["failed_branches"]/["success"]` are OVERRIDDEN with verified reality (so `dag_state.merged_branches` is trustworthy).
- `:1744` cleanup gate: `branches_to_clean` is now filtered to branches in `dag_state.merged_branches`; unmerged ones are kept (logged as `kept`), never `git branch -D`'d.
- **Applied live:** `docker cp` that file into `ddd-build-swe-agent-1:/app/swe_af/execution/dag_executor.py` + `docker restart ddd-build-swe-agent-1`. Verified importable in-container. The codex node (`ddd-build-swe-agent-codex-1`) was deliberately NOT touched (contract-upload runs there).

**Build repos:** initial commits created so greenfield builds have a base — signalops `80ac818`, marketing `412c3b5` (both on `master`, with a Python/Node `.gitignore`). signalops's orphaned first-run scaffold preserved as **dangling commit `dc794a80` / tag `recovered-bootstrap`**.

## Learnings
- **Root cause of the orphan bug:** On a greenfield repo the integration branch is `main`/`master` itself (`swe_af/prompts/git_init.py:67`). The **LLM merger agent** (`swe_af/prompts/merger.py`, success contract is loose — "or at least some did", :76) perceives merging an issue branch into a near-empty `main` as a no-op and reports `success=true, merged_branches=[]` WITHOUT merging. Then cleanup (`swe_af/prompts/workspace.py:56-69` "force-delete whether or not merged") `git branch -D`s the unmerged branch → the only commit becomes dangling. Existing repos use a distinct `feature/<slug>` integration branch clearly behind the issue branch, so the merge is unambiguous → they work. The old code never verified the merge landed before deleting (`dag_executor` built the cleanup list from `active_issues`, not `merged_branches`).
- **`checkpoint.merged_branches` is the LLM merger's self-report and is UNRELIABLE** (contract-upload shows `merged:0` yet its commits are reachable). Trust `git` (ancestor check / integration HEAD advancing), not the checkpoint field. The fix now makes `dag_state.merged_branches` reflect verified reality.
- **codex coder is NOT producing empty output this session** — both signalops (codex, 43-line `pyproject.toml` + 24 files) and contract-upload wrote real files. The signalops failure was orchestration (orphaned merge), not the codex empty-coder bug.
- **Hot-patch persistence:** `docker cp` + `docker restart` keeps the change in the container's writable layer; survives restart but **lost on `docker compose ... --force-recreate`**. So the fix must be committed + image rebuilt for durability, and the codex node patched separately.
- **`/api/v1/nodes` lags** — after restart `swe-planner` didn't list for minutes but builds still route to `swe-planner.build` (known registration-display quirk).
- **dubious-ownership:** build repos are user-1000-owned; node git runs as root → `git_init` adds `safe.directory`. For MANUAL git ops on these repos, run from the **host** (owner), not the node.
- **DB contention:** contract-upload uses the shared `build-db` Postgres; greenfield builds were told to use **SQLite for tests** (no contention). Runbook rule: DB-dependent builds one at a time.
- **RAM:** 78G host; 3 concurrent builds ran fine (~30G free). The earlier 14G dip was a transient `npm install`.

## Artifacts
- **Fix (uncommitted):** `swe_af/execution/dag_executor.py` (lines 9, 41-72, ~307-352, ~1736-1762).
- **Payloads:** `/tmp/claude-1000/-home-maceo-Dev-SWE-AF/f7d5b021-6566-4253-9523-6c75df308fff/scratchpad/` → `payload_contract_upload.json`, `payload_signalops.json` (codex), `payload_signalops_claude.json` (claude re-fire), `payload_marketing.json` (HELD — ready to submit).
- **Watchers (background bash):** `watch_done.sh`(b1d54teht, contract-upload completion), `watch_fix.sh`(bodzhmo3b, signalops fix-validation), plus `watch_build.sh`/`watch_signalops.sh`/`watch_marketing.sh` (first-issue, mostly fired).
- **Build clones/repos:** `/home/maceo/Dev/cosmic-HR04-contract-upload` (codex, integration branch `597463d0-contract-upload-hitl-tdd`); `/home/maceo/Dev/silmari-signalops` (in-place); `/home/maceo/Dev/silmari-ai-marketing-tool` (in-place).
- Prior related handoff: `/home/maceo/Dev/cosmic-HR04/thoughts/searchable/shared/handoffs/general/2026-06-26_17-34-08_contract-view-graph-render-fitview.md`.

## Action Items & Next Steps
1. **Validate the fix (CANARY):** watch `bodzhmo3b` output (`/tmp/claude-1000/-home-maceo-Dev-SWE-AF/5d698055-0fbd-41d5-b699-3e63599388a8/tasks/bodzhmo3b.output`). PASS = signalops first issue's commit lands on integration (`git -C /home/maceo/Dev/silmari-signalops rev-list --count <integ>` > 1 AND `pyproject.toml` present on the integration branch). FAIL = still orphaning → debug the `:317` reconciliation.
2. **If PASS → re-fire marketing:** `curl -s -X POST http://localhost:8080/api/v1/execute/async/swe-planner.build -H 'Content-Type: application/json' -d @<scratchpad>/payload_marketing.json`. (Greenfield, claude_code, in-place at `/home/maceo/Dev/silmari-ai-marketing-tool`.)
3. **Durability:** commit the fix on a **branch off main** (don't commit on `main` directly), then rebuild the image (`docker compose build swe-agent` per runbook §1) so it survives node recreation.
4. **Patch the codex node** (`ddd-build-swe-agent-codex-1`) with the same fix **after contract-upload finishes** (don't disrupt it): same `docker cp` + `docker restart`, or recreate from the rebuilt image. Until then, codex greenfield builds remain buggy.
5. **Reconcile finished builds** (manual; `enable_github_pr:false`):
   - contract-upload → its work is on integration `597463d0-contract-upload-hitl-tdd` in the codex clone; verify, merge into `cosmic-HR04`, open PR (the prior CV PRs #45/#46 pattern).
   - signalops / marketing greenfield → merge the build's integration branch into `master`.
6. **Watch contract-upload completion** via `b1d54teht`.

## Other Notes
- **bd:** `bd list --status=in_progress` → none. (Run bd from `/home/maceo/Dev/SWE-AF` on main.) AgentMail: not used this session; one investigation subagent `a710bad4138baa3a6` (root-caused the merge bug) can be continued via SendMessage if needed.
- **Build factory live state:** control-plane `ddd-build-control-plane-1` (:8080), `ddd-build-swe-agent-1`=`swe-planner` (claude, PATCHED), `ddd-build-swe-agent-codex-1`=`swe-planner-codex` (codex, UNPATCHED), `ddd-build-build-db-1` (Postgres). Watchdog 21600 on both nodes.
- **Monitor:** `curl -s http://localhost:8080/api/v1/executions/<exec_id> | jq '{status,error}'`; progress via `<clone>/.artifacts/execution/checkpoint.json`. Use `docker logs --tail N` only (OOM trap).
- **The cancelled marketing run's Claude planning was deep/good** (architect-review loop, 50+ acceptance criteria) before cancel — re-firing will redo planning cleanly on the patched node.
