#!/usr/bin/env bash
# Upload / download MojoFq2bamMeth dense-v1 linear pack (+ C2T FASTA) via rclone.
#
# myQNAPcloud is S3-compatible. This script configures a transient rclone remote
# from AWS_* env vars (never commit keys) and copies only the Mojo siblings.
#
# Usage:
#   export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...
#   # Upload local → QNAP (after ensure_mojo_linear_index.sh finishes):
#   scripts/rclone_sync_mojo_linear_pack.sh --upload
#   # Download QNAP → /work (Phase 0 / new cluster):
#   scripts/rclone_sync_mojo_linear_pack.sh --download
#
# Env:
#   WORK_ROOT=/work
#   LINEAR_PIN=linear/GRCh38/ensembl-114
#   LINEAR_FASTA_NAME=Homo_sapiens.GRCh38.dna.primary_assembly.fa
#   METHYLGRAPHER_LINEAR_K=15
#   S3_ENDPOINT_URL=https://s3.us-east-1.myqnapcloud.io
#   S3_BUCKET=epimethyl
#   S3_PREFIX=genomes
#   AWS_DEFAULT_REGION=us-east-1
#   AWS_REQUEST_CHECKSUM_CALCULATION=when_required
set -euo pipefail

WORK_ROOT="${WORK_ROOT:-/work}"
LINEAR_PIN="${LINEAR_PIN:-linear/GRCh38/ensembl-114}"
LINEAR_FASTA_NAME="${LINEAR_FASTA_NAME:-Homo_sapiens.GRCh38.dna.primary_assembly.fa}"
K="${METHYLGRAPHER_LINEAR_K:-15}"
S3_ENDPOINT_URL="${S3_ENDPOINT_URL:-https://s3.us-east-1.myqnapcloud.io}"
S3_BUCKET="${S3_BUCKET:-epimethyl}"
S3_PREFIX="${S3_PREFIX:-genomes}"
AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
export AWS_DEFAULT_REGION
export AWS_REQUEST_CHECKSUM_CALCULATION="${AWS_REQUEST_CHECKSUM_CALCULATION:-when_required}"

DIRECTION=""
DRY_RUN=0

usage() {
  sed -n '2,25p' "$0"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --upload) DIRECTION=upload; shift ;;
    --download) DIRECTION=download; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$DIRECTION" ]]; then
  echo "ERROR: pass --upload or --download" >&2
  usage >&2
  exit 2
fi

if [[ -z "${AWS_ACCESS_KEY_ID:-}" || -z "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
  echo "ERROR: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY required" >&2
  exit 2
fi

if ! command -v rclone >/dev/null 2>&1; then
  echo "ERROR: rclone not on PATH (install from https://rclone.org)" >&2
  exit 3
fi

LOCAL_DIR="${WORK_ROOT}/genomes/${LINEAR_PIN}"
FASTA="${LOCAL_DIR}/${LINEAR_FASTA_NAME}"
C2T="${FASTA}.C2T.fa"
PACK="${FASTA}.mojo_linear_k${K}"
REMOTE_PREFIX="${S3_BUCKET}/${S3_PREFIX}/${LINEAR_PIN}"
# rclone s3 remote name (transient config)
RCLONE_CFG="$(mktemp)"
cleanup() { rm -f "$RCLONE_CFG"; }
trap cleanup EXIT

cat >"$RCLONE_CFG" <<EOF
[epimethyl]
type = s3
provider = Other
env_auth = true
access_key_id = ${AWS_ACCESS_KEY_ID}
secret_access_key = ${AWS_SECRET_ACCESS_KEY}
endpoint = ${S3_ENDPOINT_URL}
region = ${AWS_DEFAULT_REGION}
acl = private
force_path_style = true
no_check_bucket = true
EOF

RCLONE=(rclone --config "$RCLONE_CFG")
DRY=()
if [[ "$DRY_RUN" -eq 1 ]]; then
  DRY=(--dry-run)
fi

pack_complete() {
  [[ -f "${PACK}/meta.json" && -f "${PACK}/kmers.bin" && -f "${PACK}/offsets.bin" && -f "${PACK}/postings.bin" ]]
}

if [[ "$DIRECTION" == "upload" ]]; then
  if [[ ! -f "$C2T" ]]; then
    echo "ERROR: missing $C2T — run mojo-align ensure_mojo_linear_index.sh first" >&2
    exit 4
  fi
  if ! pack_complete; then
    echo "ERROR: incomplete dense-v1 pack at $PACK" >&2
    echo "       wait for ensure_mojo_linear_index.sh / build_mojo_linear_pack.py" >&2
    exit 4
  fi
  echo "rclone copy C2T → ${REMOTE_PREFIX}/"
  "${RCLONE[@]}" copy "${DRY[@]}" "$C2T" "epimethyl:${REMOTE_PREFIX}/" --progress
  echo "rclone copy pack → ${REMOTE_PREFIX}/$(basename "$PACK")/"
  "${RCLONE[@]}" copy "${DRY[@]}" "$PACK/" "epimethyl:${REMOTE_PREFIX}/$(basename "$PACK")/" --progress
  echo "OK uploaded Mojo linear siblings under s3://${REMOTE_PREFIX}/"
  "${RCLONE[@]}" lsf "epimethyl:${REMOTE_PREFIX}/" | grep -E 'C2T|mojo_linear' || true
else
  mkdir -p "$LOCAL_DIR"
  echo "rclone copy C2T ← ${REMOTE_PREFIX}/"
  "${RCLONE[@]}" copy "${DRY[@]}" \
    "epimethyl:${REMOTE_PREFIX}/$(basename "$C2T")" \
    "$LOCAL_DIR/" --progress
  echo "rclone copy pack ← ${REMOTE_PREFIX}/$(basename "$PACK")/"
  mkdir -p "$PACK"
  "${RCLONE[@]}" copy "${DRY[@]}" \
    "epimethyl:${REMOTE_PREFIX}/$(basename "$PACK")/" \
    "$PACK/" --progress
  if [[ "$DRY_RUN" -eq 0 ]] && ! pack_complete; then
    echo "ERROR: download finished but pack incomplete under $PACK" >&2
    exit 5
  fi
  # Ensure ref.fa link for mapper
  if [[ "$DRY_RUN" -eq 0 && -f "$C2T" && ! -e "${PACK}/ref.fa" ]]; then
    ln -sf "$C2T" "${PACK}/ref.fa" 2>/dev/null || cp -a "$C2T" "${PACK}/ref.fa"
  fi
  echo "OK Mojo linear siblings under $LOCAL_DIR"
fi
