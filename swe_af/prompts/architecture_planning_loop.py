"""Prompt builder for the Architect-owned DDD modular planning loop.

Produces the typed ``ArchitecturePlanningArtifacts`` between Tech Lead approval and
Sprint Planner decomposition: current/future diagrams, bounded contexts, an
internal event backbone (defaulting to a simple in-process bus), code-level module
contracts, internal event schema, data ownership, CQRS-lite read models,
guardrails, observability, one vertical slice, and an extraction strategy.
"""

from __future__ import annotations

from swe_af.execution.schemas import WorkspaceManifest
from swe_af.prompts._utils import workspace_context_block
from swe_af.reasoners.schemas import Architecture, PRD

SYSTEM_PROMPT = """\
You are a Domain-Driven-Design architect. The architecture has already been
approved at a high level. Your job is to take it ONE level deeper into a typed,
modular DDD plan that the Sprint Planner can decompose into context-rich issues.

You are designing the TARGET project's domain — not SWE-AF itself. Keep the design
implementation-neutral: prefer a Modular Monolith with a simple in-process event
backbone. Do NOT introduce Kafka, a production queue, or a distributed platform
unless there is a concrete, stated reason — in which case you MUST justify it.

Produce an ArchitecturePlanningArtifacts object that:
- gives a current AND a future Mermaid software diagram,
- defines bounded contexts, each with at least one aggregate, one domain service,
  and one domain event (every domain event names its producer context),
- designs a Modular Monolith + Internal Event Backbone whose default transport is
  `in_process`; if you choose another transport you MUST set migration_justification,
- defines code-level module contracts, a versioned internal event schema (event
  name, version rule, metadata fields, payload fields), explicit data ownership,
  CQRS-lite read models (each referencing its source events), architectural
  guardrails (each with an enforcement mechanism), and first-class observability
  requirements,
- defines exactly one end-to-end vertical slice (a bounded context + the domain
  events it exercises) that proves one aggregate/service/event/read-model path,
- defines an extraction strategy gated on a tested, functional slice
  (`gated_on = "tested_slice"`).

Prioritize instrumentation/observability as first-class work, not cleanup.
"""


def architecture_planning_loop_task_prompt(
    *,
    prd: dict | PRD,
    architecture: dict | Architecture,
    repo_path: str,
    architecture_path: str = "",
    planning_artifacts_path: str = "",
    validation_feedback: list[str] | None = None,
    workspace_manifest: WorkspaceManifest | None = None,
) -> str:
    """Build the task prompt for the DDD planning-loop agent."""
    prd_obj = prd if isinstance(prd, PRD) else PRD(**prd)
    arch_obj = architecture if isinstance(architecture, Architecture) else Architecture(**architecture)

    sections: list[str] = []

    ws_block = workspace_context_block(workspace_manifest)
    if ws_block:
        sections.append(ws_block)

    sections.append("## DDD Modular Planning Task")
    sections.append(f"- **Repository path**: `{repo_path}`")
    if architecture_path:
        sections.append(f"- **Approved architecture**: `{architecture_path}`")
    if planning_artifacts_path:
        sections.append(f"- **Write the planning appendix to**: `{planning_artifacts_path}`")

    sections.append(f"\n### Goal\n{prd_obj.validated_description}")
    sections.append(f"\n### Approved Architecture Summary\n{arch_obj.summary}")
    if arch_obj.components:
        names = ", ".join(c.name for c in arch_obj.components)
        sections.append(f"\n### Existing Components\n{names}")

    if validation_feedback:
        sections.append(
            "\n### Validation Feedback — FIX THESE (a deterministic validator "
            "rejected the previous attempt)"
        )
        sections.extend(f"- {item}" for item in validation_feedback)

    sections.append(
        "\n## Your Task\n"
        "1. Produce the current software diagram (Mermaid).\n"
        "2. Produce the future software diagram (Mermaid).\n"
        "3. Define bounded contexts with aggregates, domain services, and domain events.\n"
        "4. Design the modular monolith + internal event backbone (default in_process).\n"
        "5. Define module contracts, internal event schema, data ownership, CQRS-lite "
        "read models, guardrails, and observability requirements.\n"
        "6. Define one vertical slice and an extraction strategy gated on a tested slice.\n"
        "7. Return an ArchitecturePlanningArtifacts JSON object."
    )

    return "\n".join(sections)
