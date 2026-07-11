#!/usr/bin/env python3
"""vLLM configuration for ROCm gfx1151 (Strix Halo)."""

ROCM_ENV = {
    "HSA_OVERRIDE_GFX_VERSION": "11.5.1",
    "PYTORCH_ROCM_ARCH": "gfx1151",
    "FLASH_ATTENTION_TRITON_AMD_ENABLE": "TRUE",
    "ROCBLAS_USE_HIPBLASLT": "1",
    "VGM_MODE": "High",
}

VRAM_SOFT_LIMIT_GB = 60
VRAM_HEADROOM_GB = 8
VLLM_HOST = "0.0.0.0"
VLLM_PORT = 13305

MODEL_PROFILES = {
    "halo-fast": {
        "model": "Qwen/Qwen2.5-Coder-14B-Instruct",
        "quantization": "awq",
        "max_num_seqs": 8,
        "gpu_memory_utilization": 0.15,
        "max_model_len": 8192,
        "dtype": "float16",
        "target tok_s": 40,
    },
    "halo-reasoning": {
        "model": "Qwen/Qwen2.5-72B-Instruct",
        "quantization": "gptq",
        "max_num_seqs": 4,
        "gpu_memory_utilization": 0.75,
        "max_model_len": 32768,
        "dtype": "float16",
        "target tok_s": 12,
    },
    "halo-vision": {
        "model": "Qwen/Qwen2-VL-7B-Instruct",
        "quantization": "awq",
        "max_num_seqs": 2,
        "gpu_memory_utilization": 0.08,
        "max_model_len": 4096,
        "dtype": "float16",
        "target_tok_s": 20,
    },
}


def get_vllm_args(profile_name):
    """Return vLLM CLI args dict for a given model profile."""
    p = MODEL_PROFILES[profile_name]
    return {
        "model": p["model"],
        "quantization": p["quantization"],
        "max-num-seqs": p["max_num_seqs"],
        "gpu-memory-utilization": p["gpu_memory_utilization"],
        "max-model-len": p["max_model_len"],
        "dtype": p["dtype"],
        "host": VLLM_HOST,
        "port": VLLM_PORT,
    }


def build_launch_command(profile_name, python="python3"):
    """Build the full vLLM launch command line."""
    args = get_vllm_args(profile_name)
    parts = [python, "-m", "vllm.entrypoints.openai.api_server"]
    for k, v in args.items():
        parts.extend([f"--{k}", str(v)])
    return parts