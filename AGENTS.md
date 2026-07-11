# AGENTS.md — HALO Factory Implementation Guide (Pass 2)

## Project Overview

HALO Factory is a self-hosted, 24/7 agentic software factory running on a single-node
AMD Ryzen AI MAX+ 395 (Strix Halo) platform with 128 GB LPDDR5X. It accepts software
specifications, dispatches agents to implement them in isolated Kubernetes DevPods,
runs hermetic tests via Dagger, and presents results for human approval before merge.

**Base**: Forked from `kube-coder` (imran31415/kube-coder) at release v1.13.1.
**SRS**: See `HALO_Factory_MVP_SRS.md` for the full Software Requirements Specification.
**Pass 2 Status**: 271 unit tests, all stubs replaced with real implementations.

---

## Architectural Decisions

### A1: Supervisor Runtime — Host-level systemd service
The Factory Orchestrator (supervisor) runs as a host-level systemd service, NOT a K3s
Deployment. Rationale: reliable inotify filesystem watching, direct K3s API access,
no pod restart loops, simpler crash recovery. The supervisor is the only component
that runs outside K3s; everything else is containerized.

### A2: LLM Backend — Lemonade (updated from vLLM in Pass 2)
Pass 1 planned vLLM. Pass 2 uses **Lemonade** (`:13305`) as the primary LLM backend
because it's already running with 7 models on the Strix Halo node, is OpenAI-compatible,
and requires no build complexity. The HALO Kernel gateway (`:13306`) proxies to it via
`httpx.AsyncClient`. vLLM remains a future upgrade path if Lemonade throughput is insufficient.

Key ROCm env vars (for future vLLM migration):
- `HSA_OVERRIDE_GFX_VERSION=11.5.1`
- `PYTORCH_ROCM_ARCH=gfx1151`
- `FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE`
- `ROCBLAS_USE_HIPBLASLT=1`
- `VGM_MODE=High` (up to 96 GB addressable)

Model profile mapping (Lemonade):
- `halo-reasoning` → Qwen3-Next-80B-A3B-Instruct-GGUF-Q8_0 (Planner, Reviewer)
- `halo-coder` → Qwen3-Coder-30B-A3B-Instruct-GGUF (Coder agent)
- `halo-fast` → Qwen3-8B-GGUF (Tester, Merger, quick tasks)
- `halo-vision` → Qwen2.5-VL-7B-Instruct-GGUF (diagram/screenshot)

### A3: Factory Floor — Separate service, vanilla JS + SSE
The Factory Floor dashboard is a standalone service at `:8888` using vanilla JS with SSE
(Server-Sent Events). No React, no Webpack, no build step for the core dashboard. D3.js
loaded from CDN for the dependency graph. This avoids coupling with kube-coder's
Preact SPA and satisfies SRS FF-R2. Auth reuses kube-coder's oauth2-proxy pattern.

### A4: New Service Framework — FastAPI
All new HALO services (factory, tdad, agent-bridge, supervisor_api) use FastAPI.
Rationale: async support, Pydantic validation, OpenAPI auto-docs, native SSE, clean
dependency injection. The existing kube-coder `server.py` (stdlib `http.server`) is
left untouched — HALO extensions are additive.

### A5: Git as Source of Truth
All spec state, architecture decisions, and agent memory are versioned in Git. Redis is
a cache/queue, not a database. If Redis is lost, the system recovers from Git state.
Status transitions are Git commits with conventional prefixes.

### A6: Existing Server.py — Untouched
The kube-coder `server.py` (7358 lines, stdlib `http.server`) is NOT rewritten. HALO
extensions integrate through the new Agent-Bridge service (:19000) which proxies to
server.py and the HALO Kernel as needed.

### A7: Memory — Dual Layer (SQLite + Qdrant)
- SQLite (existing kube-coder `memory/` package) stays for chat memory and structured queries.
- Qdrant is added for RAG vector search (embeddings of specs, ADRs, past PRs, error logs).
- Embedding model: BAAI/bge-large-en-v1.5 (dim=1024) via sentence-transformers (Pass 2).
- Hash-based fallback if sentence-transformers not installed (graceful degradation).
- RAG is rebuildable from Git (re-index all ARCH.md, specs/, src/ within 30 min).

### A8: Test Frameworks — Match kube-coder Patterns
- Python: `unittest` (stdlib), NOT pytest. Run via `python3 -m unittest discover`.
- SPA: Vitest + `@testing-library/preact` (for kube-coder's existing dashboards).
- Factory Floor: vanilla JS tested with Playwright (Pass 2).
- Helm: `helm unittest` plugin v0.5.2, YAML-based assertions.
- New FastAPI services: `unittest` with `httpx` or `starlette.testclient` for async.

### A9: Supervisor HTTP API (Pass 2)
The Supervisor gains a FastAPI HTTP server at `:9091` for state, mutations, SSE, health,
and metrics. Factory Floor (:8888) becomes a **thin proxy** — all `/api/*` calls are
forwarded to the Supervisor via `httpx`. Business logic lives in the Supervisor (single
source of truth). Factory Floor can be restarted without affecting the pipeline.

### A10: Lemonade as Primary LLM Backend (Pass 2)
Pass 1 planned vLLM (A2). Pass 2 uses Lemonade (`:13305`) because it's already running
with 7 models. The HALO Kernel gateway proxies to it via `httpx.AsyncClient`. vLLM
remains a future upgrade path. See A2 for model mapping.

### A11: Dagger for Hermetic Test Execution (Pass 2)
Install Dagger CLI on the host. All test pipelines run in Dagger containers:
- Python: `python:3.12-slim` with pytest
- Node: `node:20-slim` with npm/yarn test
- E2E: Playwright container
Three-tier fallback: Dagger → `docker run` → host subprocess (per REL-4, logged as warning).

---

## Service Port Map (Pass 2)

| Service | Port | Module | Notes |
|---------|------|--------|-------|
| Lemonade (external) | :13305 | — | LLM backend, must be running |
| HALO Kernel (proxy) | :13306 | `halo.kernel.gateway:app` | httpx proxy to Lemonade |
| Supervisor API | :9091 | `halo.factory.supervisor_api:app` | State, mutations, SSE, health |
| Factory Floor | :8888 | `halo.factory_floor.app:app` | Thin proxy to Supervisor |
| TDAD | :8402 | `halo.tdad.app:app` | tree-sitter AST + graph store |
| Agent-Bridge | :19000 | `halo.agent_bridge.app:app` | Nanoclaw proxy, spec/file endpoints |
| Nanoclaw | socket | `halo.nanoclaw.server` | /tmp/nanoclaw.sock, JSON line protocol |
| Redis | :6379 | — | Streams + Pub/Sub + log persistence |

---

## Quick Start (Pass 2)

```bash
# 1. Stop any stale processes
make halo-stop

# 2. Start Redis (if not already running)
docker run -d --name halo-redis -p 6379:6379 redis:7-alpine

# 3. Create demo spec
make halo-demo

# 4. Start all services
make halo-start

# 5. Check status
make halo-status

# 6. Run smoke tests
make halo-smoke

# 7. Open Factory Floor in browser
#    http://localhost:8888

# 8. Stop when done
make halo-stop
```

---

## Directory Structure (Pass 2)

```
halo/                           # All HALO Factory services
├── factory/                    # Factory Orchestrator (supervisor)
│   ├── supervisor.py           # Main event loop (inotify + API server, A1/A9)
│   ├── supervisor_api.py       # FastAPI HTTP API (:9091, A9, Pass 2 NEW)
│   ├── dispatcher.py           # Redis Streams dispatch + agent roles
│   ├── devpod_manager.py       # K3s DevPod lifecycle + list_devpods()
│   ├── event_publisher.py      # Redis Pub/Sub events + log persistence
│   ├── recovery.py             # Crash recovery + idempotency
│   ├── circuit_breaker.py      # Model backend circuit breaking
│   ├── workflow.py             # Spec-driven workflow + TDD loop
│   ├── alerts.py               # ntfy alert integration
│   ├── agents/                 # Agent role implementations
│   │   ├── planner.py
│   │   ├── coder.py
│   │   ├── tester.py
│   │   ├── reviewer.py
│   │   ├── merger.py
│   │   └── prompts.py          # System prompt templates
│   └── systemd/
│       └── halo-supervisor.service
├── factory_floor/              # Factory Floor dashboard (vanilla JS + SSE)
│   ├── app.py                  # Thin proxy to Supervisor (Pass 2, A9)
│   ├── static/
│   │   ├── index.html
│   │   ├── app.js              # SSE handling, auto-refresh, renderAll()
│   │   ├── kanban.js
│   │   ├── graph.js            # D3 dependency graph (Pass 2 NEW)
│   │   ├── logs.js
│   │   ├── approvals.js
│   │   ├── devpods.js
│   │   ├── models.js
│   │   ├── command-palette.js
│   │   └── styles.css
│   └── csrf.py
├── tdad/                      # TDAD — Test Impact Analysis (FastAPI :8402)
│   ├── app.py
│   ├── ast_builder.py          # tree-sitter for Python/JS/TS (Pass 2 upgraded)
│   ├── graph_store.py
│   └── incremental.py
├── kernel/                    # HALO Kernel — LLM inference proxy
│   ├── gateway.py              # httpx proxy to Lemonade (Pass 2, A10)
│   ├── vllm_config.py          # Lemonade model profiles
│   ├── start_vllm.sh           # Lemonade health check + gateway start
│   └── systemd/
│       └── halo-kernel.service
├── agent_bridge/              # Agent-Bridge (FastAPI :19000)
│   ├── app.py                  # Nanoclaw proxy w/ retry (Pass 2 enhanced)
│   └── static/
├── nanoclaw/                  # Nanoclaw — Unix socket concierge
│   ├── server.py
│   └── memory.py
├── devpod/                    # DevPod extensions
│   ├── Dockerfile              # Fixed: no || true, tree-sitter installed (Pass 2)
│   └── templates/
├── dagger/                    # Dagger build engine (Pass 2 rewritten)
│   ├── pipelines/
│   │   ├── python_test.py      # Real Dagger container (Pass 2)
│   │   ├── node_test.py        # Real Dagger container (Pass 2)
│   │   └── e2e_test.py         # Real Dagger container (Pass 2)
│   ├── artifact_store.py
│   └── engine_config.py
├── specs/                     # Git-native state machine
│   ├── parser.py               # + update_spec_status() (Pass 2)
│   ├── state_machine.py
│   ├── dependency_resolver.py
│   ├── git_ops.py
│   └── arch_manager.py
├── memory/                    # Memory & RAG (Pass 2 upgraded)
│   ├── rag_indexer.py          # sentence-transformers bge-large (Pass 2)
│   ├── rag_query.py            # Graceful degradation on Qdrant failure (Pass 2)
│   └── chat_memory.py
├── common/                    # Shared libraries
│   ├── redis_client.py
│   ├── minio_client.py
│   ├── qdrant_client.py
│   ├── k3s_client.py
│   ├── git_utils.py
│   ├── models.py
│   ├── logging.py
│   └── config.py
├── requirements.txt           # Pass 2 dependencies (NEW)
└── tests/                     # 271 unit tests
    ├── test_e2e.py            # End-to-end lifecycle (Pass 2 NEW)
    ├── test_supervisor_api.py  # Supervisor HTTP API (Pass 2 NEW)
    ├── test_factory_floor.py   # Thin proxy tests (Pass 2 rewritten)
    ├── test_gateway.py         # httpx proxy tests (Pass 2 rewritten)
    ├── test_tdad.py            # tree-sitter tests (Pass 2 expanded)
    ├── test_integration.py    # Degradation tests (Pass 2 expanded)
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
- D3.js from CDN only (no npm install for the dashboard).
- Dark mode only (HALO aesthetic). Color coding per SRS FF-R6.

### Helm
- Follow kube-coder chart structure: `Chart.yaml`, `values.yaml`, `templates/`, `tests/`.
- Helm unittest YAML assertions in `charts/*/tests/`.

### Git
- Conventional commit prefixes: `feat(halo-*)`, `fix(halo-*)`, `test(halo-*)`, `chore(halo-*)`.
- Each phase has defined commit checkpoints.

---

## Test Commands

```bash
# HALO Python unit tests (all services)
make halo-tests

# HALO Python tests with coverage
make halo-coverage

# Helm lint for halo charts
make halo-helm-lint

# Helm unittest for halo charts
make halo-helm-test

# All HALO tests (Python + Helm)
make halo-test-all

# Service management (Pass 2)
make halo-start          # Start all services
make halo-stop           # Stop all services and free ports
make halo-status         # Show service status
make halo-smoke          # Run smoke tests
make halo-demo           # Create demo spec

# Kubernetes tests (existing kube-coder tests, still run)
make python-tests
make helm-test
make test-all-units
```

---

## Implementation History

### Pass 1 — Scaffolding and Mock Implementation (9 stages, 221 tests)
- Stage 1: Scaffolding + AGENTS.md
- Stage 2: halo-infra Helm chart + common client libraries
- Stage 3: HALO Kernel gateway (mock forwarder)
- Stage 4: Git-native state machine + spec parser
- Stage 5: TDAD service (regex-based) + Dagger pipelines (subprocess)
- Stage 6: Factory Orchestrator (supervisor, polling)
- Stage 7: DevPod extensions (Agent-Bridge, Nanoclaw)
- Stage 8: Factory Floor dashboard (empty state)
- Stage 9: Memory & RAG (hash placeholder) + agent roles

### Pass 2 — Production Realization (12 phases, 271 tests)
- Phase 2.0: Prerequisites (Dagger, tree-sitter, sentence-transformers, Redis)
- Phase 2.1: Real LLM proxy to Lemonade (A10)
- Phase 2.2: Supervisor HTTP API :9091 + inotify (A9)
- Phase 2.3: SSE relay to Redis Pub/Sub + real state
- Phase 2.4: TDAD tree-sitter for Python/JS/TS
- Phase 2.5: RAG with bge-large-en-v1.5 sentence-transformers
- Phase 2.6: Dagger hermetic test execution (A11)
- Phase 2.7: D3 dependency graph visualization
- Phase 2.8: DevPod Helm chart integration
- Phase 2.9: Production hardening + graceful degradation
- Phase 2.10: 16 end-to-end integration tests
- Phase 2.11: Documentation update

---

## Resource Budget (SRS §7.2)

| Component | RAM | VRAM | CPU Cores |
|-----------|-----|------|-----------|
| HALO Kernel (Lemonade 80B Q8) | 48 GB | 48 GB | 2 |
| HALO Kernel (fast 8B) | 8 GB | 8 GB | 1 |
| System + K3s | 4 GB | — | 2 |
| Supervisor + Factory API | 2 GB | — | 2 |
| TDAD | 2 GB | — | 2 |
| Qdrant + RAG | 4 GB | — | 2 |
| Redis + MinIO | 2 GB | — | 1 |
| Active DevPods (×2) | 8 GB | — | 4 |
| Headroom | 50 GB | 4 GB | 10 |
| **Total** | **128 GB** | **60 GB** | **16** |

---

## Key SRS References

- **Spec format**: `specs/SPEC-{NNN}.md` with YAML frontmatter (GIT-R1)
- **State machine**: `draft → ready → in_progress → implemented → merged | failed_*` (OR-R2)
- **Agent roles**: Planner, Coder, Tester, Reviewer, Merger (OR-R2 §4.2.2 table)
- **TDAD injection**: Before Coder writes code, inject affected tests into prompt (TDAD-R6)
- **Dagger hermetic**: All tests run in Dagger containers, no host execution (DAG-R2, A11)
- **Approval gate**: Human clicks Approve on Factory Floor → squash-merge to main (FF-R4)
- **Dark mode**: Color coding per spec status (FF-R6)
- **Graceful degradation**: Qdrant/TDAD/Kernel/Dagger fail modes (REL-4)