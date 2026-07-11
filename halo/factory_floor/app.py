#!/usr/bin/env python3
"""Factory Floor — thin proxy to Supervisor API + static SPA (:8888) (A9, FF-R1..FF-P7).

Pass 2: All /api/* requests are proxied to the Supervisor HTTP API (:9090).
Factory Floor only serves static files (HTML/CSS/JS) and proxies API calls.
Business logic lives in the Supervisor (single source of truth).
"""

import os
import json

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles


app = FastAPI(title="HALO Factory Floor", version="2.0.0-halo")

SUPERVISOR_URL = os.environ.get("HALO_SUPERVISOR_URL", "http://localhost:9090")

_static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/")
async def root():
    with open(os.path.join(_static_dir, "index.html")) as f:
        return HTMLResponse(f.read())


@app.get("/health")
async def health():
    return {"status": "ok", "supervisor_url": SUPERVISOR_URL}


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_api(path: str, request: Request):
    """Proxy all /api/* requests to Supervisor HTTP API (A9)."""
    url = f"{SUPERVISOR_URL}/api/{path}"
    headers = dict(request.headers)
    headers.pop("host", None)
    body = await request.body()

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            resp = await client.request(
                request.method,
                url,
                content=body,
                headers=headers,
            )
        except httpx.ConnectError:
            return JSONResponse(
                status_code=503,
                content={"error": "Supervisor API unavailable", "supervisor_url": SUPERVISOR_URL},
            )

    content_type = resp.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        async def stream():
            async for chunk in resp.aiter_bytes():
                yield chunk
        return StreamingResponse(stream(), media_type="text/event-stream")
    elif "application/json" in content_type:
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    else:
        return Response(content=resp.content, status_code=resp.status_code, media_type=content_type)


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
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("HALO_FACTORY_FLOOR_PORT", "8888")))