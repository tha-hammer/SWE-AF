"""Pydantic schemas for the planning pipeline artifacts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from swe_af.hitl.ask_user import AskUserForm

_MAX_COMMAND_LEN = 2000


def _validate_command(value: str) -> str:
    """Guarantee an ``AcceptanceCheck.command`` is present, sane, and runnable.

    Presence/shape only — **not** safety. Commands are shell pipelines by design
    (``| jq``, ``>``, ``&&``); the validator must not reject metacharacters. The
    trust boundary is the worktree + container the harness already runs the agent's
    Bash under. The single bound it enforces beyond non-emptiness is a length cap,
    which catches a hallucinated essay-as-command.
    """
    if not value.strip():
        raise ValueError("command must be a non-empty, non-whitespace string")
    if len(value) > _MAX_COMMAND_LEN:
        raise ValueError(
            f"command exceeds {_MAX_COMMAND_LEN} chars (got {len(value)}); "
            "likely a hallucinated essay rather than a runnable command"
        )
    return value


class PRD(BaseModel):
    """Product Requirements Document produced by the product manager."""

    validated_description: str
    acceptance_criteria: list[str]
    must_have: list[str]
    nice_to_have: list[str]
    out_of_scope: list[str]
    assumptions: list[str] = []
    risks: list[str] = []
    ask_user_form: AskUserForm | None = None  # see swe_af/hitl/ for semantics


class ArchitectureComponent(BaseModel):
    """A single component in the architecture."""

    name: str
    responsibility: str
    touches_files: list[str] = []
    depends_on: list[str] = []


class ArchitectureDecision(BaseModel):
    """A key architectural decision with rationale."""

    decision: str
    rationale: str


# ---------------------------------------------------------------------------
# DDD modular planning artifacts (Architect-owned planning loop)
#
# These describe the DDD design of the TARGET project the agents are building.
# They are implementation-neutral: the names are domain vocabulary, not a
# commitment to Kafka/event-sourcing. The deterministic validator
# (validate_planning_artifacts) reads the field names defined here, so the schema
# is the single source of truth for that contract.
# ---------------------------------------------------------------------------


class ArchitectureDiagram(BaseModel):
    """A Mermaid software diagram (current or future state)."""

    title: str = ""
    mermaid: str  # Mermaid source, e.g. "flowchart TB ..."


class AggregateSpec(BaseModel):
    """An aggregate root within a bounded context."""

    name: str
    responsibility: str = ""
    invariants: list[str] = Field(default_factory=list)


class DomainServiceSpec(BaseModel):
    """A domain service within a bounded context."""

    name: str
    responsibility: str = ""


class DomainEventSpec(BaseModel):
    """A domain event emitted within a bounded context."""

    name: str
    producer_context: str  # which bounded context produces it
    payload_summary: str = ""


class BoundedContextSpec(BaseModel):
    """A bounded context: aggregates, services, and the events it produces."""

    name: str
    purpose: str = ""
    aggregates: list[AggregateSpec] = Field(default_factory=list)
    domain_services: list[DomainServiceSpec] = Field(default_factory=list)
    domain_events: list[DomainEventSpec] = Field(default_factory=list)


class ModuleContractSpec(BaseModel):
    """A code-level module contract between bounded contexts."""

    module: str
    provides: list[str] = Field(default_factory=list)
    consumes: list[str] = Field(default_factory=list)
    notes: str = ""


class InternalEventField(BaseModel):
    """A single field in the internal event schema."""

    name: str
    type: str = "string"


class InternalEventSchemaSpec(BaseModel):
    """The versioned envelope schema for the target project's internal events.

    This is the DESIGNED schema of the target system's events — distinct from
    ``PlanningEvent`` (SWE-AF's own planner-observability stream).
    """

    event_name: str
    event_version: str  # versioning rule, e.g. "v1" / semver
    metadata_fields: list[InternalEventField] = Field(default_factory=list)
    payload_fields: list[InternalEventField] = Field(default_factory=list)


class DataOwnershipRule(BaseModel):
    """Which bounded context owns/reads which data."""

    bounded_context: str
    owns: list[str] = Field(default_factory=list)
    reads: list[str] = Field(default_factory=list)


class EventBusPlan(BaseModel):
    """Implementation guidance for the internal event bus."""

    description: str = ""
    migration_notes: str = ""  # how to move to queue/pub-sub/Kafka later


class EventBackbonePlan(BaseModel):
    """The internal event backbone: default transport + migration justification."""

    default_transport: str = "in_process"  # default: simple hand-rolled in-process bus
    migration_justification: str = ""  # REQUIRED by the validator if not in_process
    bus: EventBusPlan = Field(default_factory=EventBusPlan)


class ReadModelSpec(BaseModel):
    """A CQRS-lite read model derived from one or more domain events."""

    name: str
    source_events: list[str] = Field(default_factory=list)
    purpose: str = ""


class ArchitecturalGuardrail(BaseModel):
    """An architectural guardrail and how it is enforced."""

    rule: str
    enforcement: str  # the enforcement mechanism (review, lint, test, structure)


class ObservabilityRequirement(BaseModel):
    """A first-class observability/instrumentation requirement."""

    name: str
    detail: str = ""


class VerticalSlicePlan(BaseModel):
    """The one end-to-end vertical slice proving a context path works."""

    bounded_context: str
    domain_events: list[str] = Field(default_factory=list)
    description: str = ""


class ExtractionStrategy(BaseModel):
    """When/how to extract a context after the slice is tested and functional."""

    gated_on: Literal["tested_slice"] = "tested_slice"
    description: str = ""


class ArchitecturePlanningArtifacts(BaseModel):
    """The typed DDD modular-planning artifact the Architect produces."""

    current_diagram: ArchitectureDiagram
    future_diagram: ArchitectureDiagram
    bounded_contexts: list[BoundedContextSpec] = Field(default_factory=list)
    module_contracts: list[ModuleContractSpec] = Field(default_factory=list)
    internal_event_schema: InternalEventSchemaSpec
    data_ownership: list[DataOwnershipRule] = Field(default_factory=list)
    event_backbone: EventBackbonePlan = Field(default_factory=EventBackbonePlan)
    read_models: list[ReadModelSpec] = Field(default_factory=list)
    guardrails: list[ArchitecturalGuardrail] = Field(default_factory=list)
    observability: list[ObservabilityRequirement] = Field(default_factory=list)
    vertical_slice: VerticalSlicePlan
    extraction_strategy: ExtractionStrategy = Field(default_factory=ExtractionStrategy)


class PlanningEvent(BaseModel):
    """SWE-AF's OWN planner-observability event (the internal planning stream).

    Distinct from ``InternalEventSchemaSpec`` (the target project's designed
    events). Appended to ``.artifacts/plan/planning-events.jsonl`` — see
    ``publish_planning_event``.
    """

    event_name: str
    event_version: str = "v1"
    occurred_at: str = ""  # ISO timestamp; injected by the caller's clock
    source_context: str = ""
    correlation_id: str = ""
    payload: dict = Field(default_factory=dict)


class Architecture(BaseModel):
    """Architecture document produced by the architect."""

    summary: str
    components: list[ArchitectureComponent]
    interfaces: list[str]
    decisions: list[ArchitectureDecision]
    file_changes_overview: str
    planning_artifacts: ArchitecturePlanningArtifacts | None = None


class ReviewResult(BaseModel):
    """Tech lead review of the architecture."""

    approved: bool
    feedback: str
    scope_issues: list[str] = []
    complexity_assessment: str = "appropriate"
    summary: str


class IssueGuidance(BaseModel):
    """Per-issue guidance from the sprint planner that shapes downstream agent behavior.

    Structured fields drive loop routing (e.g. needs_deeper_qa selects the flagged
    path). Freeform fields are injected into agent prompts to shape behavior.
    """

    # Structured — drives loop routing
    needs_new_tests: bool = True
    estimated_scope: str = "medium"       # "trivial" | "small" | "medium" | "large"
    touches_interfaces: bool = False
    needs_deeper_qa: bool = False         # True => flagged path (QA + reviewer + synthesizer)

    # Freeform — shapes agent behavior
    testing_guidance: str = ""            # Proportional test instructions
    review_focus: str = ""                # What reviewer should focus on
    risk_rationale: str = ""              # Why this needs (or doesn't need) deep QA


class AcceptanceCheck(BaseModel):
    """A runnable, deterministic acceptance check authored by the planner.

    ``command`` is a shell pipeline the harness runs via ``bash -c`` in the issue's
    worktree; its exit code is the verdict (0 = green). The Pydantic validator
    guarantees the command's *presence/shape* on **every** parse — both the
    agentfield SDK path and the BAML fallback path — making it the always-on
    validity guarantee (BAML asserts are not, because the bridge is fallback-first;
    see Behavior 0). ``kind`` lets the resolver prefer ``test``/``build`` commands.
    """

    description: str
    command: str
    kind: Literal["build", "test", "check"] = "check"

    @field_validator("command")
    @classmethod
    def _command_present_and_sane(cls, value: str) -> str:
        return _validate_command(value)


class PlannedIssue(BaseModel):
    """A single issue in the sprint plan."""

    name: str  # Kebab-case slug
    title: str  # Human-readable
    description: str  # Rich, self-contained for coder
    acceptance_criteria: list[str]  # Mapped from PRD
    depends_on: list[str] = []  # Issue names
    provides: list[str] = []  # What becomes available to dependents
    estimated_complexity: str = "medium"
    files_to_create: list[str] = []  # Files this issue is expected to create
    files_to_modify: list[str] = []  # Files this issue is expected to edit
    testing_strategy: str = ""  # Test file paths, framework, coverage expectations
    sequence_number: int | None = None  # Assigned after topo sort, used in file/branch naming
    guidance: IssueGuidance | None = None  # Per-issue guidance from sprint planner
    verification: list[AcceptanceCheck] = []  # Runnable checks for the deterministic rung
    target_repo: str = ""  # Target repository for multi-repo builds (empty = default/only repo)
    # DDD planning context (additive; populated when planning_artifacts drive the sprint)
    bounded_context: str = ""  # Which bounded context this issue belongs to
    contract_refs: list[str] = Field(default_factory=list)  # Module-contract references
    domain_events: list[str] = Field(default_factory=list)  # Domain events touched
    read_models: list[str] = Field(default_factory=list)  # CQRS-lite read models touched
    guardrails: list[str] = Field(default_factory=list)  # Architectural guardrails to honor
    observability: list[str] = Field(default_factory=list)  # Instrumentation to add
    slice_role: str = ""  # "vertical-slice" marks the end-to-end proving slice


class PlanResult(BaseModel):
    """Final output of the planning pipeline."""

    prd: PRD
    architecture: Architecture
    review: ReviewResult
    issues: list[PlannedIssue]
    levels: list[list[str]]  # Parallel execution levels from topo sort
    file_conflicts: list[dict] = []  # Informational only — merger agent handles resolution
    artifacts_dir: str
    rationale: str
    planning_artifacts: ArchitecturePlanningArtifacts | None = None  # DDD planning loop output
