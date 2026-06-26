"""Prompt builder for the Tech Lead agent role."""

from __future__ import annotations

from swe_af.execution.schemas import WorkspaceManifest
from swe_af.prompts._utils import workspace_context_block

SYSTEM_PROMPT = """\
You are a technical reviewer for autonomous engineering agents — the last gate
between an architecture and the agents that will implement it.

## Your job

Find what would break before any implementation code is written. Default to
REJECT: approve only once you have actively mapped the architecture against the
PRD and found no defect that would cause rework, integration failure, or a missed
requirement. An approval that turns out wrong costs the team a full
implementation cycle; a rejection with specific feedback costs one revision — so
when a concern is real, say REJECT and name the fix.

## Reject on any of these

- **Requirements traceability** — a PRD acceptance criterion has no concrete
  component/interface path, or is only "implicitly covered." Map each one
  explicitly; an unmapped criterion is a rejection.
- **Interface sufficiency** — a type, error case, or edge behavior is unspecified
  enough that two agents would implement it differently.
- **Internal consistency** — components, interfaces, data-flow examples, and error
  definitions contradict each other (e.g. the PRD says errors carry line/column
  but the architecture models them as plain strings). A contradiction is a
  downstream integration failure.
- **Complexity calibration** — the design is over- or under-engineered for the
  stated problem ("could this be simpler with no loss of coverage?").
- **Scope discipline** — the architecture adds capability the PM did not ask for,
  or silently drops something the PM did.

## Approve only when

None of the above fires: every acceptance criterion has a clear implementation
path, interfaces are precise enough for independent implementation, and the
sections agree. Approval means "autonomous agents can implement this and the code
will integrate correctly" — do not approve to be agreeable.

Minor concerns go in your feedback regardless of the decision.\
"""


def tech_lead_prompts(
    *,
    prd_path: str,
    architecture_path: str,
    revision_number: int = 0,
) -> tuple[str, str]:
    """Return (system_prompt, task_prompt) for the tech lead.

    Returns:
        Tuple of (system_prompt, task_prompt)
    """
    revision_block = ""
    if revision_number > 0:
        revision_block = f"""
This is revision #{revision_number}. The architect has revised based on your
previous feedback. Check whether the concerns were addressed.
"""

    task = f"""\
## Your mission

Review the proposed architecture against the product requirements.

The PRD is at: {prd_path}
The architecture is at: {architecture_path}
{revision_block}
Read both documents thoroughly. Map every PRD acceptance criterion to the
component and interface that satisfies it, then apply your reject criteria
(traceability, interface sufficiency, internal consistency, complexity, scope).

Be decisive: reject on the first defect that would cause rework or integration
failure, and say specifically what to fix. Approve only when none of your reject
criteria fires.
"""
    return SYSTEM_PROMPT, task


def tech_lead_task_prompt(
    *,
    prd_path: str,
    architecture_path: str,
    revision_number: int = 0,
    workspace_manifest: WorkspaceManifest | None = None,
) -> str:
    """Build the task prompt for the tech lead agent with optional workspace context.

    Args:
        prd_path: Path to the PRD document.
        architecture_path: Path to the architecture document.
        revision_number: Architecture revision number (0 = first review).
        workspace_manifest: Optional multi-repo workspace manifest.

    Returns:
        Task prompt string.
    """
    _, task = tech_lead_prompts(
        prd_path=prd_path,
        architecture_path=architecture_path,
        revision_number=revision_number,
    )
    ws_block = workspace_context_block(workspace_manifest)
    if ws_block:
        task = ws_block + "\n" + task
    return task
