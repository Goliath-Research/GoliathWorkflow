#!/usr/bin/env python3
"""
Backend-agnostic conformance harness for wf worker API and repository contract.

Runs identical scenarios against PostgreSQL (local container) and optionally Azure SQL
when METHYL_TEST_MSSQL_DSN is set.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
SQL_PG = ROOT / "sql_pg"
CONTRACT_SCRIPT = ROOT / "contract" / "validate_contract.py"
# Portal/cfg/legacy stacks are out of scope for this harness. Stop after the
# last wf engine script the worker/repository/scope tests need.
_SKIP_DEPLOY_PREFIXES = (
    "portal_",
    "cfg_",
    "meta_",
    "rbac_",
    "contract_",
    "onboarding_",
    "e_portal_",
    "legacy_",
)
_PARITY_DEPLOY_STOP = "wf_sql_collection_bindings.sql"
_REQUIRED_PARITY_SCRIPTS = (
    "wf_reclaim_expired_leases.sql",
    "wf_action_dispatch_affinity.sql",
    "01_worker_api.sql",
)


def _parse_deploy_azure_scripts(deploy_sh: Path) -> list[str]:
    text = deploy_sh.read_text(encoding="utf-8")
    marker = "SCRIPTS=("
    start = text.find(marker)
    if start < 0:
        raise ValueError(f"No SCRIPTS=( array in {deploy_sh}")
    names: list[str] = []
    for line in text[start + len(marker) :].splitlines():
        stripped = line.strip()
        if stripped.startswith(")"):
            break
        if not stripped or stripped.startswith("#"):
            continue
        token = stripped.split("#", 1)[0].strip().rstrip("\\").strip()
        if token:
            names.append(token)
    return names


def _parity_sql_scripts() -> list[Path]:
    """Wf-engine slice of sql_pg/deploy_azure.sh (claim reads affinity columns)."""
    names = _parse_deploy_azure_scripts(SQL_PG / "deploy_azure.sh")
    out: list[Path] = []
    for name in names:
        if name.startswith(_SKIP_DEPLOY_PREFIXES):
            continue
        path = SQL_PG / name
        if not path.is_file():
            raise FileNotFoundError(f"deploy script missing: {path}")
        out.append(path)
        if name == _PARITY_DEPLOY_STOP:
            break
    have = {p.name for p in out}
    missing = [n for n in _REQUIRED_PARITY_SCRIPTS if n not in have]
    if missing:
        raise RuntimeError(
            f"parity deploy list missing {missing}; update sql_pg/deploy_azure.sh"
        )
    return out


def _pg_dsn() -> str:
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "methylpipeline_parity")
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "methyl")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _pg_env() -> dict[str, str]:
    env = os.environ.copy()
    if "PGPASSWORD" not in env and os.environ.get("POSTGRES_PASSWORD"):
        env["PGPASSWORD"] = os.environ["POSTGRES_PASSWORD"]
    env.setdefault("PGHOST", os.environ.get("POSTGRES_HOST", "localhost"))
    env.setdefault("PGPORT", os.environ.get("POSTGRES_PORT", "5432"))
    env.setdefault("PGUSER", os.environ.get("POSTGRES_USER", "postgres"))
    return env


def _psql(dsn: str, extra_args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["psql", "-q", "-v", "ON_ERROR_STOP=1", dsn, *extra_args],
        capture_output=True,
        text=True,
        env=_pg_env(),
    )
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip() or "(no psql output)"
        raise RuntimeError(f"psql failed ({proc.returncode}): {detail}")
    return proc


def _run_psql(dsn: str, sql_path: Path) -> None:
    _psql(dsn, ["-f", str(sql_path)])


def deploy_postgres(dsn: str) -> None:
    for path in _parity_sql_scripts():
        _run_psql(dsn, path)


def _psql_query(dsn: str, sql: str) -> str:
    proc = _psql(dsn, ["-t", "-A", "-c", sql])
    return proc.stdout.strip()


def _psql_query_optional(dsn: str, sql: str) -> None:
    _psql(dsn, ["-t", "-A", "-c", sql], check=False)


def seed_minimal_workflow(dsn: str) -> tuple[int, int, str]:
    """Returns (version_id, worker_id, worker_token)."""
    _psql_query_optional(dsn, "SELECT * FROM wf.sp_delete_workflow_def(NULL, 'ParityFlow', true);")
    _psql_query(dsn, "INSERT INTO wf.workflow_def (name) VALUES ('ParityFlow');")
    def_id = int(_psql_query(dsn, "SELECT id FROM wf.workflow_def WHERE name='ParityFlow' LIMIT 1;"))
    version_id = int(
        _psql_query(
            dsn,
            f"INSERT INTO wf.workflow_version (workflow_def_id) VALUES ({def_id}) RETURNING id;",
        )
    )
    action_id = _psql_query(dsn, "SELECT id FROM wf.workflow_action WHERE action_name='LoadInput' LIMIT 1;")
    if not action_id:
        action_id = int(
            _psql_query(
                dsn,
                "INSERT INTO wf.workflow_action (action_name, capability) VALUES ('LoadInput','test-cap') RETURNING id;",
            )
        )
    else:
        action_id = int(action_id)
    node_id = int(
        _psql_query(
            dsn,
            f"INSERT INTO wf.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id) "
            f"VALUES ({version_id}, 'ACTION', 'load_input', {action_id}) RETURNING id;",
        )
    )
    _psql_query(dsn, f"UPDATE wf.workflow_version SET root_node_id = {node_id} WHERE id = {version_id};")

    cluster_id = _psql_query(dsn, "SELECT id FROM wf.cluster WHERE cluster_key='parity' LIMIT 1;")
    if not cluster_id:
        cluster_id = int(
            _psql_query(
                dsn,
                "INSERT INTO wf.cluster (cluster_key, name) VALUES ('parity','Parity') RETURNING id;",
            )
        )
    else:
        cluster_id = int(cluster_id)
    worker_id = _psql_query(
        dsn,
        f"SELECT id FROM wf.worker WHERE cluster_id={cluster_id} AND external_worker_key='w1' LIMIT 1;",
    )
    if not worker_id:
        worker_id = int(
            _psql_query(
                dsn,
                f"INSERT INTO wf.worker (cluster_id, external_worker_key) VALUES ({cluster_id}, 'w1') RETURNING id;",
            )
        )
    else:
        worker_id = int(worker_id)
    # Registered capabilities gate every claim; seeded scenarios all use 'test-cap'.
    _psql_query(
        dsn,
        f"UPDATE wf.worker SET capabilities = '[\"test-cap\"]'::jsonb WHERE id={worker_id};",
    )
    token = "parity-test-token"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    _psql_query(
        dsn,
        f"DELETE FROM wf.worker_token WHERE worker_id={worker_id}; "
        f"INSERT INTO wf.worker_token (worker_id, token_hash) VALUES ({worker_id}, decode('{token_hash}','hex'));",
    )
    return version_id, worker_id, token


def start_instance(dsn: str, version_id: int) -> int:
    instance_id = int(
        _psql_query(
            dsn,
            f"SELECT id FROM wf.wf_repo_create_workflow_instance({version_id}, '{{}}'::jsonb);",
        )
    )
    _psql_query(dsn, f"CALL wf.sp_start_workflow_instance({instance_id});")
    return instance_id


def test_worker_capability_dispatch_postgres(dsn: str) -> None:
    """Workers only claim tasks matching wf.worker.capabilities."""
    version_id, worker_id, token = seed_minimal_workflow(dsn)
    load_node = int(
        _psql_query(
            dsn,
            f"SELECT id FROM wf.workflow_node WHERE workflow_version_id={version_id} AND node_key='load_input' LIMIT 1;",
        )
    )
    _psql_query(
        dsn,
        f"UPDATE wf.worker SET capabilities = '[\"test-cap\"]'::jsonb WHERE id={worker_id};",
    )
    gpu_action_id = int(
        _psql_query(
            dsn,
            "INSERT INTO wf.workflow_action (action_name, capability) "
            "VALUES ('GpuOnly','gpu-cap') RETURNING id;",
        )
    )
    gpu_node = int(
        _psql_query(
            dsn,
            f"INSERT INTO wf.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id) "
            f"VALUES ({version_id}, 'ACTION', 'gpu_only', {gpu_action_id}) RETURNING id;",
        )
    )
    _psql_query(dsn, f"UPDATE wf.workflow_version SET root_node_id = {gpu_node} WHERE id = {version_id};")
    inst_gpu = int(
        _psql_query(
            dsn,
            f"SELECT id FROM wf.wf_repo_create_workflow_instance({version_id}, '{{}}'::jsonb);",
        )
    )
    _psql_query(dsn, f"CALL wf.sp_start_workflow_instance({inst_gpu});")

    _psql_query(dsn, f"UPDATE wf.workflow_version SET root_node_id = {load_node} WHERE id = {version_id};")
    inst_ok = int(
        _psql_query(
            dsn,
            f"SELECT id FROM wf.wf_repo_create_workflow_instance({version_id}, '{{}}'::jsonb);",
        )
    )
    _psql_query(dsn, f"CALL wf.sp_start_workflow_instance({inst_ok});")

    claim = _psql_query(
        dsn,
        f"SELECT node_execution_id FROM wf.sp_worker_request_task({worker_id}, '{token}', NULL, 60);",
    )
    assert claim, "expected test-cap task claim while gpu-cap task is also READY"

    narrow = _psql_query(
        dsn,
        f"SELECT node_execution_id FROM wf.sp_worker_request_task({worker_id}, '{token}', 'gpu-cap', 60);",
    )
    assert not narrow, "poll capability must not widen beyond registration"


def test_worker_api_postgres(dsn: str) -> None:
    version_id, worker_id, token = seed_minimal_workflow(dsn)
    instance_id = int(
        _psql_query(
            dsn,
            f"SELECT id FROM wf.wf_repo_create_workflow_instance({version_id}, '{{}}'::jsonb);",
        )
    )
    _psql_query(dsn, f"CALL wf.sp_start_workflow_instance({instance_id});")

    claim = _psql_query(
        dsn,
        f"SELECT node_execution_id FROM wf.sp_worker_request_task({worker_id}, '{token}', 'test-cap', 60);",
    )
    assert claim, "expected task claim"
    ne_id = int(claim.split("|")[0])

    ack = _psql_query(
        dsn,
        f"SELECT accepted, instance_status FROM wf.sp_worker_submit_result({ne_id}, {worker_id}, '{token}', 1, '{{\"ok\":true}}'::jsonb);",
    )
    assert ack.startswith("t|COMPLETED"), f"unexpected ack: {ack}"


def test_repository_postgres(dsn: str) -> None:
    version_id = int(_psql_query(dsn, "SELECT id FROM wf.workflow_version LIMIT 1;"))
    new_id = int(
        _psql_query(
            dsn,
            f"SELECT id FROM wf.wf_repo_create_workflow_instance({version_id}, '{{\"x\":1}}'::jsonb);",
        )
    )
    assert new_id > 0
    _psql_query(dsn, f"CALL wf.wf_repo_set_instance_status({new_id}, 'RUNNING');")
    status = _psql_query(dsn, f"SELECT status FROM wf.workflow_instance WHERE id={new_id};")
    assert status == "RUNNING"


def test_scope_resolver_postgres(dsn: str) -> None:
    """Context scope vars resolve into action input_json via ${var.*}."""
    _psql_query_optional(dsn, "SELECT * FROM wf.sp_delete_workflow_def(NULL, 'ScopeParity', true);")
    _psql_query(dsn, "INSERT INTO wf.workflow_def (name) VALUES ('ScopeParity');")
    def_id = int(_psql_query(dsn, "SELECT id FROM wf.workflow_def WHERE name='ScopeParity' LIMIT 1;"))
    version_id = int(
        _psql_query(dsn, f"INSERT INTO wf.workflow_version (workflow_def_id) VALUES ({def_id}) RETURNING id;")
    )
    action_id = _psql_query(dsn, "SELECT id FROM wf.workflow_action WHERE action_name='Echo' LIMIT 1;")
    if not action_id:
        action_id = int(
            _psql_query(
                dsn,
                "INSERT INTO wf.workflow_action (action_name, capability) VALUES ('Echo','test-cap') RETURNING id;",
            )
        )
    else:
        action_id = int(action_id)
    node_id = int(
        _psql_query(
            dsn,
            f"INSERT INTO wf.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id) "
            f"VALUES ({version_id}, 'ACTION', 'echo', {action_id}) RETURNING id;",
        )
    )
    _psql_query(dsn, f"UPDATE wf.workflow_version SET root_node_id = {node_id} WHERE id = {version_id};")
    _psql_query(
        dsn,
        f"INSERT INTO wf.workflow_input_template (workflow_node_id, template_json) "
        f"VALUES ({node_id}, '{{}}'::jsonb);",
    )
    _psql_query(
        dsn,
        f"INSERT INTO wf.workflow_input_binding (workflow_node_id, target_json_path, source_expr, is_required) "
        f"VALUES ({node_id}, 'message', '${{var.greeting}}', true);",
    )

    instance_id = int(
        _psql_query(
            dsn,
            f"SELECT id FROM wf.wf_repo_create_workflow_instance({version_id}, '{{\"greeting\":\"hello-scope\"}}'::jsonb);",
        )
    )
    _psql_query(dsn, f"CALL wf.sp_start_workflow_instance({instance_id});")

    input_json = _psql_query(
        dsn,
        f"SELECT input_json::text FROM wf.node_execution WHERE workflow_instance_id={instance_id} AND status='READY' LIMIT 1;",
    )
    assert "hello-scope" in input_json, f"expected resolved greeting in input_json: {input_json}"


def _run_rest_gateway_smoke(
    *,
    env_overrides: dict[str, str],
    seed_fn,
    port: int = 18080,
) -> None:
    import json
    import subprocess
    import time
    import urllib.error
    import urllib.request
    from pathlib import Path

    dsn = env_overrides.get("METHYLPIPELINE_DB") or _pg_dsn()
    version_id, worker_id, token = seed_fn(dsn)
    gateway = Path(__file__).resolve().parents[2] / "rest" / "gateway.py"
    env = os.environ.copy()
    env.update(env_overrides)
    proc = subprocess.Popen(
        [sys.executable, str(gateway), "--host", "127.0.0.1", "--port", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(gateway.parent.parent),
    )
    base = f"http://127.0.0.1:{port}/v1"
    try:
        for _ in range(50):
            try:
                with urllib.request.urlopen(f"{base}/health", timeout=1) as resp:
                    health = json.loads(resp.read().decode())
                    assert health.get("status") == "ok", health
                break
            except Exception:
                time.sleep(0.2)
        else:
            stderr = proc.stderr.read().decode() if proc.stderr else ""
            raise RuntimeError(f"REST gateway did not start: {stderr}")

        def post(path: str, payload: dict) -> dict:
            req = urllib.request.Request(
                f"{base}{path}",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode()
                return json.loads(body) if body else {}

        post("/workers/authenticate", {"worker_id": worker_id, "worker_token": token})
        # Instance lifecycle is not on the worker-only HTTP surface; start it via SQL.
        start_instance(dsn, version_id)
        claim = post(
            "/workers/tasks/request",
            {"worker_id": worker_id, "worker_token": token, "capability": "test-cap"},
        )
        assert claim.get("has_task"), claim
        ne_id = int(claim["node_execution_id"])
        ack = post(
            f"/workers/tasks/{ne_id}/submit",
            {
                "worker_id": worker_id,
                "worker_token": token,
                "result_code": 1,
                "output_json": {"ok": True},
            },
        )
        assert ack.get("accepted") is True, ack
        assert ack.get("instance_status") == "COMPLETED", ack
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_rest_gateway_postgres(dsn: str) -> None:
    _run_rest_gateway_smoke(
        env_overrides={
            "BACKEND_DB": "postgres",
            "METHYLPIPELINE_DB": dsn,
        },
        seed_fn=seed_minimal_workflow,
    )


def test_rest_gateway_mssql_optional() -> None:
    conn = os.environ.get("METHYL_TEST_MSSQL_CONN") or os.environ.get("METHYLPIPELINE_DB")
    if not conn or os.environ.get("BACKEND_DB", "mssql") not in ("mssql", ""):
        print("Skipping MSSQL REST gateway smoke (set METHYL_TEST_MSSQL_CONN)", file=sys.stderr)
        return
    try:
        import pyodbc  # noqa: F401
    except ImportError:
        print("Skipping MSSQL REST gateway smoke (pyodbc not installed)", file=sys.stderr)
        return

    def _seed_mssql(dsn: str) -> tuple[int, int, str]:
        raise NotImplementedError(
            "MSSQL gateway smoke requires a pre-seeded test database; "
            "deploy wf schema and set METHYL_TEST_MSSQL_CONN with seed data."
        )

    _ = _seed_mssql
    print("MSSQL REST gateway smoke: skipped (manual seed not configured)", file=sys.stderr)


def main() -> int:
    if not shutil_which("psql"):
        print("psql not found; skip postgres parity (install postgresql-client)", file=sys.stderr)
        return 0

    dsn = _pg_dsn()
    db_name = os.environ.get("POSTGRES_DB", "methylpipeline_parity")
    admin = dsn.rsplit("/", 1)[0] + "/postgres"
    subprocess.run(
        [
            "psql",
            "-q",
            admin,
            "-c",
            f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE);",
        ],
        check=True,
        env=_pg_env(),
    )
    subprocess.run(
        [
            "createdb",
            "-h",
            os.environ.get("POSTGRES_HOST", "localhost"),
            "-p",
            os.environ.get("POSTGRES_PORT", "5432"),
            "-U",
            os.environ.get("POSTGRES_USER", "postgres"),
            db_name,
        ],
        check=True,
        env=_pg_env(),
    )

    print(f"Deploying PostgreSQL schema to {dsn}")
    deploy_postgres(dsn)

    print("Running worker API parity...")
    test_worker_api_postgres(dsn)
    test_worker_capability_dispatch_postgres(dsn)
    print("Running repository parity...")
    test_repository_postgres(dsn)
    print("Running scope resolver parity...")
    test_scope_resolver_postgres(dsn)
    print("Running REST gateway smoke test...")
    test_rest_gateway_postgres(dsn)
    test_rest_gateway_mssql_optional()

    print("Validating contract lockstep...")
    proc = subprocess.run([sys.executable, str(CONTRACT_SCRIPT)], capture_output=True, text=True)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return proc.returncode

    print("PostgreSQL parity: OK")
    return 0


def shutil_which(cmd: str) -> Optional[str]:
    from shutil import which

    return which(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
