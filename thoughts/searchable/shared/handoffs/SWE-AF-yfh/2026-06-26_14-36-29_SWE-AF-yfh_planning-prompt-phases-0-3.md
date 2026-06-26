---
date: 2026-06-26T18:36:29Z
researcher: tha-hammer
git_commit: 72e085e
branch: feat/planning-prompt-enhancement
repository: SWE-AF
topic: "Planning-Prompt Enhancement — Phases 0–3 shipped (worktree); Phases 4–5 remaining"
tags: [implementation, prompts, planning, wisdom, evals, tech_lead, sprint_planner, worktree]
status: in_progress
last_updated: 2026-06-26
last_updated_by: tha-hammer
type: implementation_handoff
---

# Handoff: SWE-AF-yfh — Planning-prompt enhancement, Phases 0–3 done

## Where this work lives (READ FIRST)

**All work is on a git worktree, NOT main.** Main is clean (the prior uncommitted
prompt drafts were moved into the worktree by request).
- Worktree: `/home/maceo/Dev/SWE-AF-yfh-prompts`  ·  branch `feat/planning-prompt-enhancement`
- 8 commits on top of main `42a5cc1`. Branch is **local only** (no push — conservative
  profile; upstream push to Agent-Field/SWE-AF previously 403'd).
- Run tests in the worktree: `cd /home/maceo/Dev/SWE-AF-yfh-prompts && UV_LINK_MODE=copy uv sync --extra dev`
  then `AGENTFIELD_SERVER=http://localhost:9999 NODE_ID=swe-planner uv run python -m pytest tests/prompt_evals/`

## Task(s)

Execute the TDD plan `thoughts/searchable/shared/plans/2026-06-26-07-31-SWE-AF-tdd-planning-prompt-enhancement.md`.

- **Phase 0 (SWE-AF-ixn)** — eval net + golden baselines + classification — **DONE, closed.**
- **Phase 1 (SWE-AF-23z)** — `_utils.py` lean helpers — **DONE, closed.**
- **Phase 2 (SWE-AF-292)** — tech_lead REJECT-first — **DONE, closed** (accepted on merits; see Learnings).
- **Phase 3 (SWE-AF-n5k)** — per-file de-bloat — **DONE, closed** (4/5 files; issue_writer verified load-bearing).
- **Phase 4 (SWE-AF-f9m)** — few-shot `<example>` blocks — **NOT STARTED** (next actionable).
- **Phase 5 (SWE-AF-bbh)** — end-to-end verification — **NOT STARTED.**

## Commits (feat/planning-prompt-enhancement)

```
72e085e de-dup sprint_planner SYSTEM vs task/schema (244->212; per-prompt budget)
b3fcf18 lean product_manager role + drop control-flow prose (86->79)
f02fb2d de-bloat architect, swap DDD essay for interface example (98->80)
88eb597 distill architecture_planning_loop tutorial to heuristics (164->40; leak removed)
5170094 correct tech_lead fixture claim — non-regression, not a delta
85d4eb1 tech_lead REJECT-first anti-sycophancy reframing (60->36)
97561c3 prompt-evals: observed-behavior eval net + golden baselines (Phase 0)
1386e3d chore(prompts): carry in-progress planning-prompt drafts as Phase-0 baseline
```

## The eval net (the safety harness — keep it green)

`tests/prompt_evals/` — **17 passed / 0 xfailed** as of `72e085e`.
- `eval_checks.py`: AST-extracts each `SYSTEM_PROMPT` literal (so the check is import-free).
  Prompt-source checks: per-prompt line budget (`line_budget()`, default 120, sprint_planner 215)
  + domain-leakage (`DOMAIN_LEAK_TOKENS`). Golden-output checks: schema validity,
  every-issue-has-a-runnable-command, exactly-one-vertical-slice.
- `tests/fixtures/prompt_evals/baseline/` — two real `PlanResult` goldens (goal_a version-flag,
  goal_b build-metrics) captured live via `swe-planner.plan`, claude/sonnet.
- **All `SYSTEM_PROMPT`s MUST stay plain string literals** — `extract_system_prompt` asserts it.
  Do not make a SYSTEM_PROMPT an f-string / computed value (would break the net + Phase 4 wiring).

## Learnings

- **Baseline trap (resolved):** the plan's diagnosis was written against UNCOMMITTED draft bloat
  on main (`architect.py`, `architecture_planning_loop.py`). Committed HEAD was already lean.
  The drafts were moved into the worktree (commit `1386e3d`) and main restored. Always check
  `git diff HEAD -- <file>` before trusting a line-number-based diagnosis.
- **Anti-sycophancy is not provably removable by prompt framing (Phase 2).** A seeded *blatant*
  flaw is rejected by BOTH the APPROVE-first baseline and the REJECT-first prompt (verified live:
  `exec_20260626_174501_ikasz30r`, baseline `approved=false`). A real sycophancy *delta* only shows
  on borderline architectures and is statistical. tech_lead reframing shipped on design merits
  (leaner, WISDOM-aligned, non-regressive), not a hard delta. `tests/fixtures/prompt_evals/tech_lead/`
  is a non-regression guard, not a delta proof.
- **issue_writer dual contract is LOAD-BEARING — do NOT collapse it.** Verified seam (agent
  `a243991fb2f3416e4`): `IssueWriterOutput` schema carries only `{issue_name,issue_file_path,success}`;
  the harness Write-suffix writes only `.agentfield_output.json`; the `issue-*.md` file is written
  by the agent because `issue_writer.py:237` tells it to. Removing that = no artifact for any
  provider (the codex-class bug). The plan's "schema/Write-suffix owns output" premise is false here.
- **Provider output seam map** (for any future write-plumbing edits): dispatch in
  `swe_af/runtime/codex_harness_patch.py:412-432`. codex → `--output-schema`/`--output-last-message`
  (no Write tool); claude/opencode → AgentField Write-suffix ("use your Write tool to create {path}").
  The reasoner `run_issue_writer` (`swe_af/reasoners/execution_agents.py:492-509`) does NOT write the
  .md post-harness.
- **sprint_planner is legitimately the richest prompt.** After removing genuine SYSTEM↔task↔schema
  duplication it is 212 lines of real guidance; forcing it under 120 would gut substantive content.
  Preserved verbatim: the `d024ba6` real-boundary-test block, the SWE-AF-4of scope-verification block,
  the full Test-Driven Decomposition section + worked TDD example, the verification-field instruction.

## Phase 1 helpers (added, NOT yet wired into prompts)

`swe_af/prompts/_utils.py`: `lean_role(domain, function)`, `xml_block(tag, content)`,
`criterion_command_discipline()`. Tests in `tests/test_prompt_utils.py`. **Phase 3 did NOT wire
prompt bodies to these** (the de-bloat was done inline). Wiring them is optional cleanup; if done,
keep SYSTEM_PROMPTs as plain literals (do not build them via `lean_role()` calls).

## Action Items & Next Steps

1. **Phase 4 (SWE-AF-f9m) — next actionable.** Add 3–5 `<example>` few-shot pairs for the two
   format-critical outputs: architect interface contracts (architect.py already has ONE example
   from Phase 3 — extend) and sprint decomposition (sprint_planner has the lexer TDD example —
   add 2–3 more). Wrap in XML. Keep within per-prompt budgets; eval net must stay green.
2. **Phase 5 (SWE-AF-bbh) — e2e verification.** Re-run the eval net; diff against the Phase-0
   goldens for semantic regression; spot-check one real **codex (gpt-5.5)** build and one **claude**
   build through PM→sprint-planner on the build factory. This is also where a live tech_lead GREEN
   (new prompt in a rebuilt node) would go IF a sycophancy delta is ever pursued (decided not worth it).
3. **Optional:** wire prompts to the Phase-1 `_utils` helpers; lean the issue_writer markdown
   skeleton (Contract A) for quality WITHOUT touching the line-237 write instruction (Contract B).
4. **Separate open question (from the prior handoff #3):** the codex node's
   `HARNESS_MODEL=openrouter/...kimi` overrides the gpt-5.5 planning default for no-`models` builds.
   Decision taken this session: **always pass an explicit `models`/`*_model` config in payloads**
   (used for the golden capture). Node env not neutralized.

## Artifacts

- TDD plan: `thoughts/searchable/shared/plans/2026-06-26-07-31-SWE-AF-tdd-planning-prompt-enhancement.md`
- 0a classification: `thoughts/searchable/shared/reviews/SWE-AF-ixn-0a-prompt-classification.md`
- Eval net: `tests/prompt_evals/{eval_checks.py,test_prompt_evals.py}` + `tests/fixtures/prompt_evals/`
- Edited prompts: `swe_af/prompts/{architecture_planning_loop,architect,product_manager,sprint_planner,tech_lead,_utils}.py`
- issue_writer (verified, unchanged): `swe_af/prompts/issue_writer.py`
- Scratch repos used for live runs (outside the repo): `/home/maceo/Dev/_prompt-eval-scratch`,
  `/home/maceo/Dev/_tech-lead-eval`.

## Other Notes

- Beads (local-only): epic **SWE-AF-yfh** open; **ixn, 23z, 292, n5k** CLOSED; **f9m, bbh** open.
- Build factory: control-plane `ddd-build-control-plane-1` :8080; nodes `ddd-build-swe-agent-1`
  (claude `swe-planner`, Max-plan OAuth) + `ddd-build-swe-agent-codex-1`. Capture goldens via
  `POST /api/v1/execute/async/swe-planner.plan`; monitor `GET /api/v1/executions/<exec_id>`
  (NO list endpoint — single id only). A full plan run is ~20–30 min (DDD loop is the slow part).
- Resumable subagents: prompt-classification `aa428ad966244bdb7`, pipeline-map `ad803c3ee2bd0f1e2`,
  issue_writer-seam `a243991fb2f3416e4`.
