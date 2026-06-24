# Project Instructions for AI Agents

This file provides instructions and context for AI coding agents working on this project.

> **🏭 Running / debugging the build factory (image build, control-plane + nodes, auth,
> submitting & monitoring builds, the watchdog env-var trap, `resume_build`, model role
> keys, codex setup, gotchas)? → [`docs/BUILD_RUNBOOK.md`](docs/BUILD_RUNBOOK.md).**
> Read it first — don't grep the codebase to rediscover this.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd dolt push
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->


## Build & Test

**Running the SWE-AF build factory (build the image, launch the control-plane + agent
nodes, submit/monitor/resume builds, wire Claude/Codex auth) → [`docs/BUILD_RUNBOOK.md`](docs/BUILD_RUNBOOK.md).**
It covers the non-obvious operational traps (the `AGENTFIELD_ASYNC_`-prefixed watchdog
env, `timeout ≠ failure`, root-owned `.artifacts`, codex `bwrap` bypass, one-control-plane
rule) so you don't have to rediscover them.

```bash
# Python deps / tests
uv sync --extra dev
uv run python -m pytest        # NOT bare `pytest`
```

## Architecture Overview

_Add a brief overview of your project architecture_

## Conventions & Patterns

_Add your project-specific conventions here_
