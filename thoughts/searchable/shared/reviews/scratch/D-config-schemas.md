# D — Config & Schemas citation verification

Worktree: `/home/maceo/Dev/SWE-AF-baml`
Branch: `feat/baml-structured-output` @ `6517b17245a9948a3052caa997f5b070f37ddd80` (matches the stated 6517b17)
Method: Read + grep, no files modified.

---

## Claim 1 — schemas.py:421 `CoderResult.tests_passed` "# Self-reported" — ACCURATE

Line 421 exactly:
```python
    tests_passed: bool | None = None  # Self-reported: did tests pass?
```
Field name, annotation (`bool | None = None`), and the `# Self-reported` comment all present at line 421. Verbatim.

## Claim 2 — schemas.py:414-426 CoderResult region — ACCURATE

`class CoderResult(BaseModel)` opens at **line 414** (`"""Output from the coder agent."""`). Fields (414–425):
- `files_changed: list[str] = []` (417)
- `summary: str = ""` (418)
- `complete: bool = True` (419)
- `iteration_id: str = ""` (420)
- `tests_passed: bool | None = None  # Self-reported` (421)
- `test_summary: str = ""` (422)
- `codebase_learnings: list[str] = []  # for shared memory` (423)
- `agent_retro: dict = {}  # for shared memory` (424)
- `repo_name: str = ""  # multi-repo` (425)

Class body ends at 425; line 426 is blank. Region cited correctly.

## Claim 3 — schemas.py:703 BuildConfig + "add fields after line 703" — DRIFTED

`class BuildConfig(BaseModel)` is actually at **line 684**, NOT 703. So "class BuildConfig at/near 703" is WRONG — it is ~19 lines above.
Line 703 itself:
```python
    agent_max_turns: int = DEFAULT_AGENT_MAX_TURNS
```
This IS inside BuildConfig (the model spans 684–~813), and 703 is a defaultable field. BuildConfig IS a Pydantic model (`BaseModel`, `model_config = ConfigDict(extra="forbid")`) with all-defaultable fields. So "add new defaultable fields after line 703" is mechanically fine — but the plan's claim that line 703 is where `class BuildConfig` sits is incorrect; 703 is just an interior field line. Verdict: DRIFTED (insertion point usable; class location citation wrong, corrected to 684).
NOTE: `extra="forbid"` — see Claim 6.

## Claim 4 — schemas.py:1002 ExecutionConfig — DRIFTED

`class ExecutionConfig(BaseModel)` is at **line 988**, NOT 1002. Line 1002:
```python
    max_coding_iterations: int = 5
```
That is an interior field of ExecutionConfig, not the class def. ExecutionConfig exists (988), is a separate Pydantic `BaseModel` with `model_config = ConfigDict(extra="forbid")`. Relationship to BuildConfig: it is a SEPARATE model (the DAG-executor config). BuildConfig is the end-to-end pipeline config; a SUBSET of its fields are copied into an ExecutionConfig at the execute boundary. Several ExecutionConfig fields are explicitly commented "Mirrored from BuildConfig" (1013–1018: check_ci, max_ci_fix_cycles, ci_wait_seconds, ci_poll_seconds). Verdict: DRIFTED (class at 988, not 1002; mirroring relationship confirmed).

## Claim 5 — schemas.py:822-848 to_execution_config_dict / 3-way duplication — ACCURATE (with sharpening)

`to_execution_config_dict` spans **822–848** exactly as cited. It returns an explicit dict literal listing each field one-by-one:
```python
    def to_execution_config_dict(self) -> dict:
        return {
            "runtime": self.runtime,
            "models": self.models,
            "permission_mode": self.permission_mode,
            "max_retries_per_issue": self.max_retries_per_issue,
            ... (explicit per-field) ...
            "ci_poll_seconds": self.ci_poll_seconds,
        }
```
**Is it really a 3-place duplication? YES.** To get a flag from build → executor you must touch THREE locations:
1. declare it as a field on `BuildConfig` (684+),
2. declare it as a field on `ExecutionConfig` (988+),
3. add an explicit `"key": self.key` line in `to_execution_config_dict` (822–848).
The method does NOT use `model_dump()` or any field iteration — it is a hand-written allow-list. So the plan's Behavior 6 "mirror in all three" is well grounded.

**BUT the silent-drop framing is WRONG / needs correction (see Claim 6).** Because `ExecutionConfig` has `model_config = ConfigDict(extra="forbid")`:
- If you add a key to `to_execution_config_dict` but forget the `ExecutionConfig` field → `ExecutionConfig(**d)` RAISES `ValidationError` (extra forbidden). Loud, not silent.
- If you add `ExecutionConfig` + `BuildConfig` fields but forget `to_execution_config_dict` → the flag SILENTLY drops to the ExecutionConfig default (this is the real silent-failure mode, and it's exactly why all three must be touched).
So: the duplication is real and 3-way; the failure is "loud if you over-add, silent default if you under-add (omit the dict line)". Plan should phrase it as "omitting the to_execution_config_dict line silently falls back to the default" rather than a generic silent drop.

## Claim 6 — end-to-end propagation into run_coding_loop.config — CONFIRMED, no gap (one caveat)

Chain (all verified):
1. `BuildConfig.to_execution_config_dict()` → plain dict. Called at `swe_af/app.py:931` (`exec_config = cfg.to_execution_config_dict()`), passed as `config=exec_config` into `app.call("<NODE>.execute", ...)`.
2. The `execute` reasoner (`swe_af/app.py:1571-1572`):
   ```python
   effective_config = dict(config) if config else {}
   exec_config = ExecutionConfig(**effective_config) if effective_config else ExecutionConfig()
   ```
   → builds a real `ExecutionConfig`. (extra="forbid" applies here.)
3. `run_dag(...)` → inside `dag_executor.py`, `run_coding_loop` is called at **806–815** with `config=config`, where `config` is that `ExecutionConfig`.
4. `run_coding_loop(config: ExecutionConfig)` (`coding_loop.py:516-524`) reads `config.<field>` directly (e.g. `config.max_coding_iterations`, `config.agent_timeout_seconds`, `config.permission_mode` at 545-547).

So `config.enable_deterministic_checks` WOULD be readable inside run_coding_loop **iff** the field is added to ExecutionConfig (step 2 builds an ExecutionConfig; run_coding_loop's `config` param IS an ExecutionConfig — confirmed by signature at coding_loop.py:521). run_coding_loop does NOT receive a BuildConfig; it receives ExecutionConfig built via the dict from to_execution_config_dict. No gap — provided all three places are edited.
CAVEAT / the load-bearing risk: because of `extra="forbid"` on ExecutionConfig, the order of the three edits matters in tests. If a test or the build constructs `ExecutionConfig(**to_execution_config_dict())` after you add the dict key but before the ExecutionConfig field, it raises. The plan must add the ExecutionConfig field in the same change.

## Claim 7 — dag_executor.py:741-742 model_dump() PlannedIssue → dict — ACCURATE

Lines 741-742:
```python
    all_issues = [
        i if isinstance(i, dict) else i.model_dump() if hasattr(i, "model_dump") else dict(i)
        for i in issues
    ]
```
Confirms: each issue, if a Pydantic model, is converted via `.model_dump()`. Pydantic `model_dump()` recurses — nested models (incl. a `verification` field that is a list of sub-models) become nested plain dicts / `list[dict]`. So `verification` survives as `list[dict]` after this conversion. Citation accurate (line numbers exact).

## Claim 8 — fields don't already exist — CONFIRMED

`grep -rn 'enable_deterministic_checks\|max_deterministic_check_retries' . --include='*.py'` → exit 1, ZERO matches anywhere in the repo. Neither field exists yet. Safe to add.

---

## Bottom line
- Claims 1, 2, 5, 7, 8: ACCURATE.
- Claims 3, 4: DRIFTED — the cited line numbers point at interior fields, not the class definitions. `class BuildConfig` = line **684** (not 703); `class ExecutionConfig` = line **988** (not 1002). Insertion logic still works.
- Claim 5: real 3-place duplication (hand-written allow-list, no model_dump). Plan's "mirror in all three" is correct; reframe "silent drop" → "omitting the to_execution_config_dict line silently defaults".
- Claim 6: flag DOES propagate BuildConfig → dict → ExecutionConfig → run_coding_loop.config, no architectural gap. The only hazard is `ExecutionConfig` `extra="forbid"`: all three edits must land together or `ExecutionConfig(**d)` raises.
