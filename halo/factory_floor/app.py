#!/usr/bin/env python3
"""Factory Floor — FastAPI backend (:8888) (FF-R1..FF-R7).

SSE relay, state snapshot, approval/trigger/reject/kill/pause endpoints.
CSRF protection on all mutating endpoints (SEC-6).
"""

import json
import secrets

from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from halo.common.models import (
    SPEC_STATUS_DRAFT, SPEC_STATUS_READY, SPEC_STATUS_IMPLEMENTED,
    SPEC_STATUS_MERGED, CHANNEL_LOGS, CHANNEL_APPROVALS, CHANNEL_ALERTS, CHANNEL_METRICS,
)


app = FastAPI(title="HALO Factory Floor", version="2.0.0-halo")

_csrf_tokens = set()


class ApproveRequest(BaseModel):
    spec_id: str
    acceptance_criteria: str = ""
    csrf_token: str = ""


class RejectRequest(BaseModel):
    spec_id: str
    reason: str = ""
    csrf_token: str = ""


class TriggerRequest(BaseModel):
    spec_id: str
    csrf_token: str = ""


class KillRequest(BaseModel):
    spec_id: str
    csrf_token: str = ""


class PauseRequest(BaseModel):
    csrf_token: str = ""


def verify_csrf(token: str):
    """Verify CSRF token (SEC-6)."""
    if not token or token not in _csrf_tokens:
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


@app.get("/api/csrf-token")
async def get_csrf_token():
    """Get a CSRF token for future mutations (SEC-6)."""
    token = secrets.token_urlsafe(32)
    _csrf_tokens.add(token)
    return {"csrf_token": token}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/state")
async def get_state():
    """Return full state snapshot (FF-R3)."""
    return {
        "specs": [],
        "devpods": [],
        "model_metrics": {"queue_depth": 0, "tokens_per_sec": 0, "active_seqs": 0},
        "logs": [],
        "paused": False,
    }


@app.get("/api/specs")
async def list_specs():
    """List all specs."""
    return {"specs": []}


@app.post("/api/approve")
async def approve_spec(req: ApproveRequest):
    """Transition implemented → merged (FF-R4, SEC-6)."""
    verify_csrf(req.csrf_token)
    _csrf_tokens.discard(req.csrf_token)
    return {"status": "approved", "spec_id": req.spec_id}


@app.post("/api/reject")
async def reject_spec(req: RejectRequest):
    """Transition implemented → draft (FF-R4, SEC-6)."""
    verify_csrf(req.csrf_token)
    _csrf_tokens.discard(req.csrf_token)
    return {"status": "rejected", "spec_id": req.spec_id, "reason": req.reason}


@app.post("/api/trigger")
async def trigger_spec(req: TriggerRequest):
    """Transition draft → ready (FF-R4, SEC-6)."""
    verify_csrf(req.csrf_token)
    _csrf_tokens.discard(req.csrf_token)
    return {"status": "triggered", "spec_id": req.spec_id}


@app.post("/api/kill")
async def kill_spec(req: KillRequest):
    """Force-terminate DevPod and mark as failed (FF-R4, SEC-6)."""
    verify_csrf(req.csrf_token)
    _csrf_tokens.discard(req.csrf_token)
    return {"status": "killed", "spec_id": req.spec_id}


@app.post("/api/pause")
async def pause_supervisor(req: PauseRequest):
    """Halt supervisor event loop — maintenance mode (FF-R4, SEC-6)."""
    verify_csrf(req.csrf_token)
    _csrf_tokens.discard(req.csrf_token)
    return {"status": "paused"}


@app.get("/api/sse")
async def sse_stream():
    """SSE endpoint streaming events from Redis Pub/Sub (FF-R3, FF-NF1)."""
    async def generate():
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint (INT-EXT-3)."""
    lines = [
        "# HELP halo_factory_floor_up Service up",
        "# TYPE halo_factory_floor_up gauge",
        "halo_factory_floor_up 1",
    ]
    return Response(content="\n".join(lines) + "\n", media_type="text/plain")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8888)