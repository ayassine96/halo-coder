#!/usr/bin/env python3
"""HALO Factory — unified start/stop/test helper (Pass 2).

Usage:
  python3 scripts/halo-test.py start-all       Start ALL services (Kernel, Supervisor, Floor, TDAD, Bridge, Nanoclaw)
  python3 scripts/halo-test.py stop-all        Kill ALL HALO services and free ports
  python3 scripts/halo-test.py status          Show which HALO services are running
  python3 scripts/halo-test.py start-kernel    Start individual service
  python3 scripts/halo-test.py start-supervisor Start Supervisor (includes HTTP API)
  python3 scripts/halo-test.py start-floor     Start Factory Floor (thin proxy to Supervisor)
  python3 scripts/halo-test.py start-tdad       Start TDAD
  python3 scripts/halo-test.py start-bridge     Start Agent-Bridge
  python3 scripts/halo-test.py start-nanoclaw   Start Nanoclaw
  python3 scripts/halo-test.py create-spec      Create demo spec in /tmp/halo-test
  python3 scripts/halo-test.py test-kernel      Smoke test Kernel
  python3 scripts/halo-test.py test-supervisor  Smoke test Supervisor API
  python3 scripts/halo-test.py test-floor       Smoke test Factory Floor (proxied)
  python3 scripts/halo-test.py test-tdad        Smoke test TDAD
  python3 scripts/halo-test.py test-bridge      Smoke test Agent-Bridge
  python3 scripts/halo-test.py test-all         Run all smoke tests

Environment variables (override defaults):
  HALO_KERNEL_PORT        Default: 13306  (13305 is Lemonade)
  HALO_TDAD_PORT          Default: 8402
  HALO_FACTORY_FLOOR_PORT Default: 8888
  HALO_AGENT_BRIDGE_PORT  Default: 19000  (9000 commonly occupied)
  HALO_SUPERVISOR_PORT    Default: 9091   (9090 may be occupied by system)
  HALO_KERNEL_BACKEND_URL Default: http://localhost:13305  (Lemonade)
  HALO_KERNEL_API_KEY     Default: halo-local

Prerequisites (Pass 2):
  pip install --break-system-packages fastapi uvicorn httpx pydantic redis pyyaml
  Redis running on :6379 (docker run -d --name halo-redis -p 6379:6379 redis:7-alpine)
  Lemonade running on :13305
"""
import sys
import os
import json
import signal
import subprocess
import time
import textwrap
import urllib.request

WORKDIR = "/tmp/halo-test"
PROJECTS_DIR = f"{WORKDIR}/projects"
DEMO_PROJECT = f"{PROJECTS_DIR}/demo"
SPECS_DIR = f"{DEMO_PROJECT}/specs"

KERNEL_PORT = os.environ.get("HALO_KERNEL_PORT", "13306")
TDAD_PORT = os.environ.get("HALO_TDAD_PORT", "8402")
FLOOR_PORT = os.environ.get("HALO_FACTORY_FLOOR_PORT", "8888")
BRIDGE_PORT = os.environ.get("HALO_AGENT_BRIDGE_PORT", "19000")
SUPERVISOR_PORT = os.environ.get("HALO_SUPERVISOR_PORT", "9091")
BACKEND_URL = os.environ.get("HALO_KERNEL_BACKEND_URL", "http://localhost:13305")
API_KEY = os.environ.get("HALO_KERNEL_API_KEY", "halo-local")

PID_DIR = f"{WORKDIR}/pids"

SERVICES = {
    "kernel": {
        "port": KERNEL_PORT,
        "module": "halo.kernel.gateway:app",
        "label": "HALO Kernel (Lemonade proxy)",
    },
    "supervisor": {
        "port": SUPERVISOR_PORT,
        "module": "halo.factory.supervisor_api:app",
        "label": "Supervisor API",
    },
    "floor": {
        "port": FLOOR_PORT,
        "module": "halo.factory_floor.app:app",
        "label": "Factory Floor (proxy)",
    },
    "tdad": {
        "port": TDAD_PORT,
        "module": "halo.tdad.app:app",
        "label": "TDAD (tree-sitter)",
    },
    "bridge": {
        "port": BRIDGE_PORT,
        "module": "halo.agent_bridge.app:app",
        "label": "Agent-Bridge",
    },
}


def _pid_file(name):
    os.makedirs(PID_DIR, exist_ok=True)
    return os.path.join(PID_DIR, f"{name}.pid")


def _kill_pid(pid):
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.5)
        os.kill(pid, 0)
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _port_in_use(port):
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    result = sock.connect_ex(("127.0.0.1", int(port)))
    sock.close()
    return result == 0


def _free_port(port, name):
    if _port_in_use(port):
        print(f"  Port :{port} is in use — attempting to free it...")
        pid = _get_pid_on_port(port)
        if pid:
            print(f"    Killing PID {pid} on :{port}")
            _kill_pid(pid)
            time.sleep(0.5)
        if _port_in_use(port):
            print(f"    WARNING: Port :{port} still in use after kill — {name} may fail")


def _get_pid_on_port(port):
    try:
        result = subprocess.run(
            ["ss", "-tlnp", f"sport = :{port}"],
            capture_output=True, text=True, timeout=2
        )
        for line in result.stdout.split("\n"):
            if f":{port} " in line and "pid=" in line:
                pid_part = line.split("pid=")[1].split(",")[0].split(")")[0]
                return int(pid_part)
    except Exception:
        pass
    return None


def cmd_stop_all():
    print("Stopping all HALO services ...")
    for name in SERVICES:
        pid_path = _pid_file(name)
        if os.path.exists(pid_path):
            with open(pid_path) as f:
                pid = int(f.read().strip())
            print(f"  Stopping {name} (PID {pid}) ...")
            _kill_pid(pid)
            os.unlink(pid_path)
    if os.path.exists("/tmp/nanoclaw.sock"):
        os.unlink("/tmp/nanoclaw.sock")
        print("  Removed /tmp/nanoclaw.sock")
    for name, info in SERVICES.items():
        _free_port(info["port"], name)
    print("All HALO services stopped.")


def cmd_status():
    print("HALO Service Status:")
    print(f"  {'Service':<25} {'Port':<8} {'Status':<10} {'PID':<8}")
    print(f"  {'-'*25} {'-'*8} {'-'*10} {'-'*8}")
    for name, info in SERVICES.items():
        port = info["port"]
        running = _port_in_use(port)
        pid = _get_pid_on_port(port) or "-"
        status = "RUNNING" if running else "stopped"
        print(f"  {info['label']:<25} :{port:<6} {status:<10} {pid}")
    redis_up = _port_in_use("6379")
    print(f"  {'Redis':<25} :6379    {'RUNNING' if redis_up else 'stopped':<10} {'-':<8}")
    lemonade_up = _port_in_use("13305")
    print(f"  {'Lemonade (external)':<25} :13305   {'RUNNING' if lemonade_up else 'stopped':<10} {'-':<8}")
    nanoclaw = os.path.exists("/tmp/nanoclaw.sock")
    print(f"  {'Nanoclaw socket':<25} socket   {'RUNNING' if nanoclaw else 'stopped':<10} {'-':<8}")


def _start_service(name, env=None):
    info = SERVICES[name]
    port = info["port"]
    _free_port(port, name)
    print(f"  Starting {info['label']} on :{port} ...")
    full_env = dict(os.environ)
    full_env.update(env or {})
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", info["module"],
         "--host", "0.0.0.0", "--port", port],
        env=full_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with open(_pid_file(name), "w") as f:
        f.write(str(proc.pid))
    time.sleep(1.5)
    if _port_in_use(port):
        print(f"    OK (PID {proc.pid})")
        return True
    else:
        print(f"    FAILED — check for errors")
        return False


def cmd_start_all():
    print("=" * 60)
    print("HALO Factory — Starting All Services (Pass 2)")
    print(f"  Kernel :{KERNEL_PORT}  Supervisor :{SUPERVISOR_PORT}  Floor :{FLOOR_PORT}")
    print(f"  TDAD :{TDAD_PORT}  Bridge :{BRIDGE_PORT}")
    print(f"  Backend: {BACKEND_URL} (Lemonade)")
    print("=" * 60)

    ensure_dirs()

    _start_service("kernel", {
        "HALO_KERNEL_PORT": KERNEL_PORT,
        "HALO_KERNEL_BACKEND_URL": BACKEND_URL,
        "HALO_KERNEL_API_KEY": API_KEY,
    })
    _start_service("supervisor", {
        "HALO_SUPERVISOR_PORT": SUPERVISOR_PORT,
        "HALO_PROJECTS_DIR": PROJECTS_DIR,
        "HALO_KERNEL_URL": f"http://localhost:{KERNEL_PORT}",
    })
    _start_service("floor", {
        "HALO_FACTORY_FLOOR_PORT": FLOOR_PORT,
        "HALO_SUPERVISOR_URL": f"http://localhost:{SUPERVISOR_PORT}",
    })
    _start_service("tdad", {
        "HALO_TDAD_PORT": TDAD_PORT,
    })
    _start_service("bridge", {
        "HALO_AGENT_BRIDGE_PORT": BRIDGE_PORT,
        "HALO_PROJECT_DIR": DEMO_PROJECT,
        "HALO_KERNEL_URL": f"http://localhost:{KERNEL_PORT}",
    })

    print("\n  Starting Nanoclaw socket service ...")
    nanoclaw_env = dict(os.environ)
    nanoclaw_env["HALO_KERNEL_URL"] = f"http://localhost:{KERNEL_PORT}"
    if os.path.exists("/tmp/nanoclaw.sock"):
        os.unlink("/tmp/nanoclaw.sock")
    os.environ["HALO_KERNEL_URL"] = f"http://localhost:{KERNEL_PORT}"
    proc = subprocess.Popen(
        [sys.executable, "-m", "halo.nanoclaw.server"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    with open(_pid_file("nanoclaw"), "w") as f:
        f.write(str(proc.pid))
    time.sleep(1)
    if os.path.exists("/tmp/nanoclaw.sock"):
        print(f"    OK (PID {proc.pid})")
    else:
        print(f"    FAILED")

    print("\n" + "=" * 60)
    print("All services started. Use 'status' to verify.")
    print(f"  Factory Floor: http://localhost:{FLOOR_PORT}")
    print(f"  Supervisor API: http://localhost:{SUPERVISOR_PORT}")
    print(f"  Kernel:         http://localhost:{KERNEL_PORT}")
    print("=" * 60)


def cmd_status2():
    cmd_status()


def ensure_dirs():
    os.makedirs(SPECS_DIR, exist_ok=True)
    os.makedirs(f"{DEMO_PROJECT}/src", exist_ok=True)


def cmd_start_kernel():
    ensure_dirs()
    _start_service("kernel", {
        "HALO_KERNEL_PORT": KERNEL_PORT,
        "HALO_KERNEL_BACKEND_URL": BACKEND_URL,
        "HALO_KERNEL_API_KEY": API_KEY,
    })


def cmd_start_supervisor():
    ensure_dirs()
    _start_service("supervisor", {
        "HALO_SUPERVISOR_PORT": SUPERVISOR_PORT,
        "HALO_PROJECTS_DIR": PROJECTS_DIR,
        "HALO_KERNEL_URL": f"http://localhost:{KERNEL_PORT}",
    })


def cmd_start_floor():
    _start_service("floor", {
        "HALO_FACTORY_FLOOR_PORT": FLOOR_PORT,
        "HALO_SUPERVISOR_URL": f"http://localhost:{SUPERVISOR_PORT}",
    })


def cmd_start_tdad():
    _start_service("tdad", {"HALO_TDAD_PORT": TDAD_PORT})


def cmd_start_bridge():
    ensure_dirs()
    _start_service("bridge", {
        "HALO_AGENT_BRIDGE_PORT": BRIDGE_PORT,
        "HALO_PROJECT_DIR": DEMO_PROJECT,
        "HALO_KERNEL_URL": f"http://localhost:{KERNEL_PORT}",
    })


def cmd_start_nanoclaw():
    if os.path.exists("/tmp/nanoclaw.sock"):
        os.unlink("/tmp/nanoclaw.sock")
    os.environ["HALO_KERNEL_URL"] = f"http://localhost:{KERNEL_PORT}"
    proc = subprocess.Popen([sys.executable, "-m", "halo.nanoclaw.server"])
    with open(_pid_file("nanoclaw"), "w") as f:
        f.write(str(proc.pid))
    time.sleep(1)
    if os.path.exists("/tmp/nanoclaw.sock"):
        print(f"Nanoclaw started (PID {proc.pid})")
    else:
        print("Nanoclaw FAILED to start")


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

    arch_content = "# Architecture — demo\n\n## Overview\n\nA demo FastAPI project for HALO Factory testing.\n"
    with open(f"{DEMO_PROJECT}/ARCH.md", "w") as f:
        f.write(arch_content)
    print(f"Created ARCH.md: {DEMO_PROJECT}/ARCH.md")

    print(f"\nDemo project created at {DEMO_PROJECT}")


def cmd_test_kernel():
    base = f"http://localhost:{KERNEL_PORT}"
    print(f"Testing HALO Kernel ({base}) ...")
    try:
        resp = urllib.request.urlopen(f"{base}/health", timeout=5)
        data = json.loads(resp.read())
        print(f"  /health: status={data['status']} backend_reachable={data.get('backend_reachable', '?')}")
        print(f"           models={data.get('models', [])}")
    except Exception as e:
        print(f"  /health FAILED: {e}")
        return
    try:
        resp = urllib.request.urlopen(f"{base}/v1/models", timeout=5)
        data = json.loads(resp.read())
        print(f"  /v1/models: {[m['id'] for m in data['data']]}")
    except Exception as e:
        print(f"  /v1/models FAILED: {e}")
    body = json.dumps({"model": "halo-fast", "messages": [{"role": "user", "content": "hello"}]}).encode()
    req = urllib.request.Request(f"{base}/v1/chat/completions",
                                 data=body, headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"][:80]
        print(f"  /v1/chat/completions (halo-fast): {content}")
    except Exception as e:
        print(f"  /v1/chat/completions FAILED: {e}")
    try:
        resp = urllib.request.urlopen(f"{base}/metrics", timeout=5)
        lines = resp.read().decode().strip().split("\n")
        print(f"  /metrics: {len(lines)} lines")
    except Exception as e:
        print(f"  /metrics FAILED: {e}")


def cmd_test_supervisor():
    base = f"http://localhost:{SUPERVISOR_PORT}"
    print(f"Testing Supervisor API ({base}) ...")
    try:
        resp = urllib.request.urlopen(f"{base}/health", timeout=5)
        data = json.loads(resp.read())
        print(f"  /health: {data}")
    except Exception as e:
        print(f"  /health FAILED: {e}")
        return
    try:
        resp = urllib.request.urlopen(f"{base}/api/state", timeout=5)
        data = json.loads(resp.read())
        print(f"  /api/state: specs={len(data['specs'])} devpods={len(data['devpods'])} paused={data['paused']}")
        if data["specs"]:
            print(f"    First spec: {data['specs'][0]['id']} — status={data['specs'][0]['status']}")
    except Exception as e:
        print(f"  /api/state FAILED: {e}")
    try:
        resp = urllib.request.urlopen(f"{base}/api/csrf-token", timeout=5)
        token = json.loads(resp.read())["csrf_token"]
        print(f"  /api/csrf-token: got token ({token[:16]}...)")
    except Exception as e:
        print(f"  /api/csrf-token FAILED: {e}")
    try:
        resp = urllib.request.urlopen(f"{base}/metrics", timeout=5)
        print(f"  /metrics: OK")
    except Exception as e:
        print(f"  /metrics FAILED: {e}")


def cmd_test_floor():
    base = f"http://localhost:{FLOOR_PORT}"
    print(f"Testing Factory Floor ({base}) ...")
    try:
        resp = urllib.request.urlopen(f"{base}/health", timeout=5)
        data = json.loads(resp.read())
        print(f"  /health: {data}")
    except Exception as e:
        print(f"  /health FAILED: {e}")
        return
    try:
        resp = urllib.request.urlopen(f"{base}/api/state", timeout=10)
        data = json.loads(resp.read())
        print(f"  /api/state (proxied): specs={len(data['specs'])} paused={data['paused']}")
    except Exception as e:
        print(f"  /api/state FAILED: {e}")
    try:
        resp = urllib.request.urlopen(f"{base}/api/csrf-token", timeout=5)
        token = json.loads(resp.read())["csrf_token"]
        print(f"  /api/csrf-token (proxied): got token ({token[:16]}...)")
    except Exception as e:
        print(f"  /api/csrf-token FAILED: {e}")


def cmd_test_tdad():
    base = f"http://localhost:{TDAD_PORT}"
    print(f"Testing TDAD ({base}) ...")
    try:
        resp = urllib.request.urlopen(f"{base}/health", timeout=5)
        data = json.loads(resp.read())
        print(f"  /health: {data}")
    except Exception as e:
        print(f"  /health FAILED: {e}")
        return
    ensure_dirs()
    body = json.dumps({"repo": DEMO_PROJECT, "changed_files": [], "spec_id": "SPEC-001"}).encode()
    req = urllib.request.Request(f"{base}/index",
                                 data=body, headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        print(f"  /index: modules={data.get('modules',0)} tests={data.get('tests',0)} edges={data.get('edges',0)}")
    except Exception as e:
        print(f"  /index FAILED: {e}")
    body = json.dumps({"repo": DEMO_PROJECT, "changed_files": ["src/app.py"], "spec_id": "SPEC-001"}).encode()
    req = urllib.request.Request(f"{base}/analyze",
                                 data=body, headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        print(f"  /analyze: affected_tests={data['affected_tests']} confidence={data['confidence']}")
    except Exception as e:
        print(f"  /analyze FAILED: {e}")


def cmd_test_bridge():
    base = f"http://localhost:{BRIDGE_PORT}"
    print(f"Testing Agent-Bridge ({base}) ...")
    try:
        resp = urllib.request.urlopen(f"{base}/health", timeout=5)
        data = json.loads(resp.read())
        print(f"  /health: {data}")
    except Exception as e:
        print(f"  /health FAILED: {e}")
        return
    try:
        resp = urllib.request.urlopen(f"{base}/api/files", timeout=5)
        data = json.loads(resp.read())
        print(f"  /api/files: {len(data['items'])} items at root")
    except Exception as e:
        print(f"  /api/files FAILED: {e}")
    try:
        resp = urllib.request.urlopen(f"{base}/api/launchers", timeout=5)
        data = json.loads(resp.read())
        print(f"  /api/launchers: {list(data.keys())}")
    except Exception as e:
        print(f"  /api/launchers FAILED: {e}")


def cmd_test_supervisor():
    base = f"http://localhost:{SUPERVISOR_PORT}"
    print(f"Testing Supervisor API ({base}) ...")
    try:
        resp = urllib.request.urlopen(f"{base}/health", timeout=5)
        data = json.loads(resp.read())
        print(f"  /health: {data}")
    except Exception as e:
        print(f"  /health FAILED: {e}")
        return
    try:
        resp = urllib.request.urlopen(f"{base}/api/state", timeout=5)
        data = json.loads(resp.read())
        print(f"  /api/state: specs={len(data['specs'])} devpods={len(data['devpods'])} paused={data['paused']}")
        if data["specs"]:
            print(f"    First spec: {data['specs'][0]['id']} — status={data['specs'][0]['status']}")
    except Exception as e:
        print(f"  /api/state FAILED: {e}")
    try:
        resp = urllib.request.urlopen(f"{base}/api/csrf-token", timeout=5)
        token = json.loads(resp.read())["csrf_token"]
        print(f"  /api/csrf-token: got token ({token[:16]}...)")
    except Exception as e:
        print(f"  /api/csrf-token FAILED: {e}")
    try:
        resp = urllib.request.urlopen(f"{base}/metrics", timeout=5)
        print(f"  /metrics: OK")
    except Exception as e:
        print(f"  /metrics FAILED: {e}")


def cmd_test_all():
    print("=" * 60)
    print("HALO Factory — Full Smoke Test (Pass 2)")
    print(f"  Kernel :{KERNEL_PORT}  Supervisor :{SUPERVISOR_PORT}  Floor :{FLOOR_PORT}")
    print(f"  TDAD :{TDAD_PORT}  Bridge :{BRIDGE_PORT}")
    print("=" * 60)
    print()
    cmd_test_kernel()
    print()
    cmd_test_supervisor()
    print()
    cmd_test_floor()
    print()
    cmd_test_tdad()
    print()
    cmd_test_bridge()
    print()
    print("=" * 60)
    print("All smoke tests complete.")
    print("=" * 60)


COMMANDS = {
    "start-all": cmd_start_all,
    "stop-all": cmd_stop_all,
    "status": cmd_status,
    "start-kernel": cmd_start_kernel,
    "start-supervisor": cmd_start_supervisor,
    "start-floor": cmd_start_floor,
    "start-tdad": cmd_start_tdad,
    "start-bridge": cmd_start_bridge,
    "start-nanoclaw": cmd_start_nanoclaw,
    "create-spec": cmd_create_spec,
    "test-kernel": cmd_test_kernel,
    "test-supervisor": cmd_test_supervisor,
    "test-floor": cmd_test_floor,
    "test-tdad": cmd_test_tdad,
    "test-bridge": cmd_test_bridge,
    "test-all": cmd_test_all,
}


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        print(f"\nCurrent port config:")
        print(f"  Kernel=:{KERNEL_PORT}  Supervisor=:{SUPERVISOR_PORT}  Floor=:{FLOOR_PORT}")
        print(f"  TDAD=:{TDAD_PORT}  Bridge=:{BRIDGE_PORT}")
        print(f"  Backend={BACKEND_URL} (Lemonade)")
        print(f"\nAvailable commands: {', '.join(sorted(COMMANDS))}")
        sys.exit(1)
    COMMANDS[sys.argv[1]]()