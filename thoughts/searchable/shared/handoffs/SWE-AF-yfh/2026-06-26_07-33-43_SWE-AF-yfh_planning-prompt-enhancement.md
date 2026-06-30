---
date: 2026-06-26T11:33:43Z
researcher: tha-hammer
git_commit: 0df8b00
branch: main
repository: SWE-AF
topic: "Planning-Prompt Language & Construction Enhancement — Implementation Strategy"
tags: [implementation, strategy, prompts, planning, wisdom, anthropic, evals, codex, model-config]
status: complete
last_updated: 2026-06-26
last_updated_by: tha-hammer
type: implementation_strategy
---

# Handoff: SWE-AF-yfh — Planning-prompt enhancement (planned) + codex build fixes (shipped)

## Task(s)

1. **Planning-prompt language & construction enhancement** — STATUS: **planned, not started.**
   A TDD plan + beads epic were created to bring the six `swe_af/prompts/` planning-stage prompts
   into line with Anthropic/WISDOM prompting guidance, behind an observed-behavior eval net.
   No prompt code changed yet. Next actionable work = Phase 0 (**SWE-AF-ixn**).
   - Plan: `thoughts/searchable/shared/plans/2026-06-26-07-31-SWE-AF-tdd-planning-prompt-enhancement.md`

2. **Codex build pipeline fixes** — STATUS: **shipped + pushed + verified.** (Context that led here.)
   - Codex structured-output bug (SWE-AF, was the PM "failed to produce a valid PRD") — fixed, `af34660`.
   - Codex planning loop ran `model=sonnet` under codex (SWE-AF-32k) — fixed/closed (`8664d70` by a codex agent), then planning_loop defaulted to `gpt-5.5` (`e2c4ac4`, mine).

## Critical References

- **TDD plan (the deliverable to execute):** `thoughts/searchable/shared/plans/2026-06-26-07-31-SWE-AF-tdd-planning-prompt-enhancement.md`
- **Prompting guidance (WISDOM):** repo research docs `thoughts/searchable/shared/research/2026-06-11-05-51-swe-af-prompts-and-prompting-wisdom.md` (Part A principles, Part B current state), `…-06-11-06-35-coding-specific-prompting-for-swe-af-agents.md`, `…-06-17-07-54-agent-prompt-seams-implementer-generalization.md`. Originals: `~/.claude/SAI/USER/WISDOM/ai-that-works-2026/`.
- **Build factory ops:** `docs/BUILD_RUNBOOK.md` (codex gotchas section updated this session).

## Recent changes

Shipped to `main` (pushed to origin tha-hammer/SWE-AF):
- `swe_af/runtime/codex_harness_patch.py` — `_codex_strict_json_schema` coerces typeless union arms to `{"type":"string"}` (OpenAI strict structured-output fix); default sandbox branch → `--dangerously-bypass-approvals-and-sandbox`. Commit `af34660`.
- `swe_af/execution/schemas.py:528-533` — `_RUNTIME_BASE_MODELS["codex"]` now overrides `planning_loop_model` → `"gpt-5.5"` (others stay `gpt-5.3-codex`). Commit `e2c4ac4`.
- `swe_af/app.py:827` (planning_loop_model passthrough) + `ROLE_TO_MODEL_FIELD` `planning_loop` entry — committed in `8664d70` (codex agent).
- Tests updated: `tests/test_model_config.py`, `tests/test_planner_pipeline.py`, `tests/fast/test_app.py`.
- `docs/BUILD_RUNBOOK.md` — corrected codex root-cause gotchas (monkeypatch path, `Any`-field schema, sandbox, config.toml ownership).

Created this session (uncommitted, in `thoughts/` + beads):
- The TDD plan file (above).
- Beads epic + 6 phase issues (see Other Notes).

NOTE: a prior `agentfield` misdiagnosis was reverted clean (the active codex path is SWE-AF's
monkeypatch `codex_harness_patch.py`, NOT `agentfield/harness/providers/codex.py`).

## Learnings

- **The codex structured-output path is `swe_af/runtime/codex_harness_patch.py`** (monkeypatches `CodexProvider.execute` with a native `codex exec --output-schema --output-last-message`, prompt via stdin). Editing agentfield's provider has NO effect on builds. `inspect.getsource` shows the unpatched file unless the app's `apply_codex_harness_patch()` ran.
- **Model resolution:** `resolve_runtime_models` (schemas.py) precedence = base < env(`SWE_DEFAULT_MODEL`→`AI_MODEL`→`HARNESS_MODEL`) < `models["default"]` < `models["<role>"]`. **The codex node carries `HARNESS_MODEL=openrouter/moonshotai/kimi-k2.6`** (from shared `.env`), which overrides the gpt-5.5 base default for codex builds that pass NO `models` config — so the gpt-5.5 planning default only surfaces when env is unset OR the payload sets `models`. Flagged to user; not yet neutralized.
- **Prompt audit (two parallel agents) findings** are baked into the plan's Diagnosis table. Highest-leverage single edit = `tech_lead.py:58-68` REJECT-first reframing (first-token sycophancy on a review gate). Biggest bloat = `sprint_planner.py` (~245-line SYSTEM, restated 2-3×) and `architecture_planning_loop.py:21-156` (135-line tutorial w/ typos, emoji, cosmic-HR leakage).
- **Governing constraint:** WISDOM `clone-prompts-verbatim` — proven prompts must NOT be paraphrased. Phase 0 must classify locked-vs-open before any edit.
- **Output-contract caution:** removing in-prompt "write the file" plumbing requires verifying the harness suffix covers each provider (claude Write-suffix / codex `--output-schema` / opencode) first — same class of bug as the codex fix.

## Artifacts

- `thoughts/searchable/shared/plans/2026-06-26-07-31-SWE-AF-tdd-planning-prompt-enhancement.md` (the plan — read first)
- `thoughts/searchable/shared/research/2026-06-11-05-51-swe-af-prompts-and-prompting-wisdom.md`
- `thoughts/searchable/shared/research/2026-06-11-06-35-coding-specific-prompting-for-swe-af-agents.md`
- `thoughts/searchable/shared/research/2026-06-17-07-54-agent-prompt-seams-implementer-generalization.md`
- Planning prompts to edit: `swe_af/prompts/{product_manager,architect,tech_lead,architecture_planning_loop,sprint_planner,issue_writer}.py`, shared `swe_af/prompts/_utils.py`
- `docs/BUILD_RUNBOOK.md`

## Action Items & Next Steps

1. **Start Phase 0 (SWE-AF-ixn) — it is the only unblocked PP issue.** `bd update SWE-AF-ixn --claim`.
   - (0a) Classify each of the 6 prompts locked-vs-open (git log + `thoughts/.../handoffs/`).
   - (0b) Capture golden PRD/Architecture/PlanningArtifacts/sprint outputs for 2-3 fixed goals → `tests/fixtures/prompt_evals/baseline/`.
   - (0c) Build `tests/prompt_evals/`: schema validity, criteria→command coverage, exactly-one-vertical-slice, no-target-project-leakage, SYSTEM_PROMPT line-budget. RED proof: net must FAIL on planning-loop leakage + sprint over-length.
2. Then Phase 1 (SWE-AF-23z, `_utils.py` helpers) and Phase 2 (SWE-AF-292, tech_lead REJECT-first) — both unblock after Phase 0.
3. **Decide the `HARNESS_MODEL` question** (separate from the prompt work): neutralize `HARNESS_MODEL` on the codex node so the gpt-5.5 planning default applies to no-`models` builds, OR always pass `models` in codex payloads. User was asked; awaiting decision.

## Other Notes

- **Beads (local-only; no Dolt remote configured):**
  - Epic **SWE-AF-yfh** — Planning-prompt enhancement.
  - **SWE-AF-ixn** Phase 0 (GATE, READY/unblocked) → **SWE-AF-23z** Phase 1, **SWE-AF-292** Phase 2 → **SWE-AF-n5k** Phase 3 → **SWE-AF-f9m** Phase 4 → **SWE-AF-bbh** Phase 5.
  - SWE-AF-32k (codex planning loop sonnet) — CLOSED.
  - SWE-AF-x04 — unrelated in-progress build (not this work).
- **Build factory state:** control-plane `ddd-build-control-plane-1` :8080; codex node `ddd-build-swe-agent-codex-1` (image `swe-af-ddd:codex`, rebuilt from main with the gpt-5.5 planning default + seccomp:unconfined + dedicated `~/.codex-build` home). `main` is in sync with origin.
- **Pipeline orchestration:** `swe_af/app.py:1706` `plan()` runs PM→architect→tech_lead(review loop)→planning_loop(3.5)→sprint_planner→issue_writer; reasoners in `swe_af/reasoners/pipeline.py`.
- Two prompt-audit subagents are resumable: `af27664bac2b5e695` (wisdom synthesis), `a680f8b77f0f49b8e` (prompt audit).
