---
date: 2026-06-17T07:54:00-04:00
researcher: maceo
git_commit: 27cb8a8dbac05802f312442071981d095974639a
branch: main
repository: SWE-AF
topic: "Seams and interfaces for changing agent prompts / generalizing the workflow; the 'coder' → 'implementer' rename surface"
tags: [research, codebase, prompts, reasoners, dag-executor, coder, agent-roles, model-config]
status: complete
last_updated: 2026-06-17
last_updated_by: maceo
---

# Research: Seams to Change Agent Prompts, Generalize the Workflow, and Rename "coder" → "implementer"

**Date**: 2026-06-17 07:54 EDT (-0400)
**Researcher**: maceo
**Git Commit**: 27cb8a8dbac05802f312442071981d095974639a
**Branch**: main
**Repository**: SWE-AF (Agent-Field/SWE-AF)

## Research Question

The codebase is pinned as a coding agent. Identify all the seams and interfaces needed to change the prompts in order to change the nature of the agents so that any workflow can be used. The "coder" agent will change to the more generic "implementer" agent and will be the LLM that actually does the task.

## Summary

SWE-AF is built on the AgentField SDK. Each named agent ("role") is an async Python
function decorated with `@router.reasoner()`. There is **no enum, dict, or registry**
that maps role names to behaviour — the role *is* the function, and the function
statically wires three things together by direct import:

1. **A prompt module** in `swe_af/prompts/<role>.py` (a `SYSTEM_PROMPT` string constant
   + a `<role>_task_prompt(...)` builder function),
2. **An output schema** (a Pydantic model in `reasoners/schemas.py` or `execution/schemas.py`),
3. **An LLM invocation** via `router.harness(task_prompt, system_prompt=..., schema=..., model=..., provider=..., tools=...)`.

The **workflow** (which agents run, in what order, with what gating) is **hardcoded
imperatively** in Python function bodies — there is no declarative graph file. The
top-level phase order lives in `app.py`'s `build()`; the planning sub-sequence lives
in `plan()`; the per-issue inner loop lives in `execution/coding_loop.py`. The issue
*execution order* within the DAG is data-driven (computed from `depends_on` fields the
planner emits), but the *set of stages* and *which agents exist* are fixed in code.

There are therefore three distinct "seams" relevant to the request:

- **Prompt seam** — change an agent's nature by editing its prompt module
  (`swe_af/prompts/<role>.py`). The system prompt defines identity; the task-prompt
  builder defines what runtime data is injected. This is the lowest-friction seam.
- **Role-wiring seam** — rename/repurpose a role by changing the reasoner function,
  its prompt import, its schema, its model-config field, and the call sites that
  invoke it by string (`f"{NODE_ID}.run_coder"`). This is the "coder → implementer"
  rename surface (~100+ reference sites).
- **Workflow seam** — make "any workflow" usable. Two existing extension points
  matter: (a) `execute_fn_target` in `execute()` (`app.py:1776`) already lets an
  external agent target *replace* the entire built-in coding loop, and (b) the
  per-role model/provider resolution (`ROLE_TO_MODEL_FIELD`, `_RUNTIME_BASE_MODELS`).
  Beyond those, the phase sequence itself is not parameterized — it is written out
  longhand in `build()`.

The "coder" is the agent the request calls "the LLM that actually does the task." It
is defined at `reasoners/execution_agents.py:963` (`run_coder`), invoked once per
coding-loop iteration from `execution/coding_loop.py:616`, and is the innermost LLM
call with file-mutating tools (`Read/Write/Edit/Bash/Glob/Grep`).

## Detailed Findings

### 1. The agent-role construct (no registry — the function IS the role)

Every role is an `@router.reasoner()`-decorated async function. The decorator
(`agentfield/router.py:30`) appends the function to `router.reasoners` and wraps it for
DAG tracking; registration onto an `Agent` happens at `Agent.include_router(router)`.
The router is constructed in `swe_af/reasoners/__init__.py`:

```python
router = AgentRouter(tags=["swe-planner"])
apply_codex_harness_patch()
from . import execution_agents  # registers execution reasoners
from . import pipeline           # registers planning reasoners
```

- **Planning roles** (`swe_af/reasoners/pipeline.py`): `run_product_manager` (159),
  `run_environment_scout` (241), `run_architect` (358), `run_tech_lead` (418),
  `run_sprint_planner` (478).
- **Execution roles** (`swe_af/reasoners/execution_agents.py`): `run_coder` (963),
  `run_qa` (1044), `run_code_reviewer` (1118), `run_qa_synthesizer` (1201),
  `run_verifier` (525), `run_replanner` (318), `run_retry_advisor` (125),
  `run_issue_advisor` (205), `run_issue_writer` (444), `run_git_init` (598),
  `run_workspace_setup` (681), `run_merger` (748), `run_integration_tester` (821),
  `run_workspace_cleanup` (896), `generate_fix_issues` (1297), `run_repo_finalize`
  (1395), `run_github_pr` (1453), `run_ci_watcher` (1526), `run_ci_fixer` (1578),
  `run_pr_resolver` (1667).

"Reasoner" and "execution agent" are the same mechanism; the file split (`pipeline.py`
vs `execution_agents.py`) is organizational (planning phase vs execution phase). All
go through the identical `router.harness(...)` path — **except** `run_qa_synthesizer`
(`execution_agents.py:1239`), which uses `router.ai(...)` (a single-shot, no-tool LLM
call) and is the only role defaulting to `"haiku"`.

The string literal `"coder"` does **not** appear in any dispatch/routing table — only
in observability tags like `tags=["coder", "start"]` (`execution_agents.py:987`) and in
the `ROLE_TO_MODEL_FIELD` config map (see §5).

### 2. The prompt seam — `swe_af/prompts/`

Every prompt module follows one of two shapes. Both expose a module-level
`SYSTEM_PROMPT` string (the agent's standing identity) plus a builder function.

- **Shape A — tuple-returning (planning tier)**: `architect.py`, `product_manager.py`,
  `tech_lead.py`, `sprint_planner.py`. A `<role>_prompts(...) -> tuple[str, str]`
  returning `(SYSTEM_PROMPT, task_prompt)`, plus a `<role>_task_prompt(...)` wrapper
  that prepends the workspace block and returns just the task `str`.
- **Shape B — string-returning (execution tier)**: everyone else. A single
  `<role>_task_prompt(...) -> str`.

The public surface is `swe_af/prompts/__init__.py` (18 names re-exported). Seven modules
are imported directly by consumers and are **not** in `__all__`: `fix_generator.py`,
`issue_advisor.py`, `pr_resolver.py`, `github_pr.py`, `ci_fixer.py`,
`environment_scout.py`, `repo_finalize.py`.

Shared helper `swe_af/prompts/_utils.py:8` — `workspace_context_block(manifest)` —
returns a `## Workspace Repositories` Markdown block for multi-repo workspaces (empty
string for single-repo); nearly every execution-tier builder prepends it.

**The coder prompt** (`swe_af/prompts/coder.py`):
- `SYSTEM_PROMPT` (lines 8–95) — identity line verbatim:
  > "You are a senior software developer working in a fully autonomous coding pipeline.
  > You receive a well-defined issue with acceptance criteria and must implement the
  > solution in the codebase."
  Subsections: `## Isolation Awareness`, `## Principles`, `## Workflow`, `## Git Rules`,
  `## Self-Validation`, `## Output`, `## Tools Available`.
- `coder_task_prompt(issue, worktree_path="", feedback="", iteration=1,
  project_context=None, memory_context=None, workspace_manifest=None, target_repo="",
  architecture=None) -> str` (line 98). Builds a `"\n".join(sections)` Markdown string;
  `architecture` is accepted only for API compatibility (unused). Injects issue fields,
  project-context file paths, capped memory context (`failure_patterns[:5]`,
  dep-interface `exports[:5]`, `bug_patterns[:5]`), and either a `## Feedback from
  Previous Iteration` (fix-only) or `## Your Task` (first-pass) block.

**To change an agent's nature via prompts**: edit the `SYSTEM_PROMPT` constant
(identity/behaviour) and/or the `*_task_prompt` builder (what runtime data is injected).
No other file needs to change for a pure prompt edit — the reasoner imports the constant
and the builder by name.

Role-identity first sentences for every module (the "nature" of each agent) are
catalogued; e.g. `qa.py:9` "You are a QA engineer…", `architect.py:9` "You are a senior
Software Architect…", `verifier.py:9` "You are a QA architect running final acceptance
testing…", `merger.py:5` "You are a senior release engineer…", etc.

### 3. The role-wiring seam — how coder connects prompt → schema → LLM

The role→prompt mapping is a set of top-of-file static imports in
`execution_agents.py:40–85`:

```python
from swe_af.prompts.coder import SYSTEM_PROMPT as CODER_SYSTEM_PROMPT
from swe_af.prompts.coder import coder_task_prompt
# ... one pair per execution-phase prompt module
```

Planning roles use lazy in-function imports (e.g. `pipeline.py:177`).

**Full coder invocation** (`execution_agents.py:963–1027`, verified verbatim):

```python
@router.reasoner()
async def run_coder(issue, worktree_path, feedback="", iteration=1, iteration_id="",
                    project_context=None, memory_context=None, model="sonnet",
                    permission_mode="", ai_provider="claude",
                    workspace_manifest=None, target_repo="") -> dict:
    ...
    task_prompt = coder_task_prompt(issue=issue, worktree_path=worktree_path, ...)
    provider = runtime_to_harness_adapter(ai_provider)
    result = await router.harness(
        task_prompt,
        system_prompt=maybe_apply_coder_guardrail(CODER_SYSTEM_PROMPT),
        schema=CoderResult,
        model=model,
        provider=provider,
        tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        cwd=worktree_path,
        max_turns=DEFAULT_AGENT_MAX_TURNS,        # = 150
        permission_mode=permission_mode or None,
    )
    ...
    out = result.parsed.model_dump()
    out["iteration_id"] = iteration_id
    return out
```

Key facts:
- `model` (default `"sonnet"`) and `ai_provider` (default `"claude"`) are plain
  parameters; callers always override them from resolved config.
- `provider = runtime_to_harness_adapter(ai_provider)` (`runtime/providers.py:30`)
  normalizes `"claude"` → `"claude-code"`, `"open_code"/"opencode"` → `"opencode"`,
  `"codex"` → `"codex"`.
- The coder is the **only** agent whose system prompt is wrapped by
  `maybe_apply_coder_guardrail(...)` (`tools/web_search.py:60`), which appends
  `WEB_SEARCH_CODER_GUARDRAIL` when `OPENCODE_ENABLE_EXA=1` + `EXA_API_KEY` are set.
- The tool set `["Read", "Write", "Edit", "Bash", "Glob", "Grep"]` is what makes this
  "the LLM that actually does the task" — it is the file-mutating agent.

`router.harness` → `HarnessRunner.run` (`agentfield/harness/_runner.py:202`) →
`build_provider(config)` (`.../providers/_factory.py:12`) → `ClaudeCodeProvider` /
`CodexProvider` / `OpenCodeProvider` → `claude_agent_sdk.query(...)`
(`.../providers/claude.py:37`). Structured output is parsed from
`.agentfield_output.json` with stdout fallback + litellm-based JSON repair + up to 2
schema retries.

**Coder output schema**: `CoderResult` (`execution/schemas.py:414`) — `files_changed`,
`summary`, `complete`, `iteration_id`, `tests_passed`, `test_summary`,
`codebase_learnings`, `agent_retro`, `repo_name`.

### 4. The workflow seam — how the pipeline is defined and where it can be parameterized

The pipeline is **hardcoded imperatively** in Python; there is no YAML/JSON graph and no
stage registry.

**Entry points**: `swe_af/__main__.py:4` → `swe_af/app.py` constructs an AgentField
`Agent` named `swe-planner`; `build()` (`app.py:596`) is the primary reasoner.

**Top-level phase order** (`build()`):
1. **Plan + git-init (parallel)** — `app.py:754–836`, `asyncio.gather(plan_coro,
   git_init_coro)`.
2. **Human approval checkpoint (conditional)** — `app.py:864–1065`, gated on
   `HAX_API_KEY`; on change-request, re-runs `architect → [tech_lead loop] →
   sprint_planner` (bounded by `cfg.max_plan_revision_iterations`, default 2).
3. **Execute** — `app.py:1067–1079`, calls `execute()` → `run_dag()`.
4. **Verify + fix cycles** — `app.py:1091–1215`, loop ≤ `cfg.max_verify_fix_cycles`
   (default 2): `run_verifier → generate_fix_issues → execute(fix_plan) → re-verify`.
5. **Finalize** — `app.py:1247–1304`, `run_repo_finalize`.
6. **Push + PR (+ CI gate)** — `app.py:1306–1498`, `run_github_pr`, then optional
   `run_ci_watcher → run_ci_fixer` repush loop.

**Planning sub-sequence** (`plan()`, `app.py:1547–1740`): `run_product_manager →
run_environment_scout → run_architect → [run_tech_lead ↔ run_architect loop] →
run_sprint_planner → [parallel run_issue_writers]`. `_compute_levels(issues)` and
`_assign_sequence_numbers(...)` at `app.py:1674–1675` build the parallel topology from
each issue's `depends_on`.

**DAG engine**: `run_dag()` (`execution/dag_executor.py:1414`). `dag_state.levels` is a
`list[list[str]]` of concurrently-runnable issue names produced by `_compute_levels()`;
the executor iterates levels, dispatches issues with `asyncio.gather` (semaphore
`config.max_concurrent_issues`, default 3), then runs gates: fatal-provider-abort,
level-failure-abort (≥80%), debt, split, replan.

**Per-issue inner loop**: `run_coding_loop()` (`execution/coding_loop.py:516`). Coder
dispatched at `coding_loop.py:616–634`:

```python
coder_result = await _call_with_timeout(
    call_fn(f"{node_id}.run_coder", issue=issue, worktree_path=worktree_path,
            feedback=feedback, iteration=iteration, ...,
            model=config.coder_model, ai_provider=config.ai_provider),
    timeout=timeout, label=f"coder:{issue_name}:iter{iteration}")
```

After each coder iteration the loop branches on `issue["guidance"]["needs_deeper_qa"]`
(set by the sprint planner, `coding_loop.py:564–565`):
- **Default path** (`coding_loop.py:689–708`): `run_code_reviewer` only.
- **Flagged path** (`coding_loop.py:662–684`): `run_qa` + `run_code_reviewer` in
  parallel, then `run_qa_synthesizer`.

**The external-workflow extension point** (`execute()`, `app.py:1776`, verified
verbatim):

```python
if execute_fn_target:
    # External coder agent (existing path)
    async def execute_fn(issue, dag_state):
        return await app.call(execute_fn_target, issue=issue,
                              repo_path=dag_state.repo_path)
else:
    execute_fn = None  # Built-in coding loop
```

When `execute_fn_target` is set, the entire built-in coding loop (coder + QA + reviewer
+ synthesizer) is replaced by a single call to the external target, receiving `issue`
and `repo_path`. When empty (default), `_execute_single_issue()` calls
`run_coding_loop()` directly. This is the existing seam by which a different
"implementer" agent / workflow can be substituted at the per-issue level without
touching the DAG.

**Node/stage contract**: every stage is invoked via `app.call("<node_id>.<reasoner>",
**kwargs)` and returns a `dict` (unwrapped by `unwrap_call_result()` in
`execution/envelope.py`). There is no formal node interface class — it is a
convention-based calling contract. The only near-universal kwargs are `model`,
`ai_provider`, `permission_mode`. `IssueResult` (`execution/schemas.py:222`) is the
upward result shape from `_execute_single_issue()` / `run_coding_loop()`.

**Fixed vs parameterizable**:
- *Fixed in code*: planning sequence, top-level phase order, inner-loop structure.
- *Data-driven at runtime*: issue order (`_compute_levels` over `depends_on`); QA path
  (`needs_deeper_qa`); DAG mutation by the replanner (`apply_replan()`,
  `dag_executor.py:1803`).
- *Config-driven* (`BuildConfig`/`ExecutionConfig`): `max_coding_iterations` (5),
  `max_replans` (2), `max_verify_fix_cycles` (2), `max_concurrent_issues` (3),
  `enable_issue_advisor`, `enable_replanning`, `execute_fn_target`, and all per-role
  model assignments.

### 5. Model / provider resolution (per-role seam)

`ROLE_TO_MODEL_FIELD` (`execution/schemas.py:469`, verified verbatim) maps role keys to
model-config fields; `"coder": "coder_model"` at line 474. Derived structures at
489–508 build `MODEL_ROLE_KEYS`, `ALL_MODEL_FIELDS`, `_MODEL_FIELD_TO_ROLE`,
`_ALLOWED_MODEL_KEYS` (= role keys ∪ `{"default"}`), plus legacy-equivalent maps.

`_RUNTIME_BASE_MODELS` (`schemas.py:510`, verified verbatim): for `claude_code` every
field defaults to `"sonnet"` except `qa_synthesizer_model` → `"haiku"`; `open_code` →
`openrouter/minimax/minimax-m2.5`; `codex` → `gpt-5.3-codex`. (Note: the live default is
uniform sonnet — there is no built-in "Opus=plan, Haiku=code" split; that comes only
from caller-supplied `models` overrides or env vars.)

Resolution order (`schemas.py:636–681`, via `resolve_runtime_models`): runtime base →
env cascade (`SWE_DEFAULT_MODEL` → `AI_MODEL` → `HARNESS_MODEL`) → caller
`models["default"]` → caller `models["<role>"]`. `BuildConfig.resolved_models()`
(`schemas.py:818`) and `ExecutionConfig.model_post_init()` (`schemas.py:1042`) run this;
each role then has a property (e.g. `config.coder_model`, `schemas.py:1073`).

### 6. The `fast/` subsystem (a separate, simpler workflow)

`swe_af/fast/` is a speed-optimized single-pass node (`swe-fast`, port 8004) that
deliberately never imports the planning reasoners (`fast/__init__.py:1–14`). Sequence
(`fast/app.py`): `run_git_init → fast_plan_tasks → fast_execute_tasks → fast_verify →
run_repo_finalize → run_github_pr` — also hardcoded.

It does **not** define its own coder. `fast_execute_tasks` (`fast/executor.py:63`)
calls `app.call(f"{NODE_ID}.run_coder", ...)` with `worktree_path=repo_path` (no
worktrees), delegating to the same `execution_agents.run_coder` and the same
`swe_af/prompts/coder.py`. `fast/prompts.py` contains only the planner's
`FAST_PLANNER_SYSTEM_PROMPT` (line 5) + `fast_planner_task_prompt()` (line 60).

Fast model resolution (`fast/schemas.py:134`, `fast_resolve_models`) covers four roles
(`pm`, `coder`, `verifier`, `git`); `_ROLE_KEY_MAP` at `fast/schemas.py:31` contains
`"coder": "coder_model"`. Claude-code default here is `"haiku"` (`schemas.py:15`).

### 7. The "coder" → "implementer" rename surface

Renaming the role touches ~100+ sites across code, config, tests, and docs. The
load-bearing artifacts:

| Artifact | Location | Kind |
|---|---|---|
| `run_coder` reasoner | `reasoners/execution_agents.py:963` | function def |
| `run_coder` fast wrapper | `fast/__init__.py:54` | function def |
| `coder_task_prompt` | `prompts/coder.py:98` | builder fn |
| `SYSTEM_PROMPT` (coder) | `prompts/coder.py:8` | constant |
| `CoderResult` | `execution/schemas.py:414` | schema class |
| `CODER_SYSTEM_PROMPT` import | `execution_agents.py:50` | import alias |
| `maybe_apply_coder_guardrail` | `tools/web_search.py:60` | fn |
| `WEB_SEARCH_CODER_GUARDRAIL` | `tools/web_search.py:33` | constant |
| `"coder": "coder_model"` | `execution/schemas.py:474` | role→field map |
| `"coder": "coder_model"` | `fast/schemas.py:31` | fast role map |
| `coder_model` property | `execution/schemas.py:1073` | config property |
| `model=config.coder_model` | `coding_loop.py:626` | call site |
| `f"{node_id}.run_coder"` | `coding_loop.py:618` | string call target |
| `f"{NODE_ID}.run_coder"` | `fast/executor.py:64` | string call target |
| `tags=["coder", ...]` | `execution_agents.py:987,1023,1033` | observability tags |
| `_save_artifact(..., "coder", ...)` | `coding_loop.py:659` | artifact label |
| `models.coder` config key | README.md, `.env.example`, request payloads | public API surface |
| Test references | ~25 test files (esp. `tests/test_model_config.py`, `tests/fast/*`, `tests/test_multi_repo_prompts.py`, `tests/test_web_search_guardrail.py`) | tests |
| Docs / examples | `README.md` (multiple), `examples/diagrams/*.py` | docs |

Important: the config key `models.coder` and field `coder_model` are part of the
**public request/config API** (used in README examples and `.env.example`). Renaming
them is a breaking change to the external interface unless an alias is retained
(`_LEGACY_TOP_LEVEL_EQUIVALENTS` at `schemas.py:503` shows the existing legacy-alias
pattern this codebase already uses).

## Code References

- `swe_af/reasoners/__init__.py` — router construction, module load order, codex patch
- `swe_af/reasoners/execution_agents.py:40-85` — role→prompt static import seam
- `swe_af/reasoners/execution_agents.py:963-1032` — `run_coder` full invocation (verified)
- `swe_af/reasoners/pipeline.py:159-478` — planning role definitions
- `swe_af/prompts/__init__.py` — public prompt surface (`__all__`)
- `swe_af/prompts/_utils.py:8` — `workspace_context_block`
- `swe_af/prompts/coder.py:8` / `:98` — coder `SYSTEM_PROMPT` / `coder_task_prompt`
- `swe_af/app.py:596` — `build()` top-level phase order
- `swe_af/app.py:1547-1740` — `plan()` planning sub-sequence
- `swe_af/app.py:1776-1786` — `execute_fn_target` external-workflow seam (verified)
- `swe_af/execution/dag_executor.py:1414` — `run_dag()` engine; `:1803` `apply_replan()`
- `swe_af/execution/coding_loop.py:516` — `run_coding_loop()`; `:616-634` coder dispatch
- `swe_af/execution/schemas.py:414` — `CoderResult`; `:469-521` `ROLE_TO_MODEL_FIELD` + `_RUNTIME_BASE_MODELS` (verified); `:636-681` resolution; `:1073` `coder_model`
- `swe_af/runtime/providers.py:30` — `runtime_to_harness_adapter`
- `swe_af/tools/web_search.py:33` / `:60` — coder web-search guardrail
- `swe_af/fast/app.py` — fast pipeline sequence; `fast/executor.py:63` — fast coder call
- `swe_af/fast/schemas.py:15,31,134` — fast defaults, role map, resolution
- `agentfield/router.py:30` — `@router.reasoner()`; `agentfield/harness/_runner.py:202` — `HarnessRunner.run`; `agentfield/harness/providers/_factory.py:12` — provider dispatch; `agentfield/harness/providers/claude.py:37` — SDK query

## Architecture Documentation

- **Role = function, no registry.** Behaviour is composed by static import inside each
  reasoner: prompt module + schema + `router.harness(...)` call. To repurpose an agent,
  the smallest change is editing its prompt module; the largest is renaming the function
  and all string call targets / config keys.
- **Prompt module convention.** `SYSTEM_PROMPT` constant (identity) + `*_task_prompt`
  builder (runtime data injection). Planning tier additionally exposes a
  `(system, task)` tuple form. `_utils.workspace_context_block` is the shared injection
  helper.
- **Workflow is imperative Python.** Phase order in `build()`/`plan()`; per-issue
  structure in `coding_loop.py`. Only the issue *ordering* (via `depends_on` →
  `_compute_levels`), QA path (`needs_deeper_qa`), and DAG mutation (replanner) are
  data-driven at runtime.
- **Two existing generalization seams**: (1) `execute_fn_target` swaps the entire
  per-issue implementer workflow for an external agent target; (2) per-role
  model/provider resolution (`ROLE_TO_MODEL_FIELD` + runtime base maps + env cascade +
  caller `models` dict).
- **The coder is the file-mutating LLM** — the only execution agent given
  `Write/Edit/Bash` tools across all issues, invoked once per coding-loop iteration.

## Historical Context (from thoughts/)

- `thoughts/shared/research/2026-06-11-05-51-swe-af-prompts-and-prompting-wisdom.md` —
  Full audit of all 23 prompt role modules; canonical reasoner → prompt module → schema
  consumer map; module-shape convention; per-role token budgets.
- `thoughts/shared/research/2026-06-11-06-35-coding-specific-prompting-for-swe-af-agents.md`
  — Coding-specific prompting principles across all 24 modules; "one-line role vs
  persona" framing; control flow in harness vs prompt.
- `thoughts/shared/research/2026-06-11-06-45-backpressure-in-swe-af-harness.md` — Coding
  loop + verify→fix loop structure; where the coder sits; options for deterministic
  gating including a typed planner field as a configurable slot.
- `thoughts/shared/plans/2026-06-11-07-43-tdd-baml-typed-deterministic-backpressure.md`
  (+ `-REVIEW.md`) — Introduces `AcceptanceCheck` schema and `PlannedIssue.verification`
  field flowing planner → issue dict → coder context; touches PM/sprint-planner prompt
  shape and `ExecutionConfig`/`BuildConfig` wiring.
- `thoughts/shared/plans/2026-06-11-04-27-tdd-baml-structured-output-swe-af.md`
  (+ `-REVIEW.md`) — BAML structured-output parser seam in the reasoner pipeline.
- `thoughts/shared/reviews/scratch/{A..E}-*.md` — Citation-verification scratchpads for
  the above plans (BAML schemas, ci_gate runner, coding-loop insertion point, config
  schemas, PM/sprint-planner prompt producer).

No existing thought document covers an "implementer" rename or fully-pluggable workflow;
the closest prior art is the backpressure research's discussion of a typed, configurable
planner slot and the existing `execute_fn_target` external-agent seam.

## Related Beads Issues

- `SWE-AF-z10` (P2, open) — Follow-up: live-LLM verification of backpressure rung +
  output_format rollout.
- `SWE-AF-gnm` (P2, blocked) — Coder introduced prod-build breakages that passed tests
  but verification never caught (relates to coder behaviour / prompts).
- `SWE-AF-4of` (P1, blocked) — Full-suite verification loops on pre-existing failures.

## Open Questions

- Is the goal to make the *phase sequence* itself declarative (a config-defined DAG of
  agent stages), or only to substitute the per-issue implementer via the existing
  `execute_fn_target` seam? These are very different change scopes.
- Should `models.coder` / `coder_model` be renamed (breaking the public config API) or
  aliased (preserving backward compatibility via the existing `_LEGACY_*` pattern)?
- Should the rename also cover the `fast/` subsystem's coder wiring, or only the main
  `swe-planner` pipeline?
</content>
