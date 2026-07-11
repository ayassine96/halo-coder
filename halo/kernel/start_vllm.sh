#!/usr/bin/env bash
set -euo pipefail

export HSA_OVERRIDE_GFX_VERSION=11.5.1
export PYTORCH_ROCM_ARCH=gfx1151
export FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE
export ROCBLAS_USE_HIPBLASLT=1
export VGM_MODE=High

PROFILE="${HALO_MODEL_PROFILE:-halo-reasoning}"

echo "Starting vLLM server with profile: $PROFILE"

exec python3 -m vllm.entrypoints.openai.api_server \
  --model "$(python3 -c "from halo.kernel.vllm_config import MODEL_PROFILES; print(MODEL_PROFILES['$PROFILE']['model'])")" \
  --quantization "$(python3 -c "from halo.kernel.vllm_config import MODEL_PROFILES; print(MODEL_PROFILES['$PROFILE']['quantization'])")" \
  --max-num-seqs "$(python3 -c "from halo.kernel.vllm_config import MODEL_PROFILES; print(MODEL_PROFILES['$PROFILE']['max_num_seqs'])")" \
  --gpu-memory-utilization "$(python3 -c "from halo.kernel.vllm_config import MODEL_PROFILES; print(MODEL_PROFILES['$PROFILE']['gpu_memory_utilization'])")" \
  --dtype float16 \
  --host 0.0.0.0 \
  --port 13305