#!/usr/bin/env bash
# Sync /work/genomes (human_genome + pangenome) to myQNAPcloud S3.
#
# myQNAPcloud is S3-compatible object storage — use aws s3 sync (not rsync).
# Credentials must come from the environment; never pass keys on the CLI or
# commit them to git.
#
# Operator usage:
#   export AWS_ACCESS_KEY_ID=...
#   export AWS_SECRET_ACCESS_KEY=...
#   scripts/sync_genomes_to_s3.sh --dry-run
#   scripts/sync_genomes_to_s3.sh
#   scripts/sync_genomes_to_s3.sh --only pangenome
#
# Optional env overrides:
#   GENOMES_SRC=/work/genomes
#   S3_ENDPOINT_URL=https://s3.us-east-1.myqnapcloud.io
#   S3_BUCKET=epimethyl
#   S3_PREFIX=genomes
#   AWS_DEFAULT_REGION=us-east-1
#   AWS_REQUEST_CHECKSUM_CALCULATION=when_required   # if QNAP rejects newer checksums
#
# Verify after sync:
#   aws s3 ls s3://epimethyl/genomes/ --endpoint-url https://s3.us-east-1.myqnapcloud.io
#   aws s3 ls s3://epimethyl/genomes/human_genome/release-114/ \
#     --endpoint-url https://s3.us-east-1.myqnapcloud.io
#   aws s3 ls s3://epimethyl/genomes/pangenome/ \
#     --endpoint-url https://s3.us-east-1.myqnapcloud.io

set -euo pipefail

GENOMES_SRC="${GENOMES_SRC:-/work/genomes}"
S3_ENDPOINT_URL="${S3_ENDPOINT_URL:-https://s3.us-east-1.myqnapcloud.io}"
S3_BUCKET="${S3_BUCKET:-epimethyl}"
S3_PREFIX="${S3_PREFIX:-genomes}"
AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
export AWS_DEFAULT_REGION

DRY_RUN=0
DO_DELETE=0
ONLY=""

usage() {
  cat <<'EOF'
Usage: scripts/sync_genomes_to_s3.sh [options]

Sync local genomes to myQNAPcloud (S3-compatible).

Options:
  --dry-run              Pass --dryrun to aws s3 sync (no uploads)
  --delete               Pass --delete (remove remote keys absent locally; off by default)
  --only NAME            Sync only a subtree: human_genome | pangenome
  -h, --help             Show this help

Required env:
  AWS_ACCESS_KEY_ID
  AWS_SECRET_ACCESS_KEY

Optional env: GENOMES_SRC, S3_ENDPOINT_URL, S3_BUCKET, S3_PREFIX, AWS_DEFAULT_REGION
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --delete) DO_DELETE=1; shift ;;
    --only)
      ONLY="${2:-}"
      if [[ -z "$ONLY" ]]; then
        echo "ERROR: --only requires human_genome or pangenome" >&2
        exit 2
      fi
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! command -v aws >/dev/null 2>&1; then
  echo "ERROR: aws CLI not found on PATH" >&2
  exit 1
fi

if [[ -z "${AWS_ACCESS_KEY_ID:-}" || -z "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
  echo "ERROR: set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in the environment" >&2
  exit 1
fi

if [[ ! -d "$GENOMES_SRC" ]]; then
  echo "ERROR: genomes source not found: $GENOMES_SRC" >&2
  exit 1
fi

SRC="$GENOMES_SRC"
DEST_KEY="$S3_PREFIX"
if [[ -n "$ONLY" ]]; then
  case "$ONLY" in
    human_genome|pangenome) ;;
    *)
      echo "ERROR: --only must be human_genome or pangenome (got: $ONLY)" >&2
      exit 2
      ;;
  esac
  SRC="${GENOMES_SRC}/${ONLY}"
  DEST_KEY="${S3_PREFIX}/${ONLY}"
  if [[ ! -d "$SRC" ]]; then
    echo "ERROR: subtree not found: $SRC" >&2
    exit 1
  fi
fi

# Normalize trailing slash on local source for sync semantics
SRC_SYNC="${SRC%/}/"
DEST_URI="s3://${S3_BUCKET}/${DEST_KEY%/}/"

echo "Source:      $SRC_SYNC"
echo "Destination: $DEST_URI"
echo "Endpoint:    $S3_ENDPOINT_URL"
echo "Region:      $AWS_DEFAULT_REGION"
du -sh "$SRC" 2>/dev/null || true

# QNAP / custom S3 often needs path-style addressing (do not mutate ~/.aws)
AWS_CONFIG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/aws-genomes-sync.XXXXXX")"
cleanup_aws_config() { rm -rf "$AWS_CONFIG_DIR"; }
trap cleanup_aws_config EXIT
cat >"${AWS_CONFIG_DIR}/config" <<EOF
[default]
region = ${AWS_DEFAULT_REGION}
s3 =
    addressing_style = path
EOF
export AWS_CONFIG_FILE="${AWS_CONFIG_DIR}/config"
# Prefer env credentials over any shared credentials file
export AWS_SHARED_CREDENTIALS_FILE="${AWS_CONFIG_DIR}/empty_credentials"
: >"${AWS_SHARED_CREDENTIALS_FILE}"

AWS_ARGS=(
  s3 sync "$SRC_SYNC" "$DEST_URI"
  --endpoint-url "$S3_ENDPOINT_URL"
  --region "$AWS_DEFAULT_REGION"
)

if [[ "$DRY_RUN" -eq 1 ]]; then
  AWS_ARGS+=(--dryrun)
  echo "Mode:        dry-run"
fi
if [[ "$DO_DELETE" -eq 1 ]]; then
  AWS_ARGS+=(--delete)
  echo "Mode:        delete remote extras"
fi

echo "Running: aws ${AWS_ARGS[*]}"
aws "${AWS_ARGS[@]}"
echo "Done."
