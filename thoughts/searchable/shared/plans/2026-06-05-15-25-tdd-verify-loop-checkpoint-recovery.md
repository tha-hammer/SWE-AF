# Verify→Fix Loop Recovery & Checkpoint Stomp Protection — TDD Implementation Plan

## Implementation Status — ✅ COMPLETE (2026-06-07)

All seven behaviors implemented via TDD (Red→Green) and verified. 23 new tests,
all green; zero new failures or lint errors introduced (the 33 full-suite
failures are pre-existing NODE_ID/model_config ordering pollution — confirmed by
stashing source: 5 of them fail on a clean tree too).

- **B1** `_save_checkpoint` build_id-aware don't-shrink guard — `dag_executor.py`
  (`_existing_checkpoint_meta` + guard). Tests: `tests/test_checkpoint_guard.py` (5).
- **B3** namespaced fix checkpoints (`checkpoint_label`) — `_checkpoint_path`,
  `_save_checkpoint`, `run_dag` (7 save sites), `app.py` `execute` + fix call.
  Tests: `tests/test_checkpoint_namespacing.py` (3) + integration.
- **B2** main-DAG snapshot — `_dump_main_dag_result` + call site before the loop.
- **B4** convergence — `_failed_criteria_signature` + loop break.
- **B5** accept-partial debt — `_criteria_to_debt`/`_record_criteria_debt` at all
  terminal paths (cycle-cap, converged, no-fix, soft-deadline).
- **B6** soft time budget — `verify_fix_soft_deadline_seconds` (3600 default),
  `max_verify_fix_cycles` 1→2, `_within_soft_deadline` + between-cycles guard.
- **B7** cross-cycle history — `previously_failed_criteria` threaded
  `app.py` → `generate_fix_issues` → `fix_generator_task_prompt`.
  Tests B2/B4/B5/B6 in `tests/test_verify_fix_recovery.py` (10), B7 in
  `tests/test_fix_generator_history.py` (2), wiring in
  `tests/test_verify_fix_loop_integration.py` (3).

### Implementation Order (done)
- [x] 1. B1 (guard)
- [x] 2. B3 (namespacing)
- [x] 3. B2 (snapshot)
- [x] 4. B4 (convergence) + B5 (accept-partial)
- [x] 5. B6 (soft budget)
- [x] 6. B7 (history)

## Overview

Two defects, confirmed against source in
`thoughts/shared/research/2026-06-05-15-00-verify-fix-loop-checkpoint-stomp.md`:

- **P1** — the verify→fix loop (`app.py:952-1035`) has a single termination
  guard (cycle count). It has no convergence detection, no accept-partial path,
  no time awareness, and never tells the fix-generator what failed in prior
  cycles. A single fix cycle is a full DAG run that can consume the entire
  external 7200s budget.
- **P2** — fix-DAG execution writes its `DAGState` over the main DAG's
  checkpoint. `_checkpoint_path` (`dag_executor.py:683`) is a single fixed path
  keyed only on `artifacts_dir`; the fix `execute` reuses the same
  `artifacts_dir` (`app.py:1021`) with no overwrite guard.

This plan implements all seven behaviors (P2: B1+B2+B3; P1: B4+B5+B6+B7) via
**pure helpers** (fast, isolated Red→Green unit tests) plus thin integration
tests that assert the wiring inside `build()`. Every change is additive and
backward-compatible: new params default to today's behavior.

### Scope & timing semantics (read this first)

This plan delivers **checkpoint integrity + forensics + debt recording**, plus a
**between-cycles wall-clock budget**. Two defaults are deliberately raised so the
new protection is active out of the box (see Behavior 6):

- **`max_verify_fix_cycles`: 1 → 2** — allows up to 2 fix attempts, which is what
  gives convergence (B4), the time budget (B6), and cross-cycle history (B7)
  something to act on.
- **`verify_fix_soft_deadline_seconds`: 0 → 3600** — turns the time budget on.
  `0` still disables it.

Be precise about what bounds what:

- **Nothing here interrupts an in-flight fix DAG.** B6 (soft deadline) is a
  *between-cycles* gate: it is evaluated *before* launching a fix DAG
  (`app.py:1024`), at `elapsed = monotonic() - verify_loop_start`. The first fix
  cycle launches at `elapsed ≈ 0`, so it is **never** gated. The wall-clock of a
  *single* fix cycle is bounded only by the inner `agent_timeout_seconds` (2700s) ×
  retries × advisor — out of scope here.
- **Why these two numbers stay under the external 7200s cap.** The deadline gates
  the *start* of a cycle, so the worst case is `deadline + one_full_cycle` ≈
  `3600 + 2700 = 6300s` < 7200s. With `max_verify_fix_cycles = 2`: cycle 1 launches
  at `elapsed ≈ 0`; before cycle 2 the guard checks elapsed against 3600 and stops
  if exceeded. So total fix time is bounded by ~6300s with comfortable headroom.
- **B4/B6/B7 are now ACTIVE by default** (they require ≥2 fix cycles, which the new
  default provides). With the old default of 1 they were dormant; that note no
  longer applies.
- **Cost trade-off (call this out to operators):** raising `max_verify_fix_cycles`
  to 2 means a build that fails verification may now attempt a *second* fix cycle
  it previously would not have — more time and model spend on hard-to-verify
  builds. The soft deadline caps that growth, and any operator can restore the old
  behavior with `max_verify_fix_cycles=1` (or disable the budget with
  `verify_fix_soft_deadline_seconds=0`).
- **Always-on regardless of the cycle/deadline knobs**: no checkpoint stomp
  (B1+B3), a forensic main-DAG snapshot (B2), and still-failing criteria recorded
  as debt (B5).

## Current State Analysis

### Key Discoveries

- Verify→fix loop: `swe_af/app.py:952-1035`. Only guard at `app.py:968`
  (`verification.get("passed") or cycle >= cfg.max_verify_fix_cycles`).
  `failed_criteria` recomputed fresh each cycle at `app.py:972-975`.
- `max_verify_fix_cycles: int = 1` and `agent_timeout_seconds: int = 2700` live
  on `BuildConfig` (`swe_af/execution/schemas.py:697`, `:730`), `extra="forbid"`.
  The loop reads `cfg.max_verify_fix_cycles` (a `BuildConfig`).
- Checkpoint: `_checkpoint_path(dag_state)` → `<artifacts_dir>/execution/checkpoint.json`
  (`dag_executor.py:683-685`). `_save_checkpoint(dag_state, note_fn=None)`
  unconditional `open(path, "w")` (`dag_executor.py:688-697`). 7 save sites
  (all inside `run_dag`): `1436, 1505, 1517, 1557, 1676, 1734, 1799`.
- Checkpoint readers (all hardcoded to `checkpoint.json`): `resume_build`
  (`app.py:2014`); `_load_checkpoint` (`dag_executor.py:702`) called only at
  `run_dag`'s `resume=True` path (`dag_executor.py:1413-1416`). The fix `execute`
  call (`app.py:1024`) passes **no `resume`** → fix-DAGs never read a checkpoint.
- `execute(plan_result, repo_path, …, resume=False, build_id="", workspace_manifest=None)`
  (`app.py:1543-1599`) forwards to `run_dag(..., resume=resume, build_id=build_id, …)`
  at `app.py:1586-1598`.
- `run_dag(..., resume=False, build_id="", workspace_manifest=None)`
  (`dag_executor.py:1352-1363`).
- `generate_fix_issues(failed_criteria, dag_state, prd, artifacts_dir="", model="sonnet", permission_mode="", ai_provider="claude", workspace_manifest=None)`
  (`execution_agents.py:1297-1307`) → `{fix_issues, debt_items, summary}`.
  Prompt built by `fix_generator_task_prompt(failed_criteria, dag_state_summary, prd)`
  (`fix_generator.py:55-111`).
- `DAGState` (`schemas.py:276`): `all_issues: list[dict]` (count = total issues),
  `accumulated_debt: list[dict]`, `build_id: str`, `completed_issues: list[IssueResult]`.
- `app.py` does **not** import `time` (`app.py:9-26`).

### Existing test conventions (to follow)

- pytest + `pytest-asyncio`, `asyncio_mode = "auto"` (`pyproject.toml:21`).
  `make test` → `pytest tests/ -x -q`.
- `build()` integration: `patch.object(app, "call", side_effect=mock_call)`
  routing by target substring + patch `_unwrap` (`tests/fast/test_app.py:260-281`).
  Root fixture `mock_agent_ai` patches `swe_af.app.app.call` (`tests/conftest.py:120-156`).
- DAGState factories: `tests/test_coding_loop.py:28-36`, `test_planner_execute.py:50-70`.
- Checkpoint file I/O via `tmp_path` + `os.path.exists` / `Path.write_text`
  (`test_coding_loop.py:638-658`, `test_coding_loop_regressions.py:17-37`).
- `criteria_results` mock shape: `[{"criterion": "...", "passed": bool}]`
  (`tests/fast/test_verifier.py:162-179`).
- `_save_checkpoint`/`_load_checkpoint`/`_checkpoint_path` have **no direct unit
  tests today** — new tests here are greenfield.

## Desired End State

### Observable Behaviors

- Given an on-disk checkpoint with more issues than the current `DAGState`, when
  `_save_checkpoint` runs, then the file is not overwritten.
- Given the main DAG result, when `build()` enters the verify loop, then a
  `main-dag-result.json` snapshot exists on disk.
- Given a fix `execute` with a `checkpoint_label`, when it runs `run_dag`, then it
  writes `checkpoint-fix-<cycle>.json` and leaves `checkpoint.json` untouched.
- Given two verify cycles with an identical failing-criteria set, when the loop
  runs, then it stops without launching another fix DAG.
- Given the loop terminates with criteria still failing, then those criteria are
  recorded in `accumulated_debt`.
- Given a configured soft deadline already exceeded, when the loop is about to
  launch a fix DAG, then it stops and accepts-partial instead.
- Given a second+ verify cycle, when fix issues are generated, then the
  fix-generator receives the prior cycles' failed criteria.

## What We're NOT Doing

- Not changing the external 7200s `AgentField` cap (not in this repo).
- Not making fix-DAGs resumable (the namespaced fix checkpoint stays write-only).
- Not changing the loop's cycle-count *guard* logic. We **do** raise the
  `max_verify_fix_cycles` **default** (1 → 2) and add a non-zero
  `verify_fix_soft_deadline_seconds` **default** (3600) so B4/B6/B7 are active out
  of the box — see Behavior 6. The loop structure and the `cycle >= max` guard are
  unchanged.
- Not refactoring `build()` or `run_dag` structurally — only threading params and
  inserting guard calls.
- Not touching `ExecutionConfig` (the soft deadline lives on `BuildConfig`, read
  in `build()`). Verified: `to_execution_config_dict()` (`schemas.py:822-848`) is
  an explicit 20-key whitelist, so the new `BuildConfig` field is **not** forwarded
  to `ExecutionConfig` and cannot trip its `extra="forbid"`.
- Not bounding the duration of a single in-flight fix DAG. The soft deadline is a
  *between-cycles* gate (it stops *starting* another cycle, not a running one); a
  single fix cycle is bounded only by `agent_timeout_seconds`, which we do not
  change. With the new defaults total fix time is bounded by ~`3600 + 2700` ≈
  6300s (see "Scope & timing semantics").
- Not assuming a unique `artifacts_dir`. B1's guard is `build_id`-aware so it
  stays correct even when an explicit local `repo_path` causes `artifacts_dir`
  reuse across builds (cross-build writes fail open — see Behavior 1 edge cases).
  We do **not** add `build_id` to the checkpoint *path* (out of scope; the in-file
  `build_id` field is sufficient for the guard).

## Testing Strategy

- **Framework**: pytest + pytest-asyncio (`asyncio_mode = "auto"`).
- **Unit**: pure helpers (`_save_checkpoint` guard, `_dump_main_dag_result`,
  `_failed_criteria_signature`, `_criteria_to_debt`, `_within_soft_deadline`,
  `_checkpoint_path` label) — direct calls, `tmp_path` for I/O.
- **Integration**: `build()` with `patch.object(app, "call", side_effect=...)` to
  assert wiring (snapshot written, debt appended on exhaustion, fix execute
  receives `checkpoint_label` + history, loop short-circuits over budget).
- **Mocking**: per existing patterns — substring-routed `mock_call`, patched
  `_unwrap` and `app.note`.
- **New test files**:
  - `tests/test_checkpoint_guard.py` (B1, B3 path logic)
  - `tests/test_verify_fix_recovery.py` (B2, B4, B5, B6 helpers + build() wiring)
  - extend `tests/test_dag_executor_multi_repo.py` or new
    `tests/test_checkpoint_namespacing.py` (B3 run_dag/execute plumbing)
  - extend coverage for `generate_fix_issues` history (B7) in a new
    `tests/test_fix_generator_history.py`

---

## Behavior 1: `_save_checkpoint` don't-shrink guard

### Test Specification
**Given**: `<artifacts_dir>/execution/checkpoint.json` exists holding a DAGState
with `all_issues` of length N.
**When**: `_save_checkpoint(dag_state)` is called with a `dag_state` whose
`all_issues` length is M.
**Then**: if M < N the file is left unchanged; if M >= N (or no file exists, or
the existing file is unreadable/corrupt) the file is written with the new state.

**Edge Cases**: no existing file → write; existing file corrupt/unparseable →
fail-open (write); equal counts → write; empty `artifacts_dir` → no-op (existing
early return at `dag_executor.py:691`).

**Stale-checkpoint edge case — the guard MUST be `build_id`-aware (cross-build
fail-open).** The checkpoint path keys only on `artifacts_dir` (verified:
`_checkpoint_path`, `dag_executor.py:683-685` — `build_id` is *not* in the path).
This is normally unique per build because `build()` generates a fresh
`build_id = uuid.uuid4().hex[:8]` (`app.py:488`) and, for cloned repos, namespaces
`repo_path = /workspaces/{repo}-{build_id}` (`app.py:495,501`) → unique
`artifacts_dir`. **But when the caller passes an explicit local `repo_path`, it is
NOT rewritten** (`app.py:503`), so `artifacts_dir = {repo_path}/.artifacts` is
**reused across builds**. A naïve count-only guard would then refuse to write a
fresh, *smaller* build's checkpoint because a *larger* checkpoint from a previous
build still sits on disk — corrupting recovery (`resume_build` would resume the
old plan).

**Resolution (surgical):** the guard refuses to shrink **only when the on-disk
checkpoint's `build_id` equals the incoming `dag_state.build_id`** (same build).
When they differ — a different/previous build — it **fails open and overwrites**.
This is safe and complete because:
- `build_id` is unique per build (`app.py:488`); two builds never share it, so
  cross-build always fails open → **no regression on reused `artifacts_dir`**.
- The main DAG writes `checkpoint.json` with a non-empty `build_id`; the fix DAG
  passes no `build_id` (`app.py:1024`) so its state has `build_id=""` and (post-B3)
  writes `checkpoint-fix-N.json` instead — so the main checkpoint is only ever
  written by same-build, same-count main saves (never shrinks). The guard is a
  correct defense-in-depth net that triggers only on a genuine same-build shrink.

`build_id` is a `DAGState` field (`schemas.py:316`) serialized into the checkpoint,
so `_existing_checkpoint_meta` can read it back.

**Edge Cases (updated)**: no existing file → write; corrupt/unparseable →
fail-open (write); equal counts → write; empty `artifacts_dir` → no-op;
**different `build_id` on disk → fail-open (write), even if smaller**; same
`build_id` and smaller → skip.

**Property**: for all (existing_count ≥ 0, new_count ≥ 0),
`write_occurs == (new_count >= existing_count) OR existing_unreadable OR no_file OR (existing_build_id != new_build_id)`.

**Files touched**: `swe_af/execution/dag_executor.py` (guard inside
`_save_checkpoint`), `tests/test_checkpoint_guard.py`.

### TDD Cycle

#### 🔴 Red
**File**: `tests/test_checkpoint_guard.py`
```python
import json, os
from pathlib import Path
from swe_af.execution.dag_executor import _save_checkpoint, _checkpoint_path
from swe_af.execution.schemas import DAGState

def _seed_checkpoint(artifacts_dir: str, n_issues: int, build_id: str = "") -> str:
    state = DAGState(artifacts_dir=artifacts_dir, build_id=build_id,
                     all_issues=[{"name": f"i{i}"} for i in range(n_issues)])
    path = _checkpoint_path(state)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Path(path).write_text(json.dumps(state.model_dump(), default=str))
    return path

def test_save_checkpoint_refuses_to_shrink_same_build(tmp_path):
    artifacts = str(tmp_path / ".artifacts")
    path = _seed_checkpoint(artifacts, 9, build_id="b1")
    smaller = DAGState(artifacts_dir=artifacts, build_id="b1",
                       all_issues=[{"name": "fix-1"}])
    _save_checkpoint(smaller)
    on_disk = json.loads(Path(path).read_text())
    assert len(on_disk["all_issues"]) == 9   # not stomped within the same build

def test_save_checkpoint_fail_open_cross_build(tmp_path):
    """Reused artifacts_dir: a different build_id on disk → overwrite even if smaller."""
    artifacts = str(tmp_path / ".artifacts")
    path = _seed_checkpoint(artifacts, 7, build_id="old-build")
    fresh = DAGState(artifacts_dir=artifacts, build_id="new-build",
                     all_issues=[{"name": "i0"}])
    _save_checkpoint(fresh)
    on_disk = json.loads(Path(path).read_text())
    assert len(on_disk["all_issues"]) == 1        # fresh build wins
    assert on_disk["build_id"] == "new-build"

def test_save_checkpoint_allows_equal_or_larger(tmp_path):
    artifacts = str(tmp_path / ".artifacts")
    path = _seed_checkpoint(artifacts, 2)
    bigger = DAGState(artifacts_dir=artifacts,
                      all_issues=[{"name": f"i{i}"} for i in range(5)])
    _save_checkpoint(bigger)
    assert len(json.loads(Path(path).read_text())["all_issues"]) == 5

def test_save_checkpoint_writes_when_absent(tmp_path):
    artifacts = str(tmp_path / ".artifacts")
    state = DAGState(artifacts_dir=artifacts, all_issues=[{"name": "i0"}])
    _save_checkpoint(state)
    assert os.path.exists(_checkpoint_path(state))

def test_save_checkpoint_fail_open_on_corrupt_existing(tmp_path):
    artifacts = str(tmp_path / ".artifacts")
    path = _checkpoint_path(DAGState(artifacts_dir=artifacts))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Path(path).write_text("{ not json")
    state = DAGState(artifacts_dir=artifacts, all_issues=[{"name": "i0"}])
    _save_checkpoint(state)   # must not raise
    assert json.loads(Path(path).read_text())["all_issues"] == [{"name": "i0"}]
```
Note: `test_save_checkpoint_fail_open_on_corrupt_existing` seeds via raw
`Path(path).write_text("{ not json")` (no `build_id`), exercising the
unreadable→fail-open branch independent of the `build_id` check.

#### 🟢 Green
**File**: `swe_af/execution/dag_executor.py` (inside `_save_checkpoint`, after the
empty-path early return at line 691, before `open(path, "w")` at 694)
```python
def _existing_checkpoint_meta(path: str) -> tuple[int, str] | None:
    """(issue_count, build_id) of an on-disk checkpoint, or None if absent/unreadable."""
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        return len(data.get("all_issues", [])), data.get("build_id", "")
    except (json.JSONDecodeError, OSError):
        return None  # fail-open: let the caller overwrite

# ...inside _save_checkpoint, after `if not path: return`:
    meta = _existing_checkpoint_meta(path)
    if meta is not None:
        existing_count, existing_build_id = meta
        # Refuse to shrink ONLY within the same build. A different build_id means a
        # stale checkpoint from a previous build sharing a reused artifacts_dir —
        # fail open and overwrite (no cross-build regression). See Edge Cases.
        if existing_build_id == dag_state.build_id and len(dag_state.all_issues) < existing_count:
            if note_fn:
                note_fn(
                    f"Checkpoint write skipped: current {len(dag_state.all_issues)} "
                    f"issues < existing {existing_count} for build {dag_state.build_id!r} "
                    f"(refusing to shrink)",
                    tags=["execution", "checkpoint", "guard"],
                )
            return
```

#### 🔵 Refactor
- [ ] No duplication — `_existing_checkpoint_meta` is the single reader.
- [ ] Reveals intent — name states the guard's purpose; comment explains the
      cross-build fail-open.
- [ ] Complexity — one extra branch (build_id-gated), fail-open keeps it linear.
- [ ] No shallow wrappers — helper has real logic (read + parse + count + build_id).
- [ ] Fits patterns — mirrors `_load_checkpoint` JSON handling (`dag_executor.py:700-706`).

### Success Criteria
**Automated:**
- [ ] Red first: `pytest tests/test_checkpoint_guard.py -x` fails (no guard).
- [ ] Green: `pytest tests/test_checkpoint_guard.py -x` passes (incl. same-build
      shrink-refuse AND cross-build fail-open).
- [ ] Full suite: `make test`.
- [ ] No new duplication: `grep -n "all_issues" swe_af/execution/dag_executor.py` — single read path via `_existing_checkpoint_meta`.

**Manual:**
- [ ] A 1-issue fix-DAG cannot overwrite a 9-issue checkpoint of the **same** build.
- [ ] A fresh smaller build at a reused local `repo_path`/.artifacts **does**
      overwrite a larger prior build's checkpoint (no recovery corruption).

---

## Behavior 2: main-DAG snapshot before the verify loop

### Test Specification
**Given**: `build()` has the main `dag_result` after `execute` (`app.py:942`),
before the verify loop (`app.py:951`).
**When**: the snapshot helper runs.
**Then**: `<artifacts_dir>/execution/main-dag-result.json` exists and contains the
main DAG's issue set.

**Edge Cases**: empty/missing `artifacts_dir` → no-op (no raise); helper never
overwrites checkpoint.json (different filename).

**Files touched**: `swe_af/app.py` (helper + one call site after line 942),
`tests/test_verify_fix_recovery.py`.

### TDD Cycle

#### 🔴 Red
**File**: `tests/test_verify_fix_recovery.py`
```python
import json, os
from pathlib import Path
from swe_af.app import _dump_main_dag_result

def test_dump_main_dag_result_writes_snapshot(tmp_path):
    artifacts = str(tmp_path / ".artifacts")
    dag_result = {"all_issues": [{"name": f"i{i}"} for i in range(9)],
                  "completed_issues": []}
    _dump_main_dag_result(artifacts, dag_result)
    snap = Path(artifacts) / "execution" / "main-dag-result.json"
    assert snap.exists()
    assert len(json.loads(snap.read_text())["all_issues"]) == 9

def test_dump_main_dag_result_noop_without_artifacts(tmp_path):
    _dump_main_dag_result("", {"all_issues": []})  # must not raise
```

#### 🟢 Green
**File**: `swe_af/app.py` (module-level helper near `build()`)
```python
def _dump_main_dag_result(artifacts_dir: str, dag_result: dict) -> None:
    """Forensic snapshot of the main DAG result before the verify/fix loop can
    overwrite the in-memory dag_result (see app.py:944-946)."""
    if not artifacts_dir:
        return
    import json
    path = os.path.join(artifacts_dir, "execution", "main-dag-result.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(dag_result, f, indent=2, default=str)
```
Call site — `app.py` immediately after line 942 (the main `execute`):
```python
        _dump_main_dag_result(plan_result.get("artifacts_dir", artifacts_dir), dag_result)
```

#### 🔵 Refactor
- [ ] No duplication — single writer.
- [ ] Reveals intent — docstring ties to the overwrite comment at `app.py:944-946`.
- [ ] Complexity — one guard branch.
- [ ] Fits patterns — mirrors `_save_checkpoint` JSON dump style.

### Success Criteria
**Automated:**
- [ ] Red → Green on `pytest tests/test_verify_fix_recovery.py -k dump -x`.
- [ ] `make test`.

**Manual:**
- [ ] After a build, `main-dag-result.json` holds the 9-issue record even if the
      fix loop ran.

---

## Behavior 3: namespaced fix checkpoints (`checkpoint_label`)

### Test Specification
**Given**: a `checkpoint_label`.
**When**: it is threaded `execute → run_dag → _save_checkpoint → _checkpoint_path`.
**Then**: empty label → `checkpoint.json` (unchanged today's behavior);
non-empty label `fix-1` → `checkpoint-fix-1.json`, and `checkpoint.json` is not
touched by that run.

**Edge Cases**: default `""` everywhere preserves existing behavior; the 7
internal save sites all use the run-level label; the `resume=True` load path is
**not** relabeled (only main DAGs resume).

**Property**: `_checkpoint_path(state, label)` ==
`<artifacts_dir>/execution/checkpoint.json` when `label==""` else
`.../checkpoint-{label}.json`.

**Files touched**: `swe_af/execution/dag_executor.py` (`_checkpoint_path`,
`_save_checkpoint`, `run_dag` signature + its 7 `_save_checkpoint` calls),
`swe_af/app.py` (`execute` signature + the `run_dag` call at 1586 + the fix
`execute` call at 1024), `tests/test_checkpoint_namespacing.py`.

### TDD Cycle

#### 🔴 Red
**File**: `tests/test_checkpoint_namespacing.py`
```python
import os
from swe_af.execution.dag_executor import _checkpoint_path, _save_checkpoint
from swe_af.execution.schemas import DAGState

def test_checkpoint_path_default_label(tmp_path):
    s = DAGState(artifacts_dir=str(tmp_path))
    assert _checkpoint_path(s).endswith("execution/checkpoint.json")

def test_checkpoint_path_fix_label(tmp_path):
    s = DAGState(artifacts_dir=str(tmp_path))
    assert _checkpoint_path(s, label="fix-1").endswith("execution/checkpoint-fix-1.json")

def test_save_with_label_leaves_main_untouched(tmp_path):
    artifacts = str(tmp_path / ".artifacts")
    main = DAGState(artifacts_dir=artifacts,
                    all_issues=[{"name": f"i{i}"} for i in range(9)])
    _save_checkpoint(main)                       # writes checkpoint.json
    fix = DAGState(artifacts_dir=artifacts, all_issues=[{"name": "fix-1"}])
    _save_checkpoint(fix, label="fix-1")         # writes checkpoint-fix-1.json
    assert os.path.exists(_checkpoint_path(main))
    assert os.path.exists(_checkpoint_path(fix, label="fix-1"))
    import json
    main_disk = json.loads(open(_checkpoint_path(main)).read())
    assert len(main_disk["all_issues"]) == 9     # not stomped by fix
```
Plus an async wiring test (pattern: `tests/fast/test_app.py:260`) asserting the
fix `execute` invocation reaches `run_dag` with `checkpoint_label="fix-1"`.

#### 🟢 Green
**File**: `swe_af/execution/dag_executor.py`
```python
def _checkpoint_path(dag_state: DAGState, label: str = "") -> str:
    if not dag_state.artifacts_dir:
        return ""
    name = "checkpoint.json" if not label else f"checkpoint-{label}.json"
    return os.path.join(dag_state.artifacts_dir, "execution", name)

def _save_checkpoint(dag_state: DAGState, note_fn=None, label: str = "") -> None:
    path = _checkpoint_path(dag_state, label)
    ...  # B1 guard + write, unchanged otherwise
```
`run_dag(..., checkpoint_label: str = "", ...)` — bind once near the top and pass
to each of the 7 sites: `_save_checkpoint(dag_state, note_fn, label=checkpoint_label)`
(`dag_executor.py:1436,1505,1517,1557,1676,1734,1799`). The `resume` load at
`1413-1416` stays on the default (unlabeled) path.

**File**: `swe_af/app.py`
- `execute(..., checkpoint_label: str = "", ...)` (after `resume`), forwarded:
  `run_dag(..., checkpoint_label=checkpoint_label, ...)` at `app.py:1586`.
- Fix `execute` call at `app.py:1024`:
  `await app.call(f"{NODE_ID}.execute", ..., checkpoint_label=f"fix-{cycle + 1}")`.

#### 🔵 Refactor
- [ ] No duplication — filename logic lives only in `_checkpoint_path`.
- [ ] Reveals intent — `label` names the namespace.
- [ ] Complexity — one ternary; 7 call sites pass one local.
- [ ] No shallow wrappers — no new layer; existing functions gain one param.
- [ ] Fits patterns — default-param plumbing matches `build_id`/`resume`.

### Downstream note (verified)
Nothing reads `checkpoint-fix-*.json`. `resume_build` (`app.py:2014`) and
`_load_checkpoint` (`dag_executor.py:702`) both target `checkpoint.json`; the main
DAG keeps writing it (default label). Side effect (desired): `resume_build` now
resumes the real main DAG instead of the fix DAG.

**Resume recovers `execute`, not verify.** `resume_build` (`app.py:1998-2044`)
re-enters the `execute` node only — it does **not** re-run the verify/fix loop.
After this change a resumed build replays the *main* DAG (which is normally
already complete by the time the verify loop runs, so resume is a near-no-op that
restores the correct DAG state) and then returns; it will not re-verify or
re-attempt fixes. That is consistent with "Not making fix-DAGs resumable" — call
it out so nobody expects resume to re-verify.

### Success Criteria
**Automated:**
- [ ] Red → Green: `pytest tests/test_checkpoint_namespacing.py -x`.
- [ ] Regression: `pytest tests/test_dag_executor_multi_repo.py -x` (default-label
      paths unchanged).
- [ ] `make test`.

**Manual:**
- [ ] After a fix cycle, both `checkpoint.json` (main) and `checkpoint-fix-1.json`
      exist; main is intact.

---

## Behavior 4: convergence detection

### Test Specification
**Given**: the failing-criteria set of the previous cycle.
**When**: the current cycle produces an identical set (order-independent).
**Then**: the loop stops before launching another fix DAG.

**Edge Cases**: empty set; different ordering same content → converged; one
criterion changes → not converged; first cycle (no prior) → not converged.

**Property**: `_failed_criteria_signature(x) == _failed_criteria_signature(shuffle(x))`.

> **Active under the new default.** Convergence compares the current cycle's
> failing set to the *prior* cycle's, so it needs ≥2 fix cycles. The shipped
> default `max_verify_fix_cycles=2` provides exactly that, so B4 fires out of the
> box (it was dormant only under the old default of 1). Pin
> `max_verify_fix_cycles` explicitly in the convergence integration test so the
> assertion does not depend on the default.

**Files touched**: `swe_af/app.py` (helper + loop wiring),
`tests/test_verify_fix_recovery.py`.

### TDD Cycle

#### 🔴 Red
```python
from swe_af.app import _failed_criteria_signature

def test_signature_is_order_independent():
    a = [{"criterion": "X"}, {"criterion": "Y"}]
    b = [{"criterion": "Y"}, {"criterion": "X"}]
    assert _failed_criteria_signature(a) == _failed_criteria_signature(b)

def test_signature_differs_on_content():
    a = [{"criterion": "X"}]
    b = [{"criterion": "Z"}]
    assert _failed_criteria_signature(a) != _failed_criteria_signature(b)

def test_signature_empty():
    assert _failed_criteria_signature([]) == frozenset()
```

#### 🟢 Green
**File**: `swe_af/app.py`
```python
def _failed_criteria_signature(failed_criteria: list[dict]) -> frozenset:
    """Order-independent identity of a failed-criteria set for convergence."""
    return frozenset(c.get("criterion", "") for c in failed_criteria)
```
Loop wiring (`app.py`, around 972-985): after computing `failed_criteria`,
compute `sig = _failed_criteria_signature(failed_criteria)`; if
`sig == prior_failed_signature` → record debt (B5) and `break`; else set
`prior_failed_signature = sig` and continue. Initialize
`prior_failed_signature = None` before the loop.

#### 🔵 Refactor
- [ ] No duplication; [ ] intent clear; [ ] one comparison branch;
      [ ] fits pydantic-dict access style used at `app.py:972-975`.

### Success Criteria
**Automated:** [ ] Red → Green `pytest tests/test_verify_fix_recovery.py -k signature -x`; [ ] `make test`.
**Manual:** [ ] Loop stops when the same criteria fail twice.

---

## Behavior 5: accept-partial debt on termination

### Test Specification
**Given**: criteria still failing when the loop terminates (cycle cap reached,
converged, soft-deadline hit, or no fix issues generated).
**When**: the terminal path runs.
**Then**: each still-failing criterion is appended to
`dag_result["accumulated_debt"]` as `{"type": "unmet_acceptance_criterion",
"criterion": ..., "reason": ..., "severity": "high"}`.

**Edge Cases**: empty failing set → no debt; existing debt preserved (append, not
replace); dedupe against criteria already recorded by the fix-generator
(`app.py:1003-1010`).

**Contract (pin these):**
- `reason` is sourced from `criterion["evidence"]` (verifier `criteria_results`
  dicts carry `evidence` — confirmed by the reader at `fix_generator.py:74`).
- **Dedupe key is `criterion`** (the string), matched against entries already in
  `accumulated_debt` (whose `criterion` field the fix-generator path also sets at
  `app.py:1007`). Same shape both sources → safe string comparison.

**Files touched**: `swe_af/app.py` (helper + terminal wiring),
`tests/test_verify_fix_recovery.py`.

### TDD Cycle

#### 🔴 Red
```python
from swe_af.app import _criteria_to_debt

def test_criteria_to_debt_shape():
    out = _criteria_to_debt([{"criterion": "X", "evidence": "e"}])
    assert out == [{"type": "unmet_acceptance_criterion", "criterion": "X",
                    "reason": "e", "severity": "high"}]

def test_criteria_to_debt_empty():
    assert _criteria_to_debt([]) == []
```
Plus a `build()` integration test (substring-routed `mock_call`): verifier always
returns `passed=False` with one failing criterion; assert the returned
`BuildResult`'s `dag_state["accumulated_debt"]` contains an
`unmet_acceptance_criterion` after cycles exhaust. **This test must exercise the
cycle-cap break at `app.py:968`** (verifier never passes, `generate_fix_issues`
returns fixable issues so the loop runs to `cycle >= max_verify_fix_cycles`), not
only the no-fix break at `app.py:1033`. Add a *second* integration assertion for
the `:1033` path (generate_fix_issues returns no `fix_issues`) so both terminal
break sites record debt. With the new default `max_verify_fix_cycles=2` the
cap break at `:968` fires on cycle 2; pin the config explicitly in the test so the
assertion is independent of the default.

#### 🟢 Green
**File**: `swe_af/app.py`
```python
def _criteria_to_debt(failed_criteria: list[dict]) -> list[dict]:
    return [
        {"type": "unmet_acceptance_criterion",
         "criterion": c.get("criterion", ""),
         "reason": c.get("evidence", ""),
         "severity": "high"}
        for c in failed_criteria
    ]
```
Terminal wiring: at the cycle-cap break (`app.py:968`) and the converged break
(B4) and the no-fix break (`app.py:1033`), append
`_criteria_to_debt(failed_criteria)` items to `dag_result.setdefault("accumulated_debt", [])`,
skipping criteria already present (compare on `criterion`). Note the cycle-cap
break at `app.py:968` currently happens *before* `failed_criteria` is computed —
compute the still-failing set there (reuse the `app.py:972-975` comprehension)
prior to recording debt.

#### 🔵 Refactor
- [ ] No duplication — extract the `app.py:972-975` failing-set comprehension into
      a `_failing_criteria(verification)` helper reused at both the guard and the
      terminal path (removes the copy the Green step would otherwise create).
- [ ] Intent clear; [ ] dedupe keeps complexity bounded; [ ] matches existing
      debt dict shape at `app.py:1005-1010`.

### Success Criteria
**Automated:** [ ] Red → Green helper test; [ ] build() integration asserts debt;
[ ] no duplication: the `not c.get("passed", True)` comprehension appears once.
[ ] `make test`.
**Manual:** [ ] A build that can't satisfy a criterion ends with that criterion in debt.

---

## Behavior 6: soft time budget

### Test Specification
**Given**: `BuildConfig.verify_fix_soft_deadline_seconds` (default **3600**; `0` =
disabled).
**When**: the loop is about to launch a fix DAG and elapsed ≥ budget.
**Then**: it stops (accept-partial via B5) instead of launching.

**Two default changes ship with this behavior:**
- `max_verify_fix_cycles`: **1 → 2** (`schemas.py:697`).
- `verify_fix_soft_deadline_seconds`: new field, default **3600** (`0` disables).

**Edge Cases**: budget `0` → never short-circuits; elapsed < budget → proceed;
elapsed exactly == budget → stop.

> **Between-cycles gate — does NOT interrupt an in-flight fix DAG.** The guard is
> evaluated *before* launching a fix DAG at `app.py:1024`. The first fix cycle
> launches at `elapsed ≈ 0`, so it is never gated; B6 can only block a *subsequent*
> launch. With the shipped default `max_verify_fix_cycles = 2` there is a second
> launch for it to gate, so **B6 is active out of the box**. It bounds *cumulative*
> cycle count, not the wall-clock of any single DAG (that is
> `agent_timeout_seconds`, out of scope). Worst-case total fix time ≈
> `deadline + one_full_cycle` ≈ `3600 + 2700` = 6300s < the external 7200s cap.

**Property**: `_within_soft_deadline(elapsed, 0) is True` for all elapsed
(disabled); for budget > 0, `_within_soft_deadline(e, b) == (e < b)`.

**Files touched**: `swe_af/execution/schemas.py` (raise `max_verify_fix_cycles`
default at `:697`; add `verify_fix_soft_deadline_seconds`),
`swe_af/app.py` (`import time`, helper, loop timing + guard),
`tests/test_verify_fix_recovery.py`.

### TDD Cycle

#### 🔴 Red
```python
from swe_af.app import _within_soft_deadline
from swe_af.execution.schemas import BuildConfig

def test_config_defaults():
    cfg = BuildConfig(repo_url="https://x/y")
    assert cfg.max_verify_fix_cycles == 2               # raised from 1
    assert cfg.verify_fix_soft_deadline_seconds == 3600  # budget on by default

def test_soft_deadline_zero_disables():
    assert _within_soft_deadline(10_000, 0) is True      # 0 still disables

def test_soft_deadline_blocks_when_exceeded():
    assert _within_soft_deadline(100, 60) is False
    assert _within_soft_deadline(30, 60) is True
```

#### 🟢 Green
**File**: `swe_af/execution/schemas.py`
```python
    max_verify_fix_cycles: int = 2  # was 1 — allows a 2nd fix attempt so B4/B6/B7 engage
    # ...after max_verify_fix_cycles (line 697):
    verify_fix_soft_deadline_seconds: int = 3600  # between-cycles budget; 0 = disabled
```
**File**: `swe_af/app.py`
```python
import time  # near line 14, alphabetical

def _within_soft_deadline(elapsed: float, budget_seconds: int) -> bool:
    """True if a fix cycle may still start. budget 0 disables the check."""
    return budget_seconds <= 0 or elapsed < budget_seconds
```
Loop wiring: `verify_loop_start = time.monotonic()` before the loop; before the
fix `execute` at `app.py:1024`, guard:
```python
if not _within_soft_deadline(time.monotonic() - verify_loop_start,
                             cfg.verify_fix_soft_deadline_seconds):
    app.note("Verify/fix soft deadline reached — accepting with debt",
             tags=["build", "verify", "deadline"])
    # append _criteria_to_debt(failed_criteria) (B5), then break
    break
```
Confirm `to_execution_config_dict()` does **not** forward the new key to
`ExecutionConfig` (`extra="forbid"`); it lives on `BuildConfig` only.

#### 🔵 Refactor
- [ ] No duplication — single deadline predicate; [ ] intent clear; [ ] disabled
      path is a single short-circuit; [ ] field documented like neighbors
      (`ci_wait_seconds` at `schemas.py`).

### Success Criteria
**Automated:** [ ] Red → Green helper + config-default test (`==2`, `==3600`);
[ ] **regression sweep for the default bump** (verified low-risk): a grep of
`tests/` shows `max_verify_fix_cycles` appears only in *forbidden-identifier*
source guards (e.g. `test_verifier.py:79-83` — "fix-cycle logic must NOT appear in
verifier source"), which a default-value change does not affect. No current test
asserts the default is `1` or counts exactly one fix `execute`. Still: any
build()-level integration test that drives the verify loop should pin
`max_verify_fix_cycles` explicitly in its own `BuildConfig` rather than relying on
the default, so intent survives future default changes;
[ ] with the default 3600 budget + monkeypatched `time.monotonic`, the loop
short-circuits before the *second* fix DAG; [ ] `make test`.
**Manual:** [ ] With the default budget, a long first fix cycle prevents a second
from launching (debt recorded). [ ] `verify_fix_soft_deadline_seconds=0` restores
uncapped behavior.

---

## Behavior 7: cross-cycle history to the fix-generator

### Test Specification
**Given**: prior cycles' failed criteria.
**When**: `generate_fix_issues` builds its prompt on cycle ≥ 2.
**Then**: the prompt includes a "previously failed" section so repeatedly-failed
criteria can be recorded as debt (the prompt already instructs this at
`fix_generator.py:25`).

**Edge Cases**: cycle 1 → no history → prompt unchanged; empty history → no
section; default param absent → backward compatible.

**Files touched**: `swe_af/reasoners/execution_agents.py` (`generate_fix_issues`
signature + pass-through), `swe_af/prompts/fix_generator.py`
(`fix_generator_task_prompt` new optional arg + section), `swe_af/app.py` (pass
`previously_failed_criteria` at the `generate_fix_issues` call, `app.py:988`),
`tests/test_fix_generator_history.py`.

### TDD Cycle

#### 🔴 Red
**File**: `tests/test_fix_generator_history.py`
```python
from swe_af.prompts.fix_generator import fix_generator_task_prompt

def test_prompt_includes_history_section():
    prompt = fix_generator_task_prompt(
        failed_criteria=[{"criterion": "X"}],
        dag_state_summary={},
        prd={},
        previously_failed_criteria=[{"criterion": "X"}],
    )
    assert "Previously Failed" in prompt
    assert "X" in prompt

def test_prompt_omits_history_when_empty():
    prompt = fix_generator_task_prompt(
        failed_criteria=[{"criterion": "X"}], dag_state_summary={}, prd={})
    assert "Previously Failed" not in prompt
```

#### 🟢 Green
**File**: `swe_af/prompts/fix_generator.py` — add
`previously_failed_criteria: list[dict] | None = None` to
`fix_generator_task_prompt` (`:55`); when non-empty, append a
`## Previously Failed Criteria (record as debt if unfixable)` section listing
each `criterion`.
**File**: `swe_af/reasoners/execution_agents.py` — add
`previously_failed_criteria: list[dict] | None = None` to `generate_fix_issues`
(`:1298`) and forward it into `fix_generator_task_prompt` (`:1318`).
**File**: `swe_af/app.py` — track `prior_failed_criteria` (accumulated across
cycles) and pass it at the `generate_fix_issues` call (`app.py:988-998`).
**Dedupe by `criterion`** before passing/rendering so the "Previously Failed"
section does not grow with repeats across cycles (e.g. keep a
`seen_criteria: set[str]` or `{c["criterion"]: c for c in prior}.values()`).

> **Active under the new default.** History is non-empty only on cycle ≥ 2, which
> requires `max_verify_fix_cycles > 1`. The shipped default of `2` reaches a second
> fix cycle, so B7's "Previously Failed" section renders out of the box. (It was
> inert only under the old default of 1.) The no-history path remains exactly
> today's behavior on cycle 1.

#### 🔵 Refactor
- [ ] No duplication — reuse the existing section-builder style in
      `fix_generator_task_prompt` (`:67-100`); [ ] intent clear; [ ] optional arg
      keeps the no-history path identical; [ ] matches the prompt's existing
      "Existing Technical Debt" section pattern (`fix_generator.py:89-95`).

### Success Criteria
**Automated:** [ ] Red → Green `pytest tests/test_fix_generator_history.py -x`;
[ ] existing fix-generator/verifier tests still pass; [ ] `make test`.
**Manual:** [ ] On a repeated failure, the fix-generator records it as debt.

---

## Integration & E2E Testing

- **Integration** (`build()` with substring-routed `mock_call`, pattern
  `tests/fast/test_app.py:260-281`). **Config note:** B4/B6/B7 are active under the
  new default `max_verify_fix_cycles=2`. Still pin the cycle count explicitly in
  each test (don't rely on the default) so assertions survive future default
  changes.
  - **[cycles=2]** verifier returns `passed=False` with a stable failing criterion
    across cycles → assert convergence break (no second fix `execute`), debt
    appended, `success=False`.
  - **[cycles=2]** assert the fix `execute` target is invoked with
    `checkpoint_label="fix-1"` and `previously_failed_criteria` on cycle 2.
  - **[cycles=2]** small `verify_fix_soft_deadline_seconds` (monkeypatch
    `time.monotonic` so `elapsed ≥ budget` before the *second* launch) → loop
    short-circuits before the second fix `execute` and records debt. (The first
    fix `execute` is never gated — assert it still ran.)
  - **[default config]** verify the shipped defaults: `BuildConfig` has
    `max_verify_fix_cycles == 2` and `verify_fix_soft_deadline_seconds == 3600`.
  - **[any cycles]** `main-dag-result.json` exists after the run; after a fix
    cycle, `checkpoint.json` still holds the main DAG's issue count (not stomped)
    and `checkpoint-fix-1.json` exists; the cycle-cap break (`app.py:968`) records
    the still-failing criterion as `unmet_acceptance_criterion` debt.
- **E2E**: full `make test`; spot-run an existing multi-repo DAG test to confirm
  default-label checkpoints and resume behavior are unchanged.

## Implementation Order

1. B1 (guard) — isolated, no plumbing.
2. B3 (namespacing) — builds on B1's `_save_checkpoint`.
3. B2 (snapshot) — one-line build() wiring.
4. B4 (convergence) + B5 (accept-partial) — share the `_failing_criteria` helper.
5. B6 (soft budget) — depends on B5's debt path.
6. B7 (history) — independent prompt/contract change.

## References

- Research: `thoughts/shared/research/2026-06-05-15-00-verify-fix-loop-checkpoint-stomp.md`
- Verify loop: `swe_af/app.py:952-1035`; fix execute call `swe_af/app.py:1024`
- `execute`: `swe_af/app.py:1543-1599`; `run_dag`: `swe_af/execution/dag_executor.py:1352`
- Checkpoint: `swe_af/execution/dag_executor.py:683-706`, save sites
  `1436,1505,1517,1557,1676,1734,1799`
- `resume_build`: `swe_af/app.py:1999-2040`
- `BuildConfig`: `swe_af/execution/schemas.py:684-730`
- `generate_fix_issues`: `swe_af/reasoners/execution_agents.py:1297`;
  `fix_generator_task_prompt`: `swe_af/prompts/fix_generator.py:55`
- Test patterns: `tests/fast/test_app.py:260`, `tests/conftest.py:120`,
  `tests/test_coding_loop.py:28,638`, `tests/fast/test_verifier.py:162`
