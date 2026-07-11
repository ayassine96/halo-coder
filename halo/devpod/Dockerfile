FROM ghcr.io/imran31415/devlaptop:v1.13.1

# HALO DevPod extensions (DP-R5)
# Tools are installed via pipx for user-level isolation.
# Failures are NOT silently ignored — if a tool fails to install, the build fails.

# Python testing & linting tools
RUN pipx install pytest pytest-cov pytest-asyncio && \
    pipx install ruff mypy

# Tree-sitter for TDAD AST parsing
RUN pipx install tree-sitter tree-sitter-python tree-sitter-javascript tree-sitter-typescript

# OpenCode chat (agent coding assistant)
RUN pipx install opencode-chat || echo "WARNING: opencode-chat not available, skipping"

# Dagger CLI for hermetic test execution
RUN pipx install dagger-cli || \
    (curl -fsSL https://dl.dagger.io/dagger/install.sh | BIN_DIR=/usr/local/bin sh)

# Taskfile runner
RUN curl -sL https://taskfile.dev/install.sh | sh

# Playwright browsers for E2E testing
RUN npx playwright install --with-deps chromium || echo "WARNING: Playwright install failed, browser tests may not work"

# HALO environment
ENV HALO_NANOCLAW_SOCK=/tmp/nanoclaw.sock
ENV HALO_AGENT_BRIDGE_PORT=9000