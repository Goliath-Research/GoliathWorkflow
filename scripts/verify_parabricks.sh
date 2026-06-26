#!/bin/bash
# Smoke-test Parabricks Docker prerequisites on a GPU worker node.
#
# Requires:
#   - docker on PATH
#   - nvidia-smi (host GPU driver)
#   - METHYL_PARABRICKS_IMAGE (e.g. nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1)
#
# Operators should validate the newest Clara Parabricks image compatible with their
# GPU generation (Hopper/Blackwell vs Ampere) before production use.

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }
warn() { echo -e "${YELLOW}!${NC} $1"; }

echo "============================================="
echo "Parabricks / Docker verification"
echo "============================================="
echo ""

if command -v docker >/dev/null 2>&1; then
  pass "docker found: $(command -v docker)"
else
  fail "docker not found on PATH"
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  pass "nvidia-smi found"
  nvidia-smi -L || warn "nvidia-smi -L failed"
else
  fail "nvidia-smi not found; GPU driver required for Parabricks"
fi

if command -v samtools >/dev/null 2>&1; then
  pass "samtools found: $(command -v samtools)"
else
  fail "samtools not found on host; required for alignment QC flagstat (install via setup_host.sh --system-deps)"
fi

IMAGE="${METHYL_PARABRICKS_IMAGE:-}"
if [[ -z "$IMAGE" ]]; then
  fail "METHYL_PARABRICKS_IMAGE is not set (try nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1)"
fi
pass "METHYL_PARABRICKS_IMAGE=$IMAGE"

GPU_FLAGS="${METHYL_PARABRICKS_GPU_FLAGS:---gpus all}"
read -r -a GPU_FLAG_ARR <<< "$GPU_FLAGS"

echo ""
echo "Checking GPU visibility inside container..."
if docker run --rm "${GPU_FLAG_ARR[@]}" "$IMAGE" nvidia-smi -L >/dev/null 2>&1; then
  pass "GPU visible inside Parabricks container"
else
  fail "GPU not visible inside container (check NVIDIA Container Toolkit)"
fi

echo ""
echo "Checking pbrun version..."
if docker run --rm "${GPU_FLAG_ARR[@]}" "$IMAGE" pbrun --version; then
  pass "pbrun --version succeeded"
else
  fail "pbrun --version failed inside $IMAGE"
fi

echo ""
echo "Checking fq2bam_meth help..."
if docker run --rm "${GPU_FLAG_ARR[@]}" "$IMAGE" pbrun fq2bam_meth --help >/dev/null 2>&1; then
  pass "pbrun fq2bam_meth --help succeeded"
else
  warn "pbrun fq2bam_meth --help unavailable; image may still work if subcommand exists"
fi

echo ""
pass "Parabricks Docker environment looks ready"
