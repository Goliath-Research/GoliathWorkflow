#!/bin/bash
# Register a workflow worker in PostgreSQL (wf.worker + wf.worker_token).

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/register_worker.sh [options]

Options:
  --key NAME           external_worker_key (default: hostname)
  --cluster KEY        cluster_key (default: epimethyl)
  --capability NAME    Repeatable capability filter (omit for omnibus worker)
  --env-file PATH      Append WORKER_ID and WORKER_TOKEN (default: /work/epimethyl/env/worker.env)
  --token TOKEN        Use fixed token (default: random hex)
  --dry-run            Print SQL only
  -h, --help           Show this help

Requires psql and PostgreSQL connection env (PGHOST, PGUSER, PGPASSWORD, PGDATABASE).
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

WORKER_KEY="${WORKER_KEY:-$(hostname -s 2>/dev/null || echo worker-1)}"
CLUSTER_KEY="${CLUSTER_KEY:-epimethyl}"
ENV_FILE="${EPIMETHYL_ENV_DIR:-/work/epimethyl/env}/worker.env"
TOKEN=""
CAPABILITIES_JSON="null"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --key) WORKER_KEY="${2:-}"; shift 2 ;;
    --cluster) CLUSTER_KEY="${2:-}"; shift 2 ;;
    --capability)
      if [[ "$CAPABILITIES_JSON" == "null" ]]; then
        CAPABILITIES_JSON='[]'
      fi
      CAPABILITIES_JSON="$(python3 -c "import json,sys; c=json.loads(sys.argv[1]); c.append(sys.argv[2]); print(json.dumps(c))" "$CAPABILITIES_JSON" "${2:-}")"
      shift 2
      ;;
    --env-file) ENV_FILE="${2:-}"; shift 2 ;;
    --token) TOKEN="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

export PGHOST="${PGHOST:-epimethyl.postgres.database.azure.com}"
export PGPORT="${PGPORT:-5432}"
export PGDATABASE="${PGDATABASE:-${POSTGRES_DB:-postgres}}"
export PGSSLMODE="${PGSSLMODE:-require}"
export PGUSER="${PGUSER:-${POSTGRES_USER:-dba}}"

if [[ -z "${PGPASSWORD:-}" && -n "${POSTGRES_PASSWORD:-}" ]]; then
  export PGPASSWORD="$POSTGRES_PASSWORD"
fi

if [[ -z "${PGPASSWORD:-}" ]]; then
  echo "Set PGPASSWORD or POSTGRES_PASSWORD" >&2
  exit 1
fi

if [[ -z "$TOKEN" ]]; then
  TOKEN="$(openssl rand -hex 32)"
fi

TOKEN_HASH="$(printf '%s' "$TOKEN" | sha256sum | awk '{print $1}')"

SQL=$(cat <<SQL
DO \$\$
DECLARE
  v_cluster_id bigint;
  v_worker_id bigint;
BEGIN
  INSERT INTO wf.cluster (cluster_key, name, shared_storage_uri, worker_mount_path, status)
  VALUES (
    '${CLUSTER_KEY}',
    'Epimethyl cluster',
    '/work/epimethyl',
    '/work/epimethyl',
    'ACTIVE'
  )
  ON CONFLICT (cluster_key) DO UPDATE
    SET name = EXCLUDED.name,
        shared_storage_uri = EXCLUDED.shared_storage_uri,
        worker_mount_path = EXCLUDED.worker_mount_path
  RETURNING id INTO v_cluster_id;

  IF v_cluster_id IS NULL THEN
    SELECT id INTO v_cluster_id FROM wf.cluster WHERE cluster_key = '${CLUSTER_KEY}';
  END IF;

  INSERT INTO wf.worker (cluster_id, external_worker_key, display_name, capabilities, status)
  VALUES (
    v_cluster_id,
    '${WORKER_KEY}',
    '${WORKER_KEY}',
    '${CAPABILITIES_JSON}'::jsonb,
    'REGISTERED'
  )
  ON CONFLICT (external_worker_key) DO UPDATE
    SET cluster_id = EXCLUDED.cluster_id,
        capabilities = EXCLUDED.capabilities,
        status = 'REGISTERED'
  RETURNING id INTO v_worker_id;

  IF v_worker_id IS NULL THEN
    SELECT id INTO v_worker_id FROM wf.worker WHERE external_worker_key = '${WORKER_KEY}';
  END IF;

  DELETE FROM wf.worker_token WHERE worker_id = v_worker_id;
  INSERT INTO wf.worker_token (worker_id, token_hash, status)
  VALUES (v_worker_id, decode('${TOKEN_HASH}', 'hex'), 'ACTIVE');

  RAISE NOTICE 'worker_id=%', v_worker_id;
END \$\$;
SQL
)

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "$SQL"
  exit 0
fi

NOTICE="$(psql -q -v ON_ERROR_STOP=1 -c "$SQL" 2>&1 | grep 'NOTICE:' | tail -1 || true)"
WORKER_ID="$(echo "$NOTICE" | sed -n 's/.*worker_id=//p')"

if [[ -z "$WORKER_ID" ]]; then
  WORKER_ID="$(psql -q -t -A -c "SELECT id FROM wf.worker WHERE external_worker_key='${WORKER_KEY}' LIMIT 1;")"
fi

echo "Registered worker:"
echo "  WORKER_ID=$WORKER_ID"
echo "  WORKER_KEY=$WORKER_KEY"
echo "  WORKER_TOKEN=$TOKEN"

mkdir -p "$(dirname "$ENV_FILE")"
touch "$ENV_FILE"
grep -v '^WORKER_ID=' "$ENV_FILE" | grep -v '^WORKER_TOKEN=' >"${ENV_FILE}.tmp" || true
{
  cat "${ENV_FILE}.tmp" 2>/dev/null || true
  echo "WORKER_ID=$WORKER_ID"
  echo "WORKER_TOKEN=$TOKEN"
} >"$ENV_FILE"
rm -f "${ENV_FILE}.tmp"
echo "Updated $ENV_FILE"
