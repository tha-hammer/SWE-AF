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

When you go “one level deeper” (aggregates, services, events), you’re really answering:

Where does truth live, where does behavior live, and how does change propagate?

Here are the practical guidelines—not theoretical, but what actually holds up

1. Aggregates — “What must always be consistent?”
Core rule

An aggregate is a consistency boundary, not a data grouping.

Guidelines
One transactional truth per aggregate
Example: Contract ensures pricing + terms are valid together
Keep aggregates small
If it grows large → you are modeling a workflow, not a boundary
Reference other aggregates by ID only
Never embed full objects across domains
Protect invariants

Example:
A Decision must have an owner before approval
A Claim must always link to a source conversation
Anti-patterns
“God aggregates” (e.g., Project with everything inside)
Cross-domain joins inside aggregates

2. Domain Services — “Where does behavior go?”
Core rule
Use a service when behavior doesn not naturally belong to a single aggregate

Guidelines
Use services for:
Cross-aggregate logic
e.g., linking a Decision to multiple Claims
External interactions
LLM calls, vendor APIs
Complex computations
dependency resolution, simulations
Keep services:
Stateless
Focused on one capability
Litmus test
If you are asking:

“Who should own this logic?” → probably a service
3. Domain Events — “What happened that others should care about?”
Core rule
Events represent facts, not commands or intentions

Guidelines
Name events in past tense
✅ ContractCreated
❌ CreateContract
Events should be:
Immutable
Minimal but meaningful
Carry IDs, not full objects
Emit events when:
A business-relevant change occurs
Other domains might react
Anti-patterns
Emitting events for everything (noise)
Using events for internal method calls
4. Boundaries Between Contexts
Core rule
Each bounded context owns its language and model

Guidelines
Same concept ≠ same model across domains
“Owner” in Procurement ≠ “Owner” in Org context
Communicate via:
Events (preferred)
Interfaces (if synchronous needed)
5. Invariants vs Eventual Consistency
Key distinction
Inside aggregate → strong consistency
Across aggregates/domains → eventual consistency via events
Example
Contract pricing must be correct → inside aggregate
Contract affects budget → via ContractCreated event
6. Event Design Heuristics (Very Important for You)
Given your system is event-heavy:

Good events:
Change state meaningfully
Trigger downstream behavior
Bad events:
UI-driven (“ButtonClicked”)
Technical (“RowUpdated”)
7. Align with Your Systems Nature
Your system is:

Conversation-driven
Audit-heavy
Cross-domain
So prioritize:

Strong aggregates in:
Ground Truth (Claims, Decisions)
Procurement (Contracts)
Service-heavy in:
Extraction (LLM)
Dependency mapping
Simulation
Event-heavy across:
Everything
8. A Simple Mental Checklist
For each piece of logic, ask:

Step 1 — Is this state?
→ Aggregate

Step 2 — Is this behavior across things?
→ Service

Step 3 — Did something happen others care about?
→ Event

9. Example Applied (Exploded View Feature)
Aggregate
DependencyNode
DependencyEdge
Service
DependencyResolutionService
ImpactPropagationService
Events
DependencyMapped
CascadeImpactDetected
10. The Real Goal
You are organizing code AND you are building:

A system where truth is reliable, behavior is predictable, and change is observable

One-line summary
Aggregates protect truth, services execute logic, and events broadcast change—your job is to keep those responsibilities clean and non-overlapping.

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
