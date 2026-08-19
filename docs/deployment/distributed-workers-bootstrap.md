# Distributed workers bootstrap

Operator guide for seeding **PostgreSQL** or **Azure SQL** with the current action catalog (from `schemas/actions/catalog.json`) and deploying DomainProgram workflows for remote GPU worker testing.

For the full production platform (gateway + Arc enroll), see [production-platform.md](production-platform.md).

## Two-database layout (typical)

| Backend | Role | Data state |
|---------|------|------------|
| **Azure SQL** | Production / portal (until cutover) | Populated — actions, workflow defs, instances, workers, clinical portal |
| **PostgreSQL (`epimethyl`)** | Schema twin / gateway dev / CI | Full `wf` + `cfg` + clinical `portal` / `RBAC` / `Meta` / `Contract` / `Onboarding` / `e_portal` DDL + procs; **reference/runtime data often empty** |

Canonical PostgreSQL database is **`epimethyl`**. The leftover Azure PG database named **`postgres`** is a stale older wf-only deploy — do not treat it as the twin.

PostgreSQL is a **schema/procedure twin**, not a full data clone. For worker testing seed **reference metadata** only:

- `wf.workflow_action` + `wf.data_type` (catalog)
- `wf.workflow_def` … `workflow_edge` … (compiled DomainPrograms), *or* deploy via gateway
- `portal.resource_profile` (optional, for archive/H5 defaults)

Do **not** copy `workflow_instance`, `node_execution`, `wf.worker`, or production leases into PostgreSQL unless you intend a dedicated test / cutover environment.

Live gap report (tables, routines, cross-schema FKs):

```bash
python scripts/db_schema_inventory.py
# optional gate: python scripts/db_schema_inventory.py --fail-on-gap
```

### Populate empty PostgreSQL

```bash
source .venv/bin/activate

export POSTGRES_HOST=epimethyl.postgres.database.azure.com
export POSTGRES_DB=epimethyl
export POSTGRES_USER=dba
export POSTGRES_PASSWORD='...'
export PGSSLMODE=require

# 1) Catalog from git (preferred over stale MSSQL rows)
python scripts/populate_postgres_reference_data.py

# 2) Optionally clone workflow definitions from production Azure SQL
export AZURE_SQL_SERVER=....database.windows.net
export AZURE_SQL_DB=MethylPipeline
export AZURE_SQL_USER=...
export AZURE_SQL_PASSWORD='...'
python scripts/populate_postgres_reference_data.py --workflows-from-mssql --portal-profiles-from-mssql
```

**Cursor MCP:** inspect Azure SQL with the `user-azure-sql-dev` server (`mcp_SQL_execute_query`). PostgreSQL MCP requires a saved connection profile in the Cursor PostgreSQL extension (`pgsql_list_connection_profiles` must be non-empty).

## Quick start

```bash
cd /path/to/MethylPipeline
source .venv/bin/activate

# PostgreSQL (Azure Database for PostgreSQL or local)
export BACKEND_DB=postgres
export POSTGRES_HOST=epimethyl.postgres.database.azure.com
export POSTGRES_PORT=5432
export POSTGRES_DB=epimethyl
export POSTGRES_USER=dba
export POSTGRES_PASSWORD='...'
# Or: export METHYLPIPELINE_DB='postgresql://...'

bash scripts/bootstrap_distributed_workers.sh
```

```bash
# Azure SQL
export BACKEND_DB=mssql
export AZURE_SQL_SERVER=your-server.database.windows.net
export AZURE_SQL_DB=MethylPipeline
export AZURE_SQL_USER=sql-admin
export AZURE_SQL_PASSWORD='...'
export SQLCMD_TRUST_SERVER_CERTIFICATE=1   # when needed

bash scripts/bootstrap_distributed_workers.sh
```

The bootstrap script (privileged host only — GPU workers must not run it):

1. Deploys schema DDL (`workflow_engine/sql_pg/deploy_azure.sh` or `workflow_engine/sql_mssql/deploy_azure.sh`) — twins, see `scripts/check_sql_deploy_twins.py`
2. Exports task schemas + action catalog
3. Seeds `wf.workflow_action` / `wf.data_type`
4. Syncs process packs, analytes, pipeline profiles (`sync_cfg_profiles_and_action_catalog.py`, `deploy_process_pack_catalog.sh --sync`)
5. `methyl-cfg sync-library-presets`
6. Deploys DomainProgram graphs (`deploy_workflow_definitions.sh`)

## Enroll remote workers

**Production:** do **not** put DB credentials on GPU workers. After database bootstrap and gateway TLS are up:

1. Portal-preregister each VM public IP (`portal.sp_upsert_worker_enrollment`).
2. Arc-connect the VM ([arc_worker_runbook.md](arc_worker_runbook.md)).
3. Enroll through the gateway (`provision_worker_node.sh` or):

```bash
export WORKER_API_BASE=https://<gateway-fqdn>/v1
methyl-worker enroll \
  --api-base "$WORKER_API_BASE" \
  --cluster epimethyl \
  --key "$(hostname -s)"
bash scripts/install_worker_systemd.sh
```

Full story: [production-platform.md](production-platform.md) Phase 4.

Read-only health check (catalog + SQL twin scripts, no DDL/seed):

```bash
bash scripts/bootstrap_distributed_workers.sh --verify
```

## Smoke tests

```bash
export WORKER_API_BASE=http://gateway-host:8080/v1
export WORKER_STUB_EXTERNAL=1   # stub Parabricks/extract; real QC paths optional

bash scripts/smoke_sample_prep.sh --api-base "$WORKER_API_BASE"
bash scripts/smoke_study_lifecycle.sh --api-base "$WORKER_API_BASE"
```

## Per-backend reference

| Step | PostgreSQL | Azure SQL |
|------|------------|-----------|
| Schema deploy | [`workflow_engine/sql_pg/deploy_azure.sh`](../../workflow_engine/sql_pg/deploy_azure.sh) | Base: `MethylPipeline.sql` then [`workflow_engine/sql_mssql/deploy_azure.sh`](../../workflow_engine/sql_mssql/deploy_azure.sh) |
| Action catalog seed | `python workflow_engine/sql_mssql/seed_action_catalog.py` | Same (uses `BACKEND_DB=mssql`) |
| Workflow deploy | `bash scripts/deploy_workflow_definitions.sh` | Same |
| Test bed (PG only) | `workflow_engine/sql_pg/deploy_test_bed.sh` | Use gateway + `smoke_*.sh` |
| Worker API | `wf.sp_worker_request_task` | Same contract |

## Catalog contents (current)

- Action count follows `schemas/actions/catalog.json` (seed with `seed_action_catalog.py`; use `sample.archive_sample` for HDF5 archive)
- Typed task I/O under `schemas/tasks/*.schema.json`
- Exported catalog: `schemas/actions/catalog.json`

Refresh after worker package upgrades:

```bash
bash scripts/refresh_sample_prep_test_bed.sh
# or full bootstrap with --skip-schema
```

## Related

- [Production platform](production-platform.md)
- [Production runbook](production_runbook.md)
- [Worker node setup](worker_node.md)
- [SamplePrep test bed](../../workflow_engine/docs/sample_prep_test_bed.md)
- [Action parameter contract](../reference/action-parameter-contract.md)
