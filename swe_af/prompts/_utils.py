"""Shared prompt utility functions for the prompts package."""

from __future__ import annotations

from swe_af.execution.schemas import WorkspaceManifest


def workspace_context_block(manifest: WorkspaceManifest | None) -> str:
    """Return a formatted multi-repo workspace context block for prompt injection.

    Returns an empty string when the manifest is None or contains only a single
    repository (no additional context needed for single-repo workflows).

    For multi-repo workspaces, returns a formatted block describing each
    repository's name, role, and absolute path on disk.

    Args:
        manifest: The WorkspaceManifest describing the cloned repositories,
                  or None if no workspace manifest is available.

    Returns:
        A formatted string block for inclusion in agent prompts, or an empty
        string if not applicable.
    """
    if manifest is None:
        return ""

    repos = manifest.repos
    if len(repos) <= 1:
        return ""

    lines: list[str] = [
        "## Workspace Repositories",
        "",
        "This task spans multiple repositories. Each repository is listed below with its role and local path:",
        "",
    ]

    for repo in repos:
        lines.append(f"- **{repo.repo_name}** (role: {repo.role}): `{repo.absolute_path}`")

    lines.append("")

    return "\n".join(lines)


def planning_artifacts_context_block(artifacts: "object | dict | None") -> str:
    """Summarize DDD planning artifacts for a prompt (Sprint Planner / Issue Writer).

    Returns an empty string when ``artifacts`` is None/empty. Summarizes — names
    and the vertical slice — rather than dumping the full JSON, and mandates the
    enriched ``PlannedIssue`` fields so generated issues carry context.
    """
    if not artifacts:
        return ""
    data = artifacts.model_dump() if hasattr(artifacts, "model_dump") else dict(artifacts)
    if not data:
        return ""

    lines: list[str] = ["## DDD Planning Artifacts", ""]

    contexts = data.get("bounded_contexts") or []
    if contexts:
        lines.append("### Bounded Contexts")
        for ctx in contexts:
            events = ", ".join(e.get("name", "") for e in ctx.get("domain_events", []))
            lines.append(f"- **{ctx.get('name', '')}** — domain events: {events or '(none)'}")
        lines.append("")

    read_models = data.get("read_models") or []
    if read_models:
        names = ", ".join(rm.get("name", "") for rm in read_models)
        lines.append(f"- CQRS-lite read models: {names}")

    slice_ = data.get("vertical_slice") or {}
    if slice_:
        lines.append(
            f"- Vertical slice: context `{slice_.get('bounded_context', '')}` exercising "
            f"events {', '.join(slice_.get('domain_events', [])) or '(none)'}"
        )
    lines.append("")

    lines.append(
        "### Required issue context fields\n"
        "Using these artifacts, every issue you emit MUST populate, where applicable: "
        "`bounded_context`, `contract_refs`, `domain_events`, `read_models`, `guardrails`, "
        "and `observability`. Mark exactly one issue with `slice_role = \"vertical-slice\"` "
        "— the end-to-end vertical slice that proves one aggregate/service/event/read-model "
        "path. Schedule instrumentation/observability work EARLY (not as final cleanup)."
    )

    return "\n".join(lines)
