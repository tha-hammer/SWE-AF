# SWE-AF Build Factory — Operations Runbook

How to build the agent image, run the build factory, submit/monitor builds, wire auth,
and avoid the known traps. **Read this before grepping the codebase to rediscover any of it.**

The factory: a `swe-planner` SDK node runs the `build` reasoner
(`plan → execute → verify → fix → PR`) against a target repo. A separate agentfield
**control-plane** orchestrates and serves the dashboard UI.

---

## 1. Build the agent image

The image installs `agentfield` from the **local sibling SDK** (`../agentfield/sdk/python`),
NOT PyPI, so local SDK fixes flow in. This is wired via BuildKit `additional_contexts`
(needs compose ≥ v5.1.3) in `docker-compose.yml` / `docker-compose.local.yml`:

```bash
docker compose build swe-agent      # builds the node image with the local agentfield SDK
```

To iterate on just the SDK against an existing image (fast path):
```bash
cd ../agentfield/sdk/python && uv build --wheel --out-dir /tmp/img
printf 'FROM swe-af-ddd:test\nCOPY *.whl /tmp/\nRUN pip install --force-reinstall --no-deps /tmp/*.whl\n' > /tmp/img/Dockerfile
docker build -t swe-af-ddd:codex /tmp/img
```

---

## 2. Run the factory — ONE control-plane, N nodes (NEVER port-sprawl)

The control-plane runs **many** builds concurrently and shows them all in **one UI on one
port**. **Do NOT spin up a second control-plane per build** — each has isolated local
storage, so its UI only shows its own runs (this fragments the UI across ports and is a
known footgun). To scale concurrency, add more **nodes** to the *same* control-plane with
**distinct `NODE_ID`s** (e.g. `swe-planner`, `swe-planner-codex`); submit to
`<NODE_ID>.build`. The dashboard is at `http://localhost:8080`.

- One node mounts the **parent dir** so any clone is reachable:
  `-v /home/maceo/Dev:/workspaces/dev` → builds set `repo_path=/workspaces/dev/<clone>`.
- A single node runs multiple builds concurrently (async). Host RAM is the real cap
  (~2–3 heavy builds per ~24G free).

---

## 3. Auth (subscription, no API spend)

| Runtime | Set | Leave empty | Source |
|---------|-----|-------------|--------|
| **claude_code** | `CLAUDE_CODE_OAUTH_TOKEN` (Max-plan `sk-ant-oat…`) | `ANTHROPIC_API_KEY` | durable token in `/home/maceo/Dev/silmari-agent-memory/.env` (mislabeled `ANTHROPIC_API_KEY` there, but it IS the OAuth token) |
| **codex** | mount `~/.codex:/root/.codex` (ChatGPT login) | `OPENAI_API_KEY` | host `codex login` |

Setting the API-key var makes the provider fast-fail (`PM failed to produce a valid PRD`).
Codex CLI uses `auth.json` only when `OPENAI_API_KEY` is unset.

---

## 4. Submit a build

```bash
curl -s -X POST http://localhost:8080/api/v1/execute/async/swe-planner.build \
  -H 'Content-Type: application/json' -d @payload.json
```
```jsonc
{ "input": {
  "goal": "…scope STRICTLY to one bounded context; READ <research/plan doc> first…",
  "repo_path": "/workspaces/dev/<clone>",
  "additional_context": "…",
  "config": { "runtime": "claude_code", "models": {…}, "enable_github_pr": false }
}}
```

**Model role keys** (in `config.models`; `"default"` overrides all):
`pm, architect, tech_lead, planning_loop, sprint_planner, issue_writer, issue_advisor, coder, qa,
code_reviewer, qa_synthesizer, verifier, replan, retry_advisor, git, merger,
integration_tester, ci_fixer` (`swe_af/execution/schemas.py:ROLE_TO_MODEL_FIELD`).

- **Claude:** `{"default":"sonnet","pm":"opus","architect":"opus","tech_lead":"opus","sprint_planner":"opus","issue_writer":"opus"}`, `runtime:"claude_code"`
- **Codex:** planner→`gpt-5.5`, qa/review→`gpt-5.4`, coder/default→`gpt-5.4-mini`, `runtime:"codex"`

---

## 5. Monitor

```bash
curl -s http://localhost:8080/api/v1/executions/<exec_id> | jq '{status,error}'
```
Status `running` → `succeeded` | `failed`. Watch progress via the clone's
`.artifacts/execution/checkpoint.json` (`completed_issues` / `all_issues`).

---

## 6. The watchdog (CRITICAL — read this)

The agentfield watchdog cancels the `build` reasoner after N seconds of active time.
**It reads ONLY the `AGENTFIELD_ASYNC_`-prefixed env name** (`async_config.AsyncConfig.from_environment`).
SWE-AF's finalize-budget (`_effective_build_budget_seconds`) reads the **unprefixed**
`default_execution_timeout`. **Both must be set and equal**, or the watchdog stays at its
7200s (2h) default while the budget thinks it has 6h → build budgets past the kill →
**green builds are reported "failed"**:

```
AGENTFIELD_ASYNC_DEFAULT_EXECUTION_TIMEOUT=21600
AGENTFIELD_ASYNC_MAX_EXECUTION_TIMEOUT=21600
default_execution_timeout=21600
```
(Baked into the Dockerfile ENV. Verify: `docker exec <node> python -c
"from agentfield.async_config import AsyncConfig; print(AsyncConfig.from_environment().default_execution_timeout)"` → `21600.0`.)

**`timeout ≠ failure`:** a build that "failed" with `timed out after Ns of active time`
but whose checkpoint shows N/N (or near) issues completed is a **green build the watchdog
killed during verify**. Inspect the checkpoint + git log before assuming failure; verify
with the slice's own tests.

---

## 7. Resume a watchdog/crash-killed build (don't re-run from scratch)

```bash
curl -s -X POST http://localhost:8080/api/v1/execute/async/swe-planner.resume_build \
  -d '{"input":{"repo_path":"/workspaces/dev/<clone>","artifacts_dir":".artifacts",
       "config":{"runtime":"claude_code","models":{…}}}}'
```
- `resume_build` re-runs **execution only** from `.artifacts/execution/checkpoint.json`
  (skips completed issues). No verify phase afterward.
- **Config is `ExecutionConfig`** — do **NOT** pass `enable_github_pr` (extra_forbidden).
- Use the **same `repo_path`** the build was created with (the checkpoint stores absolute
  container paths; a different mount path breaks it).
- Only works if the build never reached verify→fix (which overwrites the checkpoint).

---

## 8. Gotchas cheatsheet

- **Builds run as root** → the clone's `.git` / `.artifacts` / `node_modules` become
  root-owned. Before any host git/test op: `docker exec <node> chown -R 1000:1000 <path>`.
- **Successful builds delete `.artifacts`** (it's gitignored) on completion; only
  watchdog-killed ones leave it. Don't rely on a green build's `.artifacts` persisting.
- **Stale-artifact trap**: a leftover `prd.md` is NOT proof *this* run wrote one — check
  timestamps / wipe `.artifacts` (as root) before re-testing.
- **`docker logs <node>` WITHOUT `--tail`/`--since` OOMs the session** (multi-hundred-MB
  debug JSON, exit 137). Always `--tail N`.
- **codex structured output is SWE-AF's monkeypatch, NOT agentfield's provider.**
  `swe_af/runtime/codex_harness_patch.py` replaces `CodexProvider.execute` at runtime
  with a native path: `codex exec --json -m <model> --sandbox <mode> --output-schema
  <schema.json> --output-last-message <out.json>`, prompt piped via **stdin** (no prompt
  argv — so codex logs "Reading prompt from stdin…", which is normal banner noise, NOT
  the error). Editing `agentfield/harness/providers/codex.py` has NO effect on builds.
- **`Any`-typed Pydantic fields break codex `--output-schema` (the #1 PM failure).**
  Codex forwards the schema to OpenAI strict structured-outputs, which rejects any union
  branch lacking a `type` — e.g. `default_value: Any | None` (in `AskUserFormField`)
  renders the Any arm as a bare `{}`. Result: `invalid_json_schema` (400), ~10s fail,
  "failed to produce a valid PRD". Fixed in `_codex_strict_json_schema`
  (codex_harness_patch.py) by coercing typeless union arms to `{"type":"string"}`.
- **codex sandbox: default to `--dangerously-bypass-approvals-and-sandbox`.** codex's
  `workspace-write` sandbox uses `bwrap` (mount/user namespaces) which the container
  drops/blocks → intermittent `bwrap: Failed to make / slave: Permission denied`,
  silently dropping shell commands & file writes. The patch's default branch now uses
  the bypass (container is already externally sandboxed; an explicit `permission_mode`
  still overrides). Belt-and-suspenders: the compose codex node also sets
  `security_opt: [seccomp:unconfined]` so `unshare` works (`docker exec <node> bash -c
  'unshare --user echo ok'` must print `ok`).
- **planning loop model is configurable.** The architecture planning loop uses
  `models.planning_loop` and defaults through the selected runtime like other roles.
  For codex builds, set it to a codex model explicitly or let the codex runtime base
  default apply; do not let a Claude-only model such as `sonnet` reach
  `ai_provider=codex`.
- **codex `~/.codex` mount flips `config.toml` to root-owned.** The codex node runs as
  root; sharing the host `~/.codex` means codex rewrites `config.toml` as `root:root`
  600, locking the user's interactive TUI (`Permission denied (os error 13)`). Solution
  (now in compose): mount a dedicated `~/.codex-build` (isolated `config.toml` copy) with
  `auth.json` symlinked to the live file (so OAuth stays fresh), plus the live `auth.json`
  bind-mounted at the symlink target. One-off unlock: `docker run --rm -v
  ~/.codex:/root/.codex alpine chown 1000:1000 /root/.codex/config.toml`.
- **DB integration tests truncate tables** → run against a throwaway test DB, never the
  live one. The test DB superuser (`cosmichr_user`, `rolbypassrls`) **bypasses RLS**, so
  RLS-enforcement tests "fail" as an env artifact — not a code bug.
