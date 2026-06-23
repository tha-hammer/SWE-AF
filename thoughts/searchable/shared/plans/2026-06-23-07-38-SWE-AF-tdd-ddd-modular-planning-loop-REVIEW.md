---
date: 2026-06-23
reviewer: Claude (review_plan)
plan: thoughts/searchable/shared/plans/2026-06-23-07-38-SWE-AF-tdd-ddd-modular-planning-loop.md
plan_commit: 8f262273
repository: SWE-AF
beads_issue: SWE-AF-cl2
status: needs-minor-revision
---

# Plan Review Report: DDD Modular Planning Loop

Pre-implementation architectural review. All referenced files/line numbers were
verified against the codebase at `main` (HEAD `fbe8406`). The plan is well
structured, TDD-first, and genuinely backward-compatible. Three items must be
resolved before implementation; the rest are precision improvements.

## Review Summary

| Category | Status | Issues |
|----------|--------|--------|
| Contracts | ⚠️ | 2 (validator failure semantics; non-deterministic checks) |
| Interfaces | ✅ | signatures/insertion point all verified |
| Promises | ⚠️ | 1 (retry-exhaustion raise vs force-approve) |
| Data Models | ⚠️ | 2 (field-name drift across 17 schemas; PlanningEvent undefined) |
| Integration / app.call | ✅ | NODE_ID, target strings, handoff verified |
| Test Plan | ❌ | existing planner tests will break and aren't covered |
| Branch target | ❌ | plan based on `main`, not the canonical BAML line |

**Verified correct (no action):** `plan()` @ `app.py:1547` (`@app.reasoner()`, has
`_original_func`, returns `.model_dump()` dict @ 1740); insertion point between
`app.py:1655` and the sprint call @ `1659`; variable names `prd`/`arch`/`review`
match; `NODE_ID` defaults to `"swe-planner"` so the test target strings are right;
`run_sprint_planner` called via `f"{NODE_ID}.run_sprint_planner"`; reasoner pattern
(`@router.reasoner()` + `router.harness(prompt, schema=…)` → `model_dump()` dict);
`sprint_planner_task_prompt` is keyword-only and already takes goal/prd/architecture;
`_init_dag_state(plan_result: dict)` uses `.get()` everywhere; **no planner or
DAGState schema uses `extra="forbid"`**, so additive optional fields are safe;
`PlanResult` constructor signature in the Behavior 1 test is exactly right; no
name collisions for the 17 new schemas.

---

## Critical Issues (Must Address Before Implementation)

### ❌ C1 — Branch target: the plan is based on `main`, not the canonical line
- The plan's base commit `8f262273` is on `main` and is **NOT** an ancestor of
  `feat/baml-structured-output` (verified). As of 2026-06-18 the canonical SWE-AF
  line is `feat/baml-structured-output` (see memory / SWE-AF-gnm consolidation);
  its `app.py`, `schemas.py`, and `pipeline.py` differ structurally from `main`.
- **Impact:** This plan rewrites exactly the files that diverge most (`app.py`
  plan loop, `reasoners/schemas.py`, `reasoners/pipeline.py`). Implementing on
  `main` reintroduces the divergence we just consolidated away and guarantees a
  non-trivial later merge in the highest-conflict files. The verified line numbers
  (1547/1655/1659) are `main`-state and will not match the BAML branch.
- **Recommendation:** Decide the target branch **before** writing code. If BAML is
  canonical, re-anchor the plan's line numbers against that branch and run the
  research there. If `main` is intentional (e.g., this lands on `main` then both
  merge), say so explicitly and note the merge step.

### ❌ C2 — Existing planner tests WILL break; plan only adds, doesn't update
- Inserting `run_architecture_planning_loop` between Tech Lead and Sprint Planner
  adds one LLM sub-call, shifting every existing `mock_agent_ai.side_effect`
  sequence by one. Verified breakers:
  - `tests/test_planner_pipeline.py`: `test_plan_happy_path` (5→6),
    `test_plan_pm_parsed_none` (5→6), `test_plan_returns_dict_with_levels` (6→7),
    `test_plan_tech_lead_rejects_with_max_iterations_one` (7→8).
  - `tests/test_mock_fixture_cross_feature_integration.py`: asserts
    `call_count == 5` → becomes 6.
- **Impact:** Behavior 4's "add tests beside the existing happy path" leaves the
  existing suite red. TDD Green for Behavior 4 cannot be reached without editing
  these fixtures.
- **Recommendation:** Add an explicit task in Behavior 4 (and the Implementation
  Order) to **update** the listed existing tests' `side_effect` lists and the
  integration `call_count`. Insert the planning-loop mock right after `review`.
  Note env-scout stays off in tests (conditional on `HAX_API_KEY`), so ordering is
  deterministic.

### ❌ C3 — Validator-exhaustion `raise RuntimeError` is inconsistent with the codebase
- The existing Tech Lead review loop does **not** raise when iterations are
  exhausted — it **force-approves and proceeds** (`app.py:1646-1655`,
  `"[auto-approved after max iterations]"`). Behavior 4's `for…else: raise
  RuntimeError(...)` would hard-abort the entire plan when the LLM fails to emit a
  perfectly-structured DDD artifact within N tries.
- **Impact:** A brittle, plan-killing failure mode for a deterministic
  *structural* check, diverging from the established "degrade, don't abort"
  pattern. One malformed artifact section kills an otherwise-complete plan.
- **Recommendation:** Mirror the Tech Lead pattern: after `max_planning_loop_iterations`,
  proceed with the best artifacts, record the residual validator feedback as an
  accepted-with-debt warning / `app.note`, and continue to Sprint Planner. If a
  hard fail is truly intended, justify it explicitly and add a test asserting the
  abort is the desired contract.

---

## Warnings (Should Address)

### ⚠️ W1 — Two validator checks are not deterministically checkable
`validate_planning_artifacts` (Behavior 2) lists "event backbone default transport
is `in_process` **unless a more complex transport is justified**" and "extraction
strategy exists and is **gated on a tested functional slice**." A pure validator
can't judge "justified" or "tested." Make them concrete: e.g. if
`default_transport != "in_process"` require a non-empty `migration_justification`
field; gate extraction on a boolean/enum field (`gated_on: "tested_slice"`) rather
than prose. Otherwise the check is either a no-op or non-reproducible.

### ⚠️ W2 — Canonical test fixture for `ArchitecturePlanningArtifacts` is referenced but undefined
Behaviors 2/5/6 use pytest fixtures (`complete_artifacts`, `artifacts`,
`enriched_issue`, `response`) that aren't defined anywhere in the plan. A fully
populated, valid artifact is needed by ≥4 test files (round-trip, validator,
prompts, retry). Define it **once** as a shared `conftest.py` fixture to prevent
drift; a per-file copy will silently diverge from the schema/validator.

### ⚠️ W3 — Field-name consistency across 17 schemas + validator + prompt + renderer
The validator depends on specific field names (`event_backbone.default_transport`,
per-context `aggregates`/`services`/`domain_events`, read-model `source events`,
guardrail `enforcement mechanism`, domain-event `producer context`, vertical-slice
references). With 17 new Pydantic models, name drift between schema and validator is
the most likely real bug. Behavior 1's round-trip test currently uses `...`
placeholders and locks nothing. **Recommendation:** expand the round-trip test to
assert the exact field names the validator reads, so schema and validator can't
drift apart. Treat the schema as the single source of truth and reference field
names from it in the validator.

### ⚠️ W4 — Two distinct "event" concepts share vocabulary
There are two unrelated event models: (a) `internal_event_schema` *inside*
`planning_artifacts` = the **target project's** designed domain events; (b)
Behavior 8's `planning-events.jsonl` / `PlanningEvent` = **SWE-AF's own** planner
observability stream (`PlanningArtifactsValidated`, etc., from the "Future Bounded
Contexts for the Planner" table). Same words, different domains. Add a one-line
note distinguishing them so implementers don't validate (b) with
`validate_planning_artifacts` or reuse `InternalEventSchemaSpec` for the jsonl log.

### ⚠️ W5 — `PlanningEvent` type is used but not in the schema additions
Behavior 8's `publish_planning_event(*, artifacts_dir, event: PlanningEvent)`
references a `PlanningEvent` model not listed in Behavior 1's schema set. Add it
(fields: `event_name`, `event_version`, `occurred_at`, `source_context`,
`correlation_id`, `payload`), and inject the timestamp (clock param/arg) so the
jsonl observability test is deterministic.

### ⚠️ W6 — Production config threading for the two new `plan()` params
`planning_loop_model` and `max_planning_loop_iterations` are added as `plan()`
arguments with defaults — fine for the direct-call tests. But `BuildConfig` and
`ExecutionConfig` use `extra="forbid"`, and `plan()` is invoked via `app.call`
kwargs in production. If these need real-run tuning, plan the config plumbing
(BuildConfig → … → plan kwargs) explicitly; otherwise note they're intentionally
defaults-only for this slice.

---

## Minor / Nits

- **M1 (vertical slice is prompt-only):** "≥1 issue with `slice_role="vertical-slice"`"
  is enforced only via the Sprint Planner prompt. Consider a deterministic
  post-sprint check (at least one planned issue carries the slice role) so the
  guarantee isn't purely LLM-trust.
- **M2 (extract the loop in Green, not "if it gets too large"):** `plan()` is
  already ~200 lines (1547-1740). Do the `_run_architecture_planning_loop_until_valid`
  extraction as part of Green to keep `plan()` readable, rather than deferring.
- **M3 (validator dict vs model):** `plan()` passes a **dict** (app.call returns
  `model_dump()`), but the validator's tests mutate model attributes
  (`complete_artifacts.bounded_contexts[0].domain_events = []`). Ensure
  `validate_planning_artifacts` handles **both** and add an explicit dict-input
  test, since the dict path is the production path.
- **M4 (docs strings):** `docs/ARCHITECTURE.md` and `README.md` exist; Behavior 9's
  literal-substring asserts are fine — just ensure the exact strings ("DDD Planning
  Loop", "Modular Monolith", "Internal Event Backbone", "CQRS-lite") are added.

---

## Suggested Plan Amendments

```diff
# Pre-flight (before Implementation Order)
+ Resolve C1: confirm target branch (canonical feat/baml-structured-output vs main);
+   re-anchor line numbers if BAML.

# Behavior 2 (Validator)
~ Make "transport justified" concrete: non-empty migration_justification when
+   default_transport != "in_process".
~ Make "extraction gated on tested slice" a checkable field, not prose.
+ Add explicit dict-input test (production path passes a dict).

# Behavior 1 (Schemas)
+ Add PlanningEvent model (used by Behavior 8).
~ Expand round-trip test to assert the exact field names the validator reads
+   (lock schema↔validator contract).

# Behavior 4 (plan orchestration)
~ Replace `for…else: raise RuntimeError` with force-accept + recorded warning,
+   matching the Tech Lead force-approve pattern (or justify the hard fail).
+ UPDATE existing tests' side_effect lists (test_plan_happy_path,
+   test_plan_pm_parsed_none, test_plan_returns_dict_with_levels,
+   test_plan_tech_lead_rejects_with_max_iterations_one) and the
+   call_count==5 assertion in test_mock_fixture_cross_feature_integration.
+ Do the _run_architecture_planning_loop_until_valid extraction in Green.

# Tests (cross-cutting)
+ Add a shared conftest fixture: one fully-populated, valid ArchitecturePlanningArtifacts.
```

## Approval Status

- [ ] Ready for Implementation
- [x] **Needs Minor Revision** — resolve C1 (branch), C2 (update existing tests),
      C3 (raise→force-accept) before coding; fold W1–W6 into the affected
      Behaviors. No fundamental design flaws; the architecture, backward-compat
      strategy, and TDD structure are sound.
- [ ] Needs Major Revision
