# Environment templates (`deploy/env/`)

Committed examples for production `/work/epimethyl/env/`. Copy and edit on the cluster; **do not commit secrets**.

| Template | Target on cluster | Consumers |
|----------|-------------------|-----------|
| `gateway.mssql.env.example` | `/work/epimethyl/env/gateway.env` | `methyl-gateway`, `methyl-study-start`, `deploy_workflow_definitions.sh`, `bootstrap_distributed_workers.sh` |
| `gateway.postgres.env.example` | same | same |
| `worker.env.example` | `/work/epimethyl/env/worker.env` | `methyl-worker` systemd units |

## Database variables

| Backend | Required env |
|---------|----------------|
| **PostgreSQL** | `BACKEND_DB=postgres`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` (or `METHYLPIPELINE_DB`) |
| **Azure SQL** | `BACKEND_DB=mssql`, `AZURE_SQL_SERVER`, `AZURE_SQL_DB`, `AZURE_SQL_USER`, `AZURE_SQL_PASSWORD` (or `METHYLPIPELINE_DB`) |

Do **not** use `PGHOST` / `PGDATABASE` — the Python gateway and Admin CLI read `POSTGRES_*` via [`workflow_engine/rest/connection.py`](../../workflow_engine/rest/connection.py).

## MSSQL base schema

Before incremental deploy scripts, apply the base schema once:

```bash
# Azure SQL — base DDL then incremental
sqlcmd -S "$AZURE_SQL_SERVER" -d "$AZURE_SQL_DB" -U "$AZURE_SQL_USER" -P "$AZURE_SQL_PASSWORD" \
  -i workflow_engine/sql_mssql/MethylPipeline.sql
bash workflow_engine/sql_mssql/deploy_azure.sh
```

PostgreSQL greenfield: `bash workflow_engine/sql_pg/deploy_azure.sh` (includes base objects).

## Related

- [Usage ch.14](../../docs/usage/14-deployment-and-distributed-workflow.qmd)
- [Production runbook](../../docs/deployment/production_runbook.md)
- [Operator journey](../../docs/deployment/operator-journey.md)
