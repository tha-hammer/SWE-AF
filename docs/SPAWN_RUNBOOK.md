# SWE-AF — How to Spawn a Build Run (Agent Runbook)

A checklist-driven guide for an agent that needs to **spawn one or more build-factory
runs** against a target repo. Covers the decision procedure and the non-obvious traps
that cause silent failures or stomp a human's work.

> This is the **spawn** companion to [`BUILD_RUNBOOK.md`](BUILD_RUNBOOK.md) (image build,
> control-plane/node ops, watchdog, auth, resume, build-db). Read section 4 there for the
> raw submit mechanics + model-role keys; read this for *how to do it without breaking things*.

---

## 0. Golden rules (read first)

1. **Never restart a node while builds are in flight.** A node restart re-registers the
   node with a new instance ID; the control-plane then fails every in-flight execution
   with `agent_restart_orphaned` ("previous process is gone, in-flight reasoner cannot be
   revived"). This is the #1 cause of mass build failure. Only `docker restart` a node
   when nothing is running on it.
2. **`POST /executions/<id>/cancel` does NOT kill the in-flight reasoner** — it only marks
   status `cancelled` while the codex/claude process keeps running on the node. To truly
   stop a build you must restart the node (see rule 1 — kills *all* in-flight). So firing
   a "replacement" build after a cancel causes a **2-build collision on the same clone**.
3. **Never spawn a build onto a repo path a human is actively editing.** Check
   `git status` first. If the working tree is dirty in the build's scope, STOP and resolve
   (commit / clone / ask) — a 6h build will stash, overwrite, or entangle that WIP.
4. **One target repo = one build.** Parallel builds on the same clone diverge/collide.
   For parallelism, give each build its **own clone** (or its own bounded file lane — see §6).

---

## 1. Pre-flight checklist (before every spawn)

```bash
# a) factory is up
docker ps --filter name=ddd-build --format '{{.Names}}\t{{.Status}}'
#    need: control-plane + the target node (swe-planner=claude / swe-planner-codex=codex), all healthy

# b) capacity — ~2-3 heavy builds per ~24G free; back off < 8G avail
free -g | awk '/^Mem:/{print "avail="$7"G"}'; cut -d' ' -f1-3 /proc/loadavg

# c) target repo is a clean git repo on the intended base
git -C <repo> rev-parse --is-inside-work-tree
git -C <repo> branch --show-current && git -C <repo> log --oneline -1
git -C <repo> status --porcelain        # MUST be empty in the build's scope (see Golden rule 3)

# d) the build's INPUT docs (plan/research/PRD it must READ) are present IN the repo tree
#    — and whether they are TRACKED or just on-disk (matters for clones, see §3)
```

---

## 2. Decide: in-place vs dedicated clone

| Situation | Spawn into | Why |
|-----------|-----------|-----|
| Repo is clean, not your active checkout, single build | **in-place** | simplest; matches how runs are usually set up |
| Repo has uncommitted WIP **outside** the build scope | in-place OK (build branches off HEAD) | but confirm scope files are clean |
| Repo is **your active checkout** / has a fix branch / pending integration | **dedicated clone** | a 6h build locks the repo + can entangle your branch |
| Repo has WIP **inside** the build scope | **commit WIP first**, then in-place or clone off that commit | else the build overwrites it or builds on a stale base |
| Running **N builds in parallel** | **N clones** (or §6 lanes) | shared clone → divergent forks + merge collisions |

Make a clone:
```bash
git clone --quiet <repo> <repo>-<slice>      # full clone, NOT a worktree*
git -C <repo>-<slice> checkout -q <base-branch>
```
\* **Worktrees break inside the container** — they store host-absolute `.git` paths that
don't resolve under the node's `/workspaces/dev` mount. Always use a full clone.

---

## 3. Stage the build's input docs (the untracked-input trap)

The build runs at `repo_path` and reads its plan/research/PRD **from that tree**. If those
docs are **untracked** (common — they're often freshly written), a `git clone` will NOT
copy them. Copy them into the clone explicitly:

```bash
# example: plan/research live under thoughts/, mockups under a design dir
cp -rn <repo>/thoughts <repo>-<slice>/ 2>/dev/null
cp -n  <repo>/ARCHITECTURE.md <repo>-<slice>/ 2>/dev/null
cp -rn <repo>/<design-or-mockups-dir> <repo>-<slice>/ 2>/dev/null
# then VERIFY each path the goal references actually exists in the clone:
ls <repo>-<slice>/<each-referenced-plan/research/mockup-path>
```

Also confirm any **sibling-repo references** the goal cites (e.g. reading another repo for
schema/fixtures) are reachable: the node mounts `/home/maceo/Dev:/workspaces/dev`, so
`/home/maceo/Dev/<sibling>` → `/workspaces/dev/<sibling>` resolves automatically.

---

## 4. Build the payload

`repo_path` is the **container** path: `/workspaces/dev/<dir>` (host `/home/maceo/Dev/<dir>`).

```bash
# reuse a known-good codex config (planner gpt-5.5, qa/review gpt-5.4) from any prior payload:
CONFIG=$(jq -c '.input.config' <some-prior-codex-payload>.json)

jq -n --rawfile g goal.txt --arg rp "/workspaces/dev/<dir>" --argjson cfg "$CONFIG" \
  '{input:{goal:$g, repo_path:$rp, config:$cfg}}' > payload.json
```

**Write the goal to a file** (`--rawfile`) — goals are long and JSON-escaping them inline
is error-prone. A good goal states: read <plan/research> IN FULL first; this is a CODING
(or docs) run not planning; the exact scope + owned paths; what is frozen/out-of-scope;
tech stack as the repo already uses it; test command; "commit locally on an integration
branch, do NOT push and do NOT open a PR"; apply CodeCleanup; deliver working committed code.

Config: `runtime` = `codex` or `claude_code`; `enable_github_pr:false`; model-role keys per
[`BUILD_RUNBOOK.md` §4](BUILD_RUNBOOK.md). If the build wrote a `prd.md` before failing, you
can reconstruct a lost goal from `<repo>/.artifacts/plan/prd.md`.

---

## 5. Launch + verify it actually started

```bash
curl -s -X POST http://localhost:8080/api/v1/execute/async/<NODE_ID>.build \
  -H 'Content-Type: application/json' -d @payload.json | jq '{execution_id,status,error}'
#   NODE_ID = swe-planner (claude) | swe-planner-codex (codex). Returns status:queued.

# within ~30s confirm running (not orphaned by a node blip):
curl -s http://localhost:8080/api/v1/executions/<exec_id> | jq '{status,error}'   # -> running
```

If status is `failed` with `agent_restart_orphaned`, the node restarted under it — relaunch
(Golden rule 1). If `repo_path` was wrong, the build dies early with an empty/partial
`.artifacts/plan/` and no checkpoint.

---

## 6. Parallel runs — keep them from colliding

If you must run multiple builds touching the **same** codebase concurrently, isolate them
so two builds never edit the same file:

- **Each build in its own clone** (preferred), merged back one at a time afterward.
- Or an **ownership manifest** + **additive seams** so each slice only adds new files:
  auto-discovery instead of editing a shared registry (e.g. router/model auto-import),
  per-slice file lanes, a frozen-shared-file list, and reserved migration-id namespaces.
  Bake the manifest + the slice's exclusive paths into each goal; tell builds "if you must
  edit a frozen file, STOP and report it." (See the marketing-slice precedent: builds
  self-policed and touched zero frozen files.)
- The one seam this usually misses: **shared build config** (`package.json`, lockfiles,
  `tailwind.config`, `playwright.config`) — expect to **union-merge** those at integration.

---

## 7. Monitor without OOM-ing yourself

```bash
# poll status (cheap):
curl -s http://localhost:8080/api/v1/executions/<exec_id> | jq '{status,error}'
# progress: the clone's checkpoint (current_level / merged_branches):
cat <repo>/.artifacts/execution/checkpoint.json | jq '{current_level,merged_branches}'
# node logs: ALWAYS --tail / --since (debug logs are hundreds of MB → docker logs OOM trap):
docker logs --tail 200 ddd-build-swe-agent-codex-1 2>&1 | grep -iE 'error|fail|orphan'
```

To wait on a long build, run a background poll-loop that exits on terminal status (and on
low-RAM as a safety trip), rather than blocking. Prefer one watcher per wave.

**`timeout` ≠ failure.** A build that "fails" with *"Reasoner 'build' timed out after
21600.0s"* hit the 6h watchdog cap during QA/merge polish — its code is usually complete
and its work is on the integration branch. Verify the branch (commits landed, tests green)
before treating it as a real failure.

---

## 8. After a build finishes — verify & reconcile

```bash
# find the build's integration branch in its clone:
git -C <repo> branch | grep -v '^\*\? *\(main\|master\)$'

# verify lane discipline (parallel runs) — frozen files must be UNTOUCHED:
git -C <repo> diff --name-only <base>..<integration> | grep -E '<frozen-file-list>'   # expect empty

# merge back (off the shared base), resolve any union-merge config, run tests under TZ=UTC
# (host-local TZ causes off-by-one date-test flakes that pass in the build's UTC container).
```

**Ownership note:** builds run as **root** in the node, so a build's clone/`.artifacts`/branch
refs end up `root:root`. For host-side git ops either `sudo chown -R $USER <repo>` or run git
through the node: `docker exec <node> git -C /workspaces/dev/<dir> <cmd>` (this is also how
you delete a root-owned branch ref the host can't).

---

## 9. Failure triage cheat-sheet

| Symptom | Cause | Fix |
|---------|-------|-----|
| All in-flight builds `failed` together, `agent_restart_orphaned` | node was restarted mid-flight | relaunch; never restart a node with builds running |
| Build `failed` instantly, empty/partial `.artifacts/plan/`, no checkpoint | bad `repo_path`, or repo not a git repo at that path | fix path (container `/workspaces/dev/...`); ensure it's a git repo |
| Two builds fighting over one clone | fired a replacement after a `/cancel` that didn't actually stop the first | restart node to clear both, then fire exactly one |
| `failed: timed out after 21600s` | 6h watchdog cap during polish | verify branch is complete/green — usually a real success |
| Greenfield build's only commit vanished | (historical) merge-orphan bug | fixed in `dag_executor.py` (verify-then-merge) — ensure node/image carries it |
| Host git op "permission denied" on a build's files/refs | build ran as root | `chown -R $USER` or run git via `docker exec <node>` |
| A build "looks partial" — issue branches unmerged | stale worktree refs / consolidated slices | authoritative ref check → §10c (it may already be complete) |
| Unsure if a dashboard row is a rogue run | child execution of your build | classify by parent/root → §10b |

→ Step-by-step diagnostics for each of these are in **§10 Debugging recipes**.

---

## 10. Debugging recipes (from real incidents)

The control-plane `GET /api/v1/executions` **list endpoint does not exist** (404), and the
single-execution API does **not** return `reasoner`/`parent`/`repo_path`/`goal` (all null).
So the **node logs are the source of truth** for what ran and how it's related. Always
`--since`/`--tail` them (raw `docker logs` OOMs — see §7).

### 10a. Mass failure: every in-flight build died at once

```bash
# 1) Is it the orphan trap? Look for the signature:
docker logs --since 90m ddd-build-swe-agent-codex-1 2>&1 | grep -i 'agent_restart_orphaned' | head
#    "swe-planner-codex re-registered with new instance X (was Y); in-flight reasoner cannot be revived"

# 2) Confirm the node restarted — and WHY (clean restart vs OOM/crash):
docker inspect ddd-build-swe-agent-codex-1 \
  --format 'RestartCount={{.RestartCount}} OOMKilled={{.State.OOMKilled}} ExitCode={{.State.ExitCode}} StartedAt={{.State.StartedAt}} FinishedAt={{.State.FinishedAt}}'
#    RestartCount=0, OOMKilled=false, ExitCode=0, sub-second Started↔Finished gap = a DELIBERATE
#    `docker restart` (someone stopped a build the wrong way). OOMKilled=true / nonzero exit = resource crash.
dmesg 2>/dev/null | grep -iE 'killed process|out of memory' | tail   # kernel OOM (often needs sudo)
```
Fix: relaunch the orphaned builds (reconstruct goals from each repo's `.artifacts/plan/prd.md`).
Root-cause prevention is Golden Rule 1 — don't restart a node with builds in flight; if you
must stop one build, you still take the whole node down, so drain first.

### 10b. "Is this a new run something spawned, or a child of mine?"

A build fans out into many child executions (`plan`, `execute`, then per-issue `run_coder`/
`run_qa`/`run_code_reviewer`/`run_qa_synthesizer`), **each with its own exec_id** — so the
dashboard shows many rows per build. Builds do **not** spawn sibling top-level runs. Classify
any suspicious exec_id from the logs:

```bash
LOG=/tmp/cclog.txt; docker logs --since 100m ddd-build-swe-agent-codex-1 > "$LOG" 2>&1
# what is exec X — a top-level build or a child?
grep -F '"execution_id":"<exec_X>"' "$LOG" | head -1 | jq -c '{reasoner:.reasoner_id, parent:.parent_execution_id, root:.root_workflow_id}'
#    reasoner:"build" + parent:null  => a real top-level run
#    parent:"exec_…" / reasoner:"execute|run_coder|…" => a CHILD of that parent build
# count the REAL builds = distinct root workflows (each root = one top-level build you launched):
grep -oE '"root_workflow_id":"[^"]+"' "$LOG" | sort -u
```
If the distinct-root count == the number you launched, nothing self-spawned.

### 10c. Assessing a finished/timed-out build's completeness

Worktree-backed builds create per-issue branches under `.worktrees/`; `git branch`'s `+`
(checked-out-in-worktree) view is **unstable between reads** and stale worktrees are marked
`prunable`. Don't trust a single `git branch` snapshot — take an **authoritative** one:

```bash
# stabilize the ref view first (root-owned → via node):
docker exec <node> git -C /workspaces/dev/<repo> worktree prune
# authoritative: every head + whether it's merged into the integration branch:
IB=<integration-branch>
for r in $(git -C <repo> for-each-ref --format='%(refname:short)' refs/heads); do
  [ "$r" = "$IB" ] && continue
  git -C <repo> merge-base --is-ancestor "$r" "$IB" 2>/dev/null \
    && echo "MERGED   $r" || echo "UNMERGED(+$(git -C <repo> rev-list --count $IB..$r)) $r"
done
```
**Pitfall:** the first integration branch your grep matches is often a *stale orphan branch*
(0 commits ahead) — the real one is usually the **checked-out** branch (`*`) with the merge
commits. And an issue that looks "unmerged" may already be present: check whether its files
exist on the integration branch (`git ls-tree -r $IB --name-only | grep <its-files>`) before
concluding work is missing.

### 10d. Before discarding a build's dirty working tree — check its DIRECTION

A timed-out build can leave a confused/reverted state staged. Never `reset --hard` blindly —
verify what the dirty tree actually does first:

```bash
git -C <repo> diff --cached --stat | tail -1                 # how big
D=$(git -C <repo> diff --cached)
echo "$D" | grep -cE '^\+.*<NEW-BRAND>'   # additions toward the goal
echo "$D" | grep -cE '^\-.*<NEW-BRAND>'   # removals of goal work  ← if this dominates, the tree is a REGRESSION
```
In one incident the "163 dirty files" were a **reverse-rebrand** (581 deletions of the new
brand) the build staged near timeout — discarding it (`reset --hard <integration>`) was the
*correct* action, not data loss. Direction-check first; then decide.

### 10e. Verify a reconciliation actually works (don't just merge)

After resolving conflicts / discarding regressions, run the build's **own** verification, not
just a build:

```bash
docker exec <node> bash -lc 'cd /workspaces/dev/<repo>/<subtree> && go build ./... && go test ./...'
# many builds ship their own acceptance tests — run them:
docker exec <node> bash -lc 'cd /workspaces/dev/<repo> && python3 -m pytest tests/test_*rebrand*.py -q'
```
Run anything date-sensitive under `TZ=UTC` (the build container is UTC; host-local TZ throws
off-by-one date-test flakes that look like real failures).

### 10f. Conflict-resolution heuristic for these builds

Slice/behavior builds are **additive** — most merge conflicts are two sides appending to the
same file (DTOs in `port.go`, copy keys in `ui.json`, an auto-changelog). Resolve by **union**
(keep both blocks). When the same key has two values, prefer the one set by the behavior that
*owns* that concept (e.g. the brief/evidence behavior's `"Evidence unavailable"` over an
earlier placeholder), and confirm against the plan's Desired-End-State examples.

### 10g. `git clean -fd` will wipe untracked build inputs

Build input docs (plan/research/mockups) are often **untracked** (§3) and a build does not
commit them. `git clean -fd` during cleanup **deletes them**, breaking a re-launch/continuation.
Re-copy from the live source before re-firing, and prefer targeted `rm -f .agentfield_*.json`
over a blanket `clean` when scrubbing scratch on a repo whose inputs are untracked.

---

## 11. Minimal happy-path recipe

```bash
# clean repo, single in-place codex run:
G=/tmp/goal.txt   # write the goal (read plan IN FULL; coding run; scope; commit on integ branch; no push/PR)
CONFIG=$(jq -c '.input.config' <prior-codex-payload>.json)
jq -n --rawfile g "$G" --arg rp "/workspaces/dev/<dir>" --argjson cfg "$CONFIG" \
  '{input:{goal:$g, repo_path:$rp, config:$cfg}}' > /tmp/payload.json
curl -s -X POST http://localhost:8080/api/v1/execute/async/swe-planner-codex.build \
  -H 'Content-Type: application/json' -d @/tmp/payload.json | jq '{execution_id,status}'
# confirm running, then monitor per §7.
```
