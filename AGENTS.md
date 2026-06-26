# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd prime` for full workflow context.

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work atomically
bd close <id>         # Complete work
bd dolt push          # Push beads data to remote
```

## Beads Embedded-Mode Notes

This repo uses Beads with embedded Dolt storage under `.beads/embeddeddolt/`.
Use these diagnostics instead of assuming server mode:

```bash
bd dolt status
bd config apply --dry-run
bd lint
bd dolt push
bd dolt pull
```

`bd doctor` is not currently supported in embedded mode, and `bd preflight`
prints Beads CLI project checks, not SWE-AF project checks. If
`bd config validate` reports a missing `SWE_AF` database on `127.0.0.1:3307`,
rerun it without inherited shared-server environment variables:

```bash
env -u BEADS_DOLT_AUTO_START -u BEADS_DOLT_DATA_DIR -u BEADS_DOLT_SERVER_HOST -u BEADS_DOLT_SERVER_PORT bd config validate
```

This repo was verified with Homebrew `bd` 1.0.5 first in `PATH`; an older
`~/.local/bin/bd` may also exist and should not take precedence.

## Non-Interactive Shell Commands

**ALWAYS use non-interactive flags** with file operations to avoid hanging on confirmation prompts.

Shell commands like `cp`, `mv`, and `rm` may be aliased to include `-i` (interactive) mode on some systems, causing the agent to hang indefinitely waiting for y/n input.

**Use these forms instead:**
```bash
# Force overwrite without prompting
cp -f source dest           # NOT: cp source dest
mv -f source dest           # NOT: mv source dest
rm -f file                  # NOT: rm file

# For recursive operations
rm -rf directory            # NOT: rm -r directory
cp -rf source dest          # NOT: cp -r source dest
```

**Other commands that may prompt:**
- `scp` - use `-o BatchMode=yes` for non-interactive
- `ssh` - use `-o BatchMode=yes` to fail instead of prompting
- `apt-get` - use `-y` flag
- `brew` - use `HOMEBREW_NO_AUTO_UPDATE=1` env var

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
