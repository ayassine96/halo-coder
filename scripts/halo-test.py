#!/usr/bin/env python3
"""Manual testing helper script for HALO Factory.

Usage:
  python3 scripts/halo-test.py <command>

Commands:
  start-kernel      Start the HALO Kernel gateway (:13305)
  start-tdad        Start the TDAD service (:8402)
  start-floor       Start the Factory Floor dashboard (:8888)
  start-bridge      Start the Agent-Bridge (:9000)
  start-nanoclaw    Start the Nanoclaw socket service
  start-supervisor  Start the Supervisor (polls for specs)
  create-spec       Create a sample spec file in /tmp/halo-test
  test-kernel       Send a test request to the Kernel
  test-tdad         Send a test analyze request to TDAD
  test-floor        Test Factory Floor endpoints
  test-bridge       Test Agent-Bridge endpoints
  test-all          Run all API smoke tests
"""
import sys
import os
import json
import subprocess
import tempfile
import textwrap

WORKDIR = "/tmp/halo-test"
PROJECTS_DIR = f"{WORKDIR}/projects"
DEMO_PROJECT = f"{PROJECTS_DIR}/demo"
SPECS_DIR = f"{DEMO_PROJECT}/specs"


def ensure_dirs():
    os.makedirs(SPECS_DIR, exist_ok=True)
    os.makedirs(f"{DEMO_PROJECT}/src", exist_ok=True)


def cmd_start_kernel():
    print("Starting HALO Kernel gateway on :13305 ...")
    subprocess.run([sys.executable, "-m", "uvicorn",
                    "halo.kernel.gateway:app", "--host", "0.0.0.0", "--port", "13305"])


def cmd_start_tdad():
    print("Starting TDAD service on :8402 ...")
    subprocess.run([sys.executable, "-m", "uvicorn",
                    "halo.tdad.app:app", "--host", "0.0.0.0", "--port", "8402"])


def cmd_start_floor():
    print("Starting Factory Floor on :8888 ...")
    subprocess.run([sys.executable, "-m", "uvicorn",
                    "halo.factory_floor.app:app", "--host", "0.0.0.0", "--port", "8888"])


def cmd_start_bridge():
    print("Starting Agent-Bridge on :9000 ...")
    os.environ.setdefault("HALO_PROJECT_DIR", DEMO_PROJECT)
    subprocess.run([sys.executable, "-m", "uvicorn",
                    "halo.agent_bridge.app:app", "--host", "0.0.0.0", "--port", "9000"])


def cmd_start_nanoclaw():
    print("Starting Nanoclaw socket service ...")
    os.environ.setdefault("HALO_KERNEL_URL", "http://localhost:13305")
    subprocess.run([sys.executable, "-m", "halo.nanoclaw.server"])


def cmd_start_supervisor():
    print("Starting Supervisor ...")
    os.environ["HALO_PROJECTS_DIR"] = PROJECTS_DIR
    subprocess.run([sys.executable, "-m", "halo.factory.supervisor"])


def cmd_create_spec():
    ensure_dirs()
    spec_content = textwrap.dedent("""\
        ---
        id: SPEC-001
        title: "Hello World FastAPI Endpoint"
        status: draft
        depends_on: []
        blocks: []
        tags: [api, fastapi, tdd]
        author: halo-agent
        created_at: 2026-07-11T00:00:00Z
        ---
        # SPEC-001: Hello World FastAPI Endpoint

        ## Description

        Create a simple FastAPI application with a single GET endpoint
        that returns a JSON greeting.

        ## Acceptance Criteria

        - GET / returns HTTP 200
        - Response body is JSON: {"message": "Hello, HALO Factory!"}
        - Response content-type is application/json

        ## Test Requirements

        - Write test in tests/test_app.py
        - Use pytest with --junitxml output
    """)
    spec_path = f"{SPECS_DIR}/SPEC-001.md"
    with open(spec_path, "w") as f:
        f.write(spec_content)
    print(f"Created spec: {spec_path}")

    src_code = """\
#!/usr/bin/env python3
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello, HALO Factory!"}
"""
    src_path = f"{DEMO_PROJECT}/src/app.py"
    with open(src_path, "w") as f:
        f.write(src_code)
    print(f"Created source: {src_path}")

    test_code = """\
#!/usr/bin/env python3
from fastapi.testclient import TestClient
from src.app import app

client = TestClient(app)

def test_root():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json() == {"message": "Hello, HALO Factory!"}
"""
    test_dir = f"{DEMO_PROJECT}/tests"
    os.makedirs(test_dir, exist_ok=True)
    test_path = f"{test_dir}/test_app.py"
    with open(test_path, "w") as f:
        f.write(test_code)
    print(f"Created test: {test_path}")

    arch_content = f"# Architecture — demo\n\n## Overview\n\nA demo FastAPI project for HALO Factory testing.\n"
    with open(f"{DEMO_PROJECT}/ARCH.md", "w") as f:
        f.write(arch_content)
    print(f"Created ARCH.md: {DEMO_PROJECT}/ARCH.md")

    print(f"\nDemo project created at {DEMO_PROJECT}")
    print("To make the spec ready for processing, change 'status: draft' to 'status: ready' in the spec file.")


def cmd_test_kernel():
    import urllib.request
    print("Testing HALO Kernel (http://localhost:13305) ...")
    try:
        resp = urllib.request.urlopen("http://localhost:13305/health")
        data = json.loads(resp.read())
        print(f"  /health: {data}")
    except Exception as e:
        print(f"  /health FAILED: {e}")
        return
    try:
        resp = urllib.request.urlopen("http://localhost:13305/v1/models")
        data = json.loads(resp.read())
        print(f"  /v1/models: {[m['id'] for m in data['data']]}")
    except Exception as e:
        print(f"  /v1/models FAILED: {e}")
    body = json.dumps({"model": "halo-fast", "messages": [{"role": "user", "content": "hello"}]}).encode()
    req = urllib.request.Request("http://localhost:13305/v1/chat/completions",
                                 data=body, headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read())
        print(f"  /v1/chat/completions (halo-fast): {data['choices'][0]['message']['content'][:60]}")
    except Exception as e:
        print(f"  /v1/chat/completions FAILED: {e}")
    try:
        resp = urllib.request.urlopen("http://localhost:13305/metrics")
        print(f"  /metrics (first line): {resp.read().decode().strip().split(chr(10))[0]}")
    except Exception as e:
        print(f"  /metrics FAILED: {e}")


def cmd_test_tdad():
    import urllib.request
    print("Testing TDAD (http://localhost:8402) ...")
    try:
        resp = urllib.request.urlopen("http://localhost:8402/health")
        data = json.loads(resp.read())
        print(f"  /health: {data}")
    except Exception as e:
        print(f"  /health FAILED: {e}")
        return
    ensure_dirs()
    body = json.dumps({"repo": DEMO_PROJECT, "changed_files": ["src/app.py"], "spec_id": "SPEC-001"}).encode()
    req = urllib.request.Request("http://localhost:8402/analyze",
                                 data=body, headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read())
        print(f"  /analyze: affected_tests={data['affected_tests']}, confidence={data['confidence']}")
    except Exception as e:
        print(f"  /analyze FAILED: {e}")
    try:
        resp = urllib.request.urlopen("http://localhost:8402/metrics")
        print(f"  /metrics (first line): {resp.read().decode().strip().split(chr(10))[0]}")
    except Exception as e:
        print(f"  /metrics FAILED: {e}")


def cmd_test_floor():
    import urllib.request
    print("Testing Factory Floor (http://localhost:8888) ...")
    try:
        resp = urllib.request.urlopen("http://localhost:8888/health")
        data = json.loads(resp.read())
        print(f"  /health: {data}")
    except Exception as e:
        print(f"  /health FAILED: {e}")
        return
    try:
        resp = urllib.request.urlopen("http://localhost:8888/api/state")
        data = json.loads(resp.read())
        print(f"  /api/state: {list(data.keys())}")
    except Exception as e:
        print(f"  /api/state FAILED: {e}")
    try:
        resp = urllib.request.urlopen("http://localhost:8888/api/csrf-token")
        token = json.loads(resp.read())["csrf_token"]
        print(f"  /api/csrf-token: got token ({token[:16]}...)")
    except Exception as e:
        print(f"  /api/csrf-token FAILED: {e}")
        return
    try:
        resp = urllib.request.urlopen("http://localhost:8888/metrics")
        print(f"  /metrics (first line): {resp.read().decode().strip().split(chr(10))[0]}")
    except Exception as e:
        print(f"  /metrics FAILED: {e}")


def cmd_test_bridge():
    import urllib.request
    print("Testing Agent-Bridge (http://localhost:9000) ...")
    try:
        resp = urllib.request.urlopen("http://localhost:9000/health")
        data = json.loads(resp.read())
        print(f"  /health: {data}")
    except Exception as e:
        print(f"  /health FAILED: {e}")
        return
    try:
        resp = urllib.request.urlopen("http://localhost:9000/api/files")
        data = json.loads(resp.read())
        print(f"  /api/files: {len(data['items'])} items at root")
    except Exception as e:
        print(f"  /api/files FAILED: {e}")
    try:
        resp = urllib.request.urlopen("http://localhost:9000/api/launchers")
        data = json.loads(resp.read())
        print(f"  /api/launchers: {list(data.keys())}")
    except Exception as e:
        print(f"  /api/launchers FAILED: {e}")


def cmd_test_all():
    print("=" * 60)
    print("HALO Factory — Full Smoke Test")
    print("=" * 60)
    print()
    cmd_test_kernel()
    print()
    cmd_test_tdad()
    print()
    cmd_test_floor()
    print()
    cmd_test_bridge()
    print()
    print("=" * 60)
    print("All smoke tests complete.")
    print("=" * 60)


COMMANDS = {
    "start-kernel": cmd_start_kernel,
    "start-tdad": cmd_start_tdad,
    "start-floor": cmd_start_floor,
    "start-bridge": cmd_start_bridge,
    "start-nanoclaw": cmd_start_nanoclaw,
    "start-supervisor": cmd_start_supervisor,
    "create-spec": cmd_create_spec,
    "test-kernel": cmd_test_kernel,
    "test-tdad": cmd_test_tdad,
    "test-floor": cmd_test_floor,
    "test-bridge": cmd_test_bridge,
    "test-all": cmd_test_all,
}


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        print(f"Available commands: {', '.join(sorted(COMMANDS))}")
        sys.exit(1)
    COMMANDS[sys.argv[1]]()