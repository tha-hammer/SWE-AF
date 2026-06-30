# Citation Verification — ci_gate.py runner reuse (Behavior 4)

**Worktree:** `/home/maceo/Dev/SWE-AF-baml`
**Branch/commit:** `feat/baml-structured-output` @ `6517b17` (verified `git rev-parse HEAD` = `6517b17245a9948a3052caa997f5b070f37ddd80`)
**Mode:** read-only verification. No files modified.

---

## Claim 1 — `CommandRunner` type alias @ ci_gate.py:38

**Verdict: DRIFTED (line + signature inaccurate as quoted) + CONTRACT MISMATCH.**

Plan quote: `CommandRunner = Callable[[Sequence[str], str], CompletedProcess]` at line 38.

Actual line 38:
```python
CommandRunner = Callable[[Sequence[str], str], "subprocess.CompletedProcess[str]"]
```

Line number is correct (38). The plan's quote is *approximately* right but drops the parameterization: actual is `subprocess.CompletedProcess[str]` (string-forward-ref, `[str]`-parameterized), not bare `CompletedProcess`.

### CRITICAL CONTRACT ISSUE — argv `Sequence[str]` vs shell string

The `CommandRunner` signature is `Callable[[Sequence[str], str], CompletedProcess[str]]`:
- **arg 1 = `Sequence[str]`** — an **argv list** (e.g. `["gh", "pr", "checks", "42", ...]`), NOT a shell command string.
- **arg 2 = `str`** — the **cwd** (working directory), NOT a command.

Every existing call site passes an argv list as arg1 and a path as arg2:
- `_fetch_failed_logs`: `runner(["gh", "run", "view", run_id, "--log-failed"], repo_path)` (line 106)
- `watch_pr_checks`: `cmd_runner(["gh", "pr", "checks", str(pr_number), "--json", fields], repo_path)` (lines 187-193)
- `mark_pr_ready`: `cmd_runner(["gh", "pr", "ready", str(pr_number)], repo_path)` (line 335)

The default implementation `_default_runner` does `subprocess.run(list(cmd), ...)` with **no `shell=` arg** (defaults to `shell=False`), so `cmd` is interpreted as argv.

**Behavior 4 wants to run shell PIPELINES via `shell=True` with a `command` STRING.** `subprocess.run` with `shell=True` requires `args` to be a **string** (the shell command line), not an argv list. This is a **direct, irreconcilable type mismatch** with the existing `CommandRunner` contract:

1. The type says arg1 is `Sequence[str]` (argv). A shell-string runner needs arg1 to be `str`.
2. The semantics of arg2 differ too: existing contract uses arg2 as **cwd**; if Behavior 4 reuses the slot it must keep cwd semantics, but it cannot also smuggle `shell=True` through a type whose default impl hardcodes `shell=False` (implicitly) and `list(cmd)`.
3. Reusing `_default_runner` is impossible for shell pipelines: it does `subprocess.run(list(cmd), ...)` — `list("my | pipeline")` would explode the string into a list of single characters.

**Reconciliation the plan MUST surface:** Behavior 4 cannot reuse `CommandRunner` as-is for shell-string pipeline execution. Options: (a) define a **distinct** runner type for the deterministic_check, e.g. `ShellRunner = Callable[[str, str], CompletedProcess[str]]` (command-string, cwd); (b) keep argv + drop `shell=True` and pass the pipeline as `["bash", "-c", pipeline]` (argv-compatible, satisfies the existing `Sequence[str]` contract WITHOUT shell=True at the type level — the shell is `bash -c`); or (c) generalize the alias to `Callable[[Sequence[str] | str, str], CompletedProcess[str]]` and branch in the default runner. The plan's stated approach (reuse `CommandRunner` + `shell=True` + `command` string) is a **type contract violation as written**.

---

## Claim 2 — `_default_runner` @ ci_gate.py:41-50

**Verdict: ACCURATE (line range exact).**

Actual lines 41-50:
```python
def _default_runner(
    cmd: Sequence[str], cwd: str
) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        list(cmd),
        cwd=cwd or None,
        capture_output=True,
        text=True,
        check=False,
    )
```

- **shell?** NO `shell=` argument → `subprocess.run` defaults to `shell=False`. Runs `list(cmd)` as **argv**.
- **cwd?** YES — passes `cwd=cwd or None` (empty string → `None`).
- **timeout handling?** NONE. There is **no `timeout=` argument** on this `subprocess.run`. The default runner can block indefinitely. (See Claim 7 — the only timeout in ci_gate is the wall-clock `wait_seconds` poll cap in `watch_pr_checks`, not a per-subprocess timeout, and there is **no `-1` exit_code sentinel** anywhere.)
- `capture_output=True`, `text=True`, `check=False`.

---

## Claim 3 — `_LOG_TAIL_CHARS = 3000` @ ci_gate.py:31

**Verdict: ACCURATE.**

Actual line 31: `_LOG_TAIL_CHARS: int = 3000`. Value (3000) and line (31) both confirmed. (Annotated `: int`.)

---

## Claim 4 — `_tail` @ ci_gate.py:92-95

**Verdict: ACCURATE (line range exact).**

Actual lines 92-95:
```python
def _tail(text: str, max_chars: int = _LOG_TAIL_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return "…[truncated]…\n" + text[-max_chars:]
```

**Exact signature:** `_tail(text: str, max_chars: int = _LOG_TAIL_CHARS) -> str`. Params: `text: str`, `max_chars: int` (defaults to module-level `_LOG_TAIL_CHARS`). Returns `str`.

**Feasibility of promoting `_tail` / `_LOG_TAIL_CHARS` to a shared `_proc.py`:**

`grep -rn '_tail'` across `swe_af/` and `tests/`:
- `swe_af/execution/ci_gate.py:92` (def), `:110` (call inside `_fetch_failed_logs`).
- `tests/test_ci_gate.py:20` (import), `:118`, `:120`, `:124`, `:125` (tests `test_tail_truncates_long_strings`, `test_tail_passes_short_strings_through`).

`grep -rn '_LOG_TAIL_CHARS'`:
- `swe_af/execution/ci_gate.py:31` (def), `:92` (default arg).

**Assessment: FEASIBLE.** `_tail`/`_LOG_TAIL_CHARS` are used only inside `ci_gate.py` (one production call) plus the ci_gate test file (which imports `_tail` from `swe_af.execution.ci_gate`). No *other* module imports `_tail`. Promoting to a shared `swe_af/execution/_proc.py` is mechanically safe **provided** `ci_gate.py` re-exports or imports it so the existing `from swe_af.execution.ci_gate import (... _tail ...)` in `tests/test_ci_gate.py:20` continues to resolve (otherwise that import breaks). Cleanest: `_proc.py` owns the canonical defs; `ci_gate.py` does `from swe_af.execution._proc import _tail, _LOG_TAIL_CHARS` (keeping the names importable from ci_gate for the existing test). `_proc.py` itself does NOT exist yet (`ls` → No such file).

---

## Claim 5 — test doubles `_ScriptedRunner` / `_FakeClock` / `_no_sleep` @ test_ci_gate.py:43-81

**Verdict: ACCURATE (line range exact).**

`_completed` helper (lines 27-30) — builds the scripted return value:
```python
def _completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )
```

`_ScriptedRunner` (lines 43-69):
```python
class _ScriptedRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.checks_queue: list[subprocess.CompletedProcess] = []
        self.run_view_queue: list[subprocess.CompletedProcess] = []
        self.ready_queue: list[subprocess.CompletedProcess] = []

    def __call__(self, cmd, cwd):  # type: ignore[no-untyped-def]
        self.calls.append(list(cmd))
        if cmd[:3] == ["gh", "pr", "checks"]:
            assert self.checks_queue, "ran out of scripted gh pr checks replies"
            return self.checks_queue.pop(0)
        if cmd[:3] == ["gh", "run", "view"]:
            if self.run_view_queue:
                return self.run_view_queue.pop(0)
            return _completed(stdout="(no log captured)\n")
        if cmd[:3] == ["gh", "pr", "ready"]:
            if self.ready_queue:
                return self.ready_queue.pop(0)
            return _completed(returncode=0)
        raise AssertionError(f"unexpected command in test: {cmd}")
```

- **Signature matches `CommandRunner`:** `__call__(self, cmd, cwd)` — two positional args (argv list + cwd string).
- **Returns `subprocess.CompletedProcess`?** YES — via `_completed(...)` (built with `subprocess.CompletedProcess(...)`).
- **What it scripts on:** keys on the **first 3 argv tokens** (`cmd[:3]`) — `["gh","pr","checks"]`, `["gh","run","view"]`, `["gh","pr","ready"]` — and pops the next reply from the matching per-kind FIFO queue (`checks_queue` / `run_view_queue` / `ready_queue`). Records every call in `self.calls`.
- **Scripted fields** of each `CompletedProcess`: `stdout`, `stderr`, `returncode` (args fixed to `[]`).

`_FakeClock` (lines 72-77):
```python
class _FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
    def now(self) -> float:
        return self.t
```
Passed as `now=clock.now`. Tests advance time by wrapping the runner (e.g. `clock.t += 5.0` before delegating).

`_no_sleep` (lines 80-81):
```python
async def _no_sleep(_seconds: float) -> None:
    return None
```
Async no-op; injected as `sleep=_no_sleep`.

**Grounding for Behavior 4 "copy the pattern":** the pattern is solid for argv-keyed `gh` commands. NOTE for B4: `_ScriptedRunner.__call__` does `cmd[:3]` and `list(cmd)` — both assume `cmd` is an **argv list/sequence**. If B4's deterministic_check runner takes a **shell command STRING** (per Claim 1's mismatch), this scripted-runner pattern must be **re-shaped** (a string `cmd` has no meaningful `cmd[:3]` argv slice — `"gh pr checks"[:3]` == `"gh "`). The copy is not 1:1 if the runner contract changes to a string.

---

## Claim 6 — `deterministic_check.py` does NOT exist

**Verdict: CONFIRMED — does not exist.** `ls swe_af/execution/deterministic_check.py` → "No such file or directory". It is new in the plan.

---

## Claim 7 — ci_gate timeout / subprocess-raise handling today

**Verdict: WRONG (plan's premise is unsupported). ci_gate has NO per-subprocess timeout and NO `-1` exit_code sentinel.**

Searched the entire `ci_gate.py`:
- `_default_runner` (lines 41-50) calls `subprocess.run(...)` with **NO `timeout=`** argument and does **NOT** catch `subprocess.TimeoutExpired` or any exception. A hung subprocess blocks forever; a raise propagates uncaught.
- The **only** timeout mechanism is the **wall-clock poll cap** in `watch_pr_checks`: `if elapsed() >= wait_seconds:` (line 290) → returns a `CIWatchResult` with `status="timed_out"` (lines 306-314) or `status="no_checks"` (lines 292-305). This is a *polling-loop* cap, not a subprocess timeout.
- The non-zero-exit handling (lines 195-211) distinguishes "checks failing but valid JSON" from "real gh error" via stdout presence — it does **not** involve any timeout or `-1` sentinel.
- There is **no occurrence of `-1`, `exit_code = -1`, `TimeoutExpired`, or `timeout=` anywhere in ci_gate.py.**

**Behavior 4's claim "mirrors ci_gate timeout handling with exit_code sentinel -1" has NO basis in the current ci_gate code.** ci_gate does not produce a `-1` sentinel, does not set a subprocess timeout, and does not catch `TimeoutExpired`. B4 would be **introducing a new pattern**, not mirroring an existing one. The review must flag this as an inaccurate provenance claim — B4 needs to specify its own timeout + `-1` sentinel behavior rather than citing ci_gate as precedent. (`CompletedProcess.returncode` for a killed-by-signal process is negative, but ci_gate never relies on or asserts that.)

---

## Claim 8 — `subprocess.run` with `shell=True` anywhere in `swe_af/`?

**Verdict: CONFIRMED — `shell=True` is used NOWHERE in the codebase.**

`grep -rn 'shell=True' --include='*.py' .` (excluding `.venv`) → **zero matches** (repo-wide).
`grep -rn 'shell=True' swe_af/` → zero matches.

`subprocess.run` IS used heavily (≈24 sites in `swe_af/app.py` + 1 in `ci_gate.py:44`) but **all** are argv-style (`shell=False` default). Behavior 4's `shell=True` would be a **brand-new pattern** introduced to the codebase — no precedent exists. Combined with Claim 1, this reinforces that the existing `CommandRunner` (argv `Sequence[str]`) contract was deliberately argv-only, and a shell-string/`shell=True` runner is foreign to the established convention.

---

## Summary of contract risks the review MUST surface

1. **CommandRunner type mismatch (Claim 1):** alias is `Callable[[Sequence[str], str], CompletedProcess[str]]` = (argv-list, cwd). Behavior 4's shell-pipeline-via-`shell=True`-with-command-STRING is incompatible: `shell=True` needs a `str` command, not a `Sequence[str]`; `_default_runner` does `list(cmd)` which would shred a command string. Reuse as-is is impossible — needs a distinct runner type, or `["bash","-c",pipeline]` argv, or a generalized alias.
2. **No timeout/`-1` precedent (Claim 7):** ci_gate has no per-subprocess timeout and no `-1` exit_code sentinel; B4's "mirrors ci_gate" provenance is false.
3. **No `shell=True` precedent (Claim 8):** zero `shell=True` in the entire codebase — B4 introduces a new pattern.
4. **`_tail`/`_LOG_TAIL_CHARS` promotion (Claim 4):** feasible to `_proc.py`, but must preserve importability from `ci_gate` (test imports `_tail` from ci_gate at test_ci_gate.py:20).
5. **Scripted-runner copy (Claim 5):** pattern keys on `cmd[:3]` argv slice; breaks if B4's runner takes a string.
