# PostgreSQL deploy scripts (`sql_pg/`)

Parallel implementation of the MethylPipeline **wf** schema contract for PostgreSQL 15+ (17+ recommended for SQL/JSON).

Deploy **in order**:

| # | Script | Purpose |
|---|--------|---------|
| 1 | [`00_schema.sql`](00_schema.sql) | Tables, indexes, worker registry |
| 2 | [`03_engine_core.sql`](03_engine_core.sql) | Engine runtime (activate, continue, scope stubs) |
| 3 | [`05_runtime_parity.sql`](05_runtime_parity.sql) | `${var.*}` / `${ctx.*}` resolver, input builder |
| 4 | [`06_scope_writepath_parity.sql`](06_scope_writepath_parity.sql) | Scope open/copy, output bindings, branch vars |
| 5 | [`07_scope_encoding_parity.sql`](07_scope_encoding_parity.sql) | Canonical JSON scalar encoding |
| 6 | [`01_worker_api.sql`](01_worker_api.sql) | Worker claim/submit/heartbeat |
| 7 | [`02_repository_api.sql`](02_repository_api.sql) | Middle-tier repository wrappers |
| 8 | [`04_admin.sql`](04_admin.sql) | Admin (`sp_delete_workflow_def`) |
| 9 | [`wf_action_schema.sql`](wf_action_schema.sql) | Action I/O JSON Schema storage + repo procs |

After SQL deploy, seed action schemas:

```bash
source .venv/bin/activate
methyl-export-task-schemas
python workflow_engine/sql/seed_action_schemas.py
```

## Azure Database for PostgreSQL

Use [`deploy_azure.sh`](deploy_azure.sh) from a machine whose IP is allowed in the server firewall (Azure Portal → Networking, or run from Azure Cloud Shell / a VM in the same VNet).

**Native auth (`dba`):**

```bash
export PGHOST=epimethyl.postgres.database.azure.com
export PGPORT=5432
export PGDATABASE=epimethyl
export PGUSER=dba
export PGPASSWORD='...'          # store in Key Vault / env, not in git
export PGSSLMODE=require

./workflow_engine/sql_pg/deploy_azure.sh
```

**Microsoft Entra ID:**

```bash
export PGHOST=epimethyl.postgres.database.azure.com
export PGPORT=5432
export PGDATABASE=epimethyl
export PGUSER='you@epimethyl.com'
export PGPASSWORD="$(az account get-access-token --resource https://ossrdbms-aad.database.windows.net --query accessToken --output tsv)"
export PGSSLMODE=require

./workflow_engine/sql_pg/deploy_azure.sh
```

Connect to database **`epimethyl`** (not `postgres`) for the wf schema. If the database does not exist yet, create it as an admin on the `postgres` database first:

```sql
CREATE DATABASE epimethyl OWNER dba;
```

**Middle-tier env (Delphi / REST gateway):**

```bash
export BACKEND_DB=postgres
export POSTGRES_HOST=epimethyl.postgres.database.azure.com
export POSTGRES_PORT=5432
export POSTGRES_DB=epimethyl
export POSTGRES_USER=dba
export POSTGRES_PASSWORD='...'
```

After schema deploy, migrate **data** separately (pg_dump/pg_restore or ETL). The scripts above create objects only — no seed workflows or domain tables beyond `wf`.

## Local container

```bash
docker run -d --name methyl-pg -e POSTGRES_PASSWORD=methyl -e POSTGRES_DB=methylpipeline -p 5432:5432 postgres:17
for f in 00_schema.sql 03_engine_core.sql 05_runtime_parity.sql 06_scope_writepath_parity.sql 07_scope_encoding_parity.sql 01_worker_api.sql 02_repository_api.sql 04_admin.sql wf_action_schema.sql; do
  psql "postgresql://postgres:methyl@localhost:5432/methylpipeline" -f "workflow_engine/sql_pg/$f"
done
```

## REST gateway (Linux / CI)

```bash
export POSTGRES_PASSWORD=methyl POSTGRES_DB=methylpipeline_parity
python workflow_engine/rest/gateway.py --port 8080
```

Maps [`contracts/openapi.yaml`](../contracts/openapi.yaml) to PostgreSQL wf objects. The Delphi `MethylWfGateway` Windows service (`WfEngineSrv`, DMVC-based; `/console` for development) exposes the same routes via UniDAC.

## Connection string (middle-tier)

```
Provider Name=PostgreSQL;Data Source=localhost;Port=5432;Database=methylpipeline;User ID=postgres;Password=methyl;
```

Set `BACKEND_DB=postgres` and `METHYLPIPELINE_DB` (or `POSTGRES_*` env vars — see `WfEngine.Dialect.pas`).

## Contract validation

```bash
python workflow_engine/contract/validate_contract.py
```

## Notes

- Result-returning worker APIs are implemented as **functions** returning `TABLE` (PostgreSQL procedures cannot `RETURN QUERY`).
- Object names match the Azure SQL contract in [`../contract/db_objects.yaml`](../contract/db_objects.yaml).
- FOREACH control flow requires SQL runtime parity (`wf_sql_runtime_parity.sql` / `sql_pg` equivalents); the Delphi middle-tier is gateway-only.
