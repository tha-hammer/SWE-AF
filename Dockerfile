FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps: git (worktrees, branches), curl (healthcheck), jq (agent bash),
# openssh-client (optional SSH git), gh CLI (draft PRs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl openssh-client jq nodejs npm && \
    # Install GitHub CLI
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        | tee /etc/apt/sources.list.d/github-cli.list > /dev/null && \
    apt-get update && apt-get install -y --no-install-recommends gh && \
    # Install OpenCode CLI v1.2+ for opencode provider (with run --model support)
    curl -fsSL https://opencode.ai/install | bash && \
    # Install Codex CLI for codex runtime provider
    npm install -g @openai/codex && \
    codex_path="$(command -v codex)" && \
    mv "${codex_path}" /usr/local/bin/codex-real && \
    printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    '' \
    'auth_mode="${SWE_CODEX_AUTH_MODE:-auto}"' \
    '' \
    'case "${auth_mode}" in' \
    '  chatgpt)' \
    '    unset OPENAI_API_KEY' \
    '    ;;' \
    '  api_key)' \
    '    if [ -z "${OPENAI_API_KEY:-}" ]; then' \
    '      echo "SWE_CODEX_AUTH_MODE=api_key requires OPENAI_API_KEY to be set" >&2' \
    '      exit 2' \
    '    fi' \
    '    ;;' \
    '  auto)' \
    '    ;;' \
    '  *)' \
    '    echo "Invalid SWE_CODEX_AUTH_MODE: ${auth_mode}. Expected one of: auto, chatgpt, api_key" >&2' \
    '    exit 2' \
    '    ;;' \
    'esac' \
    '' \
    'exec /usr/local/bin/codex-real "$@"' \
    > /usr/local/bin/codex && \
    chmod +x /usr/local/bin/codex && \
    rm -rf /var/lib/apt/lists/*

# Add OpenCode to PATH for non-interactive shells
ENV PATH="/root/.opencode/bin:${PATH}"

# Tell OpenCode to read its model AND small_model from the deployer's
# HARNESS_MODEL env var via {env:...} interpolation. Without this config,
# OpenCode auto-selects a small_model from whatever providers it finds
# keys for — landing on DeepSeek V3.1 in our environment, bypassing every
# env var the deployer set. Per-call -m on `opencode run` pins the main
# model regardless; small_model is what falls through to config, so it
# has to honor the same env var the rest of the stack uses.
#
# Default HARNESS_MODEL inside the image so a fresh container with no
# env override has *some* value to interpolate. Railway / docker-compose
# overrides win because their env injects after the image's ENV.
ENV HARNESS_MODEL=openrouter/moonshotai/kimi-k2.6
RUN mkdir -p /root/.config/opencode && \
    echo '{"$schema":"https://opencode.ai/config.json","model":"{env:HARNESS_MODEL}","small_model":"{env:HARNESS_MODEL}","provider":{"openrouter":{"options":{"apiKey":"{env:OPENROUTER_API_KEY}"}}}}' \
    > /root/.config/opencode/opencode.json

# Git identity — env vars take highest precedence and are inherited by all
# subprocesses including Claude Code agent instances spawned by the SDK
ENV GIT_AUTHOR_NAME="SWE-AF" \
    GIT_AUTHOR_EMAIL="eng@agentfield.ai" \
    GIT_COMMITTER_NAME="SWE-AF" \
    GIT_COMMITTER_EMAIL="eng@agentfield.ai"

# Configure git identity and use gh CLI as credential helper so all git
# HTTPS operations (clone, push, fetch) authenticate via GH_TOKEN at runtime.
RUN git config --global user.name "SWE-AF" && \
    git config --global user.email "eng@agentfield.ai" && \
    gh auth setup-git --hostname github.com --force

# Install uv for fast package installation
RUN pip install --no-cache-dir uv

# Install project dependencies
COPY requirements-docker.txt /app/requirements.txt
RUN uv pip install --system -r /app/requirements.txt

# Override the PyPI-published agentfield with the LOCAL checkout so SDK fixes
# land in the image before they're published to PyPI. The source comes from the
# `agentfield_sdk` build context (../agentfield/sdk/python), wired via
# build.additional_contexts in docker-compose*.yml — or for a raw build pass
# `docker build --build-context agentfield_sdk=../agentfield/sdk/python .`.
# Only pyproject/README/package are copied (the 424MB .venv stays out). Local
# version (0.1.90-rc.3) is LOWER than the PyPI 0.1.x already installed above, so
# --reinstall-package forces the swap regardless of version.
COPY --from=agentfield_sdk pyproject.toml README.md /app/vendor/agentfield/
COPY --from=agentfield_sdk agentfield /app/vendor/agentfield/agentfield
RUN uv pip install --system --reinstall-package agentfield /app/vendor/agentfield

# Copy application code
COPY . /app/

# Pre-create /workspaces so named-volume mounts inherit correct permissions
# (without this, Docker creates it as root read-only on fresh deployments)
RUN mkdir -p /workspaces && chmod 777 /workspaces

EXPOSE 8003

ENV PORT=8003 \
    AGENTFIELD_SERVER=http://control-plane:8080 \
    NODE_ID=swe-planner \
    # Runtime watchdog headroom (6h, the agentfield max). build() finalizes with
    # completed work at its own (smaller) budget BEFORE this fires, so a green
    # build is never reported "failed" by the watchdog. See _effective_build_budget_seconds.
    #
    # CRITICAL: the agentfield watchdog (async_config.AsyncConfig.from_environment)
    # ONLY reads the AGENTFIELD_ASYNC_-prefixed names. The unprefixed
    # `default_execution_timeout` below is read solely by SWE-AF's build-budget calc
    # (_effective_build_budget_seconds). They MUST agree, or the budget and the real
    # watchdog diverge: with only the unprefixed var set, the watchdog stayed at its
    # 7200s default while the budget rose to 6h, so build budgeted past the 2h kill
    # and green builds died as "failed". Set BOTH.
    AGENTFIELD_ASYNC_DEFAULT_EXECUTION_TIMEOUT=21600 \
    AGENTFIELD_ASYNC_MAX_EXECUTION_TIMEOUT=21600 \
    default_execution_timeout=21600

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD ["python", "-m", "swe_af"]
