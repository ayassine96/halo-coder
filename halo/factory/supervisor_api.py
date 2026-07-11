#!/usr/bin/env python3
"""HALO Supervisor HTTP API (:9090) (A9, FF-R3, FF-R4).

FastAPI server running alongside the supervisor. Serves:
- GET /api/state — full state snapshot (specs, devpods, model_metrics, paused)
- GET /api/specs — list all specs
- GET /api/spec/{spec_id} — single spec detail
- POST /api/approve — transition implemented → merged
- POST /api/reject — transition implemented → draft
- POST /api/trigger — transition draft → ready
- POST /api/kill — force-terminate DevPod
- POST /api/pause — halt supervisor event loop
- GET /api/sse — SSE relay of Redis Pub/Sub events
- GET /health — liveness probe
- GET /metrics — Prometheus metrics
"""

import os
import json
import asyncio
import secrets
import time

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
import httpx

from halo.common.models import (
    SPEC_STATUS_DRAFT, SPEC_STATUS_READY, SPEC_STATUS_IN_PROGRESS,
    SPEC_STATUS_IMPLEMENTED, SPEC_STATUS_MERGED,
    CHANNEL_LOGS, CHANNEL_APPROVALS, CHANNEL_ALERTS, CHANNEL_METRICS,
)
from halo.specs.state_machine import can_transition, transition
from halo.specs.parser import parse_specs_dir


KERNEL_URL = os.environ.get("HALO_KERNEL_URL", "http://localhost:13306")

app = FastAPI(title="HALO Supervisor API", version="2.0.0-halo")

_csrf_tokens = set()


def _get_supervisor():
    """Get the supervisor instance attached to app state."""
    return getattr(app.state, "supervisor", None)


def verify_csrf(token: str):
    if not token or token not in _csrf_tokens:
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


@app.get("/health")
async def health():
    sup = _get_supervisor()
    redis_ok = False
    k3s_ok = False
    if sup:
        if sup.redis:
            try:
                sup.redis.ping()
                redis_ok = True
            except Exception:
                redis_ok = False
        if sup.k3s:
            try:
                k3s_ok = sup.k3s.namespace_exists("default")
            except Exception:
                k3s_ok = False
        return {
            "status": "ok",
            "paused": sup._paused,
            "redis_connected": redis_ok,
            "k3s_connected": k3s_ok,
        }
    return {"status": "ok", "paused": False, "redis_connected": redis_ok, "k3s_connected": k3s_ok}


@app.get("/api/csrf-token")
async def get_csrf_token():
    token = secrets.token_urlsafe(32)
    _csrf_tokens.add(token)
    return {"csrf_token": token}


def _spec_to_dict(spec):
    return {
        "id": spec.id,
        "title": spec.title,
        "status": spec.status,
        "depends_on": spec.depends_on,
        "blocks": spec.blocks,
        "tags": spec.tags,
        "author": spec.author,
        "project": getattr(spec, "_project", ""),
        "body": spec.body[:200] if spec.body else "",
        "file_path": spec.file_path,
    }


@app.get("/api/state")
async def get_state():
    sup = _get_supervisor()
    specs_list = []
    devpods_list = []
    model_metrics = {"queue_depth": 0, "tokens_per_sec": 0, "active_seqs": 0}
    paused = False
    logs = []

    if sup:
        paused = sup._paused
        try:
            all_specs = sup.scan_projects()
            specs_list = [_spec_to_dict(s) for s in all_specs.values()]
        except Exception:
            pass
        try:
            if sup.devpod_manager:
                devpods_list = sup.devpod_manager.list_devpods()
        except Exception:
            pass
    else:
        try:
            projects_dir = os.environ.get("HALO_PROJECTS_DIR", "/var/halo/projects")
            if os.path.isdir(projects_dir):
                for project in os.listdir(projects_dir):
                    specs_dir = os.path.join(projects_dir, project, "specs")
                    if os.path.isdir(specs_dir):
                        for sid, spec in parse_specs_dir(specs_dir).items():
                            spec._project = project
                            specs_list.append(_spec_to_dict(spec))
        except Exception:
            pass

    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{KERNEL_URL}/metrics")
            if resp.status_code == 200:
                for line in resp.text.split("\n"):
                    if line.startswith("halo_kernel_active_seqs"):
                        model_metrics["active_seqs"] = int(float(line.split()[-1]))
                    elif line.startswith("halo_kernel_tokens_total"):
                        model_metrics["tokens_per_sec"] = int(float(line.split()[-1]))
    except Exception:
        pass

    try:
        redis_host = os.environ.get("HALO_REDIS_HOST", "localhost")
        redis_port = int(os.environ.get("HALO_REDIS_PORT", "6379"))
        import redis as redis_mod
        r = redis_mod.Redis(host=redis_host, port=redis_port, socket_timeout=1)
        raw_logs = r.lrange(f"{CHANNEL_LOGS}:recent", 0, 49)
        logs = [json.loads(l.decode()) if isinstance(l, bytes) else json.loads(l) for l in raw_logs]
    except Exception:
        pass

    return {
        "specs": specs_list,
        "devpods": devpods_list,
        "model_metrics": model_metrics,
        "logs": logs,
        "paused": paused,
    }


@app.get("/api/specs")
async def list_specs():
    sup = _get_supervisor()
    if sup:
        try:
            all_specs = sup.scan_projects()
            return {"specs": [_spec_to_dict(s) for s in all_specs.values()]}
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})
    return {"specs": []}


@app.get("/api/spec/{spec_id}")
async def get_spec(spec_id: str):
    sup = _get_supervisor()
    if sup:
        try:
            all_specs = sup.scan_projects()
            if spec_id in all_specs:
                return _spec_to_dict(all_specs[spec_id])
        except Exception:
            pass
    return JSONResponse(status_code=404, content={"error": f"Spec {spec_id} not found"})


class ApproveReq(BaseModel):
    spec_id: str
    acceptance_criteria: str = ""
    csrf_token: str = ""

class RejectReq(BaseModel):
    spec_id: str
    reason: str = ""
    csrf_token: str = ""

class TriggerReq(BaseModel):
    spec_id: str
    csrf_token: str = ""

class KillReq(BaseModel):
    spec_id: str
    csrf_token: str = ""

class PauseReq(BaseModel):
    csrf_token: str = ""


@app.post("/api/approve")
async def approve_spec(req: ApproveReq):
    verify_csrf(req.csrf_token)
    _csrf_tokens.discard(req.csrf_token)
    sup = _get_supervisor()
    if sup and sup.workflow:
        try:
            sup.workflow.approve_spec(req.spec_id)
            return {"status": "approved", "spec_id": req.spec_id}
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})
    return {"status": "approved", "spec_id": req.spec_id}


@app.post("/api/reject")
async def reject_spec(req: RejectReq):
    verify_csrf(req.csrf_token)
    _csrf_tokens.discard(req.csrf_token)
    sup = _get_supervisor()
    if sup and sup.workflow:
        try:
            sup.workflow.reject_spec(req.spec_id, req.reason)
            return {"status": "rejected", "spec_id": req.spec_id, "reason": req.reason}
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})
    return {"status": "rejected", "spec_id": req.spec_id, "reason": req.reason}


@app.post("/api/trigger")
async def trigger_spec(req: TriggerReq):
    verify_csrf(req.csrf_token)
    _csrf_tokens.discard(req.csrf_token)
    sup = _get_supervisor()
    if sup:
        try:
            specs = sup.scan_projects()
            if req.spec_id in specs:
                spec = specs[req.spec_id]
                if can_transition(spec.status, SPEC_STATUS_READY):
                    spec.status = SPEC_STATUS_READY
                    spec_path = spec.file_path
                    if spec_path and os.path.exists(spec_path):
                        from halo.specs.parser import update_spec_status
                        update_spec_status(spec_path, SPEC_STATUS_READY)
                    if sup.event_publisher:
                        sup.event_publisher.log_event(req.spec_id, f"Spec triggered to ready")
                    return {"status": "triggered", "spec_id": req.spec_id}
                else:
                    return JSONResponse(status_code=409, content={"error": f"Cannot trigger spec in '{spec.status}' state"})
            else:
                return JSONResponse(status_code=404, content={"error": f"Spec {req.spec_id} not found"})
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})
    return {"status": "triggered", "spec_id": req.spec_id}


@app.post("/api/kill")
async def kill_spec(req: KillReq):
    verify_csrf(req.csrf_token)
    _csrf_tokens.discard(req.csrf_token)
    sup = _get_supervisor()
    if sup and sup.devpod_manager:
        try:
            sup.devpod_manager.destroy(req.spec_id)
        except Exception:
            pass
    return {"status": "killed", "spec_id": req.spec_id}


@app.post("/api/pause")
async def pause_supervisor(req: PauseReq):
    verify_csrf(req.csrf_token)
    _csrf_tokens.discard(req.csrf_token)
    sup = _get_supervisor()
    if sup:
        if sup._paused:
            sup.resume()
            return {"status": "resumed"}
        else:
            sup.pause()
            return {"status": "paused"}
    return {"status": "paused"}


@app.get("/api/sse")
async def sse_stream():
    """SSE relay of Redis Pub/Sub events (FF-R3, FF-NF1)."""
    async def generate():
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"

        redis_host = os.environ.get("HALO_REDIS_HOST", "localhost")
        redis_port = int(os.environ.get("HALO_REDIS_PORT", "6379"))
        channels = [CHANNEL_LOGS, CHANNEL_APPROVALS, CHANNEL_ALERTS, CHANNEL_METRICS]

        try:
            import redis
            r = redis.Redis(host=redis_host, port=redis_port)
            pubsub = r.pubsub()
            for ch in channels:
                pubsub.subscribe(ch)

            for msg in pubsub.listen():
                if msg["type"] == "message":
                    data = msg["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    yield f"data: {data}\n\n"
        except Exception:
            import time
            while True:
                await asyncio.sleep(30)
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/metrics")
async def metrics():
    lines = [
        "# HELP halo_supervisor_up Service up",
        "# TYPE halo_supervisor_up gauge",
        "halo_supervisor_up 1",
    ]
    sup = _get_supervisor()
    if sup:
        lines.append(f"halo_supervisor_paused {'1' if sup._paused else '0'}")
    return Response(content="\n".join(lines) + "\n", media_type="text/plain")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("HALO_SUPERVISOR_PORT", "9090")))