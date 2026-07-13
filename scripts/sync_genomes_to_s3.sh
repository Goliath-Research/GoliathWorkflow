#!/usr/bin/env bash
# Sync /work/genomes <-> myQNAPcloud S3 (human_genome + pangenome).
#
# myQNAPcloud is S3-compatible object storage — use aws s3 sync (not rsync).
# Credentials must come from the environment; never pass keys on the CLI or
# commit them to git.
#
# Operator usage (upload local → QNAP):
#   export AWS_ACCESS_KEY_ID=...
#   export AWS_SECRET_ACCESS_KEY=...
#   scripts/sync_genomes_to_s3.sh --dry-run
#   scripts/sync_genomes_to_s3.sh
#   scripts/sync_genomes_to_s3.sh --only pangenome
#
# Operator usage (download QNAP → local, fill missing files):
#   scripts/sync_genomes_to_s3.sh --download --dry-run
#   scripts/sync_genomes_to_s3.sh --download
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
DIRECTION="upload"  # upload = local→S3, download = S3→local

usage() {
  cat <<'EOF'
Usage: scripts/sync_genomes_to_s3.sh [options]

Sync genomes between local /work/genomes and myQNAPcloud (S3-compatible).

Options:
  --download             Sync S3 → local (fill missing/outdated under /work/genomes)
  --dry-run              Pass --dryrun to aws s3 sync (no transfers)
  --delete               Pass --delete (remove destination extras absent on source; off by default)
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
    --download) DIRECTION="download"; shift ;;
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

LOCAL="$GENOMES_SRC"
REMOTE_KEY="$S3_PREFIX"
if [[ -n "$ONLY" ]]; then
  case "$ONLY" in
    human_genome|pangenome) ;;
    *)
      echo "ERROR: --only must be human_genome or pangenome (got: $ONLY)" >&2
      exit 2
      ;;
  esac
  LOCAL="${GENOMES_SRC}/${ONLY}"
  REMOTE_KEY="${S3_PREFIX}/${ONLY}"
fi

if [[ "$DIRECTION" == "upload" && ! -d "$LOCAL" ]]; then
  echo "ERROR: genomes source not found: $LOCAL" >&2
  exit 1
fi

# Ensure local dest exists for downloads
if [[ "$DIRECTION" == "download" ]]; then
  mkdir -p "$LOCAL"
fi

LOCAL_SYNC="${LOCAL%/}/"
REMOTE_URI="s3://${S3_BUCKET}/${REMOTE_KEY%/}/"

if [[ "$DIRECTION" == "download" ]]; then
  SRC_SYNC="$REMOTE_URI"
  DEST_SYNC="$LOCAL_SYNC"
else
  SRC_SYNC="$LOCAL_SYNC"
  DEST_SYNC="$REMOTE_URI"
fi

echo "Direction:   $DIRECTION"
echo "Source:      $SRC_SYNC"
echo "Destination: $DEST_SYNC"
echo "Endpoint:    $S3_ENDPOINT_URL"
echo "Region:      $AWS_DEFAULT_REGION"
if [[ -d "$LOCAL" ]]; then
  du -sh "$LOCAL" 2>/dev/null || true
fi

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
  s3 sync "$SRC_SYNC" "$DEST_SYNC"
  --endpoint-url "$S3_ENDPOINT_URL"
  --region "$AWS_DEFAULT_REGION"
)

if [[ "$DRY_RUN" -eq 1 ]]; then
  AWS_ARGS+=(--dryrun)
  echo "Mode:        dry-run"
fi
if [[ "$DO_DELETE" -eq 1 ]]; then
  AWS_ARGS+=(--delete)
  echo "Mode:        delete destination extras"
fi

echo "Running: aws ${AWS_ARGS[*]}"
aws "${AWS_ARGS[@]}"
echo "Done."
