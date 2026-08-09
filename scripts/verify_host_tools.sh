#!/usr/bin/env bash
# Verify per-VM host CLIs required by GPU workers (not shipped on /work NFS).
#
# Cluster init mounts /work once; each GPU VM must still run:
#   bash …/setup_host.sh --system-deps --gpu --no-venv
# before enroll / Align. Missing samtools caused production Align FAIL after
# dual-map (node 893).
#
# Optional: point samtools spill at local disk (faster than NFS):
#   export TMPDIR=/var/tmp/methyl-samtools
#   mkdir -p "$TMPDIR"

set -euo pipefail

PASS=0
FAIL=0

pass() { echo "PASS: $*"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $*" >&2; FAIL=$((FAIL + 1)); }

echo "============================================="
echo "Host tools verification (per-VM apt packages)"
echo "============================================="

require_bin() {
  local name="$1"
  local why="$2"
  if command -v "$name" >/dev/null 2>&1; then
    pass "$name -> $(command -v "$name") ($why)"
  else
    fail "$name not on PATH ($why). Install: setup_host.sh --system-deps [--gpu]"
  fi
}

require_bin samtools "WGBS QC BAM fixmate/sort/markdup + alignment flagstat"
require_bin bedtools "MethylMapper interval ops"
require_bin fastp "SamplePrep trim remediation"

echo ""
if [[ "$FAIL" -eq 0 ]]; then
  echo "Host tools OK ($PASS checks)"
  if [[ -n "${TMPDIR:-}" ]]; then
    echo "TMPDIR=$TMPDIR (use local disk under /var/tmp or /scratch for samtools sort spill)"
  else
    echo "TIP: set TMPDIR to local HDD/SSD (e.g. /var/tmp/methyl-samtools) so samtools sort does not spill on NFS"
  fi
  exit 0
fi
echo "Host tools FAILED ($FAIL missing). /work is shared; these packages are per-VM."
exit 1
