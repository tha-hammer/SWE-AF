---
date: 2026-06-11T06:35:00-04:00
researcher: maceo
git_commit: ebf00a35e6af11cd085ce4928e589a5b983b2e13
branch: main
repository: SWE-AF
topic: "Coding-specific prompting guidance for autonomous coding agents (Anthropic ∩ AI That Works), applied to swe_af/prompts"
tags: [research, prompting, coding-agents, anthropic-docs, ai-that-works, wisdom, system-prompts, swe-af]
status: complete
last_updated: 2026-06-11
last_updated_by: maceo
---

# Research: Coding-Specific Prompting Guidance for SWE-AF Agents

**Date**: 2026-06-11 06:35 -0400
**Researcher**: maceo
**Git Commit**: ebf00a35e6af11cd085ce4928e589a5b983b2e13
**Branch**: main
**Repository**: SWE-AF

## Research Question

Produce a **coding-focused** companion to the broad prompting research
([2026-06-11-05-51-swe-af-prompts-and-prompting-wisdom.md](thoughts/searchable/shared/research/2026-06-11-05-51-swe-af-prompts-and-prompting-wisdom.md)).
Anthropic's published prompting guidance is **general** — written to cover prose,
analysis, classification, and code alike, so some of it is prose-shaped. The
**AI That Works** (AITW) podcast is **coding-native** — every episode is about
building and instructing coding agents. This document grounds itself in the
Anthropic guidance and uses AITW to **focus that guidance on code**: which
Anthropic principles carry into an autonomous coding pipeline, how the coding
practitioners operationalize them, and which Anthropic guidance is prose-oriented
and set aside here.

Scope note: every one of the 24 prompt modules in `swe_af/prompts/` drives a
**coding-pipeline agent** (planner, coder, reviewer, QA, verifier, merger,
CI/PR fixer, etc.). So "coding-specific" is the whole surface, not a subset.

## Summary

- **Two sources, one shape.** Where Anthropic's general guidance and AITW's
  coding-native guidance converge, the principle is load-bearing for code. The
  convergence points: (1) move known control flow out of the prompt into the
  harness; (2) verification loops ("backpressure") are the product; (3) the
  context/instruction budget is finite and must be curated; (4) show patterns /
  canonical code, not abstractions; (5) be explicit + explain *why* + say what to
  do (literal instruction following); (6) gate irreversible actions; (7) editing
  is harder than creating, so front-load the spec; (8) role is one line, not a
  persona; (9) tools and sub-agents are context-isolation primitives.
- **The unifying coding thesis** is shared verbatim across both corpora:
  AITW — *"the harness has eaten the prompt"* (move logic into code/structured-output
  joints); Anthropic — *"find the smallest set of high-signal tokens"* and *"give
  Claude a check it can run."* The prompt's job in a coding agent is the part the
  harness and tools **cannot** encode.
- **Prose-oriented Anthropic guidance set aside** for this focus (documented in
  [§Prose-only guidance](#prose-oriented-anthropic-guidance-set-aside)): the
  frontend-aesthetics block, "smoothly flowing prose paragraphs" / markdown-volume
  steering, the text-to-speech-ellipses example, and tone/warmth overrides.
- **This is a synthesis of existing knowledge artifacts** (Anthropic docs/blog +
  the AITW WISDOM corpus), cross-referenced against the current
  `swe_af/prompts/` inventory. It documents what the sources say and how it maps to
  the current prompts; it does not prescribe specific edits (that belongs to a
  follow-on plan).

## How to read the two sources together

| | Anthropic published guidance | AI That Works (AITW) |
|---|---|---|
| Nature | Authoritative, first-party, **general** (prose + code + analysis) | Practitioner, coding-native; every episode is a coding-agent build |
| Strength | What the model *is* and *will be* (deprecations, literal following, context engineering) | How coding teams **operationalize** it (harnesses, backpressure, learning tests) |
| Coding use here | The principle and its rationale | The coding-specific shape, failure modes, and concrete patterns |

Anthropic sources cited below were fetched/verified 2026-06-11 (see
[§Sources](#sources)). AITW citations are the WISDOM extracts under
`~/.claude/SAI/USER/WISDOM/ai-that-works-2026/`.

---

## Coding-Specific Principles

### 1. Move known control flow into the harness; the prompt is for the uncertain

- **AITW (12-factor, `2026-01-13…`):** "Don't use prompts for control flow. If you
  know what the workflow is, use control flow for control flow." A long planning
  prompt "was secretly a workflow"; splitting it into phases with structured-output
  joints "literally made the model do the thing the prompt asked for, by removing
  the choice." Exit conditions live "in code, not the prompt."
- **Anthropic (Building Effective Agents):** workflows = "LLMs and tools…
  orchestrated through predefined code paths"; agents = "LLMs dynamically direct
  their own processes." "Find the simplest solution possible, and only increas[e]
  complexity when needed." Building blocks: prompt chaining, routing,
  parallelization, orchestrator-workers, evaluator-optimizer.
- **Coding focus:** in a coding pipeline, fixed orderings (build → test → commit;
  plan → architect → review) belong in the orchestrator; the prompt should carry
  the judgment the code can't pre-decide. AITW's "150–200 instruction" attention
  ceiling (`2026-01-13…:54`) is the symptom signal that a prompt has absorbed a
  workflow.

### 2. Verification loops are the product ("backpressure")

- **AITW (backpressure, `2026-02-10…`):** "backpressure is any mechanism that gives
  the model a way to fix its own mistakes without dragging you into the loop"
  (compilers, type checks, unit tests — "run automatically, fail loudly, and the
  model can read the failure and try again"). **Cheapest-check-first:** compiler
  errors → type checks → unit tests → integration → e2e → human. "Compiler errors
  are the gold standard. Free, deterministic, instant." Design the harness/checks
  **before** the code. Backpressure "must be deterministic, not LLM-as-judge"
  ("You can accidentally steer a model. You cannot accidentally steer a type
  checker"); LLM-as-judge works only narrowly for *structural* checks (does the
  implementation match the plan?). "It just needs to be observable," not binary.
- **AITW (no-vibes, `2026-01-27…`):** order steps so "each chunk is independently
  verifiable"; size phases around verification points; "if the model can check its
  own work, that's the best — you don't have to."
- **AITW (frontend, `2026-04-14…`):** the same primitive for UI — Storybook as
  "unit testing for visual stuff"; "model writes UI → screenshots it → looks at the
  screenshot → iterates." Bug reports captured as stories "become regression tests
  by default."
- **Anthropic (Claude Code best practices):** "Give Claude a check it can run:
  tests, a build, a screenshot to compare." "Claude stops when the work looks done.
  Without a check it can run, 'looks done' is the only signal available, and you
  become the verification loop." The email-validation example: ship the function
  *with* example test cases and "run the tests after implementing."
- **Anthropic (Claude 4 best practices):** self-checking — "Before you finish,
  verify your answer against [test criteria]… catches errors reliably, especially
  for coding and math."
- **Coding focus:** instruct each agent toward the **cheapest legible check it can
  run itself**, and order the issue's behaviors so a check sits between them.

### 3. The context/instruction budget is finite — curate it

- **Anthropic (context engineering):** "find the smallest possible set of
  high-signal tokens that maximize the likelihood of [the] desired outcome."
  **Context rot**: recall degrades as tokens pile up. **Right altitude**: system
  prompts "specific enough to guide… yet flexible enough to provide strong
  heuristics" — neither "hardcoding complex, brittle logic" nor "vague… high-level
  guidance."
- **Anthropic (Claude Code):** "Most best practices are based on one constraint:
  Claude's context window fills up fast, and performance degrades as it fills."
  CLAUDE.md: "Keep it concise. For each line, ask: 'Would removing this cause Claude
  to make mistakes?' If not, cut it. Bloated CLAUDE.md files cause Claude to ignore
  your actual instructions." Sub-agents run in separate context windows and "report
  back summaries."
- **AITW:** "Prune, prune, prune" — 5–7 great skills beat 70 (`2026-02-24…`); every
  tool/skill description is an attention tax charged every session (`2026-03-10…`);
  zero-warnings as a context-engineering decision ("warnings flood the agent's
  context window") (`2026-01-13…`).
- **Coding focus:** the instruction budget competes with the code, diffs, errors,
  and file contents the coding agent must hold — the leaner the standing
  instructions, the more budget for the actual task.

### 4. Show patterns / canonical code, not abstractions

- **AITW (no-vibes-Feb, `2026-02-24…`):** "Give the model a pattern to replicate,
  not a problem to innovate on." "The pattern in your repo IS your prompt." A
  codebase "regresses to the average of the best and worst pattern"; "one bad grep…
  is all it takes for your system to be bad."
- **Anthropic (multishot + context engineering):** "Examples are one of the most
  reliable ways to steer Claude's output format, tone, and structure"; "include
  3–5 examples" wrapped in `<example>` tags; curate "diverse, canonical examples"
  rather than exhaustive edge cases.
- **Coding focus:** for SWE-AF specifically, the **architecture document** is the
  canonical pattern source the coder is told to treat as ground truth — the
  example-anchoring principle maps onto pointing the coder at existing repo
  patterns + the architecture, not abstract instruction.

### 5. Literal instruction following: explicit, say-what-to-do, explain why

- **Anthropic (Claude 4):** newer models "interpret prompts literally… do not infer
  requests you didn't make." Levers: **be explicit**; **say what TO do, not what to
  avoid**; **explain the why** ("Claude is smart enough to generalize from the
  explanation"); for agentic use, **be explicit about action** ("Change this
  function…" not "Can you suggest…").
- **Anthropic (Claude 4, coding-specific):** mitigate the Opus 4.5/4.6 "tendency to
  overengineer" — "Don't add features, refactor code, or make 'improvements' beyond
  what was asked… the right amount of complexity is the minimum needed for the
  current task." Mitigate test-gaming — "Implement a solution that works correctly
  for all valid inputs, not just the test cases. Do not hard-code values…"
- **AITW:** simplicity over cleverness; "vibe coding means not caring about the
  code" — the engineering work is in the ticket and architecture, not the
  autocomplete (no-vibes trilogy).
- **Coding focus:** explicit, motivated instructions + an anti-overengineering /
  anti-test-gaming stance are the coding-native expression of "say what to do and
  why." Note the asymmetry Anthropic flags: positive instructions and rationale
  generalize; long lists of prohibitions do not.

### 6. Gate irreversible actions; let reversible ones run free

- **Anthropic (Claude 4):** "Without guidance, Claude Opus 4.6 may take actions that
  are difficult to reverse… deleting files, force-pushing, or posting to external
  services." Recommended split: local reversible actions (edit files, run tests) →
  proceed; destructive/shared-system (force-push, drop tables, send messages) →
  confirm first.
- **AITW:** reversibility decides auto-vs-human (`2026-02-17…`); backpressure exists
  "to reduce the surface area where a human has to be in the loop" (`2026-02-10…`).
- **Coding focus:** the coding pipeline's irreversible boundaries (push, PR open,
  merge, branch/worktree mutation) are exactly where confirmation/guardrail prompts
  earn their tokens — reversible local edits do not need them.

### 7. Editing is harder than creating — front-load the spec

- **AITW (12-factor):** "Editing with consistency is a much harder task than
  creating with consistency." Steering after the model commits 1000 lines is
  expensive; do the design discussion early in the context window. "Plans are too
  long to review" → the **structure outline** is the alignment artifact, not the
  plan.
- **AITW (no-vibes-March, `2026-03-31…`):** the ticket/spec is the leverage point
  ("200 lines of spec → thousands of lines of code; one wrong line compounds");
  "ask for options, not answers"; models are sycophants — "the first token the model
  emits steers everything after."
- **Anthropic (Claude Code):** explore → plan → implement → commit separation
  ("letting Claude jump straight to coding can produce code that solves the wrong
  problem"); "the most useful specs are self-contained: they name the files and
  interfaces involved, state what is out of scope, and end with an end-to-end
  verification step."
- **Coding focus:** maps directly onto SWE-AF's plan-before-execute pipeline — the
  PM/architect/sprint-planner artifacts are the cheap-to-steer surface; the coder is
  the expensive-to-edit surface.

### 8. Role: one line, not a persona

- **Anthropic:** "Setting a role… focuses Claude's behavior and tone… Even a single
  sentence makes a difference" (`system="You are a helpful coding assistant
  specializing in Python."`). "heavy-handed role prompting is often unnecessary";
  "Don't over-constrain the role." Character is trained, not prompted.
- **AITW (claude-skills, `2026-03-10…`):** "company-shaped personas (backend
  engineer, frontend engineer)" are an anti-pattern — "the company abstraction has
  nothing to do with how the model allocates attention"; put instructions in
  skills, not personas.
- **Coding focus:** a coding agent needs a crisp role (domain + function) and its
  task constraints, not a backstory.

### 9. Tools & sub-agents are context-isolation primitives

- **Anthropic (Writing effective tools):** "a few thoughtful tools targeting
  specific high-impact workflows"; **namespacing** to disambiguate; return only
  high-signal info (avoid `uuid`/`mime_type` noise); "prompt-engineer your tool
  descriptions… think of how you would describe your tool to a new hire"; error
  messages as steering ("clearly communicate specific and actionable improvements,
  rather than opaque error codes").
- **Anthropic (Claude Code):** sub-agents for context isolation ("run in separate
  context windows and report back summaries"); writer/reviewer multi-Claude ("a
  fresh context improves code review since Claude won't be biased toward code it
  just wrote"); adversarial diff review in a fresh subagent.
- **AITW (claude-skills):** skills = instruction modules; sub-agents = context
  isolation; slash commands = entry points — don't conflate; skills inject as a
  user message → instruction-following attention.
- **Coding focus:** SWE-AF already separates concerns into reasoners with their own
  prompts/schemas; this body of guidance concerns how their tool surfaces and
  isolation are framed.

---

## Prose-oriented Anthropic guidance set aside

Documented for transparency — Anthropic guidance that is prose/UX-shaped and not
central to a backend coding pipeline, so it is **not** carried into the coding
focus above:

- The **frontend aesthetics** block (typography/color/motion/backgrounds, "make
  creative, distinctive frontends") — applies only if/when an agent renders UI. The
  AITW frontend episode (`2026-04-14…`) gives the coding analog if SWE-AF ever
  targets UI: verify visually via Storybook + screenshots rather than prose
  aesthetics instructions.
- **"Smoothly flowing prose paragraphs"** / removing-markdown-to-reduce-markdown
  output steering — format control for prose answers.
- The **text-to-speech "never use ellipses"** example — a prose-output constraint
  (the underlying *technique*, "explain the why," is carried over in §5).
- **Tone/warmth overrides** ("use a warm, collaborative tone") — consumer-product
  voice, not coding correctness.

(Anthropic's own framing supports the filter: character/tone is trained in, and
"heavy-handed role prompting is often unnecessary"; the coding work is correctness
and verifiability, not voice.)

---

## Coding synthesis ↔ current `swe_af/prompts` (facts only)

All 24 modules are coding agents; stated side by side without prescription, for a
follow-on plan to weigh. (Inventory facts from the companion research doc.)

| Coding-focused principle (source) | Observable in current prompts |
|---|---|
| Control flow → harness; prompt for the uncertain (AITW 12-factor; Anthropic agents) | Each `*_task_prompt` ends with a numbered "## Your Task" / "Workflow" step list inside the prompt |
| Verification loop / cheapest-check-first (AITW backpressure; Anthropic "a check it can run") | `coder.py` self-validates then reports `tests_passed`/`test_summary`; separate `qa`/`code_reviewer`/`verifier` reasoners run downstream checks; ordering is pipeline-level, not stated per-issue as cheapest-first |
| Finite instruction budget; "would removing this cause mistakes?" (Anthropic; AITW prune) | `SYSTEM_PROMPT` sizes 32–155 lines; `sprint_planner` 155 / `pr_resolver` 136 / `ci_fixer` 118 |
| Show patterns / canonical examples (AITW codebase-is-the-prompt; Anthropic 3–5 examples) | 0 few-shot example pairs; coder is pointed at the architecture doc + "follow existing patterns" prose; 2 modules carry one inline bad/good contrast |
| Be explicit, explain *why*, say what to do (Anthropic Claude 4) | Instructions are mostly imperative; **negative** framing dominates (32+ DO NOT/NEVER; 12–16-item "ABSOLUTELY FORBIDDEN" in `ci_fixer`/`pr_resolver`); rationale present in some modules, absent in most negatives |
| Anti-overengineering / anti-test-gaming (Anthropic Claude 4 coding) | `coder.py` "Simplicity first… no over-engineering, no speculative features"; "tests verify behavior, not implementation details" |
| Gate irreversible actions (Anthropic; AITW reversibility) | Present as hard prohibitions: `coder` "Do NOT push"; `merger`/`git_init`/`github_pr` "Do NOT rewrite history / force push / merge" |
| Front-load the spec; editing > creating (AITW; Anthropic explore-plan-code) | Pipeline is plan→execute; `architect`↔`tech_lead` revision loop exists; planning artifacts precede the coder |
| Role = one line, not a persona (Anthropic; AITW personas anti-pattern) | 23 modules open with a multi-clause seniority persona ("You are a senior … who has shipped products used by millions") |
| Tools/sub-agents = context isolation; high-signal tool descs (Anthropic) | Reasoners are separated with own prompts/schemas; tool lists passed via harness `tools=[…]`; prompts describe a "Tools Available" section in prose |

---

## Sources

**Anthropic (verified 2026-06-11):**
- Prompting best practices (consolidated, current to Opus 4.8): https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices
- Building effective agents: https://www.anthropic.com/engineering/building-effective-agents
- Effective context engineering for AI agents: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Writing effective tools for AI agents: https://www.anthropic.com/engineering/writing-tools-for-agents
- Claude Code best practices: https://code.claude.com/docs/en/best-practices

**AI That Works WISDOM (`~/.claude/SAI/USER/WISDOM/ai-that-works-2026/`):**
- `2026-01-13-applying-12-factor-principles-to-coding-agent-sdks.md` — control flow vs prompt; structured-output joints; 150–200 instructions; editing > creating; plans too long
- `2026-02-10-agentic-backpressure-deep-dive.md` — deterministic verification loops; cheapest-check-first; learning tests; design the harness first
- `2026-01-27-no-vibes-allowed.md`, `2026-02-24-no-vibes-february.md`, `2026-03-31-no-vibes-march.md` — verifiable phases; codebase-is-the-prompt; spec is the leverage point; sycophancy/first-token
- `2026-03-10-claude-agent-skills-deep-dive.md` — skills vs sub-agents vs commands; persona anti-pattern; instruction budget
- `2026-02-17-automating-aitw.md` — multi-pass pipelines; reversibility decides auto-vs-human
- `2026-04-14-agentic-coding-for-frontend-apps.md` — visual verification (Storybook/screenshots) as the coding analog of backpressure
- `2026-02-03-prompting-is-becoming-a-product-surface.md` — structured output as the joint / tripwire

**Companion research:**
- `thoughts/searchable/shared/research/2026-06-11-05-51-swe-af-prompts-and-prompting-wisdom.md` — full prompt inventory, broad WISDOM, and Anthropic Part D
- Local Anthropic notes: `~/Dev/A1_workspace-blueprint/writing-room/research/anthropic-prompt-engineering-evolution_2026-06-07.md`, `…/anthropic-prompting-examples-what-actually-works_2026-06-07.md`

## Open Questions

For a follow-on **plan**, not this research:

1. Which coding principles become explicit prompt changes vs. harness/orchestration
   changes (per §1, some "principles" are code, not prompt)?
2. For verification (§2): should each issue's instructions name a cheapest-check-first
   ladder, and does the pipeline already encode the ordering the prompts would
   otherwise describe?
3. How does the `clone-prompts-verbatim` constraint (companion doc, Part C) bound a
   negative-instruction-to-positive or persona-trimming rewrite of "proven" prompts?
4. Examples (§4): is the canonical-pattern source the architecture doc (already
   referenced) or should issue-level prompts carry in-repo code exemplars?
5. Measurement: AITW's "evals from observed behavior" + backpressure suggest grading
   prompt changes against real build runs — is there a corpus to draw from?
