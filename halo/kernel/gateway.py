#!/usr/bin/env python3
"""HALO Kernel — OpenAI-compatible LLM inference gateway with admission control.

Implements SRS HK-R1..HK-R5:
- Gateway on :13306 (avoids Lemonade on :13305)
- Model profiles mapped to Lemonade backend models (halo-fast, halo-reasoning, halo-coder, halo-vision)
- Admission control: HTTP 202 + Retry-After when max-num-seqs exceeded (HK-R3)
- /health endpoint (HK-R1, REL-1) with backend liveness check
- /metrics endpoint for Prometheus (HK-R5)
- Real proxy to Lemonade via httpx (A10)
"""

import os
import asyncio
import json
import time
from collections import defaultdict

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from halo.kernel.vllm_config import MODEL_PROFILES, VRAM_SOFT_LIMIT_GB


app = FastAPI(title="HALO Kernel Gateway", version="2.0.0-halo")

BACKEND_URL = os.environ.get("HALO_KERNEL_BACKEND_URL", "http://localhost:13305")
BACKEND_API_KEY = os.environ.get("HALO_KERNEL_API_KEY", "halo-local")
BACKEND_TIMEOUT = int(os.environ.get("HALO_KERNEL_BACKEND_TIMEOUT", "120"))

_metrics = defaultdict(float)
_metrics["start_time"] = time.time()
_admission_queue = {}


@app.get("/health")
async def health():
    backend_ok = await _check_backend()
    return {
        "status": "ok" if backend_ok else "degraded",
        "backend_url": BACKEND_URL,
        "backend_reachable": backend_ok,
        "models": list(MODEL_PROFILES.keys()),
    }


async def _check_backend():
    """Check if LLM backend is reachable."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{BACKEND_URL}/v1/models",
                headers={"Authorization": f"Bearer {BACKEND_API_KEY}"},
            )
            return resp.status_code == 200
    except Exception:
        return False


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {"id": name, "object": "model", "owned_by": "halo"}
            for name in MODEL_PROFILES
        ],
    }


@app.get("/metrics")
async def metrics():
    """Prometheus-format metrics (HK-R5)."""
    lines = [
        "# HELP halo_kernel_requests_total Total requests",
        "# TYPE halo_kernel_requests_total counter",
        f"halo_kernel_requests_total {_metrics['requests_total']:.0f}",
        "# HELP halo_kernel_admissions_queued Total requests queued (202)",
        "# TYPE halo_kernel_admissions_queued counter",
        f"halo_kernel_admissions_queued {_metrics['admissions_queued']:.0f}",
        "# HELP halo_kernel_active_seqs Active sequences",
        "# TYPE halo_kernel_active_seqs gauge",
        f"halo_kernel_active_seqs {_metrics['active_seqs']:.0f}",
        "# HELP halo_kernel_tokens_total Total tokens generated",
        "# TYPE halo_kernel_tokens_total counter",
        f"halo_kernel_tokens_total {_metrics['tokens_total']:.0f}",
        "# HELP halo_kernel_vram_limit_gb VRAM soft limit in GB",
        "# TYPE halo_kernel_vram_limit_gb gauge",
        f"halo_kernel_vram_limit_gb {VRAM_SOFT_LIMIT_GB}",
    ]
    return Response(content="\n".join(lines) + "\n", media_type="text/plain")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """OpenAI-compatible chat completions with admission control (HK-R3)."""
    _metrics["requests_total"] += 1
    body = await request.json()
    model = body.get("model", "halo-reasoning")

    if model not in MODEL_PROFILES:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": f"Unknown model: {model}", "type": "invalid_request_error"}},
        )

    profile = MODEL_PROFILES[model]
    current_seqs = _metrics["active_seqs"]
    max_seqs = profile["max_num_seqs"]

    if current_seqs >= max_seqs:
        _metrics["admissions_queued"] += 1
        retry_after = max(1, int(current_seqs * 2))
        return JSONResponse(
            status_code=202,
            content={"message": "Request queued — max sequences reached", "model": model},
            headers={"Retry-After": str(retry_after)},
        )

    _metrics["active_seqs"] += 1
    try:
        result = await _forward_to_backend(body, "chat/completions")
        if isinstance(result, dict) and "usage" in result:
            _metrics["tokens_total"] += result["usage"].get("completion_tokens", 0)
        return result
    except httpx.ConnectError:
        return JSONResponse(
            status_code=503,
            content={"error": {"message": "LLM backend unavailable", "type": "backend_error"}},
            headers={"Retry-After": "10"},
        )
    except httpx.TimeoutException:
        return JSONResponse(
            status_code=504,
            content={"error": {"message": "LLM backend timeout", "type": "backend_error"}},
            headers={"Retry-After": "15"},
        )
    finally:
        _metrics["active_seqs"] -= 1


@app.post("/v1/completions")
async def completions(request: Request):
    """OpenAI-compatible text completions."""
    _metrics["requests_total"] += 1
    body = await request.json()
    model = body.get("model", "halo-fast")

    if model not in MODEL_PROFILES:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": f"Unknown model: {model}", "type": "invalid_request_error"}},
        )

    _metrics["active_seqs"] += 1
    try:
        return await _forward_to_backend(body, "completions")
    except httpx.ConnectError:
        return JSONResponse(
            status_code=503,
            content={"error": {"message": "LLM backend unavailable", "type": "backend_error"}},
            headers={"Retry-After": "10"},
        )
    except httpx.TimeoutException:
        return JSONResponse(
            status_code=504,
            content={"error": {"message": "LLM backend timeout", "type": "backend_error"}},
            headers={"Retry-After": "15"},
        )
    finally:
        _metrics["active_seqs"] -= 1


def _resolve_model(body):
    """Translate HALO profile name to backend model ID."""
    model = body.get("model", "halo-reasoning")
    if model in MODEL_PROFILES:
        body = dict(body)
        body["model"] = MODEL_PROFILES[model]["backend_model"]
    return body


async def _forward_to_backend(body, endpoint):
    """Forward request to LLM backend (Lemonade) via httpx (A10)."""
    translated = _resolve_model(body)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {BACKEND_API_KEY}",
    }
    async with httpx.AsyncClient(timeout=BACKEND_TIMEOUT) as client:
        resp = await client.post(
            f"{BACKEND_URL}/v1/{endpoint}",
            json=translated,
            headers=headers,
        )
    if resp.status_code != 200:
        return JSONResponse(
            status_code=resp.status_code,
            content=resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"error": resp.text},
        )
    return resp.json()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("HALO_KERNEL_PORT", "13306")))