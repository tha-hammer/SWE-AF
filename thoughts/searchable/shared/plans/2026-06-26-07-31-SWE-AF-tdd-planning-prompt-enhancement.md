---
date: 2026-06-26T11:31:21Z
researcher: tha-hammer
git_commit: 0df8b00
branch: main
repository: SWE-AF
topic: "Planning-Prompt Language & Construction Enhancement"
tags: [tdd, plan, prompts, planning, wisdom, anthropic, evals]
status: proposed
last_updated: 2026-06-26
last_updated_by: tha-hammer
type: tdd_implementation_plan
---

# TDD Plan: Enhance SWE-AF Planning-Prompt Language & Construction

## Goal

Bring the six planning-stage prompts in `swe_af/prompts/` into line with the Anthropic/WISDOM
prompting guidance, **without behavioral regression**, by (1) building an observed-behavior eval
net first, then (2) restructuring the prompts behind that net. Better prompts compound with the
gpt-5.5 planning model just wired in (`_RUNTIME_BASE_MODELS["codex"].planning_loop_model`).

Planning prompts in scope (pipeline order; see `swe_af/app.py:1706` `plan()`):
- `swe_af/prompts/product_manager.py` (`SYSTEM_PROMPT:9`, `pm_task_prompt:155`) → `run_product_manager` (`pipeline.py:159`)
- `swe_af/prompts/architect.py` (`SYSTEM_PROMPT:9`, `architect_task_prompt:137`)
- `swe_af/prompts/tech_lead.py` (`SYSTEM_PROMPT:8`, `tech_lead_task_prompt:125`)
- `swe_af/prompts/architecture_planning_loop.py` (`SYSTEM_PROMPT:16`, `architecture_planning_loop_task_prompt:46`) → `run_architecture_planning_loop` (`pipeline.py:717`)
- `swe_af/prompts/sprint_planner.py` (`SYSTEM_PROMPT:9`, `sprint_planner_task_prompt:337`)
- `swe_af/prompts/issue_writer.py` (`SYSTEM_PROMPT:8`, `issue_writer_task_prompt:110`)
- Shared scaffolding: `swe_af/prompts/_utils.py` (`workspace_context_block:8`)

## Source material (the "WISDOM")

- WISDOM corpus (originals): `~/.claude/SAI/USER/WISDOM/ai-that-works-2026/` (16 episodes + `INDEX.md`) —
  load-bearing: *12-factor coding agents*, *agentic backpressure*, *no-vibes*, *agent-skills*.
- Anthropic curated notes (2026-06-07): `~/Dev/A1_workspace-blueprint/writing-room/research/anthropic-prompt-engineering-evolution_2026-06-07.md` + `…-what-actually-works_2026-06-07.md`.
- Repo research (distilled guidance ↔ current prompts):
  `thoughts/searchable/shared/research/2026-06-11-05-51-swe-af-prompts-and-prompting-wisdom.md`,
  `…-06-11-06-35-coding-specific-prompting-for-swe-af-agents.md`,
  `…-06-17-07-54-agent-prompt-seams-implementer-generalization.md`.

## The target standard (acceptance shape for every planning prompt)

1. One-line role (domain+function), no seniority persona.
2. Instructions = judgment/heuristics only — no harness control flow, no schema restatement.
3. Injected runtime data in XML tags (`<prd>`, `<architecture>`, `<prior_responses>`); task query last.
4. Positive instructions + a one-line "why" instead of prohibition lists.
5. 3–5 `<example>` few-shots for format-critical outputs.
6. No output plumbing in the prompt — delegate to the harness suffix / native `--output-schema`.
7. Review/critique prompts framed to find what breaks (REJECT-first); exploration prompts "give options."

## Diagnosis (ranked, from the two-agent audit)

| # | Principle violated | Concrete gap |
|---|---|---|
| 1 | Role = one line | 40–80-line hero personas in every SYSTEM_PROMPT (cross-cutting) |
| 2 | Sycophancy / first-token | `tech_lead.py:58-68` frames APPROVE-first on a rejection gate |
| 3 | Control flow → harness | `product_manager.py:88-95` bakes ask_user iteration into prose |
| 4 | Attention budget | `sprint_planner.py` ~245-line SYSTEM restated 2-3× in task; `architecture_planning_loop.py:21-156` 135-line tutorial w/ typos, emoji, cosmic-HR leakage (`140-149`) |
| 5 | Output contract → harness | hand-rolled write plumbing everywhere; `issue_writer.py` dual contract (`26-84` + `233-242`) |
| 6 | Say-what-to-do + examples | negative-instruction-heavy; 0 few-shot `<example>` pairs; 0 XML structure |

Governing constraint (WISDOM Part C): **`clone-prompts-verbatim`** — proven prompts must not be
paraphrased. Classification gates all edits.

---

## Phases (TDD: build the eval net first, then change prompts behind it)

### Phase 0 — Classify + baseline + eval net  (GATE — must precede any prompt edit)

**0a. Classify each of the 6 prompts** as `locked` (battle-tested, e.g. validated by cosmic-HR
builds — check git log + `thoughts/.../handoffs/`) vs `open`. Record in the plan/issue. Do not edit
`locked` text without explicit sign-off.

**0b. Golden baseline (RED reference).** For 2–3 fixed goals (one tiny like the codex smoke, one
realistic bounded-context), capture current PRD / Architecture / ArchitecturePlanningArtifacts /
sprint issues as golden JSON under `tests/fixtures/prompt_evals/baseline/`. These are the
"observed behavior" references (prompts are not cheaply unit-testable).

**0c. Eval harness (the test net).** Deterministic checks runnable in CI against any prompt output:
- schema validity (each artifact validates against its Pydantic model);
- **every acceptance criterion maps to a runnable command** (PM + sprint);
- exactly-one vertical-slice issue when DDD artifacts drove the sprint (`app.py:1851` guard mirror);
- **no target-project leakage** (no cosmic-HR / domain-specific tokens in general prompts);
- token-budget assertions (SYSTEM_PROMPT line counts under target ceilings).

- **Test (Given/When/Then):** Given the eval harness, When run against the *current* prompts'
  golden outputs, Then schema+criteria+slice checks pass and the leakage/budget checks **fail**
  for the known offenders (planning-loop leakage, sprint over-length) — proving the net detects
  what later phases fix.
- **Files:** `tests/prompt_evals/` (harness + fixtures). No `swe_af/` changes.

### Phase 1 — Shared scaffolding in `_utils.py`  (removes bloat across all 6 at once)

- `lean_role(domain, function)` — one-line role template.
- factor the duplicated "every criterion MUST map to a command" idiom (PM `57-59`, sprint `58-59`/`312-313`).
- `xml_block(tag, content)` for injected runtime data.
- Remove hand-rolled write-plumbing; centralize any needed output hint behind the existing
  harness-suffix seam. **Verify per provider** (claude Write-suffix, codex `--output-schema`,
  opencode) before deleting in-prompt write instructions.

- **Test:** unit tests for the helpers (`tests/test_prompt_utils.py`); the eval net still green on
  unchanged prompt bodies (helpers added, not yet wired).

### Phase 2 — tech_lead REJECT-first reframing  (highest behavior-change / lowest LOC)

- Reorder decision framing (`tech_lead.py:58-68`) to lead with REJECT/criticality; collapse the
  five-check list duplicated across SYSTEM (`36-66`) and task (`98-121`) into one; lean role.
- **Test (behavioral):** seed a flawed architecture fixture (e.g. missing error path / wrong
  boundary); eval asserts tech_lead **rejects** it. Baseline (APPROVE-first) rubber-stamps it →
  this is the RED→GREEN proof.

### Phase 3 — Per-file de-bloat / restructure  (each behind the eval net)

- `product_manager.py`: cut ask-user iteration (`88-95`) + "How Your PRD Will Be Used" (`131-138`); lean role.
- `architect.py`: delete Modularity/DDD essay (`57-90`), add one concrete interface-contract example; fix typos (`26-30`).
- `architecture_planning_loop.py`: replace 135-line tutorial (`21-156`) with ~15-line heuristic checklist; strip emoji/smart-quotes/typos; remove cosmic-HR examples (`140-149`).
- `sprint_planner.py`: de-dup SYSTEM vs task builder; keep the strong TDD example (`130-154`).
- `issue_writer.py`: resolve dual output contract — one contract only; drop the 60-line `.md` skeleton (`26-84`) if the schema/Write-suffix owns it.

- **Test:** after each file, eval net green (schema/criteria/slice), leakage+budget checks now
  pass for that file, golden-diff reviewed for no semantic regression.

### Phase 4 — Few-shot `<example>` blocks

- Add 3–5 `<example>` pairs for the two format-critical outputs: architect interface contracts,
  sprint decomposition. Wrap in XML.
- **Test:** eval net green; format-conformance check on example-shaped outputs.

### Phase 5 — End-to-end verification

- Re-run eval net + diff against Phase-0 golden baseline.
- Spot-check one real **codex (gpt-5.5)** build and one **claude** build through PM→sprint-planner
  on the build factory; confirm no schema/behavioral regression and the artifacts still flow into
  Sprint Planner / Issue Writer.

## Risks / guardrails

- **Locked prompts** — Phase 0 classification is non-negotiable (paraphrasing a proven prompt is
  the documented failure mode).
- **Output-contract removal** — confirm the harness suffix covers each provider before deleting
  in-prompt write instructions, or a provider silently produces no artifact (the exact class of bug
  fixed in the codex structured-output work, `swe_af/runtime/codex_harness_patch.py`).
- **Behavioral drift** — no edit lands without passing the observed-behavior eval net.

## Measurable outcomes

- Planning-prompt token volume materially down (sprint_planner ~245 → target; planning-loop
  tutorial 135 → ~15 lines).
- tech_lead rejects a seeded-flaw architecture it currently rubber-stamps.
- 100% acceptance-criteria→command coverage; zero target-project leakage; single output contract per prompt.

## Beads

Epic **SWE-AF-yfh**, dependency-chained per phase:
- Phase 0 — **SWE-AF-ixn** (classify + golden baseline + eval net) — GATE
- Phase 1 — **SWE-AF-23z** (shared `_utils.py` scaffolding) — blocked by ixn
- Phase 2 — **SWE-AF-292** (tech_lead REJECT-first) — blocked by ixn
- Phase 3 — **SWE-AF-n5k** (per-file de-bloat) — blocked by 23z + 292
- Phase 4 — **SWE-AF-f9m** (few-shot examples) — blocked by n5k
- Phase 5 — **SWE-AF-bbh** (e2e verification) — blocked by f9m
