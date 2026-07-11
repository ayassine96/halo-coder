# HALO Factory — Manual Testing Guide

This guide walks you through testing every HALO Factory service end-to-end, from
unit tests through live HTTP API calls to the full spec lifecycle.

**Prerequisites**:
- Python 3.11+
- `pip install --break-system-packages fastapi uvicorn httpx pyyaml redis minio`
- Git, curl, jq (optional but helpful)

**Time required**: ~30 minutes for all tests.

---

## Table of Contents

1. [Quick Start: One-Command Smoke Test](#1-quick-start-one-command-smoke-test)
2. [Unit Tests (Automated)](#2-unit-tests-automated)
3. [Helm Chart Tests](#3-helm-chart-tests)
4. [Service-by-Service Live Tests](#4-service-by-service-live-tests)
   - 4.1 [HALO Kernel Gateway (:13305)](#41-halo-kernel-gateway-13305)
   - 4.2 [TDAD Service (:8402)](#42-tdad-service-8402)
   - 4.3 [Factory Floor (:8888)](#43-factory-floor-8888)
   - 4.4 [Agent-Bridge (:9000)](#44-agent-bridge-9000)
   - 4.5 [Nanoclaw Unix Socket](#45-nanoclaw-unix-socket)
5. [Spec Parser & State Machine](#5-spec-parser--state-machine)
6. [Dependency Resolver](#6-dependency-resolver)
7. [Full Spec Lifecycle (End-to-End)](#7-full-spec-lifecycle-end-to-end)
8. [Factory Floor UI (Browser)](#8-factory-floor-ui-browser)
9. [Multi-Service Integration Test](#9-multi-service-integration-test)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Quick Start: One-Command Smoke Test

A helper script (`scripts/halo-test.py`) automates starting services and running
smoke tests against them.

### Create a demo project with a sample spec

```bash
python3 scripts/halo-test.py create-spec
```

This creates `/tmp/halo-test/projects/demo/` with:
- `specs/SPEC-001.md` — a sample spec (FastAPI endpoint)
- `src/app.py` — matching source code
- `tests/test_app.py` — matching test
- `ARCH.md` — architecture doc

### Start all services (in separate terminals)

Open 4 terminals and run:

```bash
# Terminal 1 — HALO Kernel
python3 -m uvicorn halo.kernel.gateway:app --host 0.0.0.0 --port 13305

# Terminal 2 — TDAD
python3 -m uvicorn halo.tdad.app:app --host 0.0.0.0 --port 8402

# Terminal 3 — Factory Floor
python3 -m uvicorn halo.factory_floor.app:app --host 0.0.0.0 --port 8888

# Terminal 4 — Agent-Bridge
HALO_PROJECT_DIR=/tmp/halo-test/projects/demo \
  python3 -m uvicorn halo.agent_bridge.app:app --host 0.0.0.0 --port 9000
```

### Run the smoke test

```bash
python3 scripts/halo-test.py test-all
```

**Expected output**:
```
============================================================
HALO Factory — Full Smoke Test
============================================================

Testing HALO Kernel (http://localhost:13305) ...
  /health: {'status': 'ok', 'models': ['halo-fast', 'halo-reasoning', 'halo-vision']}
  /v1/models: ['halo-fast', 'halo-reasoning', 'halo-vision']
  /v1/chat/completions (halo-fast): [HALO Kernel placeholder response]
  /metrics (first line): # HELP halo_kernel_requests_total Total requests

Testing TDAD (http://localhost:8402) ...
  /health: {'status': 'ok', 'indexed': False}
  /analyze: affected_tests=['tests/test_app.py'], confidence=1.0
  /metrics (first line): # HELP halo_tdad_modules Total indexed modules

Testing Factory Floor (http://localhost:8888) ...
  /health: {'status': 'ok'}
  /api/state: ['specs', 'devpods', 'model_metrics', 'logs', 'paused']
  /api/csrf-token: got token (0sC0-lXQ9k39dByT...)
  /metrics (first line): # HELP halo_factory_floor_up Service up

Testing Agent-Bridge (http://localhost:9000) ...
  /health: {'status': 'ok'}
  /api/files: 4 items at root
  /api/launchers: ['terminal', 'vscode', 'files', 'spec']

============================================================
All smoke tests complete.
============================================================
```

---

## 2. Unit Tests (Automated)

Run the full test suite (221 tests):

```bash
make halo-tests
```

Or directly:

```bash
python3 -m unittest discover -s halo/tests -p 'test_*.py' -v
```

**Verify**: `Ran 221 tests in 0.2s — OK`

### Run a specific module

```bash
python3 -m unittest halo.tests.test_gateway -v        # Kernel (12 tests)
python3 -m unittest halo.tests.test_spec_parser -v     # Parser (10 tests)
python3 -m unittest halo.tests.test_state_machine -v   # State machine (15 tests)
python3 -m unittest halo.tests.test_factory -v          # Orchestrator (46 tests)
python3 -m unittest halo.tests.test_factory_floor -v   # Factory Floor (15 tests)
python3 -m unittest halo.tests.test_tdad -v            # TDAD + Dagger (25 tests)
python3 -m unittest halo.tests.test_integration -v     # End-to-end (25 tests)
```

### With coverage

```bash
make halo-coverage
# or
cd halo && coverage run -m unittest discover -s tests -p 'test_*.py' && coverage report && coverage html
open htmlcov/index.html
```

---

## 3. Helm Chart Tests

### Prerequisites

```bash
helm plugin install https://github.com/helm-unittest/helm-unittest.git --version v0.5.2
```

### Lint both charts

```bash
make halo-helm-lint
```

**Expected**: `2 chart(s) linted, 0 chart(s) failed`

### Run helm unittests

```bash
make halo-helm-test
```

**Expected**: PASS for both `charts/halo-infra/` and `charts/halo-factory-floor/`.

### Template render (verify YAML output)

```bash
helm template test-infra charts/halo-infra/ | head -50
helm template test-floor charts/halo-factory-floor/ | head -30
```

Verify you see Deployments, PVCs, Services, Ingress, and NetworkPolicy rendered.

---

## 4. Service-by-Service Live Tests

Each section starts a service and tests its endpoints with `curl`. Run each in a
separate terminal or background the process.

### 4.1 HALO Kernel Gateway (:13305)

**Start**:
```bash
python3 -m uvicorn halo.kernel.gateway:app --host 0.0.0.0 --port 13305
```

#### Test: Health check

```bash
curl -s http://localhost:13305/health | python3 -m json.tool
```

**Expected**:
```json
{"status": "ok", "models": ["halo-fast", "halo-reasoning", "halo-vision"]}
```

#### Test: List models

```bash
curl -s http://localhost:13305/v1/models | python3 -m json.tool
```

**Expected**: 3 models listed with `id` fields `halo-fast`, `halo-reasoning`, `halo-vision`.

#### Test: Chat completion (accepted)

```bash
curl -s -X POST http://localhost:13305/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"halo-fast","messages":[{"role":"user","content":"Write a hello world function"}]}' \
  | python3 -m json.tool
```

**Expected**: HTTP 200 with `choices[0].message.content` containing a response.

#### Test: Chat completion (queued — admission control)

This needs to simulate the server being at capacity. The gateway tracks
`active_seqs` in memory. Send 8+ concurrent requests to `halo-fast` (max_num_seqs=8)
to fill the queue, then send one more:

```bash
# Fire 8 requests in parallel
for i in $(seq 1 8); do
  curl -s -X POST http://localhost:13305/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"model":"halo-fast","messages":[{"role":"user","content":"hello"}]}' &
done

# The 9th should get HTTP 202
curl -s -i -X POST http://localhost:13305/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"halo-fast","messages":[{"role":"user","content":"hello"}]}' \
  | head -10
```

**Expected**: `HTTP/1.1 202 Accepted` with `Retry-After` header.

> Note: Because the mock forwarder completes instantly, you may need to simulate
> latency. In production with real vLLM, concurrent requests will hold slots.
> You can also manually set `active_seqs` by modifying the gateway's `_metrics`
> dict for testing purposes.

#### Test: Unknown model rejected

```bash
curl -s -X POST http://localhost:13305/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"nonexistent","messages":[]}' | python3 -m json.tool
```

**Expected**: HTTP 400 with error message.

#### Test: Prometheus metrics

```bash
curl -s http://localhost:13305/metrics
```

**Expected**: Prometheus-format text with metrics like:
```
halo_kernel_requests_total 1
halo_kernel_admissions_queued 0
halo_kernel_active_seqs 0
halo_kernel_vram_limit_gb 60
```

---

### 4.2 TDAD Service (:8402)

**Start**:
```bash
python3 -m uvicorn halo.tdad.app:app --host 0.0.0.0 --port 8402
```

#### Test: Health check

```bash
curl -s http://localhost:8402/health | python3 -m json.tool
```

**Expected**: `{"status": "ok", "indexed": false}` (first run).

#### Test: Full index a repository

```bash
curl -s -X POST http://localhost:8402/index \
  -H "Content-Type: application/json" \
  -d '{"repo":"/tmp/halo-test/projects/demo","changed_files":[]}' \
  | python3 -m json.tool
```

**Expected**: `{"modules": 1, "tests": 1, "edges": 1}` (the demo project has 1
source file `src/app.py`, 1 test file `tests/test_app.py`).

#### Test: Analyze changed files

```bash
curl -s -X POST http://localhost:8402/analyze \
  -H "Content-Type: application/json" \
  -d '{"repo":"/tmp/halo-test/projects/demo","changed_files":["src/app.py"],"spec_id":"SPEC-001"}' \
  | python3 -m json.tool
```

**Expected**:
```json
{
    "affected_tests": ["tests/test_app.py"],
    "confidence": 1.0,
    "uncovered_paths": []
}
```

The TDAD service correctly identified that changing `src/app.py` affects the test
`tests/test_app.py`.

#### Test: Analyze with no matching tests

```bash
curl -s -X POST http://localhost:8402/analyze \
  -H "Content-Type: application/json" \
  -d '{"repo":"/tmp/halo-test/projects/demo","changed_files":["src/nonexistent.py"],"spec_id":"SPEC-001"}' \
  | python3 -m json.tool
```

**Expected**: `affected_tests: []`, `uncovered_paths: ["src/nonexistent.py"]`.

#### Test: Metrics

```bash
curl -s http://localhost:8402/metrics
```

After indexing, expect `halo_tdad_modules 1`, `halo_tdad_tests 1`,
`halo_tdad_edges 1`.

---

### 4.3 Factory Floor (:8888)

**Start**:
```bash
python3 -m uvicorn halo.factory_floor.app:app --host 0.0.0.0 --port 8888
```

#### Test: Health check

```bash
curl -s http://localhost:8888/health
```

#### Test: State snapshot

```bash
curl -s http://localhost:8888/api/state | python3 -m json.tool
```

**Expected**: JSON with `specs`, `devpods`, `model_metrics`, `logs`, `paused` fields.

#### Test: Get CSRF token (required for mutations)

```bash
TOKEN=$(curl -s http://localhost:8888/api/csrf-token | python3 -c "import sys,json;print(json.load(sys.stdin)['csrf_token'])")
echo "Token: $TOKEN"
```

#### Test: Approve a spec (CSRF required)

```bash
curl -s -X POST http://localhost:8888/api/approve \
  -H "Content-Type: application/json" \
  -d "{\"spec_id\":\"SPEC-001\",\"acceptance_criteria\":\"test passes\",\"csrf_token\":\"$TOKEN\"}" \
  | python3 -m json.tool
```

**Expected**: `{"status": "approved", "spec_id": "SPEC-001"}`.

#### Test: Approve WITHOUT CSRF (should fail)

```bash
curl -s -X POST http://localhost:8888/api/approve \
  -H "Content-Type: application/json" \
  -d '{"spec_id":"SPEC-002"}' -w "\nHTTP %{http_code}\n"
```

**Expected**: `HTTP 403` with `{"detail": "Invalid CSRF token"}`.

#### Test: Token is one-time (reuse should fail)

```bash
# Reuse the same token from above
curl -s -X POST http://localhost:8888/api/approve \
  -H "Content-Type: application/json" \
  -d "{\"spec_id\":\"SPEC-002\",\"csrf_token\":\"$TOKEN\"}" -w "\nHTTP %{http_code}\n"
```

**Expected**: `HTTP 403` — token was consumed.

#### Test: Get a fresh token and test reject/trigger/kill/pause

```bash
TOKEN=$(curl -s http://localhost:8888/api/csrf-token | python3 -c "import sys,json;print(json.load(sys.stdin)['csrf_token'])")
curl -s -X POST http://localhost:8888/api/reject \
  -H "Content-Type: application/json" \
  -d "{\"spec_id\":\"SPEC-003\",\"reason\":\"bad code\",\"csrf_token\":\"$TOKEN\"}"
echo ""

TOKEN=$(curl -s http://localhost:8888/api/csrf-token | python3 -c "import sys,json;print(json.load(sys.stdin)['csrf_token'])")
curl -s -X POST http://localhost:8888/api/trigger \
  -H "Content-Type: application/json" \
  -d "{\"spec_id\":\"SPEC-001\",\"csrf_token\":\"$TOKEN\"}"
echo ""

TOKEN=$(curl -s http://localhost:8888/api/csrf-token | python3 -c "import sys,json;print(json.load(sys.stdin)['csrf_token'])")
curl -s -X POST http://localhost:8888/api/kill \
  -H "Content-Type: application/json" \
  -d "{\"spec_id\":\"SPEC-001\",\"csrf_token\":\"$TOKEN\"}"
echo ""

TOKEN=$(curl -s http://localhost:8888/api/csrf-token | python3 -c "import sys,json;print(json.load(sys.stdin)['csrf_token'])")
curl -s -X POST http://localhost:8888/api/pause \
  -H "Content-Type: application/json" \
  -d "{\"csrf_token\":\"$TOKEN\"}"
```

#### Test: SSE endpoint

```bash
curl -s -N http://localhost:8888/api/sse
```

**Expected**: Immediate `data: {"type":"connected"}` event. The stream stays open
(receiving future events in production).

#### Test: Prometheus metrics

```bash
curl -s http://localhost:8888/metrics
```

---

### 4.4 Agent-Bridge (:9000)

**Start** (point to the demo project):
```bash
HALO_PROJECT_DIR=/tmp/halo-test/projects/demo \
  python3 -m uvicorn halo.agent_bridge.app:app --host 0.0.0.0 --port 9000
```

#### Test: Health check

```bash
curl -s http://localhost:9000/health
```

#### Test: Get current spec

```bash
curl -s http://localhost:9000/api/spec -w "\n" | head -c 300
```

**Expected**: JSON with `file: "SPEC-001.md"` and `content` containing the spec
frontmatter and body.

#### Test: List files

```bash
curl -s http://localhost:9000/api/files | python3 -m json.tool
```

**Expected**: Items array with `ARCH.md` (file), `specs` (dir), `src` (dir),
`tests` (dir).

#### Test: Browse subdirectory

```bash
curl -s http://localhost:9000/api/files?path=src | python3 -m json.tool
```

**Expected**: `{"path": "src", "items": [{"name": "app.py", "size": 148, "type":
"file"}]}`

#### Test: Launchers

```bash
curl -s http://localhost:9000/api/launchers | python3 -m json.tool
```

**Expected**: Links to terminal, vscode, files, spec.

#### Test: Chat (Nanoclaw not running — expected error)

```bash
curl -s -X POST http://localhost:9000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"hello"}' | python3 -m json.tool
```

If Nanoclaw is not running, expect `{"response": "[nanoclaw error: ...]"}`.
See [§4.5](#45-nanoclaw-unix-socket) to start Nanoclaw.

---

### 4.5 Nanoclaw Unix Socket

**Start** (requires HALO Kernel running on :13305):
```bash
python3 -m halo.nanoclaw.server
```

This creates `/tmp/nanoclaw.sock`. Test with a Python one-liner:

```python
python3 -c "
import socket, json
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.connect('/tmp/nanoclaw.sock')
sock.sendall(json.dumps({'action': 'health'}).encode() + b'\n')
print(sock.recv(4096).decode())
sock.close()
"
```

**Expected**: `{"status": "ok", "model": "halo-reasoning"}`

#### Test: Chat via socket

```python
python3 -c "
import socket, json
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.connect('/tmp/nanoclaw.sock')
sock.sendall(json.dumps({'action': 'chat', 'message': 'hello world'}).encode() + b'\n')
print(sock.recv(8192).decode())
sock.close()
"
```

**Expected**: `{"response": "[HALO Kernel placeholder response]"}` (if Kernel is
running).

#### Test: Memory append/read

```python
python3 -c "
import socket, json

sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.connect('/tmp/nanoclaw.sock')
sock.sendall(json.dumps({'action': 'memory_append', 'entry': {'role': 'user', 'content': 'test message'}}).encode() + b'\n')
print('Append:', sock.recv(4096).decode().strip())

sock.sendall(json.dumps({'action': 'memory_read', 'count': 5}).encode() + b'\n')
print('Read:', sock.recv(4092).decode().strip())
sock.close()
"
```

**Expected**: `Append: {"status": "ok"}` and `Read: {"entries": [...]}`
containing the appended message.

---

## 5. Spec Parser & State Machine

### Parse a spec file from the demo project

```python
python3 -c "
from halo.specs.parser import parse_spec_file, validate_spec
spec = parse_spec_file('/tmp/halo-test/projects/demo/specs/SPEC-001.md')
print(f'ID:           {spec.id}')
print(f'Title:        {spec.title}')
print(f'Status:       {spec.status}')
print(f'Depends on:   {spec.depends_on}')
print(f'Blocks:       {spec.blocks}')
print(f'Tags:         {spec.tags}')
print(f'Author:       {spec.author}')
print(f'Body (first 80 chars): {spec.body[:80]}')
validate_spec(spec)
print('Validation:   OK')
"
```

### Test state transitions

```python
python3 -c "
from halo.specs.state_machine import can_transition, transition, get_legal_transitions

# Test all legal paths
print('Legal transitions:')
for status in ['draft', 'ready', 'in_progress', 'implemented', 'merged', 'failed_red']:
    print(f'  {status} → {get_legal_transitions(status)}')

# Test a valid transition
new, prefix = transition('ready', 'in_progress')
print(f'\nTransition ready→in_progress: {new} (commit: \"{prefix}\")')

# Test an invalid transition
try:
    transition('draft', 'merged')
except Exception as e:
    print(f'Transition draft→merged correctly rejected: {e}')
"
```

---

## 6. Dependency Resolver

Create a multi-spec project and test dependency ordering:

```python
python3 -c "
from halo.common.models import Spec
from halo.specs.dependency_resolver import DependencyResolver

specs = {
    'SPEC-001': Spec(id='SPEC-001', title='A', status='ready',
                     depends_on=['SPEC-002'], blocks=['SPEC-003']),
    'SPEC-002': Spec(id='SPEC-002', title='B', status='implemented',
                     depends_on=[], blocks=[]),
    'SPEC-003': Spec(id='SPEC-003', title='C', status='ready',
                     depends_on=['SPEC-001'], blocks=[]),
}

resolver = DependencyResolver(specs)
print('SPEC-001 is_ready:', resolver.is_ready('SPEC-001'))  # True (SPEC-002 implemented)
print('SPEC-001 is_unblocked:', resolver.is_unblocked('SPEC-001'))  # True (nothing blocks it)

# Set SPEC-001 back to in_progress
specs['SPEC-001'].status = 'in_progress'
print('SPEC-003 unblocked (SPEC-001 blocks it):', resolver.is_unblocked('SPEC-003'))

# Topological sort
specs['SPEC-001'].status = 'ready'
order = resolver.topological_sort()
print(f'Topological order: {order}')

# Parallel groups
groups = resolver.get_parallel_groups()
print(f'Parallel groups: {groups}')
"
```

---

## 7. Full Spec Lifecycle (End-to-End)

This test exercises the entire pipeline from spec creation through merge, using
the Python API directly (no live services needed).

```python
python3 -c "
from halo.specs.parser import parse_spec_content
from halo.specs.state_machine import transition, can_transition
from halo.specs.dependency_resolver import DependencyResolver
from halo.factory.dispatcher import Dispatcher
from halo.factory.workflow import Workflow, TDDLoop
from unittest.mock import MagicMock

# 1. Create a spec (WF-SPEC-1)
spec_content = '''---
id: SPEC-001
title: \"Hello World Endpoint\"
status: draft
depends_on: []
blocks: []
tags: [api]
---
# Test
Acceptance: GET / returns 200'''
spec = parse_spec_content(spec_content)
print(f'1. Created spec: {spec.id} ({spec.status})')

# 2. Transition draft → ready (WF-SPEC-2)
spec.status, prefix = transition(spec.status, 'ready')
print(f'2. Transitioned to {spec.status} (commit: \"{prefix}\")')

# 3. Check dependencies (WF-SPEC-3)
resolver = DependencyResolver({'SPEC-001': spec})
assert resolver.can_start('SPEC-001'), 'Spec should be startable'
print('3. Dependencies satisfied — spec can start')

# 4. Dispatch Planner (WF-SPEC-4..5)
dispatcher = MagicMock()
dispatcher.dispatch_planner('SPEC-001', prompt='Plan it')
print('4. Planner dispatched')

# 5. Simulate plan complete → dispatch Coder (WF-SPEC-6..7)
dispatcher.dispatch_coder('SPEC-001', tdad_tests=['tests/test_app.py'])
print('5. Coder dispatched with TDAD injection')

# 6. TDD cycle (WF-TDD-1..5)
tdd = TDDLoop()
tdd.start('SPEC-001')
print(f'6. TDD phase: {tdd.get_phase(\"SPEC-001\")}')
tdd.verify_red('SPEC-001', tests_failed=True)
print(f'   After Red: {tdd.get_phase(\"SPEC-001\")}')
tdd.verify_green('SPEC-001', tests_passed=True)
print(f'   After Green: {tdd.get_phase(\"SPEC-001\")}')
tdd.complete_refactor('SPEC-001', tests_still_pass=True)
print(f'   After Refactor: {tdd.get_phase(\"SPEC-001\") or \"complete\"}')

# 7. Transition in_progress → implemented (WF-SPEC-9..12)
spec.status = 'in_progress'
spec.status, _ = transition(spec.status, 'implemented')
print(f'7. Transitioned to {spec.status}')

# 8. Human approval (WF-SPEC-13..14)
spec.status, prefix = transition(spec.status, 'merged')
print(f'8. Human approved — transitioned to {spec.status} (commit: \"{prefix}\")')

print()
print('=== Full spec lifecycle complete: draft → ready → in_progress → implemented → merged ===')
"
```

---

## 8. Factory Floor UI (Browser)

Once the Factory Floor is running (`python3 -m uvicorn halo.factory_floor.app:app
--port 8888`), open a browser:

```
http://localhost:8888
```

### Verify

1. **Page loads** — you should see a dark-themed dashboard with a topbar header
2. **Navigation buttons** — Kanban, Graph, Logs, Approvals, DevPods, Models
3. **Pause button** — red, top-right corner
4. **Command palette** — press `Ctrl+K` to open the command input
5. **Try commands**:
   - Type `> logs` and press Enter — should switch to the Logs view
   - Type `> pause` and press Enter — attempts to pause (needs CSRF token,
     will fail silently without one)
6. **Kanban board** — empty (no specs loaded in state snapshot yet)

> Note: The Factory Floor UI in Pass 1 shows an empty state because `/api/state`
> returns empty arrays. In Pass 2, this will connect to Redis for live data.

---

## 9. Multi-Service Integration Test

This test starts Kernel + TDAD together and verifies their interaction:

```bash
# Start Kernel
python3 -m uvicorn halo.kernel.gateway:app --host 127.0.0.1 --port 13305 &
sleep 2

# Start TDAD
python3 -m uvicorn halo.tdad.app:app --host 127.0.0.1 --port 8402 &
sleep 2

# 1. Index the demo project in TDAD
echo "=== TDAD: Indexing demo project ==="
curl -s -X POST http://localhost:8402/index \
  -H "Content-Type: application/json" \
  -d '{"repo":"/tmp/halo-test/projects/demo","changed_files":[]}'

echo ""
echo ""

# 2. Ask TDAD which tests are affected by changing src/app.py
echo "=== TDAD: Analyze src/app.py changes ==="
curl -s -X POST http://localhost:8402/analyze \
  -H "Content-Type: application/json" \
  -d '{"repo":"/tmp/halo-test/projects/demo","changed_files":["src/app.py"],"spec_id":"SPEC-001"}'

echo ""
echo ""

# 3. Use Kernel to "generate" a plan (mock)
echo "=== Kernel: Chat completion (plan generation) ==="
curl -s -X POST http://localhost:13305/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"halo-reasoning","messages":[{"role":"user","content":"Create a plan for SPEC-001: Hello World FastAPI Endpoint"}]}'

echo ""
echo ""

# 4. Check Kernel metrics reflect the request
echo "=== Kernel: Metrics after requests ==="
curl -s http://localhost:13305/metrics | grep requests_total

echo ""

# 5. Check TDAD metrics reflect indexing
echo "=== TDAD: Metrics after indexing ==="
curl -s http://localhost:8402/metrics | grep -E '(modules|tests|edges)'

# Cleanup
kill %1 %2 2>/dev/null
wait 2>/dev/null
```

**Expected output**:
```
=== TDAD: Indexing demo project ===
{"modules":1,"tests":1,"edges":1}

=== TDAD: Analyze src/app.py ===
{"affected_tests":["tests/test_app.py"],"confidence":1.0,"uncovered_paths":[]}

=== Kernel: Chat completion (plan generation) ===
{"id":"halo-cmpl-mock","object":"chat.completion","model":"halo-reasoning",...}

=== Kernel: Metrics after requests ===
halo_kernel_requests_total 1

=== TDAD: Metrics after indexing ===
halo_tdad_modules 1
halo_tdad_tests 1
halo_tdad_edges 1
```

---

## 10. Troubleshooting

### Port already in use

```bash
# Find what's using a port
lsof -i :13305
ss -tlnp | grep 13305

# Kill the process
kill -9 <PID>

# Or use a different port
python3 -m uvicorn halo.kernel.gateway:app --port 13306
```

Common port conflicts on Strix Halo systems:
- `:13305` — Lemonade server (use `:13306` for testing)
- `:9000` — Various dev servers (use `:19000` for Agent-Bridge)

### Import errors

```bash
# Ensure you're in the repo root (so `halo/` is importable as a package)
cd /home/ayassine/Projects/kube-coder
python3 -c "import halo; print('OK')"

# Install missing dependencies
pip install --break-system-packages fastapi uvicorn httpx pyyaml
```

### Redis not available

The HALO Factory is designed for graceful degradation when Redis is unavailable.
Services will start but dispatching and pub/sub events will silently fail. To
test with Redis:

```bash
# Start a local Redis
docker run -d --name halo-redis -p 6379:6379 redis:7-alpine

# Verify
redis-cli ping
# PONG

# Or install redis-server locally
sudo apt install redis-server
sudo systemctl start redis-server
```

### Qdrant not available

RAG indexer/query will silently return empty results when Qdrant is not running.
To test with Qdrant:

```bash
docker run -d --name halo-qdrant -p 6333:6333 qdrant/qdrant:latest

# Verify
curl http://localhost:6333/healthz
```

### MinIO not available

Artifact upload/download will fail but tests mock the MinIO client. To test with
MinIO:

```bash
docker run -d --name halo-minio -p 9000:9000 -p 9020:9020 \
  -e MINIO_ROOT_USER=halo-admin -e MINIO_ROOT_PASSWORD=halo-password \
  minio/minio server /data --console-address ":9020"

# Verify
curl http://localhost:9000/minio/health/live
```

### Tests fail with ModuleNotFoundError

```bash
# Ensure PYTHONPATH includes the repo root
export PYTHONPATH=/home/ayassine/Projects/kube-coder:$PYTHONPATH

# Or run from the repo root
cd /home/ayassine/Projects/kube-coder
python3 -m unittest discover -s halo/tests -p 'test_*.py' -v
```

### Factory Floor CSRF fails

CSRF tokens are one-time use and stored in an in-memory set. If the server
restarts, all tokens are invalidated. Get a fresh token:

```bash
curl -s http://localhost:8888/api/csrf-token
```

### Nanoclaw socket not found

The Nanoclaw server creates `/tmp/nanoclaw.sock` on start. If a stale socket
file exists from a previous run, the server will unlink it. If the server fails
to start:

```bash
rm -f /tmp/nanoclaw.sock
python3 -m halo.nanoclaw.server
```

### Agent-Bridge can't find specs

The Agent-Bridge looks at the `HALO_PROJECT_DIR` environment variable. Ensure it
points to a project directory containing a `specs/` subdirectory:

```bash
export HALO_PROJECT_DIR=/tmp/halo-test/projects/demo
python3 -m uvicorn halo.agent_bridge.app:app --port 9000
```

---

## Appendix: Service Port Reference

| Service | Default Port | Alternative Port |
|---------|-------------|-----------------|
| HALO Kernel | 13305 | 13306 |
| TDAD | 8402 | 18402 |
| Factory Floor | 8888 | 18888 |
| Agent-Bridge | 9000 | 19000 |
| Nanoclaw | /tmp/nanoclaw.sock | — |
| Redis | 6379 | — |
| MinIO API | 9000 (conflicts!) | 19000 |
| MinIO Console | 9020 | — |
| Qdrant | 6333 | — |