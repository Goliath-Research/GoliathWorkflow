#!/usr/bin/env bash
# Install per-VM host packages on a GPU worker (once per machine).
#
# Shared /work (goliath, site, samples, genomes) is cluster-once NFS.
# samtools / bedtools / fastp / ODBC / NVRTC live on the VM OS disk via apt.
#
# Usage (on each sister that skipped provision_worker_node.sh):
#   sudo bash /work/goliath/current/runtime-bundle/scripts/install_host_tools_gpu_vm.sh
#   # or from a git checkout:
#   sudo bash scripts/install_host_tools_gpu_vm.sh
#
# Then re-enroll or restart the worker so capabilities re-probe, and requeue
# Aligns that failed with FileNotFoundError: samtools.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${GOLIATH_ROOT:-/work/goliath}"

if [[ -x "$SCRIPT_DIR/setup_host.sh" ]]; then
  SETUP="$SCRIPT_DIR/setup_host.sh"
elif [[ -x "$ROOT/current/runtime-bundle/scripts/setup_host.sh" ]]; then
  SETUP="$ROOT/current/runtime-bundle/scripts/setup_host.sh"
else
  echo "setup_host.sh not found next to this script or under $ROOT/current/runtime-bundle" >&2
  exit 1
fi

echo "=== Installing host system deps (samtools, bedtools, fastp, …) ==="
bash "$SETUP" --system-deps --gpu --no-venv

# Local spill for samtools sort (prefer VM disk over NFS).
SCRATCH="${METHYL_SAMTOOLS_TMPDIR:-/var/tmp/methyl-samtools}"
mkdir -p "$SCRATCH"
chmod 1777 "$SCRATCH" 2>/dev/null || true
echo "Local samtools scratch: $SCRATCH"
echo "Add to worker.env (optional): TMPDIR=$SCRATCH"

VERIFY="$SCRIPT_DIR/verify_host_tools.sh"
if [[ ! -x "$VERIFY" ]]; then
  VERIFY="$ROOT/current/runtime-bundle/scripts/verify_host_tools.sh"
fi
if [[ -x "$VERIFY" ]]; then
  bash "$VERIFY"
else
  command -v samtools
  command -v bedtools
  command -v fastp
fi

echo "Done. Restart methyl-worker (or re-enroll) so Align capability requires samtools."
