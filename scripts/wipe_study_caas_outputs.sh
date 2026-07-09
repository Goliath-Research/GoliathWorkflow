#!/usr/bin/env bash
# Wipe CAAS + Monte Carlo product outputs for one study so a clean DomainProgram
# re-run can rebuild relative CAAS links under the current mount.
#
# Usage:
#   bash scripts/wipe_study_caas_outputs.sh /work/prostate-cancer/H_PCa_good
#   bash scripts/wipe_study_caas_outputs.sh /work/prostate-cancer/H_PCa_good --yes
set -euo pipefail

STUDY_ROOT="${1:-}"
CONFIRM="${2:-}"
if [[ -z "$STUDY_ROOT" ]]; then
  echo "Usage: $0 <study_output_root> [--yes]" >&2
  exit 2
fi
STUDY_ROOT="$(readlink -f "$STUDY_ROOT" 2>/dev/null || realpath "$STUDY_ROOT")"
if [[ ! -d "$STUDY_ROOT" ]]; then
  echo "ERROR: not a directory: $STUDY_ROOT" >&2
  exit 1
fi

TARGETS=(
  "$STUDY_ROOT/.caas"
  "$STUDY_ROOT/.action_results"
  "$STUDY_ROOT/monte_carlo_runs"
  "$STUDY_ROOT/readiness"
)

echo "Will remove:"
for t in "${TARGETS[@]}"; do
  if [[ -e "$t" || -L "$t" ]]; then
    echo "  $t"
  fi
done

if [[ "$CONFIRM" != "--yes" ]]; then
  echo
  echo "Re-run with --yes to delete, then:"
  echo "  /work/prostate-cancer/configs/run_h_pca_good_mc_dmp.sh"
  exit 0
fi

for t in "${TARGETS[@]}"; do
  if [[ -e "$t" || -L "$t" ]]; then
    rm -rf "$t"
    echo "removed $t"
  fi
done
echo "Done. Re-run the DomainProgram with the fixed worker (relative CAAS + resolvedConfig)."
