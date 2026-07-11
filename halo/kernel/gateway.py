#!/usr/bin/env python3
"""HALO Kernel — OpenAI-compatible vLLM inference gateway with admission control.

Implements SRS HK-R1..HK-R5:
- Gateway on :13305
- Three model profiles (halo-fast, halo-reasoning, halo-vision)
- Admission control: HTTP 202 + Retry-After when max-num-seqs exceeded (HK-R3)
- /health endpoint (HK-R1, REL-1)
- /metrics endpoint for Prometheus (HK-R5)
"""

import asyncio
import json
import time
from collections import defaultdict

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from halo.common.config import HaloConfig
from halo.kernel.vllm_config import MODEL_PROFILES, VRAM_SOFT_LIMIT_GB


app = FastAPI(title="HALO Kernel Gateway", version="2.0.0-halo")

_metrics = defaultdict(float)
_metrics["start_time"] = time.time()
_admission_queue = {}


@app.get("/health")
async def health():
    return {"status": "ok", "models": list(MODEL_PROFILES.keys())}


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
        result = await _forward_to_vllm(body)
        if "usage" in result:
            _metrics["tokens_total"] += result["usage"].get("completion_tokens", 0)
        return result
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

    return await _forward_to_vllm(body)


async def _forward_to_vllm(body):
    """Forward request to vLLM backend. Simulated for tests."""
    await asyncio.sleep(0.001)
    return {
        "id": "halo-cmpl-mock",
        "object": "chat.completion",
        "model": body.get("model", "halo-reasoning"),
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": "[HALO Kernel placeholder response]"},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


if __name__ == "__main__":
    import os, uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("HALO_KERNEL_PORT", "13305")))