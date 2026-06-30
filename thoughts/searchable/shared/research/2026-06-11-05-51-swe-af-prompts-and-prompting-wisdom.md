---
date: 2026-06-11T05:51:00-04:00
researcher: maceo
git_commit: ebf00a35e6af11cd085ce4928e589a5b983b2e13
branch: main
repository: SWE-AF
topic: "Current state of swe_af/prompts and the prompting best-practices recorded in WISDOM"
tags: [research, codebase, prompts, prompting, wisdom, system-prompts, agents, anthropic-docs]
status: complete
last_updated: 2026-06-11
last_updated_by: maceo
last_updated_note: "Added Part D — Anthropic's published prompting guidance (local A1_workspace-blueprint notes + live docs/engineering blog)"
---

# Research: `swe_af/prompts` Current State + Prompting Best-Practices in WISDOM

**Date**: 2026-06-11 05:51 -0400
**Researcher**: maceo
**Git Commit**: ebf00a35e6af11cd085ce4928e589a5b983b2e13
**Branch**: main
**Repository**: SWE-AF

## Research Question

Two parts, in service of a future effort to update every prompt under
`/home/maceo/Dev/SWE-AF/swe_af/prompts`:

1. Document the **current prompting best-practices recorded in WISDOM** ("the
   latest updates to prompting").
2. Document the **current state of all prompt modules** in `swe_af/prompts/` —
   structure, techniques in use, sizes, and how each is consumed.

This document maps what exists. It does not prescribe changes; the gap-analysis
and rewrite belong to a follow-on plan (see [Open Questions](#open-questions)).

## Summary

- **Where the "WISDOM" lives:** `~/.claude/SAI/USER/WISDOM/ai-that-works-2026/` —
  16 wisdom-extract files from the *AI That Works* podcast (BoundaryML / BAML;
  hosts Dex Horthy + Vaibhav Gupta), generated 2026-05-08
  (`INDEX.md`). The two episodes most directly about prompting are
  `2026-02-03-prompting-is-becoming-a-product-surface.md` and
  `2026-01-13-applying-12-factor-principles-to-coding-agent-sdks.md`; seven more
  carry prompting-relevant guidance. The recurring thesis: **"the harness has
  eaten the prompt"** — move known logic into code/structured-output joints and
  keep the prompt for what is genuinely uncertain.
- **Current prompt architecture:** `swe_af/prompts/` holds **24 `SYSTEM_PROMPT`
  constants across 23 role modules** (plus `_utils.py` and `__init__.py`). Every
  role module follows one convention: a module-level triple-quoted
  `SYSTEM_PROMPT` constant + one or more task-prompt builder functions. Output
  structure is delegated to the harness `schema=` parameter (now BAML-parsed —
  see [[swe-af-baml-structured-output]]); **no** prompt embeds a JSON schema body.
- **Techniques present (verified):** persona/role framing ("You are a…") in all
  23 role modules; markdown `##` section headers throughout; numbered
  workflow/step lists; dense negative instructions ("DO NOT"/"NEVER"/"ABSOLUTELY
  FORBIDDEN"). **Absent:** XML/structured tags (0 files), explicit
  "think step by step" / `<thinking>` chain-of-thought (0 files), and formal
  few-shot input/output example pairs (0 files; two modules carry a single inline
  bad/good contrast).
- **Prompt sizes:** `SYSTEM_PROMPT` constants range 32–155 lines. Largest:
  `sprint_planner.py` (155), `pr_resolver.py` (136), `ci_fixer.py` (118),
  `issue_advisor.py` (107).
- **Governing constraints (from memory):** a recorded user-feedback memory,
  `clone-prompts-verbatim`, states that proven command prompts must be copied
  **verbatim**, not paraphrased/condensed ("so heavily edited so to be unusable").
  A second work-memory flags a past case of a "new system prompt [that] violates
  the CLI-first architecture."
- **Anthropic's published guidance ([Part D](#part-d--anthropics-published-prompting-guidance)):**
  consolidated from the user's local research notes (`A1_workspace-blueprint`,
  2026-06-07) and live Anthropic docs/engineering blog (verified 2026-06-11). Core
  themes: give a **role, not a personality** ("heavy-handed role prompting is often
  unnecessary"); **say what to do, not what to avoid**; **explain the why**; use
  **3–5 examples in `<example>` tags**; **XML tags** to structure prompts;
  manual chain-of-thought is deprecated in favor of (adaptive) thinking; prefill and
  non-default sampling params now return 400 errors; prompt engineering has been
  renamed **context engineering** ("find the smallest set of high-signal tokens").

---

## Part A — Prompting Best-Practices Recorded in WISDOM

### Where WISDOM lives

`SAI/README.md:52` defines `WISDOM/` as "Domain knowledge frames that compound
over time"; `SAI/USER/README.md:30` scopes it to "Wisdom-extract output from the
ContentAnalysis skill — podcast/video/article extracts." The relevant corpus is
the `ai-that-works-2026/` directory (16 episode extracts + `INDEX.md`).

Files read in full for this research:
- `~/.claude/SAI/USER/WISDOM/ai-that-works-2026/2026-02-03-prompting-is-becoming-a-product-surface.md`
- `~/.claude/SAI/USER/WISDOM/ai-that-works-2026/2026-01-13-applying-12-factor-principles-to-coding-agent-sdks.md`

Files extracted (prompting-relevant content only) via sub-agent:
`2026-01-27-no-vibes-allowed.md`, `2026-02-24-no-vibes-february.md`,
`2026-03-31-no-vibes-march.md`,
`2026-05-05-openai-tells-you-not-to-build-your-own-harness.md`,
`2026-03-10-claude-agent-skills-deep-dive.md`, `2026-02-17-automating-aitw.md`,
`2026-03-17-prompt-injections-guardrails.md`.

### Core principles documented in the WISDOM corpus

#### 1. Don't put control flow in a prompt
From `2026-01-13-applying-12-factor-principles-to-coding-agent-sdks.md`:
- "Don't use prompts for control flow. If you know what the workflow is, use
  control flow for control flow." A known step order written as English
  instructions is "a bash script using English and tokens" (lines 16–22, 122).
- A long planning prompt "was secretly a workflow" — research + design + outline
  + write-out stuffed into one system message; the model skipped phases. Splitting
  it into a multi-phase harness with structured-output joints "literally made the
  model do the thing the prompt asked for, by removing the choice" (lines 51–58).
- **Numeric:** "Frontier thinking models can attend to maybe 150–200 instructions
  before they start losing track" (line 54).

#### 2. The instruction/token budget is an attention budget
- `2026-03-10-claude-agent-skills-deep-dive.md`: every sub-agent/skill/MCP tool
  advertises its name+description "every single context window"; tools-block past
  ~10K tokens gets hidden behind a search tool; "company-shaped personas (backend
  engineer, frontend engineer)" are called an anti-pattern because "the company
  abstraction has nothing to do with how the model allocates attention."
- `2026-05-05-openai-tells-you-not-to-build-your-own-harness.md`: ~50K startup
  tokens before user input (32K tools + 10K system prompt); "1% accuracy
  regression per tool call compounds to ~25% over 50 calls." Tool descriptions are
  "an attention tax."
- `2026-02-24-no-vibes-february.md`: "Prune, prune, prune" — 5–7 excellent skills
  beat 70.

#### 3. Structured output is the joint — and a tripwire, not a wall
- `2026-01-13…`: "Structured outputs are the joints of a workflow"; exit
  conditions live "in code, not the prompt" (lines 42–48).
- `2026-02-03-prompting-is-becoming-a-product-surface.md`: structured output as
  prompt-injection defense — "if the model disobeys… so hard as to ignore the
  output schema… the deterministic parser is just gonna blow up and that actual
  data never reaches your code" (lines 68–75). Pair with prompt-side hardening
  ("only cite from the transcript, do not make up information").
- `2026-03-17-prompt-injections-guardrails.md`: structured output is *shape, not
  safety* — pair it with per-field validation invariants; "a schema with a
  `description` field is still a place for the model to leak the system prompt."
- `2026-05-05…`: "Don't enforce JSON grammar on tool calls that emit code." JSON
  tool calls tax complex/recursive shapes. (This is the lineage of the BAML
  structured-output work — see [[swe-af-baml-structured-output]].)

#### 4. Decompose into single-purpose passes; separate critique from fixing
- `2026-02-17-automating-aitw.md`: multi-pass pipeline (extract → compose →
  critique → fix → validate), each pass doing one thing, beats one big prompt;
  critique and fix are *separate* calls ("the following email sounds like AI slop.
  Tell me why…"); chain-of-thought via a structured `rationale`/`subtitle` field;
  anchor stage-1 with an example; starve later stages of long context.
- `2026-01-27-no-vibes-allowed.md`: order steps so each chunk is independently
  verifiable; size phases around verification points; keep rejected options
  visible so the model doesn't re-suggest killed choices.

#### 5. Examples and patterns beat abstract instruction
- `2026-02-24-no-vibes-february.md`: "Give the model a pattern to replicate, not a
  problem to innovate on"; "the pattern in your repo IS your prompt"; a codebase
  "regresses to the average of the best and worst pattern."
- `2026-02-17-automating-aitw.md`: "an example email as the anchor" in the
  structure-extraction stage.

#### 6. Models are sycophants; framing steers the first token
- `2026-03-31-no-vibes-march.md`: phrase exploration as options, not commands
  ("let's consider X" / "give me a bunch of options," not "do X"); "the first
  token the model emits steers everything after"; review framing is the whole
  signal ("is this good?" → yes; "is this bad?" → finds problems); the model
  "heavily weights the most recent messages plus the system prompt," with the
  middle fuzzy.

#### 7. Evals come from observed behavior, not up front
- `2026-03-17-prompt-injections-guardrails.md`: "Evals will slow you down… in the
  beginning"; hand-write the first ~10 cases from real behavior; asking the model
  to write test cases "generates the dumbest tests that don't model real user
  behavior."

#### 8. Skills vs sub-agents vs commands (instruction packaging)
- `2026-03-10-claude-agent-skills-deep-dive.md`: skills = instruction modules;
  sub-agents = context isolation; slash commands = user entry points; "don't put
  your custom instructions in agents." Skills inject "as a user message" → get
  instruction-following attention rather than data-processing attention.

> Cross-cutting thread named in `INDEX.md:89` and `2026-01-13…` Themes: **"The
> harness has eaten the prompt."** Every recommendation moves logic out of the
> prompt into surrounding code (structured outputs, exit conditions, phase
> routing, background validators). The prompt shrinks "back to its proper job —
> describing what the model should do when there's no code that can."

---

## Part B — Current State of `swe_af/prompts/`

### Module-shape convention (uniform across all 23 role modules)

Each role module defines:
1. A module-level `SYSTEM_PROMPT = """\ … """` constant (the trailing `\`
   suppresses the leading newline). `workspace.py` is the only module with two
   constants: `SETUP_SYSTEM_PROMPT` and `CLEANUP_SYSTEM_PROMPT`
   ([workspace.py:8](swe_af/prompts/workspace.py#L8),
   [workspace.py:56](swe_af/prompts/workspace.py#L56)).
2. One or more task-prompt builder functions, in two naming patterns:

| Builder pattern | Returns | Modules |
|---|---|---|
| `*_prompts(...)` (keyword-only) | `tuple[str, str]` = `(system, task)` | `product_manager.py:99`, `architect.py:78`, `tech_lead.py:72`, `sprint_planner.py:167` |
| `*_task_prompt(...)` | `str` (task only) | all other role modules |

The four `*_prompts()` modules also expose a `*_task_prompt()` wrapper that
prepends `workspace_context_block(...)`. Task builders assemble dynamic content
two ways: a single f-string (`architect`, `tech_lead`, `product_manager`,
`sprint_planner_prompts`) or a `sections: list[str]` accumulator joined at return
(`sprint_planner_task_prompt`, `issue_writer`, `issue_advisor`, `replanner`,
`coder`, and most others).

### Output-structure strategy

No prompt embeds a JSON Schema body. All structured output is delegated to the
harness `schema=` parameter passed in `router.harness(...)`. Some system prompts
**name** their schema in prose and enumerate fields informally:
`IssueAdvisorDecision` ([issue_advisor.py:76](swe_af/prompts/issue_advisor.py#L76)),
`ReplanDecision` ([replanner.py:59](swe_af/prompts/replanner.py#L59)),
`CIFixResult`, `VerificationResult`, `IntegrationTestResult`, `RetryAdvice`.
`issue_writer.py` is the only module embedding a full markdown **output
template** inline in its system prompt
([issue_writer.py:26-84](swe_af/prompts/issue_writer.py#L26-L84)).

### Reasoner → prompt module → schema (consumer map)

Two reasoner files consume the prompts. `pipeline.py` uses deferred (in-function)
imports; `execution_agents.py` uses top-level imports. The universal call shape is
`router.harness(prompt=…, system_prompt=…, schema=…, model=…, tools=[…], cwd=…)`.

| Reasoner (file:line) | Prompt module | Schema |
|---|---|---|
| `run_product_manager` ([pipeline.py:158](swe_af/reasoners/pipeline.py#L158)) | `product_manager.py` | `PRD` |
| `run_environment_scout` ([pipeline.py:240](swe_af/reasoners/pipeline.py#L240)) | `environment_scout.py` | `ScoutResult` |
| `run_architect` ([pipeline.py:357](swe_af/reasoners/pipeline.py#L357)) | `architect.py` | `Architecture` |
| `run_tech_lead` ([pipeline.py:417](swe_af/reasoners/pipeline.py#L417)) | `tech_lead.py` | `ReviewResult` |
| `run_sprint_planner` ([pipeline.py:477](swe_af/reasoners/pipeline.py#L477)) | `sprint_planner.py` | `SprintPlanOutput` |
| `run_retry_advisor` ([execution_agents.py:124](swe_af/reasoners/execution_agents.py#L124)) | `retry_advisor.py` | `RetryAdvice` |
| `run_issue_advisor` ([execution_agents.py:205](swe_af/reasoners/execution_agents.py#L205)) | `issue_advisor.py` | `IssueAdvisorDecision` |
| `run_replanner` ([execution_agents.py:318](swe_af/reasoners/execution_agents.py#L318)) | `replanner.py` | `ReplanDecision` |
| `run_issue_writer` ([execution_agents.py:444](swe_af/reasoners/execution_agents.py#L444)) | `issue_writer.py` | `IssueWriterOutput` |
| `run_verifier` ([execution_agents.py:525](swe_af/reasoners/execution_agents.py#L525)) | `verifier.py` | `VerificationResult` |
| `run_merger` ([execution_agents.py:748](swe_af/reasoners/execution_agents.py#L748)) | `merger.py` | `MergeResult` |
| `run_coder` ([execution_agents.py:963](swe_af/reasoners/execution_agents.py#L963)) | `coder.py` (+ `maybe_apply_coder_guardrail`) | `CoderResult` |
| `run_qa` ([execution_agents.py:1044](swe_af/reasoners/execution_agents.py#L1044)) | `qa.py` | `QAResult` |
| `run_code_reviewer` ([execution_agents.py:1118](swe_af/reasoners/execution_agents.py#L1118)) | `code_reviewer.py` | `CodeReviewResult` |
| `run_qa_synthesizer` ([execution_agents.py:1201](swe_af/reasoners/execution_agents.py#L1201)) | `qa_synthesizer.py` | `QASynthesisResult` (uses `router.ai`, not `harness`) |
| `generate_fix_issues` ([execution_agents.py:1297](swe_af/reasoners/execution_agents.py#L1297)) | `fix_generator.py` | `FixGeneratorOutput` |
| `run_ci_fixer` ([execution_agents.py:1578](swe_af/reasoners/execution_agents.py#L1578)) | `ci_fixer.py` | `CIFixResult` |
| `run_pr_resolver` ([execution_agents.py:1667](swe_af/reasoners/execution_agents.py#L1667)) | `pr_resolver.py` | `PRResolveResult` |

Two modules are referenced indirectly: `git_init.py`, `github_pr.py`,
`integration_tester.py`, `workspace.py`, `repo_finalize.py` are consumed by their
own reasoners/build steps (re-exported through
[__init__.py:20-38](swe_af/prompts/__init__.py#L20-L38) except
`environment_scout`, `github_pr`, `pr_resolver`, `repo_finalize`, which callers
import directly).

### Shared helpers

- **`workspace_context_block(manifest)`** ([_utils.py:8-44](swe_af/prompts/_utils.py#L8-L44)) —
  returns `""` for single-repo/None; otherwise a `## Workspace Repositories`
  block. Imported and prepended by 15 role modules (architect, tech_lead,
  product_manager, sprint_planner, environment_scout, coder, verifier, qa,
  code_reviewer, qa_synthesizer, retry_advisor, issue_advisor, issue_writer,
  integration_tester, workspace). `fix_generator.py` and `replanner.py` do not use
  it.
- **`format_prior_user_responses(...)`** (from `swe_af/hitl/ask_user.py`) — used
  by the four HITL-capable modules: `product_manager.py:112`, `replanner.py:118`,
  `issue_advisor.py:158`, `environment_scout.py:96`.
- **`known_service_summary_for_prompt(...)`** (from `swe_af/hitl/services.py`) —
  used only by `environment_scout.py`.

### In-prompt techniques present (verified against source)

| Technique | Prevalence | Evidence |
|---|---|---|
| Persona / role framing ("You are a…") | All 23 role modules | grep: 23 files; e.g. [coder.py:9](swe_af/prompts/coder.py#L9), [product_manager.py:10](swe_af/prompts/product_manager.py#L10) |
| `##` markdown section headers | Every module | used in both `SYSTEM_PROMPT` and task builders |
| Numbered workflow/step lists | Most modules | e.g. [coder.py:47-58](swe_af/prompts/coder.py#L47-L58) Workflow 1–6 |
| Negative instructions (DO NOT / NEVER / ABSOLUTELY FORBIDDEN) | ~20 modules (32+ occurrences) | [ci_fixer.py:32-57](swe_af/prompts/ci_fixer.py#L32-L57), [pr_resolver.py:44-68](swe_af/prompts/pr_resolver.py#L44-L68) |
| Fenced code-block examples (commands/anti-patterns) | 7 files | ci_fixer, workspace, issue_advisor, issue_writer, replanner, retry_advisor, pr_resolver |
| HITL `ask_user_form` block | 4 modules | product_manager, replanner, issue_advisor, environment_scout |
| Inline bad/good contrast (single pair, prose) | 2 modules | [qa_synthesizer.py:40-54](swe_af/prompts/qa_synthesizer.py#L40-L54), [verifier.py:73-77](swe_af/prompts/verifier.py#L73-L77) |
| XML/structured tags (`<tag>…</tag>`) | 0 files | grep: NONE |
| Explicit "think step by step" / `<thinking>` | 0 files | grep: NONE |
| Formal few-shot input/output example pairs | 0 files | none found |

### `SYSTEM_PROMPT` sizes (lines / chars)

| Module : constant | Lines | Chars |
|---|---|---|
| sprint_planner.py : SYSTEM_PROMPT | 155 | 8691 |
| pr_resolver.py : SYSTEM_PROMPT | 136 | 6735 |
| ci_fixer.py : SYSTEM_PROMPT | 118 | 5629 |
| issue_advisor.py : SYSTEM_PROMPT | 107 | 4905 |
| issue_writer.py : SYSTEM_PROMPT | 99 | 3392 |
| merger.py : SYSTEM_PROMPT | 96 | 4115 |
| replanner.py : SYSTEM_PROMPT | 92 | 4565 |
| verifier.py : SYSTEM_PROMPT | 90 | 3821 |
| product_manager.py : SYSTEM_PROMPT | 87 | 4618 |
| coder.py : SYSTEM_PROMPT | 87 | 4234 |
| code_reviewer.py : SYSTEM_PROMPT | 82 | 3306 |
| git_init.py : SYSTEM_PROMPT | 79 | 3319 |
| architect.py : SYSTEM_PROMPT | 66 | 3680 |
| integration_tester.py : SYSTEM_PROMPT | 66 | 2658 |
| tech_lead.py : SYSTEM_PROMPT | 61 | 3148 |
| retry_advisor.py : SYSTEM_PROMPT | 58 | 2856 |
| environment_scout.py : SYSTEM_PROMPT | 53 | 2674 |
| qa.py : SYSTEM_PROMPT | 52 | 2416 |
| qa_synthesizer.py : SYSTEM_PROMPT | 48 | 1834 |
| repo_finalize.py : SYSTEM_PROMPT | 46 | 1979 |
| workspace.py : SETUP_SYSTEM_PROMPT | 46 | 1686 |
| workspace.py : CLEANUP_SYSTEM_PROMPT | 44 | 1637 |
| fix_generator.py : SYSTEM_PROMPT | 43 | 1696 |
| github_pr.py : SYSTEM_PROMPT | 32 | 1314 |

### Per-module role inventory (compact)

| Module | Persona (file:line) | Notable structure |
|---|---|---|
| `product_manager.py` | senior Product Manager ([:10](swe_af/prompts/product_manager.py#L10)) | PRD producer; HITL `ask_user_form` block (:68-95); negative "Never use sprints/weeks/days" (:55) |
| `architect.py` | senior Software Architect ([:10](swe_af/prompts/architect.py#L10)) | revision-feedback loop with tech_lead; "do NOT implement hooks/abstractions" (:54) |
| `tech_lead.py` | Tech Lead ([:9](swe_af/prompts/tech_lead.py#L9)) | numbered 1–5 eval checklist; APPROVE/REJECT decision framework (:58-68) |
| `sprint_planner.py` | senior Engineering Manager ([:10](swe_af/prompts/sprint_planner.py#L10)) | longest (155 lines); 11 `##` sections incl. Per-Issue Guidance fields (:143-163) |
| `issue_writer.py` | technical writer ([:9](swe_af/prompts/issue_writer.py#L9)) | inline markdown output template (:26-84); "Keep file under 60 lines" |
| `issue_advisor.py` | senior technical lead (failed attempt) ([:15](swe_af/prompts/issue_advisor.py#L15)) | ordered actions RETRY_*/SPLIT/ESCALATE; HITL block; names `IssueAdvisorDecision` |
| `replanner.py` | senior Engineering Manager (failures) ([:9](swe_af/prompts/replanner.py#L9)) | CAN/CANNOT do sections; HITL block; names `ReplanDecision` |
| `coder.py` | senior software developer ([:9](swe_af/prompts/coder.py#L9)) | Principles 1–5, Workflow 1–6, Git Rules; output fields in prose |
| `qa.py` | QA engineer ([:9](swe_af/prompts/qa.py#L9)) | Principles 1–7, Workflow 1–7; names `test_failures`/`coverage_gaps` |
| `code_reviewer.py` | senior engineer (reviewer) ([:9](swe_af/prompts/code_reviewer.py#L9)) | Adaptive Review Depth; severity `###` BLOCKING/SHOULD_FIX/SUGGESTION |
| `qa_synthesizer.py` | feedback aggregator ([:9](swe_af/prompts/qa_synthesizer.py#L9)) | APPROVE/FIX/BLOCK logic; stuck detection; one bad/good pair |
| `verifier.py` | QA architect (final acceptance) ([:9](swe_af/prompts/verifier.py#L9)) | PASS/FAIL "no partial"; evidence requirements; one bad/good pair |
| `fix_generator.py` | senior engineer (failed criteria) ([:10](swe_af/prompts/fix_generator.py#L10)) | only module without `workspace_manifest`; schema fields inline |
| `retry_advisor.py` | senior debugging specialist ([:9](swe_af/prompts/retry_advisor.py#L9)) | classify-into-5-categories; output constraints in prose |
| `integration_tester.py` | integration QA engineer ([:9](swe_af/prompts/integration_tester.py#L9)) | Priority 1/2/3 strategy; names `IntegrationTestResult` |
| `merger.py` | senior release engineer ([:6](swe_af/prompts/merger.py#L6)) | merge strategy; inline bash example (:40); names `MergeResult` |
| `ci_fixer.py` | senior engineer (CI) ([:14](swe_af/prompts/ci_fixer.py#L14)) | `## ABSOLUTELY FORBIDDEN` 12-item list (:32-57) |
| `pr_resolver.py` | senior engineer (PR) ([:21](swe_af/prompts/pr_resolver.py#L21)) | largest non-planner (136); 16-item FORBIDDEN list; dynamic step numbering |
| `environment_scout.py` | Environment Scout ([:25](swe_af/prompts/environment_scout.py#L25)) | two-pass credential negotiation; HITL; security negatives |
| `git_init.py` | DevOps engineer (git) ([:6](swe_af/prompts/git_init.py#L6)) | mode branches (fresh/existing); 8-field output described inline |
| `github_pr.py` | DevOps engineer (PR push) ([:6](swe_af/prompts/github_pr.py#L6)) | smallest (32); PR body format with hardcoded footer URLs |
| `workspace.py` | DevOps engineer (worktrees) ([:9](swe_af/prompts/workspace.py#L9), [:57](swe_af/prompts/workspace.py#L57)) | two prompts (setup/cleanup); fenced `git worktree add` examples |
| `repo_finalize.py` | senior engineer (final review) ([:6](swe_af/prompts/repo_finalize.py#L6)) | "production-ready" mental model; What NOT to Do |

---

## Part C — Governing Constraints (from memory / thoughts)

These are recorded constraints relevant to *any* future prompt edit. They are
documented here as facts about prior decisions, not as recommendations.

- **`clone-prompts-verbatim` (user feedback memory)** —
  `~/.claude/projects/-home-maceo-Dev-silmari-agent-memory/memory/feedback_clone_prompts_verbatim.md`.
  States: when reusing a proven command prompt, "copy the command's prompt text
  **verbatim** … Do NOT paraphrase, summarize, or 'tighten' it." Origin: Maceo
  rejected a condensed `create-tdd-plan.json` as "so heavily edited so to be
  unusable." Rationale recorded: "proven prompts encode hard-won operational
  detail… paraphrasing silently strips that detail."
- **Recorded failure, 2026-05-25** —
  `~/.claude/MEMORY/LEARNING/FAILURES/2026-05/2026-05-25-130727_corrected-unfaithfully-edited-proven-prompt/`
  ("corrected — unfaithfully edited proven prompt"). Same theme.
- **CLI-first concern, 2026-05-21** —
  `~/.claude/MEMORY/WORK/20260521-121624_-tdd-plan-pipeline-the-new-system-prompt-violates-the-cli-fi…`
  ("the new system prompt violates the cli-first architecture"). A prior instance
  where a system-prompt change conflicted with a "CLI-first" architectural rule
  (`SAI/CLIFIRSTARCHITECTURE.md` per `CONTEXT_ROUTING.md:17`).

---

## Observable alignment surface (facts only)

Stated side by side, without prescription, for the follow-on plan to weigh:

- WISDOM's 12-factor extract records a "150–200 instruction" attention ceiling on
  frontier thinking models (`2026-01-13…:54`). The current `SYSTEM_PROMPT`
  constants range 32–155 lines (table above); `sprint_planner.py` is 155 lines /
  8691 chars and `pr_resolver.py` 136 lines.
- WISDOM records "don't use prompts for control flow… use code"
  (`2026-01-13…:16-22`). Current role prompts encode ordered procedure as numbered
  "Workflow"/"Your Task" step lists inside the prompt (e.g.
  [coder.py:47-58](swe_af/prompts/coder.py#L47-L58),
  every `*_task_prompt` ends with a numbered `## Your Task`).
- WISDOM records example/pattern anchoring ("give the model a pattern… an example
  as the anchor"; `2026-02-24…`, `2026-02-17…`). Current prompts contain 0 formal
  few-shot example pairs; 2 modules carry a single inline bad/good contrast.
- WISDOM records structured-output-as-tripwire + per-field validation invariants
  (`2026-02-03…:68-75`, `2026-03-17…`). Current prompts delegate structure to the
  harness `schema=` parameter (now BAML-parsed, [[swe-af-baml-structured-output]])
  and describe output fields in prose; they do not state per-field validation
  invariants in the prompt body.
- WISDOM records anti-pattern: "company-shaped personas" (`2026-03-10…`). Current
  prompts open every module with a seniority/role persona ("You are a senior …").

---

## Part D — Anthropic's Published Prompting Guidance

Added at the user's direction ("there should be WISDOM from the Anthropic blog as
well"). Two mutually-corroborating source sets:

- **Local curated notes** in the personal workspace (compiled 2026-06-07):
  - `~/Dev/A1_workspace-blueprint/writing-room/research/anthropic-prompt-engineering-evolution_2026-06-07.md`
  - `~/Dev/A1_workspace-blueprint/writing-room/research/anthropic-prompting-examples-what-actually-works_2026-06-07.md`
- **Live Anthropic sources** (fetched + verified 2026-06-11) — see
  [Anthropic sources](#anthropic-sources). The previously-separate technique pages
  are now one consolidated "Prompting best practices" page (old URLs 301-redirect to
  it); prefill and non-default sampling params return **400 errors** on Claude
  4.6+/4.7+. Recorded as facts about the current guidance.

### D1 — Role, not personality
- "Character is trained, not prompted" — curiosity/warmth/honesty exist before any
  prompt loads (*evolution* note, citing *Claude's Character*, 2024-06-08).
- Anthropic's whole "Give Claude a role" guidance is one sentence + one example:
  "Setting a role in the system prompt focuses Claude's behavior and tone… Even a
  single sentence makes a difference," e.g.
  `system="You are a helpful coding assistant specializing in Python."`
- "heavy-handed role prompting is often unnecessary"; "Don't over-constrain the
  role. 'You are a helpful assistant' is often better than 'You are a world-renowned
  expert…'." Alternative: state the *perspective in the task* rather than assign a
  persona (*what-actually-works* note).
- Full named personas (the "AcmeBot" example) are reserved for customer-facing
  product bots, and even then set name/domain/scope + information boundaries +
  scripted edge cases — not warmth/intelligence.

### D2 — Examples (few-shot)
- "Examples are one of the most reliable ways to steer Claude's output format, tone,
  and structure." Not mandatory; skip for simple/standard output, use when format,
  tone, or classification must be exact.
- "Include 3–5 examples for best results." Make them **Relevant**, **Diverse**,
  **Structured** — "Wrap examples in `<example>` tags (multiple in `<examples>`) so
  Claude can distinguish them from instructions."
- "Positive examples… tend to be more effective than negative examples or
  instructions that tell the model what not to do."
- Claude-4 nuance: because newer models follow instructions literally and "don't
  infer requests you didn't make," they may need examples *more* for exact format
  compliance, not less.

### D3 — Claude 4 levers (what moves the needle)
- **Be explicit** — "Include as many relevant features… Go beyond the basics"
  rather than "Create an analytics dashboard."
- **Explain the why** — "Your response will be read aloud by a text-to-speech
  engine, so never use ellipses…"; "Claude is smart enough to generalize from the
  explanation."
- **Say what TO do, not what to avoid** — "Your response should be composed of
  smoothly flowing prose paragraphs" rather than "Do not use markdown."
- **Match prompt style to desired output** — "removing markdown from your prompt can
  reduce the volume of markdown in the output."
- **Be explicit about action** for agentic/tool use — "Change this function…"
  rather than "Can you suggest…". Anthropic ships reusable blocks
  `<default_to_action>`, `<investigate_before_answering>`, `<use_parallel_tool_calls>`.
- **Overengineering mitigation** (Opus 4.5/4.6 "tendency to overengineer"): "Don't
  add features, refactor code, or make 'improvements' beyond what was asked"; "the
  right amount of complexity is the minimum needed for the current task."
- **Test-gaming mitigation**: "Implement a solution that works correctly for all
  valid inputs, not just the test cases. Do not hard-code values…"
- **Autonomy/safety**: gate destructive/shared-system actions (force-push, drop
  tables, send messages) behind confirmation; proceed freely on local reversible ones.

### D4 — XML tags to structure prompts
- "XML tags help Claude parse complex prompts unambiguously… Wrapping each type of
  content in its own tag (`<instructions>`, `<context>`, `<input>`) reduces
  misinterpretation." Use consistent descriptive names; nest for hierarchy; also
  usable as output containers.
- Long context: place long inputs near the top (queries-at-end "can improve response
  quality by up to 30%"); wrap docs in `<document>`/`<document_content>`/`<source>`;
  ask Claude to quote relevant parts first.

### D5 — Thinking replaced manual chain-of-thought
- Claude 3.7+ extended thinking: guidance flipped to "start by removing all
  chain-of-thought guidance from your prompts." Claude 4.6+ → adaptive thinking +
  `effort`. "A prompt like 'think thoroughly' often produces better reasoning than a
  hand-written step-by-step plan."
- Footgun: with thinking off, Opus 4.5+ is oversensitive to the literal word
  "think" — prefer "consider," "evaluate," "reason through."

### D6 — Deprecations: prefill & sampling params
- Prefill on the last assistant turn → **400 error** on Claude 4.6+ ("most use cases
  of prefill no longer require it"; use structured outputs / just ask).
- Non-default `temperature`/`top_p`/`top_k` → **400 error** on Opus 4.7+ ("Use
  prompting to guide the model's behavior").
- Anti-laziness prompting now backfires: "Instructions like 'If in doubt, use [tool]'
  will cause overtriggering."

### D7 — Context engineering (the rename, Sep 2025)
- "Context engineering is the natural progression of prompt engineering." The job is
  to "find the smallest possible set of high-signal tokens that maximize the
  likelihood of [the] desired outcome."
- **Context rot**: "as the number of tokens in the context window increases, the
  model's ability to accurately recall information… decreases."
- **Right altitude** for system prompts: "specific enough to guide behavior
  effectively, yet flexible enough to provide… strong heuristics" — neither
  "hardcoding complex, brittle logic" nor "vague… high-level guidance."
- **Tools**: "a few thoughtful tools targeting specific high-impact workflows";
  namespacing; return only high-signal info; "prompt-engineer your tool
  descriptions"; error messages as steering.
- **CLAUDE.md**: "Keep it concise. For each line, ask: 'Would removing this cause
  Claude to make mistakes?' If not, cut it. Bloated CLAUDE.md files cause Claude to
  ignore your actual instructions." Long-horizon mitigations: compaction, structured
  note-taking, sub-agent architectures.

### D8 — Building Effective Agents (Dec 2024)
- Workflows = "LLMs and tools… orchestrated through predefined code paths"; agents =
  "LLMs dynamically direct their own processes." "Find the simplest solution
  possible, and only increas[e] complexity when needed." Building blocks: augmented
  LLM, prompt chaining, routing, parallelization, orchestrator-workers,
  evaluator-optimizer. "We spent more time optimizing tools than the overall prompt."

### D9 — The throughline: "why beats what"
- The same insight surfaces in Claude-4 prompting guidance, the Jan 2026 Constitution,
  and *Teaching Claude Why* (May 2026; "cut blackmail propensity from 65% to 19%"):
  explanation generalizes, enumeration doesn't. "Surviving techniques cooperate with
  the model; dying ones fight its weaknesses" (*evolution* note).

### Anthropic guidance ↔ current `swe_af/prompts` (facts only)

No prescription — facts side by side, for the follow-on plan to weigh:

| Anthropic published guidance | Observable in current prompts |
|---|---|
| "Give a role… even a single sentence"; "heavy-handed role prompting is often unnecessary" | 23 modules open with a multi-clause seniority persona ("You are a senior … who has shipped products used by millions") |
| "Say what to do, not what to avoid"; positive examples > "what not to do" | Negative instructions are a primary device — 32+ DO NOT/NEVER; `ci_fixer`/`pr_resolver` carry 12–16-item "ABSOLUTELY FORBIDDEN" lists |
| "Include 3–5 examples… in `<example>` tags" | 0 few-shot example pairs; 2 modules carry one inline bad/good contrast |
| "XML tags help Claude parse complex prompts unambiguously" | 0 XML tags; structure is markdown `##` headers |
| "Remove all chain-of-thought… 'think thoroughly' > hand-written steps" | Procedure encoded as numbered Workflow / "Your Task" step lists in every module |
| Prefill/sampling deprecated → "use structured outputs" | Output already delegated to harness `schema=` (BAML-parsed) — aligned |
| "Right altitude"; "smallest set of high-signal tokens"; "would removing this cause mistakes?" | `SYSTEM_PROMPT` sizes 32–155 lines; `sprint_planner` 155 / `pr_resolver` 136 (size table above) |
| "Explain the why… Claude generalizes from the explanation" | Mixed: e.g. `product_manager` motivates some rules; most negatives are stated without rationale |

<a name="anthropic-sources"></a>
### Anthropic sources (verified 2026-06-11)
- Prompting best practices (consolidated, current to Opus 4.8): https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices
- Long context tips: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/long-context-tips
- Building effective agents: https://www.anthropic.com/engineering/building-effective-agents
- Effective context engineering for AI agents: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Writing effective tools for AI agents: https://www.anthropic.com/engineering/writing-tools-for-agents
- Claude Code best practices: https://code.claude.com/docs/en/best-practices (was `anthropic.com/engineering/claude-code-best-practices`)
- Claude's Character: https://www.anthropic.com/research/claude-character
- Local notes: `~/Dev/A1_workspace-blueprint/writing-room/research/anthropic-prompt-engineering-evolution_2026-06-07.md`; `…/anthropic-prompting-examples-what-actually-works_2026-06-07.md`

---

## Code References

- `swe_af/prompts/_utils.py:8-44` — `workspace_context_block` (only shared helper)
- `swe_af/prompts/__init__.py:20-38` — re-export surface (`__all__`)
- `swe_af/prompts/sprint_planner.py:9-164` — largest SYSTEM_PROMPT
- `swe_af/prompts/coder.py:8-95` — coder SYSTEM_PROMPT (representative shape)
- `swe_af/prompts/ci_fixer.py:32-57`, `swe_af/prompts/pr_resolver.py:44-68` — "ABSOLUTELY FORBIDDEN" negative-instruction blocks
- `swe_af/prompts/issue_writer.py:26-84` — only inline output template
- `swe_af/reasoners/pipeline.py:158,240,357,417,477` — planning-pipeline consumers
- `swe_af/reasoners/execution_agents.py:124,205,318,444,525,748,963,1044,1118,1201,1297,1578,1667` — execution-pipeline consumers

## Architecture Documentation

- **Uniform two-part module shape**: `SYSTEM_PROMPT` constant + task-prompt
  builder(s). Output structure is never in the prompt body; it is the harness
  `schema=` argument (BAML-parsed as of the in-progress BAML work).
- **Two builder idioms**: `*_prompts()` returning `(system, task)` for the four
  planning roles; `*_task_prompt()` returning only the task string elsewhere.
- **Section-list vs f-string assembly**: conditional sections use a
  `sections: list[str]` accumulator; fixed prompts use one f-string.
- **HITL pattern**: four roles (PM, replanner, issue_advisor, environment_scout)
  carry an `ask_user_form` block and consume `format_prior_user_responses`.

## Historical Context (from thoughts/ + memory)

- `~/.claude/SAI/USER/WISDOM/ai-that-works-2026/INDEX.md` — index of the 16-episode
  wisdom corpus; cross-cutting threads incl. "the harness has eaten the prompt"
  and "skills > MCP > sub-agents."
- `feedback_clone_prompts_verbatim.md` (silmari-agent-memory project memory) —
  verbatim-fidelity constraint on proven prompts.
- `thoughts/searchable/shared/plans/2026-06-11-04-27-tdd-baml-structured-output-swe-af.md`
  — the BAML structured-output plan (now implemented on branch
  `feat/baml-structured-output`); relevant because WISDOM frames structured output
  as the prompt's primary joint. See memory [[swe-af-baml-structured-output]].
- An in-progress, separate enhancement (branch `feat/baml-structured-output`) added
  TDD framing to `sprint_planner.py`'s SYSTEM_PROMPT; on `main@ebf00a3` (this
  research's base) the sprint planner prompt does not yet contain it.

## Related Research

- `thoughts/searchable/shared/plans/2026-06-11-04-27-tdd-baml-structured-output-swe-af.md`
  (structured-output parsing for these same reasoners)
- `thoughts/searchable/shared/plans/2026-06-11-04-27-tdd-baml-structured-output-swe-af-REVIEW.md`

## Open Questions

These are for a follow-on **plan** (e.g. `/create_tdd_plan`), not this
documentarian research:

1. Scope: "update ALL prompts" — is the target every module under
   `swe_af/prompts/`, or a prioritized subset (e.g. the largest planning prompts
   first)?
2. How should the `clone-prompts-verbatim` constraint bound the rewrite — i.e.
   which prompts count as "proven" and must be preserved verbatim vs. which are
   open to restructuring?
3. Which WISDOM principles are in-scope to apply (instruction-budget trimming,
   control-flow-to-code, example anchoring, per-field validation invariants), and
   which conflict with existing architecture (e.g. CLI-first;
   `SAI/CLIFIRSTARCHITECTURE.md`)?
4. How will "better" be measured — WISDOM's "evals from observed behavior"
   suggests harvesting real build runs rather than authoring eval cases up front;
   is there a corpus of past runs to draw from?
5. The repo also has a `swe_af/fast/prompts.py` (the fast planner) outside this
   directory — is it in scope?
