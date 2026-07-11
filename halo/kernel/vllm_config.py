#!/usr/bin/env python3
"""HALO Kernel model profiles and LLM backend configuration.

Maps HALO profile names to Lemonade backend model IDs (A10).
Lemonade runs on :13305 and serves OpenAI-compatible /v1/chat/completions.
"""

import os

ROCM_ENV = {
    "HSA_OVERRIDE_GFX_VERSION": "11.5.1",
    "PYTORCH_ROCM_ARCH": "gfx1151",
    "FLASH_ATTENTION_TRITON_AMD_ENABLE": "TRUE",
    "ROCBLAS_USE_HIPBLASLT": "1",
    "VGM_MODE": "High",
}

VRAM_SOFT_LIMIT_GB = 60
VRAM_HEADROOM_GB = 8

BACKEND_URL = os.environ.get("HALO_KERNEL_BACKEND_URL", "http://localhost:13305")
BACKEND_API_KEY = os.environ.get("HALO_KERNEL_API_KEY", "halo-local")

MODEL_PROFILES = {
    "halo-fast": {
        "backend_model": "Qwen3-8B-GGUF",
        "max_num_seqs": 8,
        "gpu_memory_utilization": 0.15,
        "max_model_len": 40960,
        "target_tok_s": 40,
        "labels": ["reasoning", "tool-calling"],
    },
    "halo-reasoning": {
        "backend_model": "Qwen3-Next-80B-A3B-Instruct-GGUF-Q8_0",
        "max_num_seqs": 4,
        "gpu_memory_utilization": 0.75,
        "max_model_len": 262144,
        "target_tok_s": 12,
        "labels": ["tool-calling", "custom"],
    },
    "halo-coder": {
        "backend_model": "Qwen3-Coder-30B-A3B-Instruct-GGUF",
        "max_num_seqs": 6,
        "gpu_memory_utilization": 0.50,
        "max_model_len": 262144,
        "target_tok_s": 25,
        "labels": ["coding", "tool-calling"],
    },
    "halo-vision": {
        "backend_model": "Qwen2.5-VL-7B-Instruct-GGUF",
        "max_num_seqs": 2,
        "gpu_memory_utilization": 0.08,
        "max_model_len": 128000,
        "target_tok_s": 20,
        "labels": ["vision"],
    },
}


def get_backend_model(profile_name):
    """Return the Lemonade backend model ID for a HALO profile."""
    return MODEL_PROFILES[profile_name]["backend_model"]


def get_vllm_args(profile_name):
    """Return vLLM-style args dict for a given model profile (for vLLM upgrade path)."""
    p = MODEL_PROFILES[profile_name]
    return {
        "model": p["backend_model"],
        "max-num-seqs": p["max_num_seqs"],
        "gpu-memory-utilization": p["gpu_memory_utilization"],
        "max-model-len": p["max_model_len"],
        "host": "0.0.0.0",
        "port": 13305,
    }


def build_launch_command(profile_name, python="python3"):
    """Build a vLLM launch command (for future vLLM upgrade path)."""
    args = get_vllm_args(profile_name)
    parts = [python, "-m", "vllm.entrypoints.openai.api_server"]
    for k, v in args.items():
        parts.extend([f"--{k}", str(v)])
    return parts