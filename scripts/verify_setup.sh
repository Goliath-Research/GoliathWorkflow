#!/bin/bash
# Verification script for repository structure and common local tooling.

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }

echo "============================================="
echo "MethylPipeline Verification"
echo "============================================="
echo ""
echo "Project root: $PROJECT_ROOT"
echo ""

echo "Checking repository structure..."

ROOT_DIRS=("packages" "configs" "docs" "scripts" "docker")
for dir in "${ROOT_DIRS[@]}"; do
  if [ -d "$PROJECT_ROOT/$dir" ]; then
    pass "$dir/"
  else
    fail "$dir/ missing"
  fi
done

echo ""
echo "Checking core packages..."

PACKAGES=(
  "methylutils"
  "methylcentroid"
  "methylcluster"
  "methyldetector"
  "methylmapper"
  "methylclassifier"
  "methylenricher"
  "methyldiseaseprogression"
  "methylalignmentqc"
  "methylextractionqc"
  "methylpredictor"
  "methylvalidation"
  "methyldomain"
  "methylfragmentomics"
)

for pkg in "${PACKAGES[@]}"; do
  if [ -d "$PROJECT_ROOT/packages/$pkg" ]; then
    if [ -f "$PROJECT_ROOT/packages/$pkg/pyproject.toml" ] || [ -f "$PROJECT_ROOT/packages/$pkg/setup.py" ]; then
      pass "packages/$pkg"
    else
      warn "packages/$pkg present but missing pyproject.toml/setup.py"
    fi
  else
    fail "packages/$pkg missing"
  fi
done

echo ""
echo "Checking workers package..."

if [ -d "$PROJECT_ROOT/workers" ]; then
  if [ -f "$PROJECT_ROOT/workers/pyproject.toml" ]; then
    pass "workers/"
  else
    warn "workers/ present but missing pyproject.toml"
  fi
else
  fail "workers/ missing"
fi

if [ -f "$PROJECT_ROOT/scripts/packages.list" ]; then
  pass "scripts/packages.list"
else
  fail "scripts/packages.list missing"
fi

echo ""
echo "Checking key docs..."

DOCS=(
  "README.md"
  "docs/OPERATIONS_MANUAL.md"
  "docs/UNIFIED_PROJECT_CONFIG_GUIDE.md"
  "docs/THEORY_AND_PACKAGES.md"
  "configs/README.md"
)

for doc in "${DOCS[@]}"; do
  if [ -f "$PROJECT_ROOT/$doc" ]; then
    pass "$doc"
  else
    fail "$doc missing"
  fi
done

echo ""
echo "Checking install and container scripts..."

SCRIPTS=(
  "scripts/setup_host.sh"
  "scripts/setup_host_conda.sh"
  "scripts/install_all.sh"
  "scripts/install_packages.sh"
  "scripts/bootstrap_epimethyl.sh"
  "scripts/setup_gpu_node.sh"
  "scripts/detect_platform.sh"
  "scripts/deploy_workflow_definitions.sh"
  "scripts/register_worker.sh"
  "scripts/verify_e2e_node.sh"
  "scripts/verify_setup.sh"
  "scripts/verify_parabricks.sh"
  "scripts/verify_methyl_extractor.sh"
  "scripts/setup_dev.sh"
  "scripts/setup_prod.sh"
  "scripts/run_container.sh"
  "scripts/manage_docker.sh"
)

for script in "${SCRIPTS[@]}"; do
  if [ -f "$PROJECT_ROOT/$script" ]; then
    if [ -x "$PROJECT_ROOT/$script" ]; then
      pass "$script"
    else
      warn "$script exists but is not executable"
    fi
  else
    fail "$script missing"
  fi
done

echo ""
echo "Checking Docker assets..."

DOCKER_FILES=(
  "docker/Dockerfile"
  "docker/Dockerfile.production"
  "docker/docker-compose.yml"
  "docker/docker-compose.production.yml"
)

for file in "${DOCKER_FILES[@]}"; do
  if [ -f "$PROJECT_ROOT/$file" ]; then
    pass "$file"
  else
    fail "$file missing"
  fi
done

echo ""
echo "Checking local tools..."

if command -v python3 >/dev/null 2>&1; then
  PYTHON_VERSION="$(python3 - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
PY
)"
  pass "python3 ($PYTHON_VERSION)"
  python3 - <<'PY' >/dev/null 2>&1 && pass "python3 >= 3.10" || fail "python3 must be >= 3.10"
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
else
  fail "python3 not found"
fi

if command -v pip >/dev/null 2>&1; then
  pass "pip"
else
  warn "pip not found in PATH"
fi

if command -v bedtools >/dev/null 2>&1; then
  pass "bedtools"
else
  warn "bedtools not found; required for methyl-mapper"
fi

if command -v docker >/dev/null 2>&1; then
  pass "docker"
  if docker compose version >/dev/null 2>&1; then
    pass "docker compose"
  else
    warn "docker compose not available"
  fi
else
  warn "docker not found; host workflow can still work without containers"
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n1 || true)"
  if [ -n "$GPU_NAME" ]; then
    pass "nvidia-smi ($GPU_NAME)"
  else
    pass "nvidia-smi"
  fi
else
  warn "nvidia-smi not found; CPU-only workflow is still supported"
fi

echo ""
echo "Checking optional Python imports..."

if command -v python3 >/dev/null 2>&1; then
  python3 - <<'PY' >/dev/null 2>&1 && pass "methyl_utils import" || warn "methyl_utils import failed; run scripts/setup_host.sh or scripts/install_all.sh"
import methyl_utils
PY
  python3 - <<'PY' >/dev/null 2>&1 && pass "methyl_predictor import" || warn "methyl_predictor import failed"
import methyl_predictor
PY
  python3 - <<'PY' >/dev/null 2>&1 && pass "methyl_validation import" || warn "methyl_validation import failed"
import methyl_validation
PY
  python3 - <<'PY' >/dev/null 2>&1 && pass "methyl_fragmentomics import" || warn "methyl_fragmentomics import failed"
import methyl_fragmentomics
PY
fi

if command -v methyl-worker >/dev/null 2>&1; then
  pass "methyl-worker CLI"
else
  warn "methyl-worker not on PATH; run scripts/install_all.sh or scripts/setup_host.sh"
fi

echo ""
echo "============================================="
echo "Verification Complete"
echo "============================================="
echo ""
echo "Supported workflows:"
echo "  Host:   bash scripts/setup_host.sh --system-deps --gpu"
echo "  Conda:  bash scripts/setup_host_conda.sh --install-miniforge"
echo "  Docker: bash scripts/setup_prod.sh"
echo ""
echo "Canonical run order:"
echo "  methyl-centroid -> methyl-detector -> methyl-mapper -> methyl-enricher -> methyl-classifier -> methyl-predictor"
echo "  Monte Carlo validation: methyl-validation --config <json>"
