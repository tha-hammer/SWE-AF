---
date: 2026-06-24T15:33:47Z
researcher: maceo
git_commit: cdc0e4d (SWE-AF main) / 30f76e9a (agentfield main)
branch: main
repository: SWE-AF / agentfield
topic: "Codex CLI provider: fix file-write sandbox + diagnose shell exec failure"
tags: [codex, agentfield, harness, sandbox, docker, seccomp, unshare]
status: complete
last_updated: 2026-06-24
last_updated_by: maceo
type: implementation_strategy
---

# Handoff: Codex provider sandbox fixes + shell-exec root cause

## Task(s)

Debugging why `swe-planner-codex` builds fail. Three layers of bugs were found and fixed, with one remaining issue that is a container security constraint (not a code bug).

### Status summary

| Layer | Status | Notes |
|---|---|---|
| Fix 1: codex sandbox (bwrap) blocks file writes | ✅ Committed | `agentfield` commit `c35737f4` |
| Fix 2: `--sandbox workspace-write` uses bwrap (still fails in container) | ✅ Committed | `agentfield` commit `30f76e9a` — replaced with `--dangerously-bypass-approvals-and-sandbox` |
| Fix 3: `stdin` not closed — codex drains parent stdin | ✅ Committed | `agentfield` commit `c35737f4` — `stdin=DEVNULL` added to `run_cli` |
| Root cause remaining: shell exec (bash) blocked by seccomp in container | ❌ Not fixed | Requires Docker compose change, NOT a code fix |

---

## Critical References

- `agentfield` provider: `/home/maceo/Dev/agentfield/sdk/python/agentfield/harness/providers/codex.py`
- `agentfield` CLI runner: `/home/maceo/Dev/agentfield/sdk/python/agentfield/harness/_cli.py`
- SWE-AF Dockerfile (codex image): `/home/maceo/Dev/SWE-AF-baml/Dockerfile`
- Compose file used by running builds: `/tmp/ddd-build/compose.yml`

---

## Recent Changes

### agentfield repo (`/home/maceo/Dev/agentfield`)

**Commit `c35737f4` — "fix(codex): grant workspace-write sandbox + close stdin"**
- `sdk/python/agentfield/harness/providers/codex.py:25-30` — Replaced `--full-auto` with `--sandbox workspace-write` + `--skip-git-repo-check`. Made unconditional (no longer gated on `permission_mode == "auto"`).
- `sdk/python/agentfield/harness/_cli.py:61` — Added `stdin=asyncio.subprocess.DEVNULL` to `create_subprocess_exec` call.
- `sdk/python/tests/test_harness_provider_codex.py:146-154` — Updated unit test to match new flags.

**Commit `30f76e9a` — "fix(codex): use --dangerously-bypass-approvals-and-sandbox"**
- `sdk/python/agentfield/harness/providers/codex.py:30` — Replaced `--sandbox workspace-write` with `--dangerously-bypass-approvals-and-sandbox`.  
  **Why:** `--sandbox workspace-write` still invokes `bwrap` internally. `bwrap` requires unprivileged user namespaces (`kernel.unprivileged_userns_clone=1`) which Docker's default seccomp filter blocks. Verified: `--dangerously-bypass-approvals-and-sandbox` writes `.agentfield_output.json` correctly in the container.
- `sdk/python/tests/test_harness_provider_codex.py:146-154` — Updated unit test again to match.

---

## Learnings

### What was fixed
1. **Original failure mechanism:** codex `exec` defaults to read-only sandbox → bwrap rejects Write tool calls → `.agentfield_output.json` never created → `parse_and_validate` returns None → PM fails.
2. **Mis-diagnosis in the `/debug` input:** The finding claimed "codex reads prompt from stdin." This was wrong. Codex receives the prompt as a CLI positional arg correctly. The actual failure was bwrap blocking the Write syscall.
3. **`--sandbox workspace-write` still uses bwrap.** Only `--dangerously-bypass-approvals-and-sandbox` fully bypasses bwrap. Both flags exist in codex 0.140.0 (container) and 0.142.0 (host).
4. **stdin is NOT DEVNULL by default in `run_cli`.** `asyncio.create_subprocess_exec` inherits parent stdin without `stdin=DEVNULL`. This causes codex to drain the parent process's stdin ("Reading additional input from stdin…" on stderr). Fixed in `_cli.py`.

### Remaining root cause: shell exec blocked by seccomp
- `unshare --user` returns "Operation not permitted" in the container.
- `Seccomp: 2, Seccomp_filters: 1` — Docker's default seccomp profile is active.
- Codex 0.140.0 uses a "unified exec process" for shell commands that internally requires user namespace creation. This fails silently — the file write still works but `git status`, `rg`, bash scripts all fail.
- Reproducer: `docker exec ... codex exec --dangerously-bypass-approvals-and-sandbox ... "Add hello world endpoint"` → stderr shows `exec_command failed for /bin/bash -lc 'git status'`: `CreateProcess { message: "Rejected(...No such file or directory (os error 2)...)"}`.
- The PM task prompt asks codex to explore the repo (git, rg). These fail silently. Codex never produces the PRD. File is not written. Run fails.
- **This is NOT fixed by any flag** — it requires the container to run without the seccomp restriction.

### Fix required for shell exec
In `/tmp/ddd-build/compose.yml`, add to the `swe-agent-codex` service:

```yaml
security_opt:
  - seccomp:unconfined
```

OR rebuild compose with `--security-opt seccomp=unconfined` on the container.

Alternatively, enable on the Docker host:
```bash
sysctl -w kernel.unprivileged_userns_clone=1
```
(Host already has this = 1, but Docker's seccomp filter still blocks `unshare` syscall inside containers regardless.)

### Codex config in container
- Mounted from host: `/home/maceo/.codex` → `/root/.codex` in container.
- Config: `model = "gpt-5.5"`, `model_reasoning_effort = "xhigh"`.
- **Important:** config has `notify` hook pointing to `/home/maceo/Dev/mcp_agent_mail/.codex/hooks/notify_wrapper.sh` — this path may not exist inside the container and could trigger spurious errors.
- Trusted paths: `/home/maceo` and `/home/maceo/Dev` — these are HOST paths. Container paths (e.g. `/workspaces/dev/cosmic-HR`) are NOT trusted, so codex may add extra restrictions on them. `--skip-git-repo-check` bypasses the git-repo check but NOT necessarily trust level restrictions.

### Key file locations
- Codex binary in container: `/usr/local/bin/codex` (wrapper) → `/usr/local/bin/codex-real` (actual binary).
- Wrapper script handles `SWE_CODEX_AUTH_MODE` env var (auto/chatgpt/api_key).
- Auth: `/root/.codex/auth.json` (mounted from `/home/maceo/.codex/auth.json`).
- agentfield version in container: `0.1.90rc3` (already had our fixes baked in when image was checked).
- agentfield in harness runner: `_runner.py` handles schema retries; "Schema retry N provider error" is logged at WARNING level.

---

## Artifacts

- `/home/maceo/Dev/agentfield/sdk/python/agentfield/harness/providers/codex.py` — fixed provider
- `/home/maceo/Dev/agentfield/sdk/python/agentfield/harness/_cli.py` — fixed stdin=DEVNULL
- `/home/maceo/Dev/agentfield/sdk/python/tests/test_harness_provider_codex.py` — updated tests

---

## Action Items & Next Steps

1. **Add `security_opt: [seccomp:unconfined]` to compose.yml** for the `swe-agent-codex` service.
   - This is the only remaining blocker for codex shell commands.
   - Either edit `/tmp/ddd-build/compose.yml` directly and restart the container, OR find where compose.yml is generated (likely from the SWE-AF control-plane or a build trigger) and patch the template there.
   - The compose.yml at `/tmp/ddd-build/compose.yml` is ephemeral — find the canonical source.

2. **Find where `/tmp/ddd-build/compose.yml` is generated.**
   - The running container label shows `"com.docker.compose.project.config_files":"/tmp/ddd-build/compose.yml"`.
   - The SWE-AF control-plane or a launch script writes this file. Find it and add `security_opt`.

3. **Rebuild the `swe-af-ddd:codex` image** with the new agentfield from local source.
   - `cd /home/maceo/Dev/SWE-AF-baml && docker build -t swe-af-ddd:codex .`
   - The Dockerfile uses `agentfield>=0.1.84` from PyPI; if local fixes are not yet on PyPI, may need to install from local wheel.
   - Check: `cd /home/maceo/Dev/agentfield && uv build sdk/python` then copy wheel into image.

4. **Verify with a fresh codex build run** after seccomp fix + image rebuild.
   - The PM step should now: (a) call codex with bypass flag, (b) codex runs shell commands successfully, (c) codex writes `.agentfield_output.json`, (d) harness validates PRD, (e) pipeline continues.

5. **Optional: suppress the notify hook warning in container.**
   - The config has a notify hook path that may not exist. Can silence with `notify = []` override or by creating the file.

---

## Other Notes

### Running infrastructure at time of handoff
- Control plane: `ddd-build-control-plane-1` at `localhost:8080`
- Codex build node: `ddd-build-swe-agent-codex-1` (image `swe-af-ddd:codex`)
- Claude Code build node: `ddd-build-swe-agent-1` (image `swe-af-ddd:test`)
- Two Claude Code builds in progress at handoff time: `run_20260624_145850_c0rvhbs8` and `run_20260624_145850_ryefyakv` — both well into sprint planning (PM, architect, tech lead all succeeded).

### Useful commands for next session
```bash
# Check container codex version
docker exec ddd-build-swe-agent-codex-1 codex --version

# Check agentfield version in container
docker exec ddd-build-swe-agent-codex-1 python3 -c "import agentfield; print(agentfield.__version__)"

# Check codex provider code in container
docker exec ddd-build-swe-agent-codex-1 python3 -c "import agentfield.harness.providers.codex as c, inspect; print(inspect.getsource(c.CodexProvider.execute)[:300])"

# Reproduce the shell exec failure
docker exec -i ddd-build-swe-agent-codex-1 bash -c 'cd /tmp && git init -q cxtest5 && codex exec --json --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check -C /tmp/cxtest5 "Run git status and report the output." </dev/null 2>&1 | tail -5'

# Check seccomp in container
docker exec ddd-build-swe-agent-codex-1 bash -c 'cat /proc/self/status | grep Seccomp; unshare --user echo ok 2>&1'

# Get recent run status
curl -s "http://localhost:8080/api/ui/v2/workflow-runs?page=1&page_size=5&sort_by=updated_at&sort_order=desc" | python3 -c "import json,sys; [print(r.get('run_id'), r.get('status')) for r in json.load(sys.stdin).get('runs', [])]"
```

### agentfield test suite
```bash
cd /home/maceo/Dev/agentfield && uv run --project sdk/python pytest sdk/python/tests/test_harness_provider_codex.py
# 12/12 pass after our fixes
```
