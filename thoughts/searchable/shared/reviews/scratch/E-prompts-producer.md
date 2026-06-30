# E — Prompts & Producer Verification

Worktree: `/home/maceo/Dev/SWE-AF-baml` — branch `feat/baml-structured-output` @ `6517b17`. Read-only.

---

## Claim 1 — PM prompt mandates "Every criterion MUST map to a command"
**Verdict: ACCURATE.** `swe_af/prompts/product_manager.py:57-59` (under `## Execution Model Awareness`):

```
- **Machine-verifiable acceptance criteria**: Every criterion MUST map to a
  command. Patterns: `cargo test --test <name>`, `stat -f%z <file> <= N`,
  `hyperfine <cmd> --export-json | jq '.results[0].mean < 0.001'`.
```
(line 60 continues: `Never: "performance is acceptable" or "code is clean."`)

---

## Claim 2 — `testing_strategy` block at sprint_planner.py:50-64
**Verdict: ACCURATE.** Lines 50-54 define the `testing_strategy` output field (inside the `## What You Produce` bullet list):

```
- **testing_strategy**: concrete test plan framed as a Red → Green → Refactor cycle —
  test file paths, framework, behaviors ordered simplest-first, any property tests,
  and which acceptance criteria each test covers. Example: "Create `tests/test_lexer.py`
  using pytest. 🔴 empty input → empty list (AC1) first, then 🔴 single number (AC2),
  🔴 invalid char → error (AC3); 🔵 refactor the dispatch once green. Covers AC1–AC3."
```
Lines 56-64 are the start of `## Your Quality Standards` (Vertical slices, Testing specificity — the latter reinforces concrete test-file-path requirements). So the range spans the `testing_strategy` field def AND the quality standards that govern it.

---

## Claim 3 — sprint_planner.py:200-228
**Verdict: ACCURATE (this is the `## Per-Issue Guidance` section).** Lines 200-228 = the `guidance` object spec. Header `## Per-Issue Guidance` at 200; `### Guidance Fields` at 206; fields enumerated 208-228: `needs_new_tests` (208), `estimated_scope` (210), `touches_interfaces` (213), `needs_deeper_qa` (215), `testing_guidance` (220), `review_focus` (224), `risk_rationale` (227). Line 228 closes the SYSTEM_PROMPT triple-quote (`risk_rationale ... \"""`).

---

## Claim 4 — sprint_planner.py:278-281
**Verdict: ACCURATE.** This is inside the FIRST task-prompt builder `sprint_planner_prompts()` (the `task` f-string). Lines 278-281:

```
For each issue, include a `testing_strategy` that specifies: (1) exact test
file paths to create, (2) the test framework, (3) categories of tests (unit,
functional, edge case), and (4) which PRD acceptance criteria the tests map to.
```
NOTE: this is the legacy `testing_strategy` task instruction (categories-of-tests framing, not Red/Green/Refactor). There are TWO task-prompt builders in this file (see claim 5).

---

## Claim 5 — sprint_planner.py:401-413
**Verdict: ACCURATE.** This is inside the SECOND task-prompt builder `sprint_planner_task_prompt()` (the section-list `.append(...)`). Lines 401-412 = the `## Decompose Test-First (TDD)` section appended to `sections`:

```
"## Decompose Test-First (TDD)\n"
"The coder agent works Red → Green → Refactor, so shape every issue for that cycle:\n"
"- Slice each issue into the smallest *observable behaviors*, not functions.\n"
"- Write each acceptance criterion in Given / When / Then form, so it becomes the\n"
"  coder's first failing test (verifiable inside a single worktree).\n"
"- Make each `testing_strategy` spell out the cycle: 🔴 the failing test to write\n"
"  first (and which AC it pins) → 🟢 minimal code to pass → 🔵 refactor while green,\n"
"  with behaviors ordered simplest-first (empty → single → many → edges → errors).\n"
"- Where an issue's input has an invariant (round-trip, idempotence, ordering),\n"
"  call for a property-based test alongside the example tests."
```
Line 413 = closing `)`. **Important structural finding:** `sprint_planner_task_prompt()` (the multi-repo aware builder, lines 311-414) is a DIFFERENT function from `sprint_planner_prompts()` (lines 232-308). The pipeline calls BOTH `sprint_planner_prompts` (for system) and `sprint_planner_task_prompt` (for task) — see Claim 7. The TDD-framed instruction lives in `sprint_planner_task_prompt`; the legacy categories-framing lives in `sprint_planner_prompts`'s unused `task` return (its task is discarded by the caller).

---

## Claim 6 — Manifest detection is prompt-text-only; NO real detector code
**Verdict: ACCURATE.** Manifest/language detection appears ONLY as natural-language prompt instructions:

- `swe_af/prompts/git_init.py:46-47` (under `## Repository Hygiene`):
  ```
  Detect the language from existing files (package.json → Node.js, pyproject.toml
  → Python, Cargo.toml → Rust, go.mod → Go, etc.) and include the standard
  ```
- `swe_af/prompts/environment_scout.py:33-36` (under `## Your responsibilities`, item 2):
  ```
  Look at config files (`railway.toml`, `fly.toml`, `vercel.json`,
  `sentry.properties`, `supabase/config.toml`, etc.), dependency manifests
  (`package.json`, `pyproject.toml`, `requirements*.txt`, `go.mod`,
  `Cargo.toml`), CI workflows ...
  ```

No real detector exists:
- `grep -rn "detect_project_commands|detect_project|detect_commands|detect_manifest" --include=*.py .` → **0 hits**.
- `grep -rn '"pyproject.toml"|"go.mod"|"Cargo.toml"|"package.json"' --include=*.py swe_af/` excluding `swe_af/prompts/` → **0 hits**.

The agent is TOLD to detect manifests via its file-reading tools; there is no Python function that reads a manifest and derives commands.

---

## Claim 7 — PRODUCER GAP (critical): where PlannedIssue is constructed
**Verdict: NO producer-side wiring gap. Schema + prompt is SUFFICIENT.**

**Construction site:** There is NO hand-written `PlannedIssue(...)` call anywhere in source. The only match for `PlannedIssue(` is the class definition `swe_af/reasoners/schemas.py:78`. `PlannedIssue` objects are produced exclusively by **auto-deserialization** of LLM output.

Trace (`swe_af/reasoners/pipeline.py`, sprint-planner step ~line 488-549):
```python
class SprintPlanOutput(BaseModel):          # pipeline.py:495
    issues: list[PlannedIssue]              # pipeline.py:496
    rationale: str
...
result = await router.harness(
    prompt=task_prompt,
    schema=SprintPlanOutput,               # pipeline.py:532
    ...
)
...
return {"issues": [issue.model_dump() for issue in result.parsed.issues], ...}  # pipeline.py:547
```
`result.parsed` is a `SprintPlanOutput` whose `.issues` is `list[PlannedIssue]` — populated entirely by the harness's schema-driven parser. `acceptance_criteria` (line 84) and `testing_strategy` (line 90) are ordinary pydantic fields populated by that parse; no manual mapping touches them.

**Parser is fully reflective over `schema.model_fields`** (`swe_af/baml_bridge.py`):
- `pydantic_to_typebuilder(model)` walks `model.model_fields` to build the BAML `@@dynamic` TypeBuilder (`_field_type`/`_map_type`), then
- `deserialize()` calls `model.model_validate(_strip_none(payload))` (line 164).

**Wiring confirmed** (`swe_af/runtime/codex_harness_patch.py:296-330`): fallback-first dual-patch seam. The SDK's native 3-strategy `try_parse_from_text(text, schema)` runs first; on `None`, `baml_parse_or_none(text, schema)` runs the BAML SAP. Patched onto BOTH `_runner.try_parse_from_text` (load-bearing — `_runner.py:141,355,466` bind it) and `_schema.try_parse_from_text`. Both paths reflect over the schema; neither has per-field code.

**Conclusion:** Adding `verification: list[AcceptanceCheck]` to `PlannedIssue` + a prompt instruction telling the planner to emit it is SUFFICIENT for the field to populate end-to-end. Both the SDK native parser and the BAML SAP read field names/types off the pydantic model reflectively. The ONE thing also needed: `AcceptanceCheck` must be a BAML-mappable type (the bridge's `_map_type` supports `str`/`int`/`bool`/`list`/`Optional`/nested `BaseModel`; an untyped `dict`/`Any` field is unmappable and would force the SDK-native path only — keep `AcceptanceCheck` a typed nested `BaseModel`). The downstream `result.parsed.issues` → `model_dump()` (pipeline.py:547) carries any new field automatically.
