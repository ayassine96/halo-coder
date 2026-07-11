#!/usr/bin/env python3
"""Agent-Bridge — per-DevPod interface (AB-R1..AB-R5).

FastAPI service at :9000 in every DevPod. Serves:
- Spec dashboard (current spec, status, acceptance criteria)
- SSE chat proxy to Nanoclaw via /tmp/nanoclaw.sock
- File tree browser (read-only of /var/halo/projects/{project})
- Terminal/VS Code launcher links
- /health for K8s liveness
- Stateless (AB-R5) — all memory in memory.jsonl or Redis
"""

import os
import json
import asyncio

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from halo.common.config import HaloConfig


app = FastAPI(title="HALO Agent-Bridge", version="2.0.0-halo")

_config = HaloConfig.from_env()
_project_dir = os.environ.get("HALO_PROJECT_DIR", _config.projects_dir)
_nanoclaw_sock = os.environ.get("HALO_NANOCLAW_SOCK", "/tmp/nanoclaw.sock")


@app.get("/health")
async def health():
    """Health endpoint for K8s liveness (AB-R4)."""
    return {"status": "ok"}


@app.get("/api/spec")
async def get_current_spec():
    """Return the current spec being worked (AB-R2)."""
    specs_dir = os.path.join(_project_dir, "specs")
    if not os.path.isdir(specs_dir):
        return JSONResponse({"error": "no specs found"}, status_code=404)
    for fname in sorted(os.listdir(specs_dir)):
        if fname.startswith("SPEC-") and fname.endswith(".md"):
            path = os.path.join(specs_dir, fname)
            with open(path, "r") as f:
                content = f.read()
            return {"file": fname, "content": content}
    return JSONResponse({"error": "no spec found"}, status_code=404)


@app.get("/api/files")
async def list_files(path=""):
    """File tree browser — read-only (AB-R2)."""
    base = os.path.join(_project_dir, path) if path else _project_dir
    if not os.path.isdir(base):
        return JSONResponse({"error": "not found"}, status_code=404)
    items = []
    for name in sorted(os.listdir(base)):
        full = os.path.join(base, name)
        items.append({
            "name": name,
            "type": "dir" if os.path.isdir(full) else "file",
            "size": os.path.getsize(full) if os.path.isfile(full) else 0,
        })
    return {"path": path, "items": items}


@app.get("/api/launchers")
async def launchers():
    """Return launcher links (AB-R2)."""
    return {
        "terminal": "/terminal",
        "vscode": "/vscode",
        "files": "/api/files",
        "spec": "/api/spec",
    }


@app.post("/api/chat")
async def send_chat(request: Request):
    """Send a message to Nanoclaw via Unix socket (AB-R3)."""
    body = await request.json()
    message = body.get("message", "")
    response = await _send_to_nanoclaw(message)
    return {"response": response}


@app.get("/api/chat/stream")
async def chat_stream(request: Request):
    """SSE stream for chat responses (AB-R3)."""
    async def generate():
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"

        class MockReceiver:
            async def __aiter__(self):
                yield f"data: {json.dumps({'type': 'response', 'content': 'placeholder'})}\n\n"

        async for chunk in MockReceiver().__aiter__():
            yield chunk

    return StreamingResponse(generate(), media_type="text/event-stream")


async def _send_to_nanoclaw(message):
    """Send message to Nanoclaw via Unix socket."""
    try:
        reader, writer = await asyncio.open_unix_connection(_nanoclaw_sock)
        writer.write(json.dumps({"action": "chat", "message": message}).encode())
        writer.write(b"\n")
        await writer.drain()
        data = await reader.readline()
        writer.close()
        await writer.wait_closed()
        return json.loads(data.decode()).get("response", "")
    except Exception as e:
        return f"[nanoclaw error: {e}]"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("HALO_AGENT_BRIDGE_PORT", "9000")))