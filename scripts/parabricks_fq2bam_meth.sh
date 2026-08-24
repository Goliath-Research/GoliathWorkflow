#!/bin/bash
# Run Parabricks fq2bam_meth (bisulfite alignment) via the shared Python runner.
#
# Usage:
#   parabricks_fq2bam_meth.sh SAMPLE_ID [--sample-dir DIR] [--genomes-dir DIR] [--reference FASTA] [--image IMAGE]
#
# Environment (cluster defaults):
#   METHYL_PARABRICKS_IMAGE          Required unless --image is passed
#   METHYL_PARABRICKS_GPU_FLAGS      Default: --gpus all
#   METHYL_PARABRICKS_BWA_THREADS    Default: 16
#   METHYL_GENOMES_DIR               Default: /work/genomes/linear/GRCh38/ensembl-116
#   METHYL_REFERENCE_FASTA           Overrides default GRCh38 primary assembly path

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -x "$PROJECT_ROOT/.venv/bin/methyl-parabricks-align" ]]; then
  RUNNER=("$PROJECT_ROOT/.venv/bin/methyl-parabricks-align")
elif [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  RUNNER=("$PROJECT_ROOT/.venv/bin/python" "-m" "methyl_worker.parabricks_runner")
else
  echo "error: activate repo .venv or install workers package" >&2
  exit 1
fi

SAMPLE_ID="${1:-}"
if [[ -z "$SAMPLE_ID" || "$SAMPLE_ID" == --* ]]; then
  echo "usage: $0 SAMPLE_ID [--sample-dir DIR] [--genomes-dir DIR] [--reference FASTA] [--image IMAGE]" >&2
  exit 1
fi
shift

SAMPLE_DIR=""
GENOMES_DIR=""
REFERENCE=""
IMAGE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sample-dir)
      SAMPLE_DIR="$2"
      shift 2
      ;;
    --genomes-dir)
      GENOMES_DIR="$2"
      shift 2
      ;;
    --reference)
      REFERENCE="$2"
      shift 2
      ;;
    --image)
      IMAGE="$2"
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$SAMPLE_DIR" ]]; then
  SAMPLE_DIR="/work/samples/${SAMPLE_ID}"
fi

if [[ -n "$GENOMES_DIR" ]]; then
  export METHYL_GENOMES_DIR="$GENOMES_DIR"
fi

ARGS=("$SAMPLE_ID" "--sample-dir" "$SAMPLE_DIR")

if [[ -n "$REFERENCE" ]]; then
  ARGS+=("--reference-fasta" "$REFERENCE")
fi
if [[ -n "$IMAGE" ]]; then
  ARGS+=("--image" "$IMAGE")
fi

exec "${RUNNER[@]}" "${ARGS[@]}"
