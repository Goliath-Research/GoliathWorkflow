#!/usr/bin/env python3
"""Register wf.cluster / wf.worker / wf.worker_token (PostgreSQL or Azure SQL)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import socket
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
WF_ENGINE = REPO_ROOT / "workflow_engine"
sys.path.insert(0, str(WF_ENGINE))

from rest.connection import resolve_connection_config  # noqa: E402
from rest.db import open_gateway_db  # noqa: E402


def _token_hash_hex(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _sql_escape(value: str) -> str:
    return value.replace("'", "''")


def _load_arc_env() -> Optional[str]:
    arc_env = Path(os.environ.get("METHYL_ARC_ENV", "/etc/methyl/arc.env"))
    if not arc_env.is_file():
        return None
    for line in arc_env.read_text(encoding="utf-8").splitlines():
        if line.startswith("ARC_RESOURCE_ID="):
            val = line.split("=", 1)[1].strip()
            return val or None
    return None


def _verify_arc_connected() -> None:
    script = REPO_ROOT / "scripts" / "verify_arc_prereqs.sh"
    if script.is_file():
        import subprocess

        subprocess.run(["bash", str(script)], check=True)
        return
    arc_id = _load_arc_env()
    if not arc_id:
        raise RuntimeError("Arc not Connected; run install_arc_agent.sh or omit --require-arc")


def register_worker(
    *,
    worker_key: str,
    cluster_key: str,
    token: str,
    capabilities: Optional[list[str]],
    allowed_cidrs: Sequence[str],
    entra_client_id: Optional[str],
    arc_resource_id: Optional[str],
    require_arc: bool,
    env_file: Path,
    dry_run: bool,
) -> int:
    if require_arc:
        _verify_arc_connected()

    token_hash = _token_hash_hex(token)
    caps_json = json.dumps(capabilities or [])
    cidrs_json = json.dumps(list(allowed_cidrs)) if allowed_cidrs else None

    config = resolve_connection_config()
    if dry_run:
        print(
            f"backend={config.backend} cluster={cluster_key} worker={worker_key} "
            f"cidrs={allowed_cidrs} entra_client_id={entra_client_id} arc_resource_id={arc_resource_id}"
        )
        return 0

    db = open_gateway_db(config)
    try:
        worker_id = _register_via_db(
            db,
            backend=config.backend,
            cluster_key=cluster_key,
            worker_key=worker_key,
            token=token,
            token_hash=token_hash,
            capabilities_json=caps_json,
            allowed_cidrs_json=cidrs_json,
            entra_client_id=entra_client_id,
            arc_resource_id=arc_resource_id,
        )
    finally:
        db.close()

    print("Registered worker:")
    print(f"  WORKER_ID={worker_id}")
    print(f"  WORKER_KEY={worker_key}")
    print(f"  WORKER_TOKEN={token}")

    env_file.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if not line.startswith("WORKER_ID=") and not line.startswith("WORKER_TOKEN="):
                lines.append(line)
    lines.append(f"WORKER_ID={worker_id}")
    lines.append(f"WORKER_TOKEN={token}")
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Updated {env_file}")
    return 0


def _register_via_db(
    db: Any,
    *,
    backend: str,
    cluster_key: str,
    worker_key: str,
    token: str,
    token_hash: str,
    capabilities_json: str,
    allowed_cidrs_json: Optional[str],
    entra_client_id: Optional[str],
    arc_resource_id: Optional[str],
) -> int:
    if backend == "postgres":
        return _register_postgres(
            db,
            cluster_key=cluster_key,
            worker_key=worker_key,
            token_hash=token_hash,
            capabilities_json=capabilities_json,
            allowed_cidrs_json=allowed_cidrs_json,
            entra_client_id=entra_client_id,
            arc_resource_id=arc_resource_id,
        )
    return _register_mssql(
        db,
        cluster_key=cluster_key,
        worker_key=worker_key,
        token=token,
        capabilities_json=capabilities_json,
        allowed_cidrs_json=allowed_cidrs_json,
        entra_client_id=entra_client_id,
        arc_resource_id=arc_resource_id,
    )


def _register_postgres(
    db: Any,
    *,
    cluster_key: str,
    worker_key: str,
    token_hash: str,
    capabilities_json: str,
    allowed_cidrs_json: Optional[str],
    entra_client_id: Optional[str],
    arc_resource_id: Optional[str],
) -> int:
    with db._pool.connection() as conn:  # type: ignore[attr-defined]
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO wf.cluster (
                  cluster_key, name, shared_storage_uri, worker_mount_path, status,
                  allowed_source_cidrs, entra_client_id, arc_resource_id
                )
                VALUES (%s, %s, '/work/epimethyl', '/work/epimethyl', 'ACTIVE', %s::jsonb, %s, %s)
                ON CONFLICT (cluster_key) DO UPDATE SET
                  name = EXCLUDED.name,
                  shared_storage_uri = EXCLUDED.shared_storage_uri,
                  worker_mount_path = EXCLUDED.worker_mount_path,
                  allowed_source_cidrs = COALESCE(EXCLUDED.allowed_source_cidrs, wf.cluster.allowed_source_cidrs),
                  entra_client_id = COALESCE(EXCLUDED.entra_client_id, wf.cluster.entra_client_id),
                  arc_resource_id = COALESCE(EXCLUDED.arc_resource_id, wf.cluster.arc_resource_id)
                RETURNING id
                """,
                (
                    cluster_key,
                    "Epimethyl cluster",
                    allowed_cidrs_json,
                    entra_client_id,
                    arc_resource_id,
                ),
            )
            cluster_id = cur.fetchone()["id"]

            cur.execute(
                """
                INSERT INTO wf.worker (cluster_id, external_worker_key, display_name, capabilities, status)
                VALUES (%s, %s, %s, %s::jsonb, 'REGISTERED')
                ON CONFLICT (external_worker_key) DO UPDATE SET
                  cluster_id = EXCLUDED.cluster_id,
                  capabilities = EXCLUDED.capabilities,
                  status = 'REGISTERED'
                RETURNING id
                """,
                (cluster_id, worker_key, worker_key, capabilities_json),
            )
            worker_id = cur.fetchone()["id"]

            cur.execute("DELETE FROM wf.worker_token WHERE worker_id = %s", (worker_id,))
            cur.execute(
                """
                INSERT INTO wf.worker_token (worker_id, token_hash, status)
                VALUES (%s, decode(%s, 'hex'), 'ACTIVE')
                """,
                (worker_id, token_hash),
            )
        conn.commit()
    return int(worker_id)


def _register_mssql(
    db: Any,
    *,
    cluster_key: str,
    worker_key: str,
    token: str,
    capabilities_json: str,
    allowed_cidrs_json: Optional[str],
    entra_client_id: Optional[str],
    arc_resource_id: Optional[str],
) -> int:
    cidrs_decl = ""
    cidrs_val = "NULL"
    if allowed_cidrs_json is not None:
        cidrs_decl = f"DECLARE @cidrs nvarchar(max) = N'{_sql_escape(allowed_cidrs_json)}';"
        cidrs_val = "@cidrs"
    entra_decl = ""
    entra_val = "NULL"
    if entra_client_id:
        entra_decl = f"DECLARE @entra nvarchar(64) = N'{_sql_escape(entra_client_id)}';"
        entra_val = "@entra"
    arc_decl = ""
    arc_val = "NULL"
    if arc_resource_id:
        arc_decl = f"DECLARE @arc nvarchar(256) = N'{_sql_escape(arc_resource_id)}';"
        arc_val = "@arc"

    sql = f"""
SET NOCOUNT ON;
{cidrs_decl}
{entra_decl}
{arc_decl}
DECLARE @cluster_id bigint;
DECLARE @worker_id bigint;
DECLARE @tok nvarchar(4000) = N'{_sql_escape(token)}';

MERGE wf.cluster AS target
USING (SELECT N'{_sql_escape(cluster_key)}' AS cluster_key) AS source
ON target.cluster_key = source.cluster_key
WHEN MATCHED THEN
  UPDATE SET
    name = N'Epimethyl cluster',
    shared_storage_uri = N'/work/epimethyl',
    worker_mount_path = N'/work/epimethyl',
    allowed_source_cidrs = COALESCE({cidrs_val}, target.allowed_source_cidrs),
    entra_client_id = COALESCE({entra_val}, target.entra_client_id),
    arc_resource_id = COALESCE({arc_val}, target.arc_resource_id)
WHEN NOT MATCHED THEN
  INSERT (cluster_key, name, shared_storage_uri, worker_mount_path, status, allowed_source_cidrs, entra_client_id, arc_resource_id)
  VALUES (
    source.cluster_key, N'Epimethyl cluster', N'/work/epimethyl', N'/work/epimethyl', N'ACTIVE',
    {cidrs_val}, {entra_val}, {arc_val}
  );

SELECT @cluster_id = id FROM wf.cluster WHERE cluster_key = N'{_sql_escape(cluster_key)}';

MERGE wf.worker AS target
USING (SELECT @cluster_id AS cluster_id, N'{_sql_escape(worker_key)}' AS external_worker_key) AS source
ON target.external_worker_key = source.external_worker_key
WHEN MATCHED THEN
  UPDATE SET cluster_id = source.cluster_id, capabilities = CAST('{_sql_escape(capabilities_json)}' AS NVARCHAR(MAX)), status = N'REGISTERED'
WHEN NOT MATCHED THEN
  INSERT (cluster_id, external_worker_key, display_name, capabilities, status)
  VALUES (source.cluster_id, source.external_worker_key, source.external_worker_key, CAST('{_sql_escape(capabilities_json)}' AS NVARCHAR(MAX)), N'REGISTERED');

SELECT @worker_id = id FROM wf.worker WHERE external_worker_key = N'{_sql_escape(worker_key)}';

DELETE FROM wf.worker_token WHERE worker_id = @worker_id;
INSERT INTO wf.worker_token (worker_id, token_hash, status)
VALUES (@worker_id, HASHBYTES('HA2_256', @tok), N'ACTIVE');

SELECT @worker_id AS worker_id;
"""
    # Fix typo HA2_256 -> SHA2_256 in sql string
    sql = sql.replace("HASHBYTES('HA2_256'", "HASHBYTES('SHA2_256'")
    row = db._fetch_one(sql, ())  # type: ignore[attr-defined]
    if not row:
        raise RuntimeError("worker registration failed")
    return int(row["worker_id"])


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Register a workflow worker in wf schema")
    parser.add_argument("--key", default="", help="external_worker_key")
    parser.add_argument("--cluster", default=os.environ.get("CLUSTER_KEY", "epimethyl"))
    parser.add_argument("--capability", action="append", default=[])
    parser.add_argument(
        "--env-file",
        default=os.path.join(os.environ.get("EPIMETHYL_ENV_DIR", "/work/epimethyl/env"), "worker.env"),
    )
    parser.add_argument("--token", default="")
    parser.add_argument("--allowed-cidr", action="append", default=[], dest="allowed_cidrs")
    parser.add_argument("--entra-client-id", default=os.environ.get("CLUSTER_ENTRA_CLIENT_ID", ""))
    parser.add_argument("--arc-resource-id", default=os.environ.get("ARC_RESOURCE_ID", ""))
    parser.add_argument("--require-arc", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    worker_key = args.key or socket.gethostname().split(".")[0] or "worker-1"
    token = args.token or secrets.token_hex(32)
    entra = args.entra_client_id.strip() or None
    arc = args.arc_resource_id.strip() or _load_arc_env()

    return register_worker(
        worker_key=worker_key,
        cluster_key=args.cluster,
        token=token,
        capabilities=args.capability or None,
        allowed_cidrs=args.allowed_cidrs,
        entra_client_id=entra,
        arc_resource_id=arc,
        require_arc=args.require_arc,
        env_file=Path(args.env_file),
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
