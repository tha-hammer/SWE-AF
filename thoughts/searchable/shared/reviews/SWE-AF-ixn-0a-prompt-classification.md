---
date: 2026-06-26
topic: "Phase 0a — locked vs open classification of the 6 planning-stage prompts"
issue: SWE-AF-ixn
epic: SWE-AF-yfh
researcher: claude (opus-4-8)
status: complete
governing_rule: clone-prompts-verbatim (WISDOM Part C) — a prompt validated by successful real builds is LOCKED
---

# Phase 0a: Planning-Prompt locked-vs-open Classification

Goal: classify each of the 6 planning-stage prompt files (and shared `_utils.py`) as
**locked** (battle-tested / proven by real builds — must NOT be paraphrased) vs **open**
(safe to restructure), with evidence, before any Phase 1–5 prompt edits.

## Method

Per file: `git log --follow` (frequency / recency / commit subjects), `git log -p` skim
(text churn vs stable), and grep of `thoughts/.../{handoffs,research,plans,reviews}` for
proven/validated statements. Decision rule = `clone-prompts-verbatim`: text exercised by
successful real cosmic-HR / build-factory runs is LOCKED; known bloat / typos / domain
leakage / unproven brand-new text is OPEN.

## Classification Table

| File | Class | One-line rationale | Strongest single evidence |
|---|---|---|---|
| `product_manager.py` | **mixed (locked core, open bloat)** | Stable since initial commit (5 commits, last text change `8a0ad0e` "prompt hardening" 2026-Q1; `0a4c3b7` only added HITL plumbing). Core requirements/PRD contract is proven by every cosmic-HR build, but the ask-user iteration prose (`88-95`) + "How Your PRD Will Be Used" (`131-138`) are control-flow/plumbing bloat. | research 2026-06-23 §"Product Manager Boundary": PM "owns the requirements contract" and is exercised in `plan()` happy-path test `test_planner_pipeline.py:158`; PM SYSTEM body untouched since `8a0ad0e`. |
| `architect.py` | **mixed (locked core, open bloat)** | 5 commits, body stable since `8a0ad0e`; recent commits (`2d92fa7`) only added `workspace_manifest`. The component/interface-contract core drives every real build, but the Modularity/DDD essay (`57-90`) + typos (`26-30`) are open. | research 2026-06-23 §"Architect Boundary": architecture doc is "single source of truth for downstream agents," validated through `run_architect` in the planner pipeline tests. |
| `tech_lead.py` | **mixed (locked core, open bloat)** | Review-gate role is proven (tech-lead reject→architect-revision loop covered by `test_planner_pipeline.py:218`), but the APPROVE-first decision framing (`58-68`) is a known first-token sycophancy defect flagged by the two-agent audit as the highest-leverage edit. | handoff 2026-06-26 SWE-AF-yfh Learnings: "Highest-leverage single edit = `tech_lead.py:58-68` REJECT-first reframing (first-token sycophancy on a review gate)." |
| `architecture_planning_loop.py` | **OPEN** | Brand-new, single commit `91c6e51` (2026-06-23), authored *for* cosmic-HR. Confirmed in-file: smart-quotes (`21`), typos ("doesn not" `50`, "Systems Nature" `111`), emoji ✅❌ (`73-74`), and hard cosmic-HR domain leakage (Procurement/Contracts/Claims/Decisions `91,120-123`, "Exploded View" example `140-149`). Not validated as a *generic* prompt — its only build run was the cosmic-HR slices it leaks. | Commit `91c6e51` "feat(planner): DDD planning artifacts schema, validator, reasoner (B1-B3)"; file lines 140-149 hardcode cosmic-HR's own bounded contexts as the worked example. |
| `sprint_planner.py` | **mixed (locked core, open bloat)** | Most-churned file (13 commits) — but the recent churn is *additive, proven* hardening: `d024ba6` real-boundary-test rule, `e5ee235`/`e746f26` SWE-AF-4of build-verification scoping, `c1fe8b8` TDD worked example. That worked example (`130-154`) and the additive rules are battle-tested and must stay verbatim; the ~245-line SYSTEM restated 2–3× in the task builder is the open bloat. | Commit `d024ba6` "harden test+mock integrity… same family as the 059 skipIf migration that crashed prod" — directly tied to a real production failure; do NOT paraphrase these blocks. |
| `issue_writer.py` | **mixed (locked core, open bloat)** | 6 commits; body proven by every build (writes the per-issue markdown agents implement). `9bdb3b6` (B5-B6) added the DDD-artifact rendering block which is newer/less-proven. Dual output contract (`26-84` prose + `233-242`) is open redundancy. | research 2026-06-23 §"Issue Writer Boundary": run by `plan()` concurrently for all issues (`app.py:1678`), covered by planner pipeline happy-path test. |
| `_utils.py` (shared) | **locked** | `workspace_context_block` / `planning_artifacts_context_block` are deterministic context renderers, not LLM-judgment prose; covered by `test_multi_repo_prompts.py` + `test_planning_artifact_prompts.py`. Phase 1 *adds* helpers here (lean_role / xml_block) rather than rewriting existing ones. | Plan Phase 1 treats it as scaffolding to extend, not paraphrase; existing functions are signature-tested. |

## Decisiveness summary

- **Fully OPEN (restructure freely):** `architecture_planning_loop.py` — unproven, leaky, typo-ridden; the single clearest win.
- **Mixed (locked core, open bloat) — edit only the bloat, keep proven text verbatim:** `product_manager.py`, `architect.py`, `tech_lead.py`, `sprint_planner.py`, `issue_writer.py`.
- **Locked (extend, don't rewrite):** `_utils.py`.

## Files needing human sign-off before editing

1. **`sprint_planner.py`** — its recent additive blocks (`d024ba6` real-boundary test rule;
   SWE-AF-4of verification-scoping; `c1fe8b8` TDD worked example `130-154`) are explicitly tied
   to a real prod failure ("059 skipIf migration that crashed prod"). The de-dup is safe, but
   touching those specific blocks needs sign-off. **Verbatim-preserve those, de-dup the rest.**
2. **`tech_lead.py`** — the REJECT-first reframing (`58-68`) is a *behavior change* on a proven
   review gate, not pure de-bloat. The plan gates it behind a behavioral eval (Phase 2 RED→GREEN),
   but flag for human confirmation that flipping APPROVE→REJECT framing is desired.
3. **`issue_writer.py`** — the DDD-artifact rendering added in `9bdb3b6` is recent; confirm whether
   it has been exercised by a *successful* build before trimming the dual contract around it.

The other three (`product_manager.py`, `architect.py`, `architecture_planning_loop.py`) and
`_utils.py` are confident calls and do not require sign-off for the scoped edits.
