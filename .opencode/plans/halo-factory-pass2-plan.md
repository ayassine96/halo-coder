# HALO Factory — Pass 2 Implementation Plan

**Date**: 2026-07-11  
**Branch**: `halo-v2`  
**Base**: Pass 1 (9 stages, 16 commits, 221 unit tests, 4 mock-backed services)

---

## 1. Pass 1 Status Assessment

### What Pass 1 Delivered (✅ Production-Quality)

| Component | Status | Notes |
|-----------|--------|-------|
| Spec parser + state machine | ✅ Complete | YAML frontmatter, legal transition enforcement, cycle detection |
| Dependency resolver | ✅ Complete | Topological sort, parallel groups, is_ready/is_unblocked |
| Git operations | ✅ Complete | Branch creation, conventional commits, squash-merge, snapshot tags |
| ARCH.md manager | ✅ Complete | Read/write/append/parse sections |
| Common client libraries | ✅ Complete | Redis, MinIO, Qdrant, K3s, Git — all real implementations |
| Agent roles (5) | ✅ Complete logic | Planner, Coder, Tester, Reviewer, Merger — prompt builders + execution flow |
| Workflow + TDD loop | ✅ Complete logic | Full WF-SPEC-1..15, retry max 3, Red/Green/Refactor |
| Circuit breaker | ✅ Complete | Per-model closed/open/half_open state machine |
| Recovery | ✅ Complete | DevPod liveness check on restart, resume or fail |
| Alerts (ntfy) | ✅ Complete | urllib-based ntfy integration |
| Helm charts (2) | ✅ Lint clean | halo-infra (Redis/MinIO/Qdrant), halo-factory-floor |
| Factory Floor frontend | ✅ Complete | Kanban, logs, approvals, devpods, models, command palette, dark mode |
| Agent-Bridge | ✅ Complete | Spec dashboard, file tree, Nanoclaw proxy with retry |
| Nanoclaw | ✅ Complete | Unix socket, JSON line protocol, memory.jsonl rotation |
| TDAD (regex-based) | ✅ Complete for Python | Index, analyze, incremental, metrics |
| Unit tests (221) | ✅ All passing | unittest.TestCase matching kube-coder convention |

### What Pass 1 Left as Stubs (❌ Must Fix for Production)

| # | Gap | Current State | Pass 2 Target |
|---|-----|---------------|----------------|
| 1 | Kernel LLM proxy | Mock: returns `[HALO Kernel placeholder response]` | Real proxy to Lemonade :13305 with `httpx.AsyncClient` |
| 2 | RAG embeddings | Hash-based placeholder (non-semantic) | sentence-transformers with bge-large-en-v1.5 |
| 3 | Dagger pipelines | `subprocess.run` on host (violates DAG-R2) | Real Dagger Engine containers |
| 4 | TDAD parser | Regex-based, Python only | tree-sitter for Python + JS/TS |
| 5 | Factory Floor `/api/state` | Empty arrays — not wired to anything | Real state from Supervisor HTTP API |
| 6 | Factory Floor `/api/sse` | Single "connected" event, then closes | Redis Pub/Sub relay with auto-reconnect |
| 7 | Supervisor watcher | Polling loop (1s `time.sleep`) | inotify/watchdog for <500ms reaction (OR-R1) |
| 8 | Missing `graph.js` | Nav button exists, no renderer | D3/Cytoscape dependency graph visualization |
| 9 | DevPod integration | Templates are 8-line ConfigMap stubs | Extend `charts/workspace/` with HALO volumes + sidecar |
| 10 | End-to-end pipeline | Only mock-based unit tests | Full spec → plan → code → test → approve → merge with real services |
| 11 | Factory Floor mutations | Echo status, don't call Supervisor/Workflow | Wire to Supervisor HTTP API |
| 12 | Dockerfile | `|| true` on all installs (silent failures) | Proper error handling, build verification |
| 13 | systemd unit | Invalid `RestartSecBurstStart` directive | Fix to `StartLimitBurst`/`StartLimitIntervalSec` |
| 14 | Docker images | Not built/published | Build and verify halo-factory-floor image |

### Available Infrastructure (Verified 2026-07-11)

| Component | Status | Details |
|-----------|--------|---------|
| Lemonade LLM | ✅ Running on :13305 | API key: `halo-local`, 7 models available |
| Docker | ✅ v29.5.2 | Engine running, ready for Dagger |
| K3s | ✅ v1.36.2 | Single node `ali-ws1`, Ready, 10d uptime |
| Redis | ❌ Not running | Install via `apt` or run in K3s |
| Dagger | ❌ Not installed | Install as Pass 2 task |
| tree-sitter | ❌ Not installed | `pip install tree-sitter tree-sitter-python tree-sitter-javascript tree-sitter-typescript` |
| sentence-transformers | ❌ Not installed | `pip install sentence-transformers` |

### Lemonade Models Available

| Lemonade Model ID | Labels | HALO Profile Mapping |
|-------------------|--------|---------------------|
| `Qwen3-Next-80B-A3B-Instruct-GGUF-Q8_0` | tool-calling, custom | `halo-reasoning` (Planner, Reviewer) |
| `Qwen3-Coder-30B-A3B-Instruct-GGUF` | coding, tool-calling, hot | `halo-coder` (Coder agent) |
| `Qwen3-8B-GGUF` | reasoning, tool-calling | `halo-fast` (Tester, Merger, quick tasks) |
| `Qwen2.5-VL-7B-Instruct-GGUF` | vision | `halo-vision` (diagram/screenshot) |
| `DeepSeek-R1-0528-Qwen3-8B-GGUF-Q4_K_M` | tool-calling, custom | Alternative reasoning |
| `Bonsai-1.7B-gguf` | tool-calling | Ultra-fast autocomplete |
| `gemma-4-26B-A4B-it-GGUF-UD-Q4_K_M` | vision, tool-calling, custom | Alternative vision |

---

## 2. Pass 2 Architecture Changes

### A9: Supervisor HTTP API (New Decision)

The Supervisor gains a FastAPI HTTP server at `:9090` for:
- `GET /api/state` — full state snapshot (specs, devpods, model_metrics, paused)
- `GET /api/specs` — list all specs with status
- `POST /api/approve` — transition implemented → merged
- `POST /api/reject` — transition implemented → draft
- `POST /api/trigger` — transition draft → ready
- `POST /api/kill` — force-terminate DevPod
- `POST /api/pause` — halt supervisor event loop
- `GET /api/sse` — SSE relay of Redis Pub/Sub events
- `GET /health` — liveness probe
- `GET /metrics` — Prometheus metrics

Factory Floor (:8888) becomes a **thin proxy** — it forwards all `/api/*` calls to the Supervisor (:9090) and serves the static SPA. No business logic in the Factory Floor backend.

**Rationale**: Single source of truth, atomic Git+Redis operations stay in the Supervisor, Factory Floor is a pure frontend. Factory Floor can be restarted without affecting the pipeline.

### A10: Lemonade as Primary LLM Backend (Updated from A2)

Pass 1 planned vLLM from the start (decision A2). Pass 2 uses Lemonade (`:13305`) as the primary LLM backend because:
- It's already running and serving 7 models
- It's OpenAI-compatible (`/v1/chat/completions`)
- The HALO Kernel gateway proxies to it via `httpx.AsyncClient`
- vLLM remains a future upgrade path if Lemonade's throughput is insufficient

Model profile mapping:
```
halo-reasoning → Qwen3-Next-80B-A3B-Instruct-GGUF-Q8_0
halo-coder     → Qwen3-Coder-30B-A3B-Instruct-GGUF
halo-fast      → Qwen3-8B-GGUF
halo-vision    → Qwen2.5-VL-7B-Instruct-GGUF
```

### A11: Dagger for Hermetic Test Execution (Updated from DAG-R2)

Install Dagger CLI on the host. Use `dagger run` for all test pipelines:
- Python: `dagger run python_test.py` — mounts source read-only, runs pytest in container
- Node: `dagger run node_test.py` — mounts source, runs npm test in container
- E2E: `dagger run e2e_test.py` — Playwright container
- Fallback: If Dagger Engine unavailable, fall back to `docker run` with explicit container commands (logged as warning per REL-4)

---

## 3. Pass 2 Implementation Plan

### Phase 2.0 — Prerequisite Installations

**Tasks:**
1. Install Dagger CLI: `curl -fsSL https://dl.dagger.io/dagger/install.sh | sh`
2. Install tree-sitter: `pip install tree-sitter tree-sitter-python tree-sitter-javascript tree-sitter-typescript`
3. Install sentence-transformers: `pip install sentence-transformers`
4. Install Redis: `sudo apt install redis-server` or deploy via `helm install redis charts/halo-infra`
5. Verify: `dagger version`, `python3 -c "import tree_sitter"`, `python3 -c "from sentence_transformers import SentenceTransformer"`

**Commit**: `chore(halo): install Pass 2 dependencies (Dagger, tree-sitter, sentence-transformers)`

---

### Phase 2.1 — Real LLM Backend (Kernel Gateway) 

**Goal**: Replace mock `_forward_to_vllm` with real `httpx.AsyncClient` proxy to Lemonade.

**Files to modify:**
- `halo/kernel/gateway.py` — Replace `_forward_to_vllm` mock with real HTTP proxy
- `halo/kernel/vllm_config.py` — Update model profiles to Lemonade models
- `halo/kernel/start_vllm.sh` — Repurpose as Lemonade health-check + startup verification
- `halo/kernel/systemd/halo-kernel.service` — Fix `RestartSecBurstStart` → `StartLimitBurst`

**Changes:**
```
_forward_to_vllm(self, body):
    # OLD: asyncio.sleep(0.001), return mock dict
    # NEW: 
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{self.backend_url}/v1/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
        return resp.json()
```

**Config:**
- `HALO_KERNEL_BACKEND_URL` env var (default: `http://localhost:13305`)
- `HALO_KERNEL_API_KEY` env var (default: `halo-local`)
- Model profile mapping in `vllm_config.py` updated to Lemonade model IDs
- If backend unreachable, return HTTP 503 with Retry-After (circuit breaker handles this)

**Tests:**
- Update `test_gateway.py` to mock `httpx.AsyncClient` instead of testing mock forwarder
- Add test for real proxy behavior: mock Lemonade response, verify passthrough
- Add test for backend-down: verify 503 + circuit breaker open

**Commit**: `feat(halo-kernel): replace mock forwarder with real Lemonade LLM proxy`

---

### Phase 2.2 — Supervisor HTTP API + inotify

**Goal**: Add FastAPI server to Supervisor, replace polling with inotify.

**Files to modify:**
- `halo/factory/supervisor.py` — Add FastAPI app, inotify watcher, HTTP endpoints
- `halo/factory/event_publisher.py` — Wire to real Redis Pub/Sub (not mock)
- `halo/factory_floor/app.py` — Transform to thin proxy (all `/api/*` → Supervisor :9090)

**New file:**
- `halo/factory/supervisor_api.py` — FastAPI routes for Supervisor HTTP API

**Supervisor API endpoints (all on :9090):**
```python
# State
GET  /api/state          → {specs, devpods, model_metrics, logs, paused}
GET  /api/specs          → {specs: [...]}
GET  /api/spec/{id}      → single spec detail

# Mutations (all CSRF-protected)
POST /api/approve        → transition implemented → merged
POST /api/reject         → transition implemented → draft
POST /api/trigger        → transition draft → ready
POST /api/kill          → force-terminate DevPod
POST /api/pause          → halt supervisor event loop

# Real-time
GET  /api/sse            → SSE relay of Redis Pub/Sub events
GET  /health             → {status, redis_connected, k3s_connected}
GET  /metrics            → Prometheus metrics
```

**inotify integration:**
```python
# Replace time.sleep(poll_interval) loop with:
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class SpecFileHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith('.md'):
            self.supervisor.on_spec_changed(event.src_path)
```

**Factory Floor becomes thin proxy:**
```python
# halo/factory_floor/app.py — all /api/* proxied to :9090
import httpx
SUPERVISOR_URL = os.environ.get("HALO_SUPERVISOR_URL", "http://localhost:9090")

@app.api_route("/api/{path:path}", methods=["GET", "POST"])
async def proxy(path: str, request: Request):
    async with httpx.AsyncClient() as client:
        resp = await client.request(
            request.method,
            f"{SUPERVISOR_URL}/api/{path}",
            content=await request.body(),
            headers=request.headers,
        )
        return Response(resp.content, resp.status_code, resp.headers)
```

**Factory Floor keeps:**
- Static file serving (`/static/*`, `/` → `index.html`)
- CSRF token management (proxied through to Supervisor)

**Tests:**
- `test_supervisor.py` — test HTTP API endpoints with mocked Redis/K3s
- `test_factory_floor.py` — update tests to verify proxy behavior
- Add inotify test: create temp dir, write spec file, verify supervisor detects it

**Commit**: `feat(halo-factory): add Supervisor HTTP API (:9090) with inotify, wire Factory Floor as thin proxy`

---

### Phase 2.3 — Factory Floor SSE + Real State

**Goal**: Wire SSE to Redis Pub/Sub, populate `/api/state` with real data.

**Files to modify:**
- `halo/factory/event_publisher.py` — Ensure Redis Pub/Sub works with real Redis connection
- `halo/factory/supervisor_api.py` — `/api/sse` yields events from Redis Pub/Sub
- `halo/factory/supervisor_api.py` — `/api/state` reads real data:
  - Specs: scan Git repos for spec files, parse frontmatter
  - DevPods: query K3s API for pod status
  - Model metrics: query Kernel gateway `/metrics`
  - Paused: supervisor's `_paused` flag

**SSE relay:**
```python
@app.get("/api/sse")
async def sse_stream():
    async def generate():
        redis = await aioredis.create_redis_pool("redis://localhost:6379")
        pubsub = redis.pubsub()
        await pubsub.subscribe("halo:factory:logs", "halo:factory:approvals",
                               "halo:factory:alerts", "halo:factory:metrics")
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                yield f"data: {msg['data'].decode()}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

**Tests:**
- Test SSE with mock Redis Pub/Sub (verify event relay)
- Test `/api/state` with mock Git repos + mock K3s pods

**Commit**: `feat(halo-factory): wire SSE to Redis Pub/Sub, populate real state from Git + K3s`

---

### Phase 2.4 — TDAD tree-sitter Upgrade

**Goal**: Replace regex-based AST with tree-sitter, add JS/TS support.

**Files to modify:**
- `halo/tdad/ast_builder.py` — Replace regex parsing with tree-sitter queries
- `halo/tdad/app.py` — No changes (API stays the same)
- `halo/tdad/graph_store.py` — No changes (graph structure stays the same)
- `halo/tdad/incremental.py` — Update to handle JS/TS files
- `halo/tests/test_tdad.py` — Update AST builder tests

**New tree-sitter implementation:**
```python
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser

class TreeSitterAstBuilder:
    def __init__(self):
        self.parsers = {
            "python": self._make_parser(tspython.language()),
            "javascript": self._make_parser(tsjs.language()),
            "typescript": self._make_parser(tsts.language_typescript()),
        }
    
    def parse_imports(self, file_path, content):
        # Walk AST for import nodes (import_statement, import_from_statement)
    def parse_definitions(self, file_path, content):
        # Walk AST for function_definition, class_definition
    def detect_test_files(self, file_path, content):
        # Walk AST for assert statements, test patterns
```

**Test project update:**
- Add a JS/TS test file to the demo project (`/tmp/halo-test/projects/demo/`)
- Verify TDAD can index and analyze JS/TS files

**Tests:**
- Update `test_tdad.py` to test tree-sitter AST extraction
- Add JS/TS index/analyze tests
- Verify backward compat: old regex tests still pass (regex as fallback if tree-sitter not installed)

**Commit**: `feat(halo-tdad): upgrade to tree-sitter AST parser with JS/TS support`

---

### Phase 2.5 — RAG with Real Embeddings

**Goal**: Replace hash-based placeholder with sentence-transformers.

**Files to modify:**
- `halo/memory/rag_indexer.py` — Replace `_default_embedding` with real model
- `halo/memory/rag_query.py` — No changes (uses same embedding_fn)
- `halo/tests/test_integration.py` — Update RAG tests

**Implementation:**
```python
class RagIndexer:
    def __init__(self, ..., embedding_model="BAAI/bge-large-en-v1.5"):
        self._model = None
        self._embedding_model_name = embedding_model
    
    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._embedding_model_name)
        return self._model
    
    def _default_embedding(self, text):
        model = self._get_model()
        vec = model.encode(text, normalize_embeddings=True)
        return vec.tolist()
    
    def rebuild_from_git(self, repo_path):
        # For each .md, .py, .js file in repo:
        #   chunk text → embed → upsert to Qdrant
        # Track progress, log timing
```

**Graceful degradation:**
- If sentence-transformers not installed, fall back to hash-based placeholder
- Log warning: "sentence-transformers not installed, using hash placeholder"
- If Qdrant not running, skip RAG context (per REL-4)

**Tests:**
- Test with mock sentence-transformers (verify embedding call)
- Test fallback to hash placeholder when model not available
- Test rebuild_from_git with mock Qdrant

**Commit**: `feat(halo-memory): wire sentence-transformers bge-large-en-v1.5 for real RAG embeddings`

---

### Phase 2.6 — Dagger Hermetic Test Execution

**Goal**: Replace subprocess fallback with real Dagger containers.

**Prerequisite**: Install Dagger CLI (`curl -fsSL https://dl.dagger.io/dagger/install.sh | sh`)

**Files to modify:**
- `halo/dagger/pipelines/python_test.py` — Real Dagger pipeline
- `halo/dagger/pipelines/node_test.py` — Real Dagger pipeline
- `halo/dagger/pipelines/e2e_test.py` — Real Dagger pipeline
- `halo/dagger/engine_config.py` — Update engine config
- `halo/tests/test_tdad.py` — Update Dagger pipeline tests

**Implementation (Python example):**
```python
import subprocess

def run_python_test(repo_path, spec_id=""):
    """Run pytest in Dagger container (DAG-R2 hermetic)."""
    cmd = [
        "dagger", "run", "python3", "-c", DAGGER_PYTHON_PIPELINE
    ]
    result = subprocess.run(cmd, cwd=repo_path, capture_output=True, timeout=300)
    # Parse results, upload artifacts to MinIO
    return {
        "exit_code": result.returncode,
        "stdout": result.stdout.decode(),
        "stderr": result.stderr.decode(),
        "passed": result.returncode == 0,
    }
```

**Dagger pipeline (inline):**
```python
DAGGER_PYTHON_PIPELINE = '''
import dagger
from dagger import function, object_type

@object_type
class PythonTest:
    @function
    async def run(self, src: dagger.Directory) -> str:
        return await (
            dagger.container()
            .from_("python:3.12-slim")
            .with_mounted_directory("/src", src)
            .with_workdir("/src")
            .with_exec(["pip", "install", "-r", "requirements.txt"])
            .with_exec(["pip", "install", "pytest", "pytest-cov"])
            .with_exec(["pytest", "--junitxml=results.xml", "-v"])
            .stdout()
        )
'''
```

**Fallback (REL-4):**
- If Dagger unavailable, use `docker run` with explicit container:
  ```bash
  docker run --rm -v $repo:/src -w /src python:3.12-slim \
    pip install pytest && pytest --junitxml=results.xml -v
  ```
- Log warning: "Dagger unavailable, using docker fallback"

**Tests:**
- Mock dagger CLI subprocess, verify command structure
- Test docker fallback path
- Test artifact upload to MinIO (mock MinIO client)

**Commit**: `feat(halo-dagger): implement real Dagger container pipelines for hermetic test execution`

---

### Phase 2.7 — Dependency Graph Visualization

**Goal**: Add `graph.js` with D3.js or Cytoscape.js for dependency graph view.

**New file:**
- `halo/factory_floor/static/graph.js` — D3/Cytoscape graph renderer

**Implementation:**
```javascript
// graph.js — D3 force-directed graph
export function renderGraph(specs) {
    const width = 800, height = 600;
    const svg = d3.select("#graph-container").append("svg")
        .attr("width", width).attr("height", height);
    
    // Nodes = specs, colored by status
    // Edges = depends_on / blocks relationships
    // Force simulation for layout
    const nodes = specs.map(s => ({ id: s.id, status: s.status, title: s.title }));
    const links = [];
    specs.forEach(s => {
        s.depends_on.forEach(dep => links.push({ source: dep, target: s.id }));
    });
    
    // D3 force simulation
    const simulation = d3.forceSimulation(nodes)
        .force("link", d3.forceLink(links).id(d => d.id))
        .force("charge", d3.forceManyBody().strength(-300))
        .force("center", d3.forceCenter(width / 2, height / 2));
    // ... render nodes + links
}
```

**index.html update:**
- Add `<div id="graph-container"></div>` (already exists)
- Add D3 CDN: `<script src="https://d3js.org/d3.v7.min.js"></script>` or Cytoscape CDN

**Tests:**
- Playwright test: navigate to Graph view, verify SVG element exists
- Manual: verify graph renders with sample specs

**Commit**: `feat(halo-factory-floor): add D3 dependency graph visualization`

---

### Phase 2.8 — DevPod Helm Chart Integration

**Goal**: Extend `charts/workspace/` with HALO volumes and Agent-Bridge sidecar.

**Files to modify:**
- `charts/workspace/values.yaml` — Add `halo` section
- `charts/workspace/templates/deployment.yaml` — Add Agent-Bridge sidecar + HALO volumes
- `charts/workspace/templates/halo-configmap.yaml` — HALO configuration (new)
- `halo/devpod/Dockerfile` — Fix `|| true` silent failures, verify build

**values.yaml addition:**
```yaml
halo:
  enabled: false       # backward compatible — off by default
  agentBridge:
    image: halo/agent-bridge:2.0.0-halo
    port: 9000
  nanoclaw:
    sockPath: /tmp/nanoclaw.sock
  kernel:
    url: http://halo-kernel.halo.svc:13305
  projects:
    path: /var/halo/projects
    readOnly: true
  reference:
    path: /var/halo/reference
    readOnly: true
  chat:
    path: /var/halo/chat
```

**Deployment template addition:**
```yaml
{{- if .Values.halo.enabled }}
# Agent-Bridge sidecar
- name: agent-bridge
  image: {{ .Values.halo.agentBridge.image }}
  ports:
  - containerPort: {{ .Values.halo.agentBridge.port }}
  env:
  - name: HALO_KERNEL_URL
    value: {{ .Values.halo.kernel.url }}
  - name: HALO_NANOCLAW_SOCK
    value: {{ .Values.halo.nanoclaw.sockPath }}
  - name: HALO_PROJECT_DIR
    value: {{ .Values.halo.projects.path }}
  volumeMounts:
  - name: halo-projects
    mountPath: {{ .Values.halo.projects.path }}
    readOnly: {{ .Values.halo.projects.readOnly }}
  - name: halo-chat
    mountPath: {{ .Values.halo.chat.path }}
  - name: nanoclaw-sock
    mountPath: /tmp

# Volumes
volumes:
- name: halo-projects
  persistentVolumeClaim:
    claimName: halo-projects
- name: halo-chat
  emptyDir: {}
- name: nanoclaw-sock
  emptyDir: {}
{{- end }}
```

**Dockerfile fix:**
- Remove `|| true` from tool installs
- Add proper error handling and build verification
- Multi-stage build for smaller image

**Helm tests:**
- Add `halo` section to `charts/workspace/tests/test-values.yaml`
- Test `halo.enabled: true` renders sidecar + volumes
- Test `halo.enabled: false` (default) renders nothing

**Commit**: `feat(halo-devpod): extend workspace chart with HALO volumes + Agent-Bridge sidecar`

---

### Phase 2.9 — Production Hardening

**Goal**: Fix all production issues, build Docker images, end-to-end health.

**Files to modify:**
- `halo/kernel/systemd/halo-kernel.service` — Fix systemd directives
- `halo/factory/systemd/halo-supervisor.service` — Add Supervisor API port
- `halo/factory_floor/csrf.py` — Either use csrf.py everywhere or remove it
- `halo/kernel/vllm_config.py` — Fix `"target tok_s"` typo
- `halo/devpod/Dockerfile` — Fix `|| true`, proper error handling
- `halo/common/models.py` — Consider migrating to Pydantic BaseModel (optional)

**New files:**
- `charts/halo-factory-floor/Dockerfile` — Factory Floor container image
- `halo/factory/systemd/halo-supervisor.service` — Updated with API port :9090

**Helm chart fixes:**
- Build and verify `halo-factory-floor:2.0.0-halo` Docker image
- Update `charts/halo-factory-floor/values.yaml` with image reference
- Ensure DevPod image builds properly

**Graceful degradation checklist (REL-4):**
- [ ] If Qdrant fails: RAG context omitted from prompts (log warning)
- [ ] If TDAD fails: Agents run full test suite instead of targeted tests (log warning)
- [ ] If HALO Kernel fails: Tasks queue with backoff, ntfy alert sent
- [ ] If Dagger fails: Fall back to docker run (log warning)
- [ ] If Redis fails: Degrade to Git-only operation (log warning)

**Tests:**
- Add degradation tests to `test_integration.py`
- Verify each failure mode produces correct behavior

**Commit**: `fix(halo): production hardening — systemd, Dockerfile, graceful degradation, Docker images`

---

### Phase 2.10 — End-to-End Integration Test

**Goal**: Full spec → merge lifecycle with real services.

**New file:**
- `halo/tests/test_e2e.py` — End-to-end integration test

**Test setup:**
```python
class TestEndToEndLifecycle(unittest.TestCase):
    """Full spec lifecycle: draft → ready → in_progress → implemented → merged.
    
    Requires:
    - Lemonade running on :13305 (or mock)
    - Redis running on :6379 (or mock)
    - K3s running (or mock)
    - Dagger installed (or docker fallback)
    """
    @classmethod
    def setUpClass(cls):
        # Start all services in background
        # Create temp Git repo with demo project
        # Start supervisor with inotify on temp repo
        # Start Factory Floor as proxy to supervisor
        # TDAD already running on :8402
    
    def test_01_create_spec(self):
        # Write SPEC-001.md with status: draft
        # Verify supervisor detects it
    
    def test_02_trigger_spec(self):
        # POST /api/trigger to supervisor
        # Verify spec transitions to ready
    
    def test_03_planner_dispatched(self):
        # Verify supervisor dispatches Planner agent
        # Verify plan.md is committed to agent/SPEC-001 branch
        # Verify LLM was called (check mock or real)
    
    def test_04_coder_dispatched(self):
        # Verify Coder agent runs
        # Verify TDAD was queried for affected tests
        # Verify code is committed to branch
    
    def test_05_tester_runs(self):
        # Verify Dagger pipeline runs (or docker fallback)
        # Verify test results XML uploaded to MinIO (or skipped)
    
    def test_06_reviewer_runs(self):
        # Verify Reviewer agent generates PR summary
    
    def test_07_approval_request(self):
        # Verify spec transitions to implemented
        # Verify approval request published to Redis Pub/Sub
        # Verify Factory Floor shows it in approval queue
    
    def test_08_human_approve(self):
        # POST /api/approve to Factory Floor (proxied to supervisor)
        # Verify Merger agent squash-merges to main
        # Verify spec transitions to merged
        # Verify branch is deleted
```

**Test modes:**
- `HALO_E2E_MOCK=1` — All external services mocked (runs in CI without GPU)
- `HALO_E2E_REAL=1` — Real Lemonade + Redis + K3s + Dagger (runs on Strix Halo)

**Playwright E2E (Factory Floor UI):**
- Update Playwright test to verify real data:
  - Kanban board shows spec card (not empty)
  - Approval queue shows implemented spec
  - SSE receives real events (not just "connected")
  - Graph view renders dependency visualization

**Commit**: `test(halo): add full end-to-end integration test with real services`

---

### Phase 2.11 — Documentation Update

**Files to update:**
- `docs_pass2.md` — New Pass 2 implementation document
- `docs/manual_test_guide.md` — Update for real services, fix port table, fix quoting
- `AGENTS.md` — Update stages to reflect Pass 2 completion
- `docs_pass1.md` — Add note pointing to Pass 2 doc

**Fixes to manual test guide:**
- Fix port reference table (default :13306, not :13305)
- Fix nanoclaw python one-liners (use single quotes)
- Fix `sock.recv(4092)` → `sock.recv(4096)` typo
- Add real-service testing sections (Lemonade, Redis, Dagger)
- Add E2E test walkthrough

**Commit**: `docs(halo): add Pass 2 documentation, fix manual test guide issues`

---

## 4. Pass 2 Commit Plan

| # | Commit Message | Phase |
|---|----------------|-------|
| 1 | `chore(halo): install Pass 2 dependencies (Dagger, tree-sitter, sentence-transformers)` | 2.0 |
| 2 | `feat(halo-kernel): replace mock forwarder with real Lemonade LLM proxy` | 2.1 |
| 3 | `feat(halo-factory): add Supervisor HTTP API (:9090) with inotify, wire Factory Floor as thin proxy` | 2.2 |
| 4 | `feat(halo-factory): wire SSE to Redis Pub/Sub, populate real state from Git + K3s` | 2.3 |
| 5 | `feat(halo-tdad): upgrade to tree-sitter AST parser with JS/TS support` | 2.4 |
| 6 | `feat(halo-memory): wire sentence-transformers bge-large-en-v1.5 for real RAG embeddings` | 2.5 |
| 7 | `feat(halo-dagger): implement real Dagger container pipelines for hermetic test execution` | 2.6 |
| 8 | `feat(halo-factory-floor): add D3 dependency graph visualization` | 2.7 |
| 9 | `feat(halo-devpod): extend workspace chart with HALO volumes + Agent-Bridge sidecar` | 2.8 |
| 10 | `fix(halo): production hardening — systemd, Dockerfile, graceful degradation, Docker images` | 2.9 |
| 11 | `test(halo): add full end-to-end integration test with real services` | 2.10 |
| 12 | `docs(halo): add Pass 2 documentation, fix manual test guide issues` | 2.11 |

**Total**: 12 commits, 11 phases, ~15-20 files modified, ~8 new files

---

## 5. Acceptance Criteria for Pass 2

The Pass 2 implementation will be considered complete when:

1. ✅ A human can write `specs/SPEC-001.md`, set `status: ready`, and watch the Factory Floor Kanban board transition the spec card from `ready` → `in_progress` → `implemented` **with real data from the Supervisor** (not empty arrays).

2. ✅ The human can click "Approve" on the Factory Floor, and the branch is squash-merged to `main` automatically by the Merger agent.

3. ✅ TDAD correctly identifies affected tests for Python AND JS/TS code changes using tree-sitter AST parsing.

4. ✅ Dagger runs `pytest` in a hermetic container and returns JUnit XML (or falls back to `docker run` with warning log).

5. ✅ The HALO Kernel proxy returns real LLM responses from Lemonade (not `[HALO Kernel placeholder response]`).

6. ✅ RAG embeddings use bge-large-en-v1.5 (not hash placeholders) when sentence-transformers is installed.

7. ✅ Factory Floor SSE receives real events from Redis Pub/Sub (not just "connected").

8. ✅ Dependency Graph view renders specs as nodes with dependency edges in the Factory Floor.

9. ✅ Factory Floor `/api/state` returns real specs, devpods, and model metrics (not empty arrays).

10. ✅ The end-to-end integration test (`test_e2e.py`) passes in both mock and real modes.

11. ✅ The system degrades gracefully when any single component fails (REL-4 checklist).

12. ✅ All existing 221 unit tests still pass (no regressions).

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Lemonade doesn't support all needed models | Low | Medium | Fall back to Qwen3-8B for all profiles; document model swap |
| Dagger CLI unavailable on node | Medium | Medium | `docker run` fallback per REL-4; log warning |
| sentence-transformers too slow on CPU | Medium | Low | Use smaller model (bge-small-en-v1.5, 384-dim) as fallback |
| tree-sitter version incompatibility | Low | Medium | Pin versions in requirements; test before upgrade |
| Redis not persistent | Medium | Medium | Git is source of truth (A5); Redis is cache only |
| K3s API rate limiting | Low | Low | Supervisor uses caching, queries max 1/s |
| Factory Floor SSE connection leaks | Medium | Medium | Auto-reconnect with exponential backoff (FF-NF1); 50 connection max |
| DevPod sidecar breaks existing workspaces | Medium | High | `halo.enabled: false` by default; backward compatible |
| End-to-end test too slow for CI | High | Medium | Mock mode for CI; real mode for manual testing |

---

## 7. Pass 2 Directory Structure (New/Modified Files)

```
halo/
├── factory/
│   ├── supervisor.py              # MODIFIED — add FastAPI, inotify
│   ├── supervisor_api.py          # NEW — HTTP API routes
│   ├── event_publisher.py         # MODIFIED — real Redis Pub/Sub
│   └── ...
├── factory_floor/
│   ├── app.py                     # MODIFIED — thin proxy to :9090
│   └── static/
│       ├── graph.js               # NEW — D3 dependency graph
│       ├── index.html             # MODIFIED — add D3 CDN
│       └── ...
├── kernel/
│   ├── gateway.py                 # MODIFIED — real httpx proxy
│   ├── vllm_config.py             # MODIFIED — Lemonade models
│   ├── start_vllm.sh              # MODIFIED — Lemonade health check
│   └── systemd/
│       └── halo-kernel.service    # MODIFIED — fix systemd directives
├── tdad/
│   └── ast_builder.py             # MODIFIED — tree-sitter
├── memory/
│   └── rag_indexer.py             # MODIFIED — real embeddings
├── dagger/
│   └── pipelines/
│       ├── python_test.py         # MODIFIED — real Dagger
│       ├── node_test.py           # MODIFIED — real Dagger
│       └── e2e_test.py            # MODIFIED — real Dagger
├── devpod/
│   └── Dockerfile                 # MODIFIED — fix || true
├── tests/
│   ├── test_gateway.py            # MODIFIED
│   ├── test_supervisor.py         # MODIFIED
│   ├── test_factory_floor.py      # MODIFIED
│   ├── test_tdad.py               # MODIFIED
│   ├── test_integration.py        # MODIFIED
│   └── test_e2e.py                # NEW — E2E integration test
charts/
├── workspace/
│   ├── values.yaml                # MODIFIED — add halo section
│   ├── templates/
│   │   ├── deployment.yaml        # MODIFIED — add sidecar + volumes
│   │   └── halo-configmap.yaml    # NEW
│   └── tests/
│       └── deployment_test.yaml   # MODIFIED — add halo tests
├── halo-factory-floor/
│   ├── Dockerfile                 # NEW
│   └── ...
docs/
├── manual_test_guide.md           # MODIFIED — fixes
└── ...
docs_pass2.md                       # NEW
```

---

## 8. Pass 2 vs Pass 1 Comparison

| Metric | Pass 1 | Pass 2 Target |
|--------|--------|---------------|
| Unit tests | 221 | ~260 (+~40 new) |
| Commits | 16 | +12 |
| Mock backends | 4 services mock-backed | 0 (all real) |
| Real LLM | No | Yes (Lemonade) |
| Real state | No (empty arrays) | Yes (Git + Redis + K3s) |
| Real SSE | No (single event) | Yes (Redis Pub/Sub relay) |
| Hermetic tests | No (subprocess) | Yes (Dagger containers) |
| TDAD parser | Regex | tree-sitter |
| RAG embeddings | Hash placeholder | bge-large-en-v1.5 |
| Dependency graph | Missing | D3.js |
| DevPod integration | Stubs | Helm chart extended |
| E2E test | Mock only | Real + mock modes |
| Production ready | No | Yes |

---

*End of Pass 2 Plan*