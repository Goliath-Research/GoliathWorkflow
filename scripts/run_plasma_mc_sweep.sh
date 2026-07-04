#!/usr/bin/env bash
# Run Monte Carlo gene stability for Plasma (cfDNA) on a VM with /work NFS mounted.
# Pair with scripts/run_buffy_mc_sweep.sh on a second VM, then compare:
#   scripts/compare_analyte_sweep_results.sh --sweep-id <ID>
#
# Example (single parameter set):
#   scripts/run_plasma_mc_sweep.sh \
#     --sweep-id stability_v1 \
#     --params-file scripts/config/analyte_sweep.example.json
#
# Example (parameter grid, sequential on this VM):
#   scripts/run_plasma_mc_sweep.sh \
#     --sweep-id grid_v1 \
#     --grid-file scripts/config/analyte_sweep.grid.example.json

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/mc_analyte_sweep_common.sh"

ANALYTE="plasma"
PROJECT_JSON="${PLASMA_PROJECT:-/work/projects/prostate-cancer/configs/project_Plasma_healthy_vs_PCa.json}"

SWEEP_ID=""
PARAMS_FILE=""
GRID_FILE=""
OUTPUT_BASE=""
RESUME_ARG=""
DRY_RUN=0
SKIP_MC=0

usage() {
  cat <<EOF
Usage: $(basename "$0") --sweep-id ID [options]

Plasma (cfDNA) MC stability runner for shared /work storage.
Writes outputs under:
  /work/projects/prostate-cancer/sweeps/<sweep-id>/[variant/]plasma/
  .../Plasma_healthy_vs_PCa/monte_carlo_runs/

$(mc_sweep_usage_header)

Plasma-specific:
  PLASMA_PROJECT         Study manifest (default: project_Plasma_healthy_vs_PCa.json)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sweep-id) SWEEP_ID="${2:-}"; shift 2 ;;
    --params-file) PARAMS_FILE="${2:-}"; shift 2 ;;
    --grid-file) GRID_FILE="${2:-}"; shift 2 ;;
    --output-base) OUTPUT_BASE="${2:-}"; shift 2 ;;
    --resume)
      if [[ "${2:-}" =~ ^[0-9]+$ ]]; then
        RESUME_ARG="$2"
        shift 2
      else
        RESUME_ARG="1"
        shift
      fi
      ;;
    --dry-run) DRY_RUN=1; shift ;;
    --skip-mc) SKIP_MC=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "$SWEEP_ID" ]]; then
  echo "Error: --sweep-id is required." >&2
  usage
  exit 1
fi

if [[ -n "$GRID_FILE" && -n "$PARAMS_FILE" ]]; then
  echo "Error: use either --params-file or --grid-file, not both." >&2
  exit 1
fi

mc_sweep_defaults
OUTPUT_BASE="${OUTPUT_BASE:-$SWEEP_ROOT/$SWEEP_ID}"

if [[ ! -f "$PROJECT_JSON" ]]; then
  echo "Error: plasma project manifest not found: $PROJECT_JSON" >&2
  exit 1
fi

if [[ -n "$GRID_FILE" ]]; then
  if [[ ! -f "$GRID_FILE" ]]; then
    echo "Error: grid file not found: $GRID_FILE" >&2
    exit 1
  fi
  mc_sweep_run_grid "$ANALYTE" "$PROJECT_JSON" "$SWEEP_ID" "$OUTPUT_BASE" \
    "$GRID_FILE" "$RESUME_ARG" "$DRY_RUN" "$SKIP_MC"
elif [[ -n "$PARAMS_FILE" ]]; then
  if [[ ! -f "$PARAMS_FILE" ]]; then
    echo "Error: params file not found: $PARAMS_FILE" >&2
    exit 1
  fi
  mc_sweep_run_one "$ANALYTE" "$PROJECT_JSON" "$SWEEP_ID" "$SWEEP_ID" \
    "$OUTPUT_BASE" "$PARAMS_FILE" "$RESUME_ARG" "$DRY_RUN" "$SKIP_MC"
else
  DEFAULT_PARAMS="$SCRIPT_DIR/config/analyte_sweep.example.json"
  if [[ ! -f "$DEFAULT_PARAMS" ]]; then
    echo "Error: no --params-file and default missing: $DEFAULT_PARAMS" >&2
    exit 1
  fi
  mc_sweep_run_one "$ANALYTE" "$PROJECT_JSON" "$SWEEP_ID" "$SWEEP_ID" \
    "$OUTPUT_BASE" "$DEFAULT_PARAMS" "$RESUME_ARG" "$DRY_RUN" "$SKIP_MC"
fi

echo "Plasma sweep complete: sweep_id=$SWEEP_ID output_base=$OUTPUT_BASE"
echo "When Buffy finishes on the other VM, run:"
echo "  $SCRIPT_DIR/compare_analyte_sweep_results.sh --sweep-id $SWEEP_ID"
