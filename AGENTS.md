# AGENTS.md — HALO Factory Implementation Guide

## Project Overview

HALO Factory is a self-hosted, 24/7 agentic software factory running on a single-node
AMD Ryzen AI MAX+ 395 (Strix Halo) platform with 128 GB LPDDR5X. It accepts software
specifications, dispatches agents to implement them in isolated Kubernetes DevPods,
runs hermetic tests via Dagger, and presents results for human approval before merge.

**Base**: Forked from `kube-coder` (imran31415/kube-coder) at release v1.13.1.
**SRS**: See `HALO_Factory_MVP_SRS.md` for the full Software Requirements Specification.

---

## Architectural Decisions

### A1: Supervisor Runtime — Host-level systemd service
The Factory Orchestrator (supervisor) runs as a host-level systemd service, NOT a K3s
Deployment. Rationale: reliable inotify filesystem watching, direct K3s API access,
no pod restart loops, simpler crash recovery. The supervisor is the only component
that runs outside K3s; everything else is containerized.

### A2: LLM Backend — vLLM from the start
We use vLLM with PagedAttention as the primary inference backend from day one, configured
for ROCm `gfx1151` (Strix Halo). Accept the build complexity risk for the throughput gain.
llama.cpp `--parallel` remains a fallback if vLLM proves unstable.

Key ROCm env vars:
- `HSA_OVERRIDE_GFX_VERSION=11.5.1`
- `PYTORCH_ROCM_ARCH=gfx1151`
- `FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE`
- `ROCBLAS_USE_HIPBLASLT=1`
- `VGM_MODE=High` (up to 96 GB addressable)

### A3: Factory Floor — Separate service, vanilla JS + SSE
The Factory Floor dashboard is a standalone service at `:8888` using vanilla JS with SSE
(Server-Sent Events). No React, no Webpack, no build step for the core dashboard. D3.js or
Cytoscape.js loaded from CDN for the dependency graph. This avoids coupling with kube-coder's
Preact SPA and satisfies SRS FF-R2. Auth reuses kube-coder's oauth2-proxy pattern.

### A4: New Service Framework — FastAPI
All new HALO services (factory.py, tdad, agent-bridge) use FastAPI. Rationale: async
support, Pydantic validation, OpenAPI auto-docs, native SSE, clean dependency injection.
The existing kube-coder `server.py` (stdlib `http.server`) is left untouched — HALO
extensions are additive and run alongside it in the DevPod via the Agent-Bridge.

### A5: Git as Source of Truth
All spec state, architecture decisions, and agent memory are versioned in Git. Redis is
a cache/queue, not a database. If Redis is lost, the system recovers from Git state.
Status transitions are Git commits with conventional prefixes.

### A6: Existing Server.py — Untouched
The kube-coder `server.py` (7358 lines, stdlib `http.server`) is NOT rewritten. HALO
extensions integrate through the new Agent-Bridge service (:9000) running in each DevPod,
which proxies to server.py and the HALO Kernel as needed.

### A7: Memory — Dual Layer (SQLite + Qdrant)
- SQLite (existing kube-coder `memory/` package) stays for chat memory and structured queries.
- Qdrant is added for RAG vector search (embeddings of specs, ADRs, past PRs, error logs).
- Embedding model: BAAI/bge-large-en-v1.5 (dim=1024).
- RAG is rebuildable from Git (re-index all ARCH.md, specs/, src/ within 30 min).

### A8: Test Frameworks — Match kube-coder Patterns
- Python: `unittest` (stdlib), NOT pytest. Run via `python3 -m unittest discover`.
- SPA: Vitest + `@testing-library/preact` (for kube-coder's existing dashboards).
- Factory Floor: vanilla JS tested with a minimal test harness (no Vitest needed — pure DOM).
- Helm: `helm unittest` plugin v0.5.2, YAML-based assertions.
- New FastAPI services: `unittest` with `httpx` or `starlette.testclient` for async.

---

## Directory Structure

```
halo/                           # All new HALO Factory services
├── factory/                    # Factory Orchestrator (supervisor)
│   ├── supervisor.py           # Main event loop (inotify, state machine)
│   ├── dispatcher.py           # Redis Streams dispatch + agent roles
│   ├── devpod_manager.py       # K3s DevPod lifecycle
│   ├── event_publisher.py      # Redis Pub/Sub events
│   ├── recovery.py             # Crash recovery + idempotency
│   ├── circuit_breaker.py      # Model backend circuit breaking
│   ├── workflow.py             # Spec-driven workflow orchestration
│   ├── alerts.py              # ntfy alert integration
│   ├── agents/                 # Agent role implementations
│   │   ├── planner.py
│   │   ├── coder.py
│   │   ├── tester.py
│   │   ├── reviewer.py
│   │   ├── merger.py
│   │   └── prompts.py          # System prompt templates
│   └── systemd/                # systemd unit files
│       └── halo-supervisor.service
├── factory-floor/             # Factory Floor dashboard (vanilla JS + SSE)
│   ├── app.py                  # FastAPI backend (:8888)
│   ├── static/                 # Vanilla HTML/CSS/JS SPA
│   │   ├── index.html
│   │   ├── app.js
│   │   ├── kanban.js
│   │   ├── graph.js
│   │   ├── logs.js
│   │   ├── approvals.js
│   │   ├── devpods.js
│   │   ├── models.js
│   │   ├── command-palette.js
│   │   └── styles.css
│   └── csrf.py                 # CSRF protection middleware
├── tdad/                      # TDAD — Test Impact Analysis (FastAPI :8402)
│   ├── app.py                  # FastAPI service
│   ├── ast_builder.py          # tree-sitter AST → test graph
│   ├── graph_store.py          # Graph persistence + query
│   └── incremental.py          # Incremental index updates
├── kernel/                    # HALO Kernel — vLLM inference gateway
│   ├── gateway.py              # FastAPI OpenAI-compatible proxy (:13305)
│   ├── vllm_config.py          # vLLM config for ROCm gfx1151
│   ├── start_vllm.sh           # vLLM launch script
│   └── systemd/
│       └── halo-kernel.service
├── agent-bridge/              # Agent-Bridge — per-DevPod interface (FastAPI :9000)
│   ├── app.py                  # FastAPI service
│   └── static/                 # Pure HTML/CSS/JS dashboard
├── nanoclaw/                  # Nanoclaw — Unix socket concierge
│   ├── server.py               # /tmp/nanoclaw.sock JSON line protocol
│   └── memory.py               # memory.jsonl management
├── devpod/                    # DevPod extensions
│   ├── Dockerfile              # Extended halo-devpod image
│   └── templates/              # Per-language DevPod templates
│       ├── python-default/
│       ├── node-default/
│       ├── rust-default/
│       └── go-default/
├── dagger/                    # Dagger build engine integration
│   ├── pipelines/
│   │   ├── python_test.py
│   │   ├── node_test.py
│   │   └── e2e_test.py
│   ├── artifact_store.py      # MinIO artifact upload/download
│   └── engine_config.py       # Dagger engine config
├── specs/                     # Git-native state machine + spec parser
│   ├── parser.py               # Spec file YAML frontmatter parser
│   ├── state_machine.py        # Status transition engine
│   ├── dependency_resolver.py  # Topological sort, deps/blocks
│   ├── git_ops.py              # Git branch/commit/squash-merge/snapshot
│   └── arch_manager.py         # ARCH.md management
├── memory/                    # Memory & RAG subsystem
│   ├── rag_indexer.py          # Qdrant embedding pipeline
│   ├── rag_query.py            # Context retrieval for agent prompts
│   └── chat_memory.py          # memory.jsonl rotation
├── common/                    # Shared libraries
│   ├── redis_client.py         # Redis Streams + Pub/Sub wrapper
│   ├── minio_client.py         # S3 artifact client
│   ├── qdrant_client.py        # Vector DB client
│   ├── k3s_client.py           # K3s API wrapper (kubectl/python)
│   ├── git_utils.py            # Shared Git operations
│   ├── models.py               # Pydantic models (shared)
│   ├── logging.py              # Structured JSON logging
│   └── config.py               # Environment config loader
└── tests/                     # All HALO Python unit tests
    ├── test_spec_parser.py
    ├── test_state_machine.py
    ├── test_dependency_resolver.py
    ├── test_gateway.py
    ├── test_tdad.py
    ├── test_supervisor.py
    └── ...
```

---

## Coding Conventions

### Python
- Follow existing kube-coder style: stdlib-first, minimal external deps.
- FastAPI services use `async` endpoints, Pydantic models for request/response.
- Tests use `unittest.TestCase` (NOT pytest), matching kube-coder's pattern.
- Run tests: `python3 -m unittest discover -s halo/tests -p 'test_*.py' -v`
- Type hints encouraged but not mandatory (matches server.py style).
- No comments unless explaining non-obvious logic.

### JavaScript (Factory Floor)
- Vanilla JS, no framework, no build step. ES modules + `<script type="module">`.
- SSE via native `EventSource` API.
- D3.js or Cytoscape.js from CDN only (no npm install for the dashboard).
- Dark mode only (HALO aesthetic). Color coding per SRS FF-R6.

### Helm
- Follow kube-coder chart structure: `Chart.yaml`, `values.yaml`, `templates/`, `tests/`.
- Helm unittest YAML assertions in `charts/*/tests/`.
- Resource limits per SRS §7.2 budget table.

### Git
- Conventional commit prefixes: `feat(halo-*)`, `fix(halo-*)`, `test(halo-*)`, `chore(halo-*)`.
- Each stage has defined commit checkpoints (see Implementation Stages below).

---

## Test Commands

```bash
# HALO Python unit tests (all services)
make halo-tests

# HALO Python tests with coverage
make halo-coverage

# Helm lint for halo-infra chart
make halo-helm-lint

# Helm unittest for halo-infra chart
make halo-helm-test

# All HALO tests (Python + Helm)
make halo-test-all

# Kubernetes tests (existing kube-coder tests, still run)
make python-tests
make helm-test
make test-all-units
```

---

## Implementation Stages

### Stage 1 — Foundation, Scaffolding & AGENTS.md
- Create `AGENTS.md` (this file)
- Scaffold `halo/` directory structure with all service subdirectories
- Extend `Makefile` with HALO targets
- Extend `.github/workflows/ci.yml` with HALO test jobs
- Bump chart versions to `0.2.0` / `appVersion: 2.0.0-halo`

### Stage 2 — halo-infra Helm Chart (Redis, MinIO, Qdrant)
- `charts/halo-infra/` chart with Redis, MinIO, Qdrant Deployments + PVCs
- Network policies restricting access to halo namespace
- `halo/common/` client libraries (redis_client, minio_client, qdrant_client)
- Helm unittests + Python unit tests for clients

### Stage 3 — HALO Kernel (vLLM Inference Gateway)
- vLLM config for ROCm gfx1151 (Strix Halo)
- FastAPI gateway on :13305 (OpenAI-compatible proxy)
- Model profiles: halo-fast, halo-reasoning, halo-vision
- Admission control with queue awareness (HTTP 202 + Retry-After)
- Health metrics endpoint (Prometheus)
- systemd unit with auto-restart + exponential backoff

### Stage 4 — Git-Native State Machine & Spec Parser
- Spec file parser (YAML frontmatter + Markdown body)
- State machine with legal transition enforcement
- Dependency resolver (topological sort, depends_on, blocks, cycle detection)
- Git operations (branch creation, conventional commits, squash-merge, snapshot tags)
- ARCH.md manager

### Stage 5 — TDAD Service + Dagger Build Engine
- TDAD FastAPI :8402 (/analyze, /health, /metrics)
- tree-sitter AST builder for Python (jedi) and JS/TS
- Code→test graph with incremental updates, index persistence
- Dagger test pipelines (Python, Node, Playwright E2E)
- MinIO artifact upload (artifacts/{project}/{spec_id}/)
- Dagger engine Helm deployment

### Stage 6 — Factory Orchestrator (Supervisor)
- systemd supervisor with inotify watcher
- State machine integration (Stage 4)
- Redis Streams dispatch + agent role definitions
- DevPod scaling via K3s API
- Event publisher (Redis Pub/Sub, atomic Git+Redis)
- Crash recovery + idempotency
- Circuit breaker for model backend failures
- Full spec-driven workflow (WF-SPEC-1 through WF-SPEC-15)
- TDD loop, failure retry (max 3), TDAD/RAG injection
- ntfy alerts

### Stage 7 — DevPod Extensions (halo-devpod Image, Agent-Bridge, Nanoclaw)
- Extended halo-devpod Dockerfile (opencode, pytest, ruff, mypy, dagger, task, gh, tree-sitter)
- Per-language DevPod templates (python, node, rust, go)
- Agent-Bridge FastAPI :9000 (spec dashboard, SSE chat, file tree, launchers)
- Nanoclaw Unix socket service (/tmp/nanoclaw.sock, memory.jsonl, Kernel proxy)
- Helm chart extensions for HALO volumes + sidecars

### Stage 8 — Factory Floor Dashboard
- FastAPI :8888 backend (SSE relay, state snapshot, approval/trigger/reject/kill/pause endpoints)
- Vanilla JS SPA (Kanban board, dependency graph, log stream, approval queue)
- DevPod status, model utilization panels
- Command palette (Ctrl+K)
- Dark mode HALO aesthetic with color coding
- CSRF protection on all mutating endpoints
- Helm chart (Deployment, Service, Ingress, ConfigMap)

### Stage 9 — Memory & RAG + Agent Roles + Security/Reliability
- Qdrant RAG indexer (bge-large-en-v1.5 embeddings)
- RAG context query for agent prompt injection
- Chat memory rotation (memory.jsonl, 10MB rotation)
- Git-native rebuild capability (re-index from Git within 30 min)
- Agent role implementations (Planner, Coder, Tester, Reviewer, Merger)
- Merger-only write access to main (SSH key as K8s Secret)
- Network policies restricting DevPod egress
- Structured logging (JSON Lines at /var/log/halo/factory.log)
- Health checks for all components
- Graceful degradation (Qdrant/TDAD/Kernel/Dagger fail modes)
- Snapshot/restore via Git tags
- End-to-end integration tests

---

## Resource Budget (SRS §7.2)

| Component | RAM | VRAM | CPU Cores |
|-----------|-----|------|-----------|
| HALO Kernel (vLLM 70B Q4) | 48 GB | 48 GB | 2 |
| HALO Kernel (fast 14B) | 8 GB | 8 GB | 1 |
| HALO Kernel (vision/backup) | 4 GB | 4 GB | 1 |
| System + K3s | 4 GB | — | 2 |
| Supervisor + Factory API | 2 GB | — | 2 |
| TDAD | 2 GB | — | 2 |
| Qdrant + Mem0 | 4 GB | — | 2 |
| Redis + MinIO | 2 GB | — | 1 |
| Active DevPods (×2) | 8 GB | — | 4 |
| Headroom | 46 GB | — | 10 |
| **Total** | **128 GB** | **60 GB** | **16** |

---

## Key SRS References

- **Spec format**: `specs/SPEC-{NNN}.md` with YAML frontmatter (GIT-R1)
- **State machine**: `draft → ready → in_progress → implemented → merged | failed_*` (OR-R2)
- **Agent roles**: Planner, Coder, Tester, Reviewer, Merger (OR-R2 §4.2.2 table)
- **TDAD injection**: Before Coder writes code, inject affected tests into prompt (TDAD-R6)
- **Dagger hermetic**: All tests run in Dagger containers, no host execution (DAG-R2)
- **Approval gate**: Human clicks Approve on Factory Floor → squash-merge to main (FF-R4)
- **Dark mode**: Color coding per spec status (FF-R6)