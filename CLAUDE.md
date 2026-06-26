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

### Embedded-Mode Diagnostics

This repo uses Beads with embedded Dolt storage under `.beads/embeddeddolt/`.
Prefer these checks:

```bash
bd dolt status
bd config apply --dry-run
bd lint
bd dolt push
bd dolt pull
```

`bd doctor` is not currently supported in embedded mode, and `bd preflight`
prints Beads CLI project checks rather than SWE-AF project checks. If
`bd config validate` reports a missing `SWE_AF` database on `127.0.0.1:3307`,
rerun it without inherited shared-server environment variables:

```bash
env -u BEADS_DOLT_AUTO_START -u BEADS_DOLT_DATA_DIR -u BEADS_DOLT_SERVER_HOST -u BEADS_DOLT_SERVER_PORT bd config validate
```

This repo was verified with Homebrew `bd` 1.0.5 first in `PATH`; an older
`~/.local/bin/bd` may also exist and should not take precedence.

## Session Completion

**When ending a work session**, complete the checks below. Follow the active
`bd prime` profile for commit/sync/push authority.

**WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Sync/push only when authorized by the active profile or user**:
   ```bash
   git pull --rebase
   bd dolt push
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All completed changes are committed and pushed when push authority is active
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Do not leave completed Beads work unsynced when `bd prime` grants sync authority
- If push is authorized and fails, resolve and retry or report the blocker clearly
- In conservative mode, report status and proposed commands instead of pushing
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
