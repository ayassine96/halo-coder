FROM ghcr.io/imran31415/devlaptop:v1.13.1

# HALO DevPod extensions
RUN pipx install opencode-chat pytest pytest-cov pytest-asyncio ruff mypy || true
RUN pipx install dagger-cli || true
RUN pipx install tree-sitter jedi || true

# Taskfile.dev
RUN curl -sL https://taskfile.dev/install.sh | sh

# Playwright browsers
RUN npx playwright install --with-deps chromium || true