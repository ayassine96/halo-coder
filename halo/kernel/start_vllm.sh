#!/usr/bin/env bash
set -euo pipefail

# HALO Kernel startup script
# Pass 2: starts the HALO Kernel gateway which proxies to Lemonade (:13305)
# Future: can be switched to vLLM by setting HALO_KERNEL_BACKEND_URL

export HSA_OVERRIDE_GFX_VERSION=11.5.1
export PYTORCH_ROCM_ARCH=gfx1151
export FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE
export ROCBLAS_USE_HIPBLASLT=1
export VGM_MODE=High

export HALO_KERNEL_BACKEND_URL="${HALO_KERNEL_BACKEND_URL:-http://localhost:13305}"
export HALO_KERNEL_API_KEY="${HALO_KERNEL_API_KEY:-halo-local}"
export HALO_KERNEL_PORT="${HALO_KERNEL_PORT:-13306}"

echo "Starting HALO Kernel gateway on :${HALO_KERNEL_PORT}"
echo "  Backend: ${HALO_KERNEL_BACKEND_URL}"

# Health check: verify Lemonade is running before starting
echo "Checking LLM backend at ${HALO_KERNEL_BACKEND_URL}..."
if curl -sf "${HALO_KERNEL_BACKEND_URL}/v1/models" -H "Authorization: Bearer ${HALO_KERNEL_API_KEY}" >/dev/null 2>&1; then
    echo "  Backend OK — models available"
else
    echo "  WARNING: Backend not reachable. Gateway will return 503 on requests."
fi

exec python3 -m uvicorn halo.kernel.gateway:app \
  --host 0.0.0.0 \
  --port "${HALO_KERNEL_PORT}"