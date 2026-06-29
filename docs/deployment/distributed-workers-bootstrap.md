# Distributed workers bootstrap

Operator guide for seeding **PostgreSQL** or **Azure SQL** with the current action catalog (33 actions, post–streamline-action-parameters) and deploying DomainProgram workflows for remote GPU worker testing.

## Quick start

```bash
cd /path/to/MethylPipeline
source .venv/bin/activate

# PostgreSQL (Azure Database for PostgreSQL or local)
export BACKEND_DB=postgres
export PGHOST=epimethyl.postgres.database.azure.com
export PGDATABASE=postgres
export PGUSER=dba
export PGPASSWORD='...'
export PGSSLMODE=require

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

The bootstrap script:

1. Deploys wf schema parity DDL (`workflow_engine/sql_pg/deploy_azure.sh` or `workflow_engine/sql/deploy_azure.sh`)
2. Runs `methyl-export-task-schemas` + `methyl-export-action-catalog`
3. Runs `scripts/check_task_input_config_boundary.py`
4. Seeds `wf.workflow_action` + task JSON schemas via `workflow_engine/sql/seed_action_catalog.py`
5. POSTs compiled SamplePrep + StudyValidation workflows via `scripts/deploy_workflow_definitions.sh`

## Gateway-only (no DB creds on laptop)

When the gateway VM has DB access and you hold an admin bearer token:

```bash
export WORKER_API_BASE=https://gateway.example.com/v1
export GATEWAY_ADMIN_BEARER_TOKEN='...'

bash scripts/bootstrap_distributed_workers.sh \
  --skip-schema \
  --use-gateway-only \
  --api-base "$WORKER_API_BASE"
```

## Register remote workers

After bootstrap, on each GPU worker node:

```bash
export BACKEND_DB=postgres   # or mssql — same as gateway
# ... same DB connection env as gateway ...

bash scripts/register_worker.sh \
  --cluster epimethyl \
  --key "$(hostname -s)" \
  --env-file /work/epimethyl/env/worker.env

bash scripts/install_worker_systemd.sh
```

Or register from the operator host during bootstrap:

```bash
bash scripts/bootstrap_distributed_workers.sh --register-worker --skip-schema
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
| Schema deploy | [`workflow_engine/sql_pg/deploy_azure.sh`](../../workflow_engine/sql_pg/deploy_azure.sh) | Base: `MethylPipeline.sql` then [`workflow_engine/sql/deploy_azure.sh`](../../workflow_engine/sql/deploy_azure.sh) |
| Action catalog seed | `python workflow_engine/sql/seed_action_catalog.py` | Same (uses `BACKEND_DB=mssql`) |
| Workflow deploy | `bash scripts/deploy_workflow_definitions.sh` | Same |
| Test bed (PG only) | `workflow_engine/sql_pg/deploy_test_bed.sh` | Use gateway + `smoke_*.sh` |
| Worker API | `wf.sp_worker_request_task` | Same contract |

## Catalog contents (current)

- **33** workflow actions (`sample.upload_h5` removed; use `sample.archive_sample`)
- Typed task I/O under `schemas/tasks/*.schema.json`
- Exported catalog: `schemas/actions/catalog.json`

Refresh after worker package upgrades:

```bash
bash scripts/refresh_sample_prep_test_bed.sh
# or full bootstrap with --skip-schema
```

## Related

- [Production runbook](production_runbook.md)
- [Worker node setup](worker_node.md)
- [SamplePrep test bed](../../workflow_engine/docs/sample_prep_test_bed.md)
- [Action parameter contract](../reference/action-parameter-contract.md)
