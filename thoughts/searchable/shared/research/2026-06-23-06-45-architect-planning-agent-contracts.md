---
date: 2026-06-23T06:45:14-04:00
researcher: maceo
git_commit: fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8
branch: main
repository: SWE-AF
topic: "Architect and planning agents: boundaries, responsibilities, interfaces, and contracts"
tags: [research, codebase, planning, architect, sprint-planner, issue-dag, replanner, contracts]
status: complete
last_updated: 2026-06-23
last_updated_by: maceo
related_issues: [SWE-AF-z10]
---

# Research: Architect and Planning Agent Contracts

**Date**: 2026-06-23 06:45 EDT (-0400)
**Researcher**: maceo
**Git Commit**: `fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8`
**Branch**: `main`
**Repository**: `SWE-AF` (`Agent-Field/SWE-AF`)

Permalink base for source references:
`https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/`

## Research Question

Research the architect and planning agents in SWE-AF: their boundaries,
responsibilities, interfaces, and contracts. The goal is to support later
enhancement of the architecture and planning steps without changing code during this
research pass.

## Executive Summary

SWE-AF has two planning surfaces:

1. The **full build planner** in
   [`swe_af/app.py:1547`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/app.py#L1547-L1740),
   which runs Product Manager -> optional Environment Scout -> Architect -> Tech
   Lead review loop -> Sprint Planner -> Issue Writer.
2. The **fast planner** in
   [`swe_af/fast/planner.py:55`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/fast/planner.py#L55-L145),
   which is a separate one-call path and deliberately does not invoke the full
   Product Manager, Architect, Tech Lead, Sprint Planner, or Issue Writer reasoners.

The full planner's main contract is a `PlanResult` containing a PRD, architecture,
tech-lead review, planned issue list, topological execution levels, file-conflict
advisories, an artifacts directory, and sprint-planner rationale. Execution consumes
that object as a DAG through `execute()` and `run_dag()`.

The **Architect** is responsible for the technical blueprint. It receives the PRD
and repository context, produces an `Architecture` schema, writes the architecture
artifact, and may be rerun with Tech Lead feedback. Its prompt explicitly treats the
architecture document as the single source of truth for downstream agents.

The **Sprint Planner** is responsible for turning PRD + Architecture into executable
DAG nodes. It does not write issue markdown files. It emits structured
`PlannedIssue` objects plus rationale. The planner owns dependency ordering,
parallelization boundaries, file ownership metadata, implementation guidance, and
acceptance criteria mapping.

The **Issue Writer** converts `PlannedIssue` stubs into concise issue markdown files.
This separates machine-readable planning data from human-readable/autonomous-agent
task files.

The **Replanner** is not part of initial planning. It is an execution-time recovery
agent invoked after unrecoverable issue failures. It consumes `DAGState`,
failed-issue results, adaptation history, escalation notes, PRD/architecture
summaries, and can continue, modify the DAG, reduce scope, or abort.

## Issue Tracker Context

`bd list --status=open` showed one open issue:

- `SWE-AF-z10` - Follow-up: live-LLM verification of backpressure rung +
  `output_format` rollout.

That issue is adjacent because historical planning docs discuss typed verification
arrays and structured-output rollout, but the current checkout at
`fcb87ad` does not contain the BAML bridge code described in those historical docs.
Current live structured-output handling is through `router.harness(..., schema=...)`
and the Codex harness patch in `swe_af/runtime/codex_harness_patch.py`.

## Planning Topology

The public app initializes the AgentField node as `swe-planner`, includes the
reasoner router, and exposes `build`, `plan`, and `execute` as top-level reasoners:

- [`swe_af/app.py:36`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/app.py#L36-L46)
  defines `NODE_ID`, creates the `Agent`, and includes the router.
- [`swe_af/reasoners/__init__.py:1`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/__init__.py#L1-L7)
  creates the planning/execution router and imports the modules that register
  reasoners.
- [`README.md:617`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/README.md#L617-L657)
  documents the `/build`, `/plan`, `/execute`, and direct specialist-call surface.

`build()` runs planning and git initialization concurrently, then passes the
completed `PlanResult` into execution:

- [`swe_af/app.py:754`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/app.py#L754-L787)
  starts `plan()` and `run_git_init()` in parallel.
- [`swe_af/app.py:1067`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/app.py#L1067-L1080)
  calls `execute()` with the plan result, git config, build id, and optional
  workspace manifest.

The initial full-planning sequence in `plan()` is:

| Stage | Function | Output contract | Primary artifact |
| --- | --- | --- | --- |
| Product Manager | `run_product_manager` | `PRD` | `.artifacts/plan/PRD.md` |
| Environment Scout | `run_environment_scout` | `ScoutResult` | merged into planning context |
| Architect | `run_architect` | `Architecture` | `.artifacts/plan/architecture.md` |
| Tech Lead | `run_tech_lead` | `ReviewResult` | `.artifacts/plan/review.json` |
| Sprint Planner | `run_sprint_planner` | `SprintPlanOutput` with `PlannedIssue[]` | structured issue stubs |
| Issue Writer | `run_issue_writer` | `{issue_name, issue_file_path, success}` | `.artifacts/plan/issues/*.md` |

Source anchors:

- [`swe_af/app.py:1563`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/app.py#L1563-L1740)
  is the full `plan()` reasoner.
- [`swe_af/reasoners/pipeline.py:158`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/pipeline.py#L158-L237)
  is `run_product_manager`.
- [`swe_af/reasoners/pipeline.py:357`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/pipeline.py#L357-L414)
  is `run_architect`.
- [`swe_af/reasoners/pipeline.py:417`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/pipeline.py#L417-L474)
  is `run_tech_lead`.
- [`swe_af/reasoners/pipeline.py:477`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/pipeline.py#L477-L549)
  is `run_sprint_planner`.
- [`swe_af/reasoners/execution_agents.py:445`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/execution_agents.py#L445-L523)
  is `run_issue_writer`.

## Shared Planning Schemas

The planning schema file is
[`swe_af/reasoners/schemas.py`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/schemas.py).
These models form the primary structured-output contract between prompts, LLM
responses, `plan()`, issue markdown generation, and execution.

| Schema | Lines | Contract |
| --- | --- | --- |
| `PRD` | [`10-20`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/schemas.py#L10-L20) | Product requirements, acceptance criteria, scope, assumptions, risks, optional ask-user form. |
| `ArchitectureComponent` | [`23-30`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/schemas.py#L23-L30) | Component name, responsibility, files, dependencies, interface. |
| `ArchitectureDecision` | [`32-37`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/schemas.py#L32-L37) | Decision, rationale, alternatives considered. |
| `Architecture` | [`39-47`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/schemas.py#L39-L47) | Architecture summary, components, interfaces, decisions, file-change overview. |
| `ReviewResult` | [`49-57`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/schemas.py#L49-L57) | Tech Lead approval gate and feedback. |
| `IssueGuidance` | [`59-75`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/schemas.py#L59-L75) | Planner-to-execution guidance flags, including deeper QA selection. |
| `PlannedIssue` | [`78-93`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/schemas.py#L78-L93) | The executable work-node specification. |
| `PlanResult` | [`96-106`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/schemas.py#L96-L106) | The complete planner output consumed by execution. |

`PlannedIssue` is the central boundary object. Required identity/work fields are
`name`, `title`, `description`, and `acceptance_criteria`. Execution-facing fields
include `depends_on`, `provides`, file lists, `testing_strategy`, `sequence_number`,
`guidance`, and `target_repo`.

`target_repo` defaults to an empty string, meaning default or only repo. Multi-repo
execution later resolves empty values to the primary repository where needed.

## Product Manager Boundary

The Product Manager is the first planning agent and owns the requirements contract.
Its prompt file is
[`swe_af/prompts/product_manager.py`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/prompts/product_manager.py).

Responsibilities from the system prompt:

- Own the contract between product vision and engineering execution.
- Ensure downstream agents can trace every future design and implementation decision
  to the PRD.
- Produce machine-verifiable acceptance criteria.
- Ask the user only for fundamental ambiguity that cannot be resolved from local
  context.

Interfaces:

- Prompt builder:
  [`product_manager_prompts(...)`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/prompts/product_manager.py#L99-L153)
  accepts `goal`, `repo_path`, `prd_path`, optional `additional_context`, and
  optional prior user responses.
- Task builder:
  [`pm_task_prompt(...)`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/prompts/product_manager.py#L155-L187)
  also accepts optional `workspace_manifest`.
- Runtime reasoner:
  [`run_product_manager(...)`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/pipeline.py#L158-L237)
  invokes `router.harness(..., schema=PRD, tools=[Read, Write, Glob, Grep, Bash])`
  and writes the PRD artifact.

Boundary notes:

- The PRD must avoid temporal sprint/deadline concepts.
- The PRD may emit an `ask_user_form`; the runtime wraps that into HITL behavior and
  reruns the Product Manager with user responses.
- This agent produces requirements, not architecture and not task decomposition.

## Architect Boundary

The Architect is the first architecture-producing agent in the full planner. Its
prompt file is
[`swe_af/prompts/architect.py`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/prompts/architect.py).

Responsibilities from the system prompt:

- Own the technical blueprint that downstream engineering agents will implement.
- Translate the PRD into a coherent system design grounded in the existing codebase.
- Define components, responsibilities, interfaces, dependencies, and file-change
  overview.
- Make parallel execution possible by describing file isolation, shared types, exact
  interface contracts, and module dependency graph.

Interfaces:

- Prompt builder:
  [`architect_prompts(...)`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/prompts/architect.py#L78-L135)
  accepts `prd`, `repo_path`, `prd_path`, `architecture_path`, and optional Tech Lead
  `feedback`.
- Task builder:
  [`architect_task_prompt(...)`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/prompts/architect.py#L137-L169)
  also accepts optional `workspace_manifest`.
- Runtime reasoner:
  [`run_architect(...)`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/pipeline.py#L357-L414)
  invokes `router.harness(..., schema=Architecture, tools=[Read, Write, Glob, Grep, Bash])`
  and writes the architecture artifact.

Output contract:

- `summary`
- `components: list[ArchitectureComponent]`
- `interfaces: list[str]`
- `decisions: list[ArchitectureDecision]`
- `file_changes: dict[str, str]`

Boundaries:

- The Architect writes the architecture artifact, not issue files.
- The Architect can be rerun with Tech Lead feedback during the review loop.
- The Architect prompt says future extension points should be documented without
  building speculative hooks or abstractions.
- It must provide exact interface signatures and error cases where the design depends
  on cross-agent integration.

## Tech Lead Review Boundary

The Tech Lead is the final quality gate before issue decomposition. Its prompt file is
[`swe_af/prompts/tech_lead.py`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/prompts/tech_lead.py).

Responsibilities:

- Review whether the architecture is complete, feasible, and aligned with the PRD.
- Reject if implementation agents would lack enough detail to work independently.
- Trace PRD acceptance criteria to architecture coverage.
- Flag ambiguous interfaces, missing contracts, complexity mismatch, contradictions,
  and scope drift.

Interfaces:

- Prompt builder:
  [`tech_lead_prompts(...)`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/prompts/tech_lead.py#L72-L123)
  accepts `prd_path`, `architecture_path`, and optional `revision_number`.
- Task builder:
  [`tech_lead_task_prompt(...)`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/prompts/tech_lead.py#L125-L151)
  also accepts optional `workspace_manifest`.
- Runtime reasoner:
  [`run_tech_lead(...)`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/pipeline.py#L417-L474)
  invokes `router.harness(..., schema=ReviewResult, tools=[Read, Glob, Grep])` and
  writes `review.json`.

Contract in `plan()`:

- [`swe_af/app.py:1615`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/app.py#L1615-L1646)
  loops through Tech Lead review and Architect revision.
- The loop allows up to three architecture revisions.
- If the review is not approved, `feedback` is passed back into `run_architect`.
- The final `review` object is included in `PlanResult` whether it was approved on
  the first pass or after revisions.

## Sprint Planner Boundary

The Sprint Planner is the bridge from architecture to execution DAG. Its prompt file
is
[`swe_af/prompts/sprint_planner.py`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/prompts/sprint_planner.py).

Responsibilities from the system prompt:

- Convert PRD + Architecture into a sequence of executable issues.
- Define work order, ownership, contracts between parallel workers, and independent
  vertical slices.
- Ensure each planned issue maps to PRD acceptance criteria and architecture
  components.
- Encode dependencies with `depends_on`.
- Encode outputs promised to downstream issues with `provides`.
- Set file ownership metadata for parallel execution.
- Set execution guidance, including whether deeper QA is needed.

Interfaces:

- Legacy/system builder:
  [`sprint_planner_prompts(...)`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/prompts/sprint_planner.py#L167-L244)
  accepts `prd`, `architecture`, `repo_path`, `prd_path`, and `architecture_path`.
- Active task builder:
  [`sprint_planner_task_prompt(...)`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/prompts/sprint_planner.py#L246-L336)
  accepts `goal`, `prd`, `architecture`, optional `workspace_manifest`, `repo_path`,
  `prd_path`, and `architecture_path`.
- Runtime reasoner:
  [`run_sprint_planner(...)`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/pipeline.py#L477-L549)
  defines an inner `SprintPlanOutput` schema with `issues: list[PlannedIssue]` and
  `rationale`.

Output fields requested by the prompt:

- `name`
- `title`
- `description`
- `depends_on`
- `provides`
- `files_to_modify`
- `files_to_create`
- `acceptance_criteria`
- `testing_strategy`
- `guidance`
- `target_repo`

Boundaries:

- The Sprint Planner does not write issue markdown files.
- The Sprint Planner does not include implementation code, function signatures, or
  step-by-step coding instructions in issues.
- The architecture remains the source of truth for implementation details.
- Parallel issues must be independently implementable and use architecture interface
  contracts as shared truth.
- File metadata is part of the execution planning contract, not merely prose.

## Issue Writer Boundary

The Issue Writer converts structured `PlannedIssue` data into issue markdown files
for autonomous implementation agents. It lives in the execution agents module because
it is a planning support writer but uses the execution-agent harness wiring:

- Prompt:
  [`swe_af/prompts/issue_writer.py`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/prompts/issue_writer.py).
- Runtime:
  [`run_issue_writer(...)`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/execution_agents.py#L445-L523).

Inputs:

- `issue`
- `prd_summary`
- `architecture_summary`
- `issues_dir`
- optional `prd_path`
- optional `architecture_path`
- optional `sibling_issues`
- optional `workspace_manifest`

Output schema:

```json
{
  "issue_name": "string",
  "issue_file_path": "string",
  "success": true
}
```

Boundaries:

- Write a concise issue file at `issues_dir/issue-<NN>-<name>.md`.
- Include WHAT, WHY, architecture reference, dependencies, acceptance criteria, files,
  and testing strategy.
- Do not copy large architecture sections.
- Do not include implementation code or copied function bodies.
- Keep issue files under 60 lines unless complexity requires more.

`plan()` calls all issue writers concurrently:

- [`swe_af/app.py:1678`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/app.py#L1678-L1724)
  launches writer calls with sibling issue context and records generated issue file
  paths.

## DAG Construction Contract

After `run_sprint_planner` returns issue dicts, `plan()` computes execution metadata:

- [`_compute_levels`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/pipeline.py#L52-L90)
  performs Kahn topological sorting over `issue["name"]` and `issue["depends_on"]`.
- [`_assign_sequence_numbers`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/pipeline.py#L134-L150)
  flattens topological levels while preserving sprint-planner order within each
  level.
- [`_validate_file_conflicts`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/pipeline.py#L93-L131)
  reports same-level file conflicts from `files_to_modify`.

Contract details:

- Issue identity is `name`.
- Dependencies are names in `depends_on`.
- Unknown dependency names are ignored by `_compute_levels`.
- Cycles raise `ValueError`.
- `levels` is a list of lists of issue names and is the execution scheduler input.
- File conflicts are advisory metadata in `PlanResult`, not a hard scheduling failure.

The final `PlanResult` is assembled at
[`swe_af/app.py:1731`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/app.py#L1731-L1740).

## Execution Handoff Contract

`execute()` consumes `PlanResult` and creates a `DAGState`:

- [`swe_af/app.py:1743`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/app.py#L1743-L1802)
  accepts `plan_result`, `repo_path`, optional `execute_fn_target`, optional config,
  git config, build id, optional `workspace_manifest`, and checkpoint label.
- [`swe_af/execution/dag_executor.py:744`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/dag_executor.py#L744-L806)
  initializes `DAGState` from `PlanResult`.
- [`swe_af/execution/dag_executor.py:1414`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/dag_executor.py#L1414-L1835)
  executes the DAG.

`DAGState` is defined in
[`swe_af/execution/schemas.py:276`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/schemas.py#L276-L330).
It stores:

- artifact paths
- PRD and architecture summaries
- `all_issues`
- `levels`
- completed, failed, skipped, and in-flight issue state
- current level
- replan history
- git branch and PR state
- merge/test history
- debt/adaptation state
- optional serialized workspace manifest

How planned issues become execution nodes:

- `run_dag()` builds `issue_by_name` from `all_issues`.
- It schedules active work by reading issue names from `dag_state.levels`.
- `_execute_level()` runs active issues concurrently, bounded by
  `config.max_concurrent_issues`.
- Worktree setup enriches issues with `worktree_path`, `branch_name`, and
  `integration_branch`.
- Multi-repo mode groups by `issue["target_repo"]` or the primary repo name.

Execution source anchors:

- [`_setup_worktrees`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/dag_executor.py#L54-L172)
- [`_enrich_issues_from_setup`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/dag_executor.py#L175-L203)
- [`_execute_level`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/dag_executor.py#L1156-L1285)
- [`run_coding_loop`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/coding_loop.py#L519-L766)

## Multi-Repo Planning and Execution Contract

Multi-repo input and workspace state are modeled in
[`swe_af/execution/schemas.py`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/schemas.py):

- `RepoSpec`:
  [`67-93`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/schemas.py#L67-L93)
- `WorkspaceRepo`:
  [`95-110`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/schemas.py#L95-L110)
- `WorkspaceManifest`:
  [`112-126`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/schemas.py#L112-L126)
- `BuildConfig` repo normalization:
  [`748-802`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/schemas.py#L748-L802)

Planning receives the workspace manifest:

- `build()` passes `workspace_manifest` to `plan()` at
  [`swe_af/app.py:757`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/app.py#L757-L764).
- `build()` passes the same manifest to `execute()` at
  [`swe_af/app.py:1070`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/app.py#L1070-L1079).
- Planning prompts use `workspace_context_block()` from
  [`swe_af/prompts/_utils.py:8`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/prompts/_utils.py#L8-L44).

The multi-repo planning contract is mostly prompt/schema based:

- `PlannedIssue.target_repo` identifies which repo an issue should modify.
- Empty `target_repo` means the default/only repo.
- Execution backfills `IssueResult.repo_name` from `target_repo` if the coding loop
  did not provide a repo name.

## Replanner Boundary

The Replanner is an execution-time recovery agent, not an initial planner stage. Its
prompt file is
[`swe_af/prompts/replanner.py`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/prompts/replanner.py).

Responsibilities:

- Own recovery after permanent issue failure.
- Decide whether execution should continue, modify the DAG, reduce scope, or abort.
- Preserve completed work.
- Avoid retrying the same failed approach.
- Ask the user only for project-level judgments.

Interfaces:

- Prompt builder:
  [`replanner_task_prompt(...)`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/prompts/replanner.py#L103-L260)
  receives `dag_state`, failed issue results, escalation notes, adaptation history,
  and prior user responses.
- Runtime reasoner:
  [`run_replanner(...)`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/reasoners/execution_agents.py#L319-L441)
  reconstructs `DAGState` and `IssueResult` objects, invokes
  `router.harness(..., schema=ReplanDecision)`, handles HITL ask-user forms, and
  falls back to `CONTINUE` on parser failure.
- Decision schema:
  [`ReplanDecision`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/schemas.py#L262-L273)
  supports `action`, `rationale`, updated issues, removed issue names, skipped issue
  names, new issues, summary, and optional ask-user form.

Runtime contract:

- `run_dag()` invokes the replanner after `FAILED_UNRECOVERABLE` or
  `FAILED_ESCALATED` results:
  [`swe_af/execution/dag_executor.py:1758`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/dag_executor.py#L1758-L1812).
- `_invoke_replanner_via_call()` delegates through AgentField:
  [`swe_af/execution/dag_executor.py:1304`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/dag_executor.py#L1304-L1350).
- `apply_replan()` mutates the DAG state:
  [`swe_af/execution/dag_utils.py:88`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/dag_utils.py#L88-L173).
- New and updated issue markdown files are written through `run_issue_writer`:
  [`swe_af/execution/dag_executor.py:1353`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/dag_executor.py#L1353-L1411).

`apply_replan()` contract details:

- Removes requested issues that are not completed.
- Marks requested issues as skipped.
- Updates existing issue dicts by name.
- Adds new issues.
- Assigns missing sequence numbers.
- Inherits `target_repo` from dependencies when possible.
- Recomputes levels.
- Resets `current_level`.
- Appends replan history.

## Fast Planner Boundary

The fast subsystem is separate from the full planning pipeline:

- [`swe_af/fast/planner.py:55`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/fast/planner.py#L55-L145)
  defines `fast_plan_tasks()`.
- [`swe_af/fast/schemas.py:42`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/fast/schemas.py#L42-L62)
  defines `FastTask` and `FastPlanResult`.
- [`swe_af/fast/prompts.py:5`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/fast/prompts.py#L5-L100)
  defines the fast planner system and task prompt.

Fast planning uses one LLM call, caps tasks, and has a deterministic fallback. It is
tested to avoid the full planner reasoners:

- [`tests/fast/test_planner.py:70`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/tests/fast/test_planner.py#L70-L87)
  asserts forbidden full-planner identifiers are absent from fast planner source.

## Model and Provider Configuration Contract

Planning roles are part of the role-to-config mapping in
[`swe_af/execution/schemas.py`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/schemas.py):

- `ROLE_TO_MODEL_FIELD` includes `pm`, `architect`, `tech_lead`,
  `sprint_planner`, `replan`, and `issue_writer`:
  [`469-487`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/schemas.py#L469-L487).
- `_LEGACY_GROUP_EQUIVALENTS` maps the `planning` group to PM, architect, tech lead,
  and sprint planner:
  [`496-501`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/schemas.py#L496-L501).
- `BuildConfig.to_execution_config_dict()` propagates runtime config into execution:
  [`825-851`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/schemas.py#L825-L851).
- `ExecutionConfig` exposes role-specific properties for architect, tech lead,
  sprint planner, replanner, and issue writer:
  [`998-1122`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/swe_af/execution/schemas.py#L998-L1122).

Documentation anchors:

- [`README.md:671`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/README.md#L671-L695)
  documents role config keys.
- [`docs/ARCHITECTURE.md:421`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/docs/ARCHITECTURE.md#L421-L438)
  documents runtime model/provider configuration.

## Structured Output Contract in This Checkout

Planning reasoners call `router.harness(..., schema=<Pydantic model>)`; schema
selection is the structured-output contract at the reasoner boundary.

Current checkout details:

- `swe_af/reasoners/pipeline.py` uses `schema=PRD`, `schema=Architecture`,
  `schema=ReviewResult`, and an inner `SprintPlanOutput`.
- `swe_af/reasoners/execution_agents.py` uses `schema=ReplanDecision` and the issue
  writer response model.
- `swe_af/runtime/codex_harness_patch.py` patches Codex-provider schema suffix and
  stdout parsing behavior.

Important historical-context distinction:

- Prior research/plans discuss BAML bridge code and BAML `output_format`.
- This checkout at `fcb87ad` does not contain `swe_af/baml_bridge.py` or live BAML
  parsing code.
- Therefore BAML notes are historical/branch context for planning enhancements, not
  the current live implementation contract in this worktree.

## Tests That Define the Contract

Planning pipeline tests:

- [`tests/test_planner_pipeline.py:158`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/tests/test_planner_pipeline.py#L158-L216)
  covers the happy path through Product Manager, Architect, Tech Lead, Sprint
  Planner, and Issue Writer.
- [`tests/test_planner_pipeline.py:218`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/tests/test_planner_pipeline.py#L218-L263)
  covers Tech Lead rejection and Architect revision.
- [`tests/test_planner_pipeline.py:265`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/tests/test_planner_pipeline.py#L265-L296)
  verifies independent issues share level 0.

Plan-to-execute tests:

- [`tests/test_planner_execute.py:25`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/tests/test_planner_execute.py#L25-L76)
  builds a minimal plan accepted by `_init_dag_state`.
- [`tests/test_planner_execute.py:78`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/tests/test_planner_execute.py#L78-L117)
  verifies `execute()` returns a `DAGState`-shaped dict.
- [`tests/test_planner_execute.py:125`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/tests/test_planner_execute.py#L125-L194)
  verifies `execute_fn_target` wiring.
- [`tests/test_conftest_malformed_planner_execute_nodeids_integration.py:137`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/tests/test_conftest_malformed_planner_execute_nodeids_integration.py#L137-L242)
  passes mocked `plan()` output into `execute()` and asserts levels/issues are emitted
  and consumed.

Multi-repo tests:

- [`tests/test_planned_issue_target_repo.py:35`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/tests/test_planned_issue_target_repo.py#L35-L62)
  verifies `PlannedIssue.target_repo` defaults and serialization.
- [`tests/test_dag_executor_multi_repo.py:514`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/tests/test_dag_executor_multi_repo.py#L514-L557)
  verifies `IssueResult.repo_name` backfill from `target_repo`.
- [`tests/test_execute_workspace_manifest_dag_pipeline.py:106`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/tests/test_execute_workspace_manifest_dag_pipeline.py#L106-L159)
  covers execute/run_dag workspace manifest passthrough.
- [`tests/test_multi_repo_prompts.py:144`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/tests/test_multi_repo_prompts.py#L144-L217)
  verifies sprint planner and coder prompt signatures/context for workspace manifest
  and target repo.

Fast planner tests:

- [`tests/fast/test_planner.py:70`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/tests/fast/test_planner.py#L70-L286)
  covers separation from the full planner, registration, functional behavior,
  fallback, and task cap behavior.

## Current Architecture Documentation

The repository docs already describe many of these contracts:

- [`docs/ARCHITECTURE.md:63`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/docs/ARCHITECTURE.md#L63-L99)
  documents the planning chain, issue DAG, `_compute_levels`, file conflicts, and
  `PlanResult`.
- [`docs/ARCHITECTURE.md:114`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/docs/ARCHITECTURE.md#L114-L176)
  documents hierarchical loops and replanning.
- [`docs/ARCHITECTURE.md:180`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/docs/ARCHITECTURE.md#L180-L199)
  documents structured concurrency gates.
- [`docs/ARCHITECTURE.md:245`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/docs/ARCHITECTURE.md#L245-L259)
  documents runtime plan mutation.
- [`docs/ARCHITECTURE.md:380`](https://github.com/Agent-Field/SWE-AF/blob/fcb87adbdc3d9da8b18bcf7e75d5046b99b026a8/docs/ARCHITECTURE.md#L380-L388)
  lists planning agents and responsibilities.

## Historical Context From Prior Research

The following existing research artifacts are relevant background. Paths are listed
without `searchable/` for long-term readability.

- `thoughts/shared/research/2026-06-11-05-51-swe-af-prompts-and-prompting-wisdom.md`
  documents the prompt inventory, prompt-builder conventions, and schema-driven
  `router.harness(..., schema=...)` pattern.
- `thoughts/shared/research/2026-06-11-06-35-coding-specific-prompting-for-swe-af-agents.md`
  frames fixed planner/control-flow ordering as harness responsibility rather than
  prompt responsibility.
- `thoughts/shared/research/2026-06-17-07-54-agent-prompt-seams-implementer-generalization.md`
  identifies prompt, role-wiring, and workflow seams; it records the planning
  subsequence as Product Manager -> Environment Scout -> Architect -> Tech
  Lead/Architect loop -> Sprint Planner -> Issue Writers.
- `thoughts/shared/research/2026-06-11-06-45-backpressure-in-swe-af-harness.md`
  records that deterministic backpressure existed only at post-PR CI and that
  command-like verification content was trapped in free-text fields.
- `thoughts/shared/plans/2026-06-11-07-43-tdd-baml-typed-deterministic-backpressure.md`
  discusses typed `AcceptanceCheck.command`, `PlannedIssue.verification`, manifest
  fallback, and planner-produced verification arrays. This appears to correspond to
  branch/planning context rather than the current live checkout.

## Open Questions for Later Enhancement Work

These questions were not answered by this research pass because they require product
or implementation direction rather than code reading:

- Should enhancement target the full planner only, or also the separate fast planner?
- Should architecture/planning enhancements be based on the current `main` checkout
  or the BAML/verification branch context referenced by `SWE-AF-z10`?
- Should `PlannedIssue` remain the sole execution-node contract, or should additional
  typed planner outputs be introduced before issue writing?
- Should file conflicts remain advisory in `PlanResult`, or become a planner-quality
  gate before execution?
- Should the Replanner stay execution-only, or should some recovery contract be
  shared with initial planning?

## Code Reference Index

- `swe_af/app.py` - public `build`, `plan`, `execute` reasoners and top-level
  orchestration.
- `swe_af/reasoners/pipeline.py` - full planning reasoners and DAG-level helpers.
- `swe_af/reasoners/schemas.py` - PRD, Architecture, ReviewResult, IssueGuidance,
  PlannedIssue, and PlanResult contracts.
- `swe_af/reasoners/execution_agents.py` - issue writer and replanner reasoners.
- `swe_af/prompts/product_manager.py` - Product Manager system and task prompts.
- `swe_af/prompts/architect.py` - Architect system and task prompts.
- `swe_af/prompts/tech_lead.py` - Tech Lead system and task prompts.
- `swe_af/prompts/sprint_planner.py` - Sprint Planner system and task prompts.
- `swe_af/prompts/issue_writer.py` - issue markdown generation prompt.
- `swe_af/prompts/replanner.py` - execution recovery prompt.
- `swe_af/execution/schemas.py` - execution DAG, replan, model config, and
  multi-repo schemas.
- `swe_af/execution/dag_executor.py` - DAG execution, worktree setup, and replan
  invocation.
- `swe_af/execution/dag_utils.py` - level recomputation and replan application.
- `swe_af/execution/coding_loop.py` - per-issue execution loop consuming
  `PlannedIssue` fields.
- `swe_af/fast/planner.py` - separate fast planning path.
- `docs/ARCHITECTURE.md` - human architecture documentation for the same contracts.
