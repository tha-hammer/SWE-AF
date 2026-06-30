---
date: 2026-06-11T07:43:46-04:00
author: maceo
git_commit: 6517b17
branch: feat/baml-structured-output
base_worktree: /home/maceo/Dev/SWE-AF-baml
repository: SWE-AF
topic: "BAML-typed deterministic backpressure rung for the SWE-AF coding loop"
tags: [tdd, plan, baml, backpressure, deterministic-checks, verification, coding-loop, harness]
status: draft
depends_on: feat/baml-structured-output (BAML parser bridge; not yet on main)
research:
  - thoughts/searchable/shared/research/2026-06-11-06-45-backpressure-in-swe-af-harness.md
  - thoughts/searchable/shared/plans/2026-06-11-04-27-tdd-baml-structured-output-swe-af.md
tier: L1
last_updated: 2026-06-11
last_updated_note: "Folded in spike findings — Behavior 0a (bridge dict/Any hardening) and Behavior 6b (BAML output_format prompt render, B7 booster)"
---

# BAML-Typed Deterministic Backpressure for the SWE-AF Coding Loop — TDD Plan

## Overview

The SWE-AF harness has exactly **one** piece of deterministic, fail-loud
backpressure today: the post-PR CI gate (`ci_gate.py`), and it runs **last** —
after a PR exists. The inner per-issue coding loop, where a check would be
cheapest and catch the most, has **none**: the coder *self-attests*
`tests_passed` (`CoderResult.tests_passed` is annotated `# Self-reported`,
[execution/schemas.py:421](swe_af/execution/schemas.py#L421)), and every in-loop
gate is an LLM verdict, never a subprocess exit code (see research:
[2026-06-11-06-45-backpressure-in-swe-af-harness.md](thoughts/searchable/shared/research/2026-06-11-06-45-backpressure-in-swe-af-harness.md)).

The blocker to adding a real rung was a **typing gap**: the planner already
*authors* runnable commands — the PM prompt mandates "Every criterion MUST map to
a command" ([prompts/product_manager.py:57-59](swe_af/prompts/product_manager.py#L57))
— but they land in untyped free-text fields (`acceptance_criteria: list[str]`,
`testing_strategy: str`) the harness can't mechanically extract.

**This plan closes that gap with BAML types and adds the rung.** It introduces a
**typed `AcceptanceCheck`** carrying a runnable `command`, which BAML's
Schema-Aligned Parser (the `feat/baml-structured-output` bridge) recovers
resiliently from harness output; a **Pydantic validator** guarantees the command's
presence/shape on *every* parse; a **deterministic manifest detector** supplies a
project-level fallback command; and a **gate-bounded rung** in `run_coding_loop`
runs the command in the issue's worktree, feeds non-zero exits back into the coder,
and blocks completion while red — true backpressure, cheapest-check-first.

### Decisions locked (with the user, 2026-06-11)

| Decision | Choice |
|---|---|
| Plan base | **Stack on `feat/baml-structured-output`** (BAML bridge is the foundation) |
| Command source | **Typed planner field + deterministic manifest-detector fallback** |
| Failure semantics | **Gate, bounded** — block completion while red; re-enter coder with the failure tail; cap, then downgrade to advisory |
| First rung locus | **Inner coding loop**, right after `run_coder` returns (cheapest-first) |

## Current State Analysis

### Key Discoveries (verified on the branch, file:line)

- **BAML bridge is real and parser-only.** `swe_af/baml_bridge.py` (branch only)
  maps a runtime Pydantic schema → `@@dynamic DynamicOutput` via `TypeBuilder`,
  parses raw harness text with `b.parse.ExtractDynamic` (no LLM), and casts back to
  the model. `_map_type` handles `list[X]`
  ([baml_bridge.py:70-72](swe_af/baml_bridge.py#L70)) and nested `BaseModel`
  ([baml_bridge.py:108-112](swe_af/baml_bridge.py#L108)) — so `list[AcceptanceCheck]`
  flows through unchanged. `baml_parse` raises; `baml_parse_or_none` declines to
  `None` ([baml_bridge.py:169-196](swe_af/baml_bridge.py#L169)).
- **BAML is fallback-first** — `baml_parse_or_none` fires *only* on the agentfield
  SDK's `None`. So on the happy path BAML never runs. **Consequence:** the
  always-on validity guarantee must live in **Pydantic** (runs on every parse, both
  paths), not in BAML asserts. BAML's role here is structural typing + SAP
  resilience.
- **`@assert`/`@check` on dynamic (`TypeBuilder`) fields is undocumented.** The
  BAML docs state checks/asserts on dynamically-built fields "are not documented";
  the Python `add_property()` API exposes `.description()`, not `.assert_()`. This
  is retired by **Behavior 0** (spike) and is **not load-bearing** either way.
- **The runner template exists and is injectable + tested — but it is argv-shaped.**
  `ci_gate.CommandRunner = Callable[[Sequence[str], str], subprocess.CompletedProcess[str]]`
  ([ci_gate.py:38](swe_af/execution/ci_gate.py#L38)) takes an **argv list** (arg1) and `cwd`
  (arg2); `_default_runner` runs `subprocess.run(list(cmd), …, check=False)` with
  **`shell=False` and NO `timeout`** ([ci_gate.py:41-50](swe_af/execution/ci_gate.py#L41)).
  `_tail` / `_LOG_TAIL_CHARS=3000` ([ci_gate.py:31,92-95](swe_af/execution/ci_gate.py#L92));
  scripted fake runner + fake clock ([tests/test_ci_gate.py:43-81](tests/test_ci_gate.py#L43)).
  **Consequence (Behavior 4):** a shell *string* cannot be passed to this argv runner
  (`list("pytest")` → `['p','y',…]`). Acceptance commands are pipelines, so the rung wraps
  each as the argv `["bash", "-c", command]` and **reuses the same `CommandRunner` type** —
  keeping `shell=False` (there is **zero** `shell=True` in the repo) and adding its **own**
  `timeout` (ci_gate has none to inherit).
- **The harness already holds the working dir.** `run_coding_loop` reads
  `worktree_path = issue.get("worktree_path", dag_state.repo_path)`
  ([coding_loop.py:543](swe_af/execution/coding_loop.py#L543)) and passes it as
  `cwd=worktree_path` to the coder. A harness-level `subprocess.run(cwd=worktree_path)`
  targets the same isolated tree.
- **The insertion point is clean.** The coder result is assigned at
  [coding_loop.py:616](swe_af/execution/coding_loop.py#L616) and its artifact saved
  at [coding_loop.py:659](swe_af/execution/coding_loop.py#L659); the path branch
  (`if needs_deeper_qa:`) is at [coding_loop.py:662](swe_af/execution/coding_loop.py#L662).
  The rung inserts **between 659 and 662** — after the coder, before any reviewer/QA
  call (so a red check costs zero LLM calls).
- **Feedback is a free-text channel.** The next-iteration `feedback` is assembled
  in `feedback_parts` and joined at [coding_loop.py:802](swe_af/execution/coding_loop.py#L802);
  the deterministic failure tail appends there.
- **`PlannedIssue` serializes to the issue dict losslessly.**
  `dag_executor.py:741-742` calls `model_dump()`; nested models become nested dicts
  (`guidance` is read as `issue.get("guidance") or {}` at
  [coding_loop.py:564](swe_af/execution/coding_loop.py#L564)). A new
  `verification: list[AcceptanceCheck]` survives as `issue.get("verification", [])`
  → `list[dict]`.
- **No manifest-detection code exists.** Detection is referenced only in *prompt
  text* (`git_init.py:46`, `environment_scout.py:35`). The detector in Behavior 3
  is genuinely new code.
- **Dependency provisioning is left to the agent.** The harness installs **no**
  target-project deps (Dockerfile installs only harness deps). A harness-level
  `pytest` in a cold worktree could fail with `ModuleNotFoundError`. **This plan
  turns that into a feature, not a blocker:** a missing-dep failure is just another
  red check whose tail ("ModuleNotFoundError: no module named X") feeds back to the
  coder, which installs deps next iteration — bounded by the gate cap.

### The two-tier deterministic layer

0. **BAML bridge enablers (spike-proven)** — harden `_map_type` so real reasoner
   schemas with bare `dict`/`Any` map instead of crashing (Behavior 0a), and render
   the prompt's output-shape section from the type via BAML `output_format`
   (Behavior 6b — a B7 booster, ~85% smaller than today's JSON Schema).
1. **Shape/validity guarantee** — typed `AcceptanceCheck.command` + Pydantic
   validator (always-on) + BAML SAP recovery (fallback path). *Behaviors 0–2.*
2. **Execution backpressure** — deterministic runner + manifest fallback +
   resolution + the gated coding-loop rung. *Behaviors 3–6.*
3. **Producer** — teach the planner to emit the typed field, with the BAML-rendered
   `output_format` (Behavior 6b) sharpening emission. *Behaviors 6b, 7.*

## Desired End State

A coder iteration that produces code failing the issue's own declared check
**cannot** complete: the harness runs the command in the worktree, sees a non-zero
exit, feeds the real failure tail back, and re-enters the coder — without spending
a reviewer call — bounded, then downgrading to advisory. When the command passes
(or none is resolvable, or the flag is off), behavior is byte-identical to today.

### Observable Behaviors

- A `RetryAdvice`-style round-trip proves a typed `AcceptanceCheck` (with a piped
  command like `… | jq …`) survives `baml_parse`.
- An empty/whitespace `command` raises a Pydantic `ValidationError`; a piped
  command is accepted.
- A `PlannedIssue` with `verification=[…]` round-trips through BAML and survives
  `model_dump()` into the issue dict.
- `detect_project_commands(tmp_with_pyproject)` → `{"test": "pytest", …}`
  deterministically; `go.mod` → `go test ./...`; `package.json` test script →
  `npm test`.
- `run_local_check("exit 1", cwd, fake_runner)` → `passed=False` with the output
  tail; `"true"` → `passed=True`.
- A runner that raises `TimeoutExpired` → `passed=False, exit_code=-1` (the rung's own
  timeout — there is no `ci_gate` timeout to mirror; a hung command must not stall the build).
- In `run_coding_loop`: a coder result whose worktree fails the command forces
  `action="fix"`, appends the tail to `feedback`, and does **not** call the
  reviewer that iteration; after `max_deterministic_check_retries` consecutive
  reds, the rung downgrades to advisory and the LLM gates run.
- Flag off / no commands / command exits 0 → reviewer path runs exactly as today
  (a spy on the runner confirms it isn't called when disabled).

## What We're NOT Doing

- **No security sanitization of the command string.** Safety is the worktree +
  container isolation (the same boundary the agent's Bash already runs under). The
  validator guarantees *presence/shape*, not safety. Commands are pipelines by
  design (`| jq`, `>`), so the runner wraps each command as the argv `["bash", "-c",
  command]` (not `shell=True`) in the isolated worktree.
- **No change to the BAML fallback-first seam** — the bridge stays parser-only.
- **No BAML asserts as the load-bearing guarantee** — Pydantic validators are. The
  BAML `@check` (if Behavior 0 proves feasible) is an optional fallback-path echo.
- **No verifier-stage / integration rung yet** — that is a deliberate second slice
  (Behavior 6 targets the inner loop only).
- **No replacing the LLM reviewer/QA/verifier** — the rung sits *before* them and
  gates; they still run on green.
- **No Go port** — `swe_af/` Python only.

## Testing Strategy

- **Framework**: `pytest` (markers `unit` / `functional` / `integration`;
  `asyncio_mode=auto`), run in the branch `.venv` via
  `AGENTFIELD_SERVER=http://localhost:9999 uv run pytest`
  (the session-autouse guard in [tests/conftest.py:76-97](tests/conftest.py#L76)
  requires the dummy server var). Install: `uv sync --extra dev`.
- **Test types**: unit (schema/validator/detector/runner — deterministic, no
  network, no LLM); functional (resolution + coding-loop rung with fake `call_fn` +
  fake runner); one optional integration (real planner emits the typed field,
  key-gated).
- **Doubles**: copy the `_ScriptedRunner` / `_FakeClock` / `_no_sleep` pattern
  ([tests/test_ci_gate.py:43-81](tests/test_ci_gate.py#L43)) for the new runner;
  copy the `_roundtrip` helper ([tests/test_baml_bridge.py:26-32](tests/test_baml_bridge.py#L26))
  for BAML round-trips.
- **Property tests** (Hypothesis) where a domain exists — see each behavior.

---

## Behavior 0: Spike — can BAML `@check`/`@assert` ride a dynamic type?

> Risk-retirement spike that directly answers the user's question about
> checks-and-asserts. **Not load-bearing** — the plan proceeds with Pydantic
> validators regardless. Deliverable: a documented capability + a one-line
> decision recorded in the plan's Risks section.
>
> **API note (verified):** there is **no fluent `@check`/`@assert` API** for dynamic
> fields — `tb.add_property()` returns a `ClassPropertyBuilder` exposing only `.alias()`
> / `.description()` (confirmed in `baml_py.pyi`). The **only** attach mechanism is
> `tb.add_baml(<raw baml string>)`, which is exactly what this spike exercises.

### Test Specification
**Given**: the branch `.venv` with `baml_py` and the generated `baml_client`.
**When**: we attempt to attach a `@check` to the `@@dynamic DynamicOutput` root via
`tb.add_baml("dynamic class DynamicOutput { command string @check(nonempty, {{ this|length > 0 }}) }")`,
then `b.parse.ExtractDynamic('{"command":""}', baml_options={"tb": tb})`.
**Then**: we record one of two outcomes deterministically — (a) the check surfaces
on the parsed result's `.checks` and we can read its status; or (b) it is rejected
/ ignored for dynamic types (TypeError / no `.checks`).

**Edge Cases**: `add_baml` raises a syntax/availability error → outcome (b).

**Files touched**: `tests/test_baml_checks_spike.py` (new, `unit`).

### TDD Cycle
🔴 **Red** — assert the *recorded expectation* (start by asserting outcome (a); let
it fail if the API rejects it).
🟢 **Green** — adjust the assertion to the **observed** behavior and add a module
docstring capturing the verdict; if (a), assert we can read `.checks[...].status`;
if (b), assert the `add_baml`/parse raises or yields no checks.
🔵 **Refactor** — write the one-line verdict into this plan's Risks section and the
Behavior-1 note (whether to add the BAML `@check` echo).

### Success Criteria
**Automated:**
- [x] Spike test passes asserting the *observed* capability: `… uv run python -m pytest tests/test_baml_checks_spike.py` — **2 passed** (verdict: outcome (a))
**Manual:**
- [x] Verdict recorded (outcome (a) — checks DO ride dynamic types, surfacing as a dict); Behavior 1's optional BAML-echo decided: **feasible but not wired** (fallback-first → Pydantic is the always-on guarantee).

---

## Behavior 0a: Harden `baml_bridge._map_type` for bare `dict` / `Any` (bridge prerequisite)

> Spike-resolved (2026-06-11). Today `_map_type` **raises `TypeError`** on a bare
> `dict`/`Any` field ([baml_bridge.py:114](swe_af/baml_bridge.py#L114)); verified
> failing schemas: `QAResult`, `MergeResult` (both carry a bare `dict`), and
> `CoderResult.agent_retro: dict = {}` ([execution/schemas.py:424](swe_af/execution/schemas.py#L424)).
> `baml_parse_or_none` currently swallows that `TypeError` → declines to `None`, so
> these schemas silently never benefit from BAML (parse **or** the `output_format`
> render of Behavior 6b). **Primary dependent: Behavior 6b** (the render must cover
> dict-bearing reasoner schemas); also a general parser-robustness win. B1's
> `AcceptanceCheck` and B2's `PlannedIssue` contain **no** bare dict, so this does not
> block them — it is sequenced early so the bridge is sound before 6b.
>
> **Spike verdict on BAML's three recommended options (each run on the real failing
> field, branch venv):**
> | Option | Result |
> |---|---|
> | **A. recursive `JsonValue` alias** via `add_baml`, field → `map<string, JsonValue>` | ✅ round-trips arbitrary nested dict exactly |
> | **B. `string` + `json.loads`** | ❌ BAML SAP writes **non-strict** JSON (unquoted keys: `{a: 1, …}`) into the string → `json.loads` raises. **Out.** |
> | **C. omit-if-defaulted** | ✅ confirmed `agent_retro` is `required=False, default={}` |
>
> The `JsonValue` alias is **not referenceable via `add_property`** (no `tb.JsonValue`
> handle) — Option A requires emitting the dynamic type via `add_baml` source.
> **Decision: default = omit-if-defaulted; `JsonValue`-alias as a documented opt-in
> upgrade** for fields whose *contents* matter.

### Test Specification
**Given**: a SWE-AF schema with a bare `dict`/`Any` field that has a default (e.g.
`CoderResult`, `QAResult`, `MergeResult`).
**When**: `pydantic_to_typebuilder(schema)` then a `baml_parse` round-trip runs.
**Then**: it no longer raises; the schema maps, and a round-trip reconstructs the
typed object with the unmappable field taking its Pydantic default (omit-if-defaulted).

**Edge Cases**:
- **Required** bare-`dict`/`Any` field → still **raises `TypeError`** (we never silently
  drop required data — only *defaulted* fields are omitted).
- a defaulted bare-`dict` field omitted from the BAML type → `_strip_none`
  ([baml_bridge.py:140](swe_af/baml_bridge.py#L140)) + the Pydantic default fill it on
  `model_validate`.
- (upgrade path, separate test) a field mapped via the `JsonValue` alias round-trips a
  nested dict exactly — opt-in, not wired by default.

**Property**: for any schema all of whose unmappable fields have defaults,
`pydantic_to_typebuilder(schema)` does not raise.

**Files touched**: `swe_af/baml_bridge.py` (`pydantic_to_typebuilder` @132 — wrap
`tb.DynamicOutput.add_property(fname, _field_type(finfo, tb))` in `try/except TypeError`:
re-raise iff `finfo.is_required()`, else skip the property), `tests/test_baml_bridge.py`
(extend).

### TDD Cycle
🔴 **Red** — assert `pydantic_to_typebuilder(QAResult)` (or `CoderResult`) does **not**
raise and that a round-trip of an instance equals the original (dict field at its
default). Fails today (`TypeError`).
🟢 **Green** — in `pydantic_to_typebuilder`, wrap the per-field `add_property` in
`try/except TypeError`; on `TypeError`, `if finfo.is_required(): raise` else `continue`.
🔵 **Refactor** — add the required-field-still-raises test; document the
omit-if-defaulted contract in the docstring; add the optional `JsonValue`-alias helper
(`_jsonish(tb)` via `add_baml`) as the documented upgrade path (not wired by default).

### Success Criteria
**Automated:**
- [x] `pydantic_to_typebuilder(QAResult/MergeResult/CoderResult)` no longer raises; round-trips green
- [x] a required bare-`dict` field still raises `TypeError`
- [x] existing `tests/test_baml_bridge.py` green (no regression on already-mappable schemas) — **13 passed**
**Manual:**
- [x] omit-if-defaulted contract documented in the `pydantic_to_typebuilder` docstring.

---

## Behavior 1: Typed `AcceptanceCheck` schema + always-on command validator

### Test Specification
**Given**: a new `AcceptanceCheck(BaseModel)` —
`description: str`, `command: str`, `kind: Literal["build","test","check"] = "check"`
— with a Pydantic validator on `command`.
**When**: it is constructed and round-tripped through `baml_parse`.
**Then**: a non-empty (incl. piped) command round-trips equal; an empty/whitespace
command raises `pydantic.ValidationError`.

**Edge Cases**:
- `command="   "` → `ValidationError`.
- `command="hyperfine x --export-json | jq '.results[0].mean < 0.001'"` → accepted
  (pipes/quotes are legal; the validator does **not** reject metacharacters).
- `command` longer than a sane bound (e.g. 2000 chars) → `ValidationError`
  (catches a hallucinated essay-as-command).

**Property**: for any `AcceptanceCheck` `J` with `command.strip()` non-empty and
within the length bound, `baml_parse(json.dumps(J_dict), AcceptanceCheck) == AcceptanceCheck(**J_dict)`.

**Files touched**: `swe_af/reasoners/schemas.py` (add `AcceptanceCheck` immediately
**before** `class PlannedIssue` — use this named anchor, not an absolute line; `class
PlannedIssue` is currently at line 78 and every absolute line below shifts once this
lands), `tests/test_acceptance_check_schema.py` (new).

### TDD Cycle
🔴 **Red** — `tests/test_acceptance_check_schema.py`: construct an `AcceptanceCheck`
with a piped command, assert `_roundtrip(AcceptanceCheck, J) == AcceptanceCheck(**J)`
(copy the `_roundtrip` helper); add `pytest.raises(ValidationError)` for empty
command. Fails (no class).
🟢 **Green** — add `AcceptanceCheck` with a `@field_validator("command")` (or
`Annotated[str, AfterValidator(...)]`) enforcing `value.strip()` non-empty and
`len(value) <= 2000`.
🔵 **Refactor** — if Behavior 0 proved (a), optionally have `pydantic_to_typebuilder`
(`baml_bridge.py:132`) inject the BAML `@check` echo for `AcceptanceCheck.command` **via
`tb.add_baml(<raw>)`** — there is **no** `.check()`/`.assert_()` builder method, so this is
raw-string injection, not a fluent call. Otherwise add a comment pointing to the Pydantic
validator as the sole guarantee. Deduplicate the length/non-empty rule into one validator
function.

### Success Criteria
**Automated:**
- [x] Red → Green on `tests/test_acceptance_check_schema.py`
- [x] `… uv run python -m pytest tests/test_acceptance_check_schema.py` green — **7 passed**
- [x] `ruff` clean
**Manual:**
- [x] Piped command accepted; empty rejected.

---

## Behavior 2: `PlannedIssue.verification` flows planner → issue dict → coder context

### Test Specification
**Given**: `PlannedIssue` with a new `verification: list[AcceptanceCheck] = []`
field.
**When**: a `PlannedIssue` carrying `verification=[AcceptanceCheck(...)]` is
`model_dump()`-ed (as `dag_executor.py:741-742` does) and round-tripped through
`baml_parse`.
**Then**: the dumped dict exposes `verification` as `list[dict]` readable via
`issue.get("verification", [])`, and the BAML round-trip reconstructs the typed
list.

**Edge Cases**:
- `verification=[]` (default) → `issue.get("verification", []) == []`, behavior
  unchanged.
- messy harness text with the `verification` block embedded → `baml_parse` recovers
  it where the SDK regex ladder returns `None` (the BAML resilience claim).

**Property**: `baml_parse(json.dumps(P.model_dump()), PlannedIssue).verification == P.verification`.

**Files touched**: `swe_af/reasoners/schemas.py` (add `verification` to `PlannedIssue`
immediately **after the `guidance` field** — currently line 92. Do **not** use "92/93":
that collides with the existing `guidance` (92) / `target_repo` (93) fields, and these
absolute numbers shift once `AcceptanceCheck` lands above), `tests/test_planned_issue_verification.py` (new).

### TDD Cycle
🔴 **Red** — assert a `PlannedIssue` round-trips with `verification` populated and
that `model_dump()["verification"][0]["command"]` is present. Fails (no field).
🟢 **Green** — add `verification: list[AcceptanceCheck] = []` to `PlannedIssue`.
🔵 **Refactor** — add the messy-text recovery case (BAML parses where
`agentfield.harness._schema.try_parse_from_text(text, PlannedIssue) is None`),
mirroring the SB-3 dual-oracle pattern from the BAML plan.

### Success Criteria
**Automated:**
- [x] Round-trip + serialization-survival tests green — **4 passed** (incl. messy-text recovery)
- [x] Existing `tests/test_baml_bridge.py` still green (no mapper regression) — **20 passed** w/ test_baml_parse
**Manual:**
- [x] `verification` visible in a dumped issue dict.

---

## Behavior 3: Deterministic manifest detector (fallback command source)

### Test Specification
**Given**: a worktree directory containing a project manifest.
**When**: `detect_project_commands(worktree_path)` runs (pure, no LLM, no network).
**Then**: returns a dict of `{kind: command}` per a fixed table:

| Manifest present | `build` | `test` |
|---|---|---|
| `pyproject.toml` / `setup.py` | — | `pytest` |
| `go.mod` | `go build ./...` | `go test ./...` |
| `package.json` w/ `scripts.test` | `npm run build` (if present) | `npm test` |
| `Cargo.toml` | `cargo build` | `cargo test` |
| `Makefile` w/ `test:` target | — | `make test` |
| none | — | `{}` (empty) |

**Edge Cases**: multiple manifests → deterministic precedence (document the order,
e.g. Cargo > go > pyproject > package.json > Makefile); `package.json` without a
`test` script → no test command; unreadable/!exists → `{}`.

**Property**: deterministic — same directory contents → identical dict
(idempotent across repeated calls).

**Files touched**: `swe_af/execution/deterministic_check.py` (new — `detect_project_commands`),
`tests/test_check_discovery.py` (new, `tmp_path`-driven).

### TDD Cycle
🔴 **Red** — `tmp_path` with a `pyproject.toml`; assert `detect_project_commands(tmp) == {"test": "pytest"}`. Fails (no module).
🟢 **Green** — implement table-driven detection via `os.path.exists` + minimal
`package.json`/`Makefile` parsing.
🔵 **Refactor** — extract the manifest→command table to a module constant; add the
multi-manifest precedence test and the empty case; ensure no duplicated `exists`
logic.

### Success Criteria
**Automated:**
- [x] Table cases + precedence + empty all green — **15 passed**
- [x] `npx jscpd swe_af/execution/deterministic_check.py` — no clones (0 found)
**Manual:**
- [x] Adding a manifest type is a one-line table edit (extensibility check) — fixed-command langs are a one-line `_DETECTORS` entry.

---

## Behavior 4: Deterministic local runner (`run_local_check`)

### Test Specification
**Given**: a `command` string, a `cwd`, an injectable runner (default: an argv runner that
wraps the command as `["bash", "-c", command]`), and a per-check `timeout`.
**When**: `run_local_check(command, cwd, runner=fake, timeout=…)` runs.
**Then**: returns `CheckResult(passed: bool, exit_code: int, output_tail: str)` —
`passed == (exit_code == 0)`, `output_tail` is `_tail(stdout+stderr, 3000)`.

**Runner contract (reconciled — see Current State):** `ci_gate.CommandRunner =
Callable[[Sequence[str], str], subprocess.CompletedProcess[str]]` takes an **argv list**,
not a shell string. So `run_local_check` builds `argv = ["bash", "-c", command]` and calls
`runner(argv, cwd)`. This **reuses the existing `CommandRunner` type unchanged**, keeps
`shell=False` (zero `shell=True` in the repo), and runs pipelines correctly (`bash -c`
interprets `| jq`, `>`). Non-login `-c` inherits the parent env (PATH etc.), avoiding
profile-sourcing surprises.

**Timeout (load-bearing — `ci_gate` has none to inherit):** the default runner passes
`timeout=timeout` to `subprocess.run`; `run_local_check` wraps the runner call in
`try/except (subprocess.TimeoutExpired, OSError)` and maps either to
`CheckResult(passed=False, exit_code=-1, output_tail=<error / "timeout">)`. Without this a
hung command (cold-worktree `pytest` blocked on network, a watch-mode runner, an
interactive prompt) blocks the build forever, breaking the "bounded" promise. The timeout
is the config knob `deterministic_check_timeout_seconds` (Behavior 6), default `600`.

**Edge Cases**:
- `"exit 1"` → `passed=False, exit_code=1`, tail captured.
- `"true"` → `passed=True`.
- `"echo hi | grep hi"` (pipeline) → `passed=True` via the `bash -c` argv wrap.
- runner raises `TimeoutExpired` / `OSError` → `passed=False, exit_code=-1`, tail = the
  error text. (This is the plan's **own** handling — there is no `ci_gate` timeout to mirror.)
- empty command → never reached (Behavior 1 validator blocks it upstream); a defensive
  `passed=False` if somehow empty.

**Property**: `run_local_check(...).passed iff exit_code == 0` for all runner outputs.

**Files touched**: `swe_af/execution/deterministic_check.py` (add `CheckResult` schema +
`run_local_check` + a default argv runner `_default_local_runner` that wraps `bash -c` and
applies `timeout`; import `_tail` from the shared `_proc.py` promoted in the Refactor step),
`tests/test_local_check.py` (new — fake runner per `test_ci_gate.py`).

### TDD Cycle
🔴 **Red** — fake runner returns `CompletedProcess(args=…, returncode=1, stdout="boom")`;
assert `run_local_check("x", "/tmp", runner=fake).passed is False` and tail contains "boom".
Fails (no function).
🟢 **Green** — implement `run_local_check`: build `["bash", "-c", command]`, call
`runner(argv, cwd)` inside `try/except (TimeoutExpired, OSError)`, return `CheckResult`. The
default `_default_local_runner(cmd, cwd)` runs `subprocess.run(list(cmd), cwd=cwd or None,
capture_output=True, text=True, check=False, timeout=DET_CHECK_TIMEOUT_SECONDS)`.
🔵 **Refactor** — promote `_tail`/`_LOG_TAIL_CHARS` to a shared `swe_af/execution/_proc.py`
imported by both `ci_gate` and `deterministic_check`; **keep `ci_gate` re-exporting `_tail`**
(`tests/test_ci_gate.py` imports `_tail` *from* `ci_gate`, so the import must stay valid).
Add the timeout-raise→`passed=False` and pipeline cases.

### Success Criteria
**Automated:**
- [x] pass / fail / tail / pipeline / timeout cases green — **10 passed**
- [x] timeout-raise → `passed=False, exit_code=-1` (own test: fake runner raises `TimeoutExpired`)
- [x] `ci_gate` tests still green after `_tail` promotion (re-export preserved) — **39 passed**
- [x] no duplication of `_tail` (grep — single def in `_proc.py`)
**Manual:**
- [x] A piped command (`echo hi | grep hi`) returns `passed=True` via the `bash -c` argv
      runner (automated as `test_real_pipeline_passes`).

---

## Behavior 5: Command resolution (typed-first, manifest-fallback)

### Test Specification
**Given**: an issue dict and its worktree.
**When**: `resolve_issue_commands(issue, worktree_path)` runs.
**Then**: returns an ordered `list[ResolvedCheck(command, source)]`:
1. typed `issue["verification"][*].command` if present (source=`"planned"`);
2. else `detect_project_commands(worktree)`'s `test`/`build` (source=`"manifest"`);
3. else `[]` (rung skipped).

**Edge Cases**:
- both present → planned wins, manifest ignored (or appended? **decision: planned
  only when present**, to honor per-issue specificity).
- `verification` present but all commands invalid (shouldn't happen post-Behavior-1)
  → treat as absent → manifest fallback.
- multi-repo issue (`target_repo`) → resolve against the issue's worktree (already
  the per-issue path).
- **Whole-suite manifest fallback can false-red.** A broad `pytest` / `npm test` reds on
  pre-existing or flaky failures unrelated to the issue's own code, and `pytest` with **no
  tests collected exits 5** (non-zero) — likely in early-TDD issues before tests exist.
  Mitigations: planned-over-manifest wins when present (targeted, e.g. `pytest -k lexer`);
  treat `pytest` exit code **5** as **not-red** (skip, not block); and the advisory cap
  (Behavior 6) stops blocking after the bound so a mis-scoped fallback cannot stall the loop.

**Property**: resolution is a pure function of `(issue, worktree contents)`.

**Files touched**: `swe_af/execution/deterministic_check.py` (add `resolve_issue_commands`
+ `ResolvedCheck`), `tests/test_check_discovery.py` (extend).

### TDD Cycle
🔴 **Red** — issue with `verification=[{command:"pytest -k lexer"}]`; assert
`resolve_issue_commands(issue, tmp)[0].command == "pytest -k lexer"` and
source=`"planned"`. Fails (no function).
🟢 **Green** — implement typed-first, manifest-fallback, empty.
🔵 **Refactor** — collapse the three branches into one readable resolution that
reveals intent; add the empty-and-no-manifest skip case.

### Success Criteria
**Automated:**
- [x] planned-wins / manifest-fallback / empty-skip all green — **22 passed** (B3+B5)
**Manual:**
- [x] Resolution order documented in the function docstring.

---

## Behavior 6: The gated coding-loop rung (the backpressure)

> **Keystone behavior.** Blast radius: `coding_loop.py` (the rung) + `schemas.py`
> (config flags/bounds, mirrored in `BuildConfig` + `ExecutionConfig` +
> `to_execution_config_dict`). The config-duplication across those three is a
> **pre-existing** coupling smell (`BuildConfig` class at
> [execution/schemas.py:684](swe_af/execution/schemas.py#L684), `ExecutionConfig` at
> [:988](swe_af/execution/schemas.py#L988), `to_execution_config_dict` at
> [:822-848](swe_af/execution/schemas.py#L822)); this plan follows the existing pattern
> rather than refactoring it — flagged here, not fixed here.
>
> **Two correctness facts verified on the branch that shape the rung:**
> 1. `run_coding_loop` has **no `continue`/`break`** in its `for iteration in range(...)`
>    body (602-760). The reviewer/QA *is* `_run_flagged_path` / `_run_default_path`
>    (664/690), which **set `action`, `summary`, `review_result`**. So the rung must
>    **gate the `if needs_deeper_qa:` branch and fall through** — it must **NOT** `continue`,
>    which would skip the iteration-history append, the checkpoint `_save_iteration_state`
>    (730-735), and the memory write (737-745).
> 2. `_save_iteration_state` persists `{"feedback": summary, …}` — the rich `feedback`
>    joined at [:802](swe_af/execution/coding_loop.py#L802) is **ephemeral, not
>    checkpointed**. So the failure tail must be folded into **`summary`** (and
>    `iteration_history`) to survive resume, in addition to `feedback_parts`.

### Test Specification
**Given**: `run_coding_loop` with a fake `call_fn` returning a `coder_result`, a fake local
runner, and `config.enable_deterministic_checks=True` (on an `ExecutionConfig` —
attribute access, `extra="forbid"`).
**When**: the coder produces code and the resolved command exits non-zero.
**Then**: the loop sets `action="fix"`, **bypasses the `if needs_deeper_qa:` reviewer/QA
branch** (no LLM call spent while red), sets `summary` (and appends to `feedback_parts`) to
carry the runner's `output_tail`, and **falls through** to the existing
history/checkpoint/memory machinery so the next iteration re-enters the coder with the tail
in `feedback`. After `config.max_deterministic_check_retries` consecutive reds, the rung
**downgrades to advisory**: it injects the tail into the reviewer context and lets the
existing path branch run.

**Edge Cases** (each its own assertion):
- **Green**: command exits 0 → rung is transparent; reviewer path runs exactly as today;
  `det_check_attempts` resets to 0.
- **Flag off** (`enable_deterministic_checks=False`) → runner never called (spy);
  byte-identical to today.
- **No commands resolved** → rung skipped; runner never called.
- **Dependency-miss** (`ModuleNotFoundError` in tail) → fed back as a normal red; bounded by
  the cap (this is the dependency-provisioning answer).
- **Cap reached** → advisory downgrade; LLM gates decide; no infinite loop.
- **No `continue`**: on a red, the rung sets `action="fix"`, `summary=<tail>`,
  `review_result=None`, and skips **only** the reviewer branch — assert the iteration
  **checkpoint was still written** on a red iteration (the history/checkpoint/memory code at
  the bottom of the loop must still run).
- **Checkpoint replay**: the tail is folded into `summary` (the persisted field) +
  `iteration_history` **before** `_save_iteration_state`
  ([coding_loop.py:730-735](swe_af/execution/coding_loop.py#L730)), and `det_check_attempts`
  is added to the checkpoint payload **and** the resume loader, so a resume mid-red-streak
  does not reset the bound.
- **Config propagation**: `BuildConfig(enable_deterministic_checks=False).to_execution_config_dict()`
  → `ExecutionConfig(**d).enable_deterministic_checks is False` (the triplication is
  otherwise untested — the other assertions set the flag directly on `ExecutionConfig`).

**Files touched**: `swe_af/execution/coding_loop.py` (rung between lines 659–662 — the seam
is a blank line + the `# --- 2. PATH BRANCH ---` comment; tail folded into `summary` and
`feedback_parts` before [coding_loop.py:802](swe_af/execution/coding_loop.py#L802);
`det_check_attempts` counter init before the loop (~583) and added to the
`_save_iteration_state` payload **and** the load path), `swe_af/execution/schemas.py` (add
`enable_deterministic_checks: bool = True`, `max_deterministic_check_retries: int = 2`, and
`deterministic_check_timeout_seconds: int = 600` to `BuildConfig` (class at 684) **and**
`ExecutionConfig` (class at 988) **and** the `to_execution_config_dict` allow-list (822-848)
— **all three together**, because `ExecutionConfig` has `model_config =
ConfigDict(extra="forbid")`: an orphan dict key **raises loudly**, while an omitted dict line
**silently falls back to the ExecutionConfig default** and ignores the `BuildConfig` value),
`tests/test_coding_loop_deterministic_gate.py` (new, `functional`).

### TDD Cycle
🔴 **Red** — fake `call_fn` yields a coder_result; fake runner returns `passed=False,
output_tail="AssertionError: …"`. Assert that after the iteration the recorded `action` is
`"fix"`, `feedback` contains `"AssertionError"`, the reviewer fake was **not** called, **and
the iteration checkpoint WAS written**. Fails (no rung).
🟢 **Green** — insert the rung after line 659:
`if config.enable_deterministic_checks:`
` gate = _run_deterministic_gate(...)`
` if gate.red and det_check_attempts < config.max_deterministic_check_retries:`
`   det_check_attempts += 1; action, summary, review_result = "fix", gate.tail, None  # skip the 662 reviewer branch`
` elif gate.red:`
`   inject gate.tail into the reviewer context; run the existing 662 branch (advisory)`
` else:`
`   det_check_attempts = 0; run the existing 662 branch`.
**Do not `continue`** — always fall through to the existing history/checkpoint/memory code so
bookkeeping runs. Append `gate.tail` to `feedback_parts` so it reaches L621's
`feedback=feedback` next iteration.
🔵 **Refactor** — extract the rung into a small helper `_run_deterministic_gate(issue,
worktree_path, config, runner) -> GateOutcome` (deep module: simple call site, logic hidden),
so `run_coding_loop` reads as `gate = _run_deterministic_gate(...); if gate.red and not
advisory: <set fix, skip reviewer> else: <existing 662 branch>`. Add the flag-off,
no-commands, green, cap-downgrade, **checkpoint-on-red**, and **config-propagation** tests;
confirm happy path unchanged via a spy.

### Success Criteria
**Automated:**
- [x] Red → Green: red check forces `fix` + feedback, no reviewer call, **checkpoint still written**
- [x] Flag-off / no-commands / green: reviewer path unchanged (spy asserts runner
      not called when disabled)
- [x] Cap → advisory downgrade (no infinite loop): bounded test terminates
- [x] `det_check_attempts` survives a simulated resume (persisted in checkpoint + reloaded)
- [x] Config propagation: `BuildConfig(enable_deterministic_checks=False)` reaches `ExecutionConfig` as `False`
- [x] Full suite: `… uv run python -m pytest -p no:randomly` — **1097 passed, 1 skipped** (after B6 commit; the lone `test_ac_14` failure was an uncommitted-working-tree artifact)
- [x] `npx jscpd swe_af/execution/coding_loop.py swe_af/execution/deterministic_check.py` — no new clones (the 1 clone is the pre-existing `_run_default_path`/`_run_flagged_path` signatures)
**Manual:**
- [DEFERRED-VERIFY] On a real build, a coder that writes failing code visibly re-iterates with the
      real test failure in its feedback — requires a live LLM build (follow-up: SWE-AF-x2g).

---

## Behavior 6b: BAML `output_format` as the prompt's output-shape section (B7 booster)

> Spike-proven (2026-06-11). Today agentfield injects the output shape as **raw JSON
> Schema** via `build_prompt_suffix` → `model_json_schema()` (agentfield
> `_schema.py:49-50,69`). BAML's `ctx.output_format` renders the *same* type far more
> compactly and readably, and we can render it **standalone, no LLM call** via
> `b.request.ExtractDynamic(<input>, baml_options={"tb": tb})` (the `.request`
> namespace returns the built request without sending it).
>
> **Measured on real schemas (branch venv):**
> | Schema | agentfield JSON Schema | BAML `output_format` | saved |
> |---|---|---|---|
> | AcceptanceCheck | 805c | 125c | 84% |
> | RetryAdvice | 1019c | 157c | 85% |
> | VerificationResult (nested) | 1726c | 251c | 85% |
>
> BAML renders nested types inline (`{ criterion: string, passed: bool, … }`) vs JSON
> Schema's `$defs`/`$ref`. **Depends on Behavior 0a** so dict-bearing schemas map.
>
> **Relationship to B7:** B7 works *without* this (the manifest fallback covers
> omissions), but a compact, readable `output_format` for the planner — now including
> `verification: list[AcceptanceCheck]` — materially raises the rate at which the
> planner emits the typed command. So 6b is a **booster** sequenced before/with B7,
> not a hard blocker.

### Test Specification
**Given**: a mappable SWE-AF schema (`AcceptanceCheck`, `RetryAdvice`,
`VerificationResult`) and a new `baml_output_format(model) -> str` helper.
**When**: `baml_output_format(model)` renders the output-shape section via `b.request`
(no LLM call), and the `build_prompt_suffix` seam chooses BAML-when-mappable /
agentfield JSON-Schema otherwise.
**Then**: the rendered string contains every field name, is materially smaller than
`json.dumps(model_json_schema())`, and an unmappable schema falls back to agentfield's
injection without raising.

**Edge Cases**:
- nested schema (`VerificationResult`) → inline nested shape, no `$ref`.
- unmappable schema (a required-`dict` field, or pre-0a) → `baml_output_format`
  raises/declines → seam falls back to agentfield JSON Schema (no crash).
- **codex provider unchanged** — it uses the native `--output-schema` schema-file path
  ([codex_harness_patch.py:150-171](swe_af/runtime/codex_harness_patch.py#L150)); 6b is
  the **claude/opencode** prompt-suffix path only.
- flag off (`enable_baml_output_format=False`) → agentfield JSON Schema, byte-identical
  to today.

**Property**: `len(baml_output_format(M)) < len(json.dumps(M.model_json_schema()))` for
every mappable M, and the render makes **no** network/LLM call.

**Files touched**: `swe_af/baml_bridge.py` (add `baml_output_format` — render via
`b.request`, marker-split the request body's
`messages[0]["content"][0]["text"]`), `swe_af/runtime/codex_harness_patch.py` (the
`build_prompt_suffix` override: for claude/opencode prefer `baml_output_format` when
mappable, else delegate to the agentfield base suffix; leave codex's schema-file path
untouched), `swe_af/execution/schemas.py` (`enable_baml_output_format: bool = False` —
**measured opt-in**: broad blast radius across *all* reasoners' happy path, so off until
A/B'd; same `BuildConfig`+`ExecutionConfig`+`to_execution_config_dict` triplication rule
as Behavior 6), `tests/test_baml_output_format.py` (new).

### TDD Cycle
🔴 **Red** — assert `baml_output_format(VerificationResult)` contains `criteria_results`
+ `criterion` and is `< len(json.dumps(VerificationResult.model_json_schema()))`. Fails
(no helper).
🟢 **Green** — implement `baml_output_format` via `b.request.ExtractDynamic(MARKER,
baml_options={"tb": pydantic_to_typebuilder(model)})`, returning the text after `MARKER`
from `req.body.json()["messages"][0]["content"][0]["text"]`.
🔵 **Refactor** — wire the seam in `codex_harness_patch.build_prompt_suffix` behind
`enable_baml_output_format`, mappable-or-fallback; add the unmappable-fallback,
codex-untouched, no-network, and flag-off tests.

### Success Criteria
**Automated:**
- [x] render is smaller than JSON Schema **and** contains all field names (mappable schemas) — **10 passed**
- [x] unmappable / required-`dict` schema → falls back to agentfield injection, no raise
- [x] flag off → agentfield JSON Schema unchanged (byte-identical seam test)
- [x] **no** network/LLM call (monkeypatch `b.ExtractDynamic` to fail; render via `b.request` still works)
**Manual:**
- [DEFERRED-VERIFY] (measured rollout) A/B emission-compliance on a real build before defaulting the flag on — flag defaults OFF; wiring config→`baml_output_format_enabled` contextvar is the rollout step (follow-up: SWE-AF-x2g).

---

## Behavior 7: Planner emits the typed `verification` field

> Touches "proven" prompts (`sprint_planner.py`, `product_manager.py`). Per the
> `clone-prompts-verbatim` constraint, this is **additive** — a new instruction +
> schema field, not a rewrite of existing prompt text.

### Test Specification
**Given**: the sprint planner system/task prompts.
**When**: an instruction is added telling the planner to populate
`verification: [{description, command, kind}]` per issue, reusing the
already-present "MUST map to a command" guidance
([product_manager.py:57-59](swe_af/prompts/product_manager.py#L57)).
**Then**: the rendered prompt contains the instruction, and (integration,
key-gated) a real planner run returns at least one issue with a non-empty
`verification[0].command`.

**Edge Cases**: planner omits it → Behavior 5's manifest fallback covers the rung;
planner emits an invalid command → Behavior 1's validator rejects at parse (loud,
not silent).

**Files touched**: `swe_af/prompts/sprint_planner.py` (additive instruction near the
`testing_strategy` block, lines 50-64 / 278-281 / 401-413),
`tests/test_sprint_planner_prompt.py` (assert instruction present);
optional `tests/test_planner_verification_integration.py` (`integration`, key-gated).

### TDD Cycle
🔴 **Red** — assert the rendered sprint-planner prompt contains the `verification`
instruction string. Fails (not present).
🟢 **Green** — append the additive instruction; do not alter existing lines.
🔵 **Refactor** — ensure the instruction references the existing PM command-pattern
examples (single source of truth, no duplicated examples); run the key-gated
integration test if a key is present.

### Success Criteria
**Automated:**
- [x] Prompt-contains-instruction test green — **2 passed** (system + rendered task)
- [DEFERRED-VERIFY] (key-gated) integration: a real plan includes a populated `verification` — needs a live LLM key (follow-up: SWE-AF-x2g)
**Manual:**
- [x] Instruction reads as additive; diff does not touch existing prompt lines — **14 insertions, 0 deletions**.

---

## Implementation Order (vertical slices)

1. **B0** spike → *visible:* documented verdict on BAML checks-on-dynamic-types.
2. **B0a** bridge `dict`/`Any` hardening → *visible:* `QAResult`/`MergeResult`/`CoderResult` map through BAML instead of crashing (unblocks 6b).
3. **B1** `AcceptanceCheck` + validator → *visible:* a typed, validated, BAML-round-tripping command.
4. **B2** `PlannedIssue.verification` → *visible:* typed checks survive planner→issue serialization.
5. **B3** manifest detector → *visible:* deterministic project-level fallback command.
6. **B4** `run_local_check` → *visible:* a real command runs in a worktree, pass/fail by exit code.
7. **B5** resolution → *visible:* typed-first / manifest-fallback command selection.
8. **B6** the gated rung → *visible:* a failing coder iteration is blocked and re-fed the real failure (the backpressure).
9. **B6b** `output_format` render → *visible:* the planner prompt's output-shape section is ~85% smaller and inline-readable (claude/opencode), behind a measured flag.
10. **B7** planner emits the field → *visible:* real plans carry runnable checks end-to-end.

B1–B6 are testable with hand-authored issue dicts before B7 teaches the planner to
emit the data — so the mechanical path is proven first, the producer last. **B0a**
precedes **B6b** (the render needs dict-bearing schemas to map); **B6b** precedes
**B7** as its emission booster but is not a hard blocker (manifest fallback covers
omissions).

## Risks & Open Items

- **BAML checks-on-dynamic-types** — undocumented; **retired by B0**, non-load-bearing
  (Pydantic validator is the guarantee). *Verdict to be recorded here after B0.*
- **Fallback-first means BAML asserts don't run on the happy path** — by design the
  validity guarantee is Pydantic, which runs on both paths (the agentfield SDK and
  BAML's `deserialize` both end at `model_validate`). Documented, not a risk to the rung.
- **Bare `dict`/`Any` mapping gap (resolved, Behavior 0a)** — `_map_type` raised
  `TypeError` on bare `dict`/`Any`, silently declining `QAResult`/`MergeResult`/
  `CoderResult` to `None`. Spike-resolved: **omit-if-defaulted** by default (skip
  unmappable *defaulted* fields, raise on *required* ones); `JsonValue`-alias-via-
  `add_baml` as the opt-in upgrade for fields whose contents matter. `string`+`json.loads`
  was rejected (BAML emits non-strict JSON into the string).
- **`output_format` render is a broad happy-path change (Behavior 6b)** — replacing
  agentfield's JSON-Schema injection touches *every* reasoner's prompt on claude/opencode.
  Mitigated by `enable_baml_output_format` defaulting **off** (measured opt-in),
  mappable-or-fallback wiring (unmappable schema → agentfield injection), and leaving
  codex's native schema path untouched. ~85% token saving is verified; the
  emission-compliance gain must be A/B'd before defaulting on.
- **Dependency provisioning** — a cold worktree can fail `pytest` with
  `ModuleNotFoundError`; handled as a normal red fed back to the coder, bounded by
  `max_deterministic_check_retries`. If this proves noisy, B5 can prepend a
  manifest-driven install (`uv sync` / `npm ci` / `go mod download`) — noted, not in
  the first slice.
- **Behavior change at default-on** — `enable_deterministic_checks` defaults `True`
  (it is the feature); the flag is the kill-switch. The bounded-then-advisory design
  prevents a misdetected/flaky command from eating the iteration budget or looping.
- **Config triplication** — adding each flag/bound touches `BuildConfig` (684) +
  `ExecutionConfig` (988) + `to_execution_config_dict` (822-848, a hand-written allow-list).
  Failure modes are **asymmetric** under `ExecutionConfig`'s `extra="forbid"`: an orphan dict
  key **raises loudly**; an omitted dict line **silently defaults** (the `BuildConfig` value
  is ignored). Land all three edits together and add the propagation test (Behavior 6).
  Pre-existing pattern, flagged not fixed.
- **Shell execution** — the runner wraps each command as the argv `["bash", "-c", command]`
  (not `shell=True`; there is zero `shell=True` in the repo) so pipelines run while keeping
  `shell=False`. The trust boundary is the container+worktree (same as the agent's existing
  Bash), per the locked safety decision.
- **Hung command / timeout** — the deterministic runner sets its **own**
  `deterministic_check_timeout_seconds` (default 600); on `TimeoutExpired` the check is a
  red (`exit_code=-1`) fed back like any other, bounded by the cap. `ci_gate` has no
  per-subprocess timeout to inherit, so this is load-bearing — without it a hung
  `pytest`/`npm test` in a cold worktree would stall the build indefinitely.
- **`clone-prompts-verbatim`** — B7 is additive; no existing prompt lines change.

## References

- Research: [2026-06-11-06-45-backpressure-in-swe-af-harness.md](thoughts/searchable/shared/research/2026-06-11-06-45-backpressure-in-swe-af-harness.md) (the gap analysis + seams)
- BAML bridge plan: [2026-06-11-04-27-tdd-baml-structured-output-swe-af.md](thoughts/searchable/shared/plans/2026-06-11-04-27-tdd-baml-structured-output-swe-af.md) (the foundation this stacks on)
- BAML bridge (shipped): `swe_af/baml_bridge.py:47-196` (branch), `baml_src/functions.baml`
- BAML render/parse API (verified): `b.parse.ExtractDynamic` (parse-only, no LLM), `b.request.ExtractDynamic` (renders the request incl. `ctx.output_format`, no send); agentfield's current schema injection: `_schema.py:49-50` (`model_json_schema()`), `:69` (`build_prompt_suffix`)
- Spike findings (2026-06-11, run in branch venv): `output_format` ~85% smaller than JSON Schema (AcceptanceCheck 805→125c, RetryAdvice 1019→157c, VerificationResult 1726→251c); `dict`/`Any` resolution — `JsonValue` alias ✅, `string`+`json.loads` ✗ (non-strict JSON), omit-if-defaulted ✅
- BAML docs: dynamic-types, checks-and-asserts, baml-vs-pydantic, types (`any`/`json` unsupported) — boundaryml.com
- Runner template: `swe_af/execution/ci_gate.py:38-50,92-95` + `tests/test_ci_gate.py:43-81`
- Coding-loop seam: `swe_af/execution/coding_loop.py:516-524,543,602,616,659,662,730-735,785-802`
- Schemas: `swe_af/reasoners/schemas.py:78-94` (PlannedIssue; `guidance`@92, `target_repo`@93), `swe_af/execution/schemas.py:414-426` (CoderResult), `:684` (BuildConfig), `:822-848` (to_execution_config_dict), `:988` (ExecutionConfig)
- Planner prompts: `swe_af/prompts/sprint_planner.py:50-64,200-228,278-281,401-413`; `swe_af/prompts/product_manager.py:57-59`
