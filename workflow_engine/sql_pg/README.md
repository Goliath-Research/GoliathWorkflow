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
| 6 | [`08_foreach_support.sql`](08_foreach_support.sql) | FOREACH control-flow (DomainProgram workflows on PostgreSQL) |
| 7 | [`01_worker_api.sql`](01_worker_api.sql) | Worker claim/submit/heartbeat |
| 8 | [`02_repository_api.sql`](02_repository_api.sql) | Middle-tier repository wrappers |
| 9 | [`04_admin.sql`](04_admin.sql) | Admin (`sp_delete_workflow_def`) |
| 10 | [`wf_action_schema.sql`](wf_action_schema.sql) | Action I/O JSON Schema storage + repo procs |
| 11 | [`wf_repo_upsert_workflow_action.sql`](wf_repo_upsert_workflow_action.sql) | Upsert action catalog rows |
| 12 | [`wf_repo_create_workflow_graph.sql`](wf_repo_create_workflow_graph.sql) | Programmatic workflow definition builder |
| 13 | [`wf_sql_collection_bindings.sql`](wf_sql_collection_bindings.sql) | Collection binding resolution at instance start |
| 14 | [`portal_resource_profile.sql`](portal_resource_profile.sql) | Portal archive storage profiles (domain config) |
| 14a | [`portal_workflow_api.sql`](portal_workflow_api.sql) | Portal workflow builder + instance lifecycle (`portal.sp_*`) |
| 15 | [`wf_drop_platform_sample_storage.sql`](wf_drop_platform_sample_storage.sql) | Drop legacy wf.platform_sample_storage if present |

After SQL deploy, seed the action catalog and deploy workflows:

```bash
source .venv/bin/activate
bash scripts/bootstrap_distributed_workers.sh --skip-schema
```

Or manually:

```bash
methyl-export-task-schemas
methyl-export-action-catalog
python workflow_engine/sql/seed_action_catalog.py
bash scripts/deploy_workflow_definitions.sh
```

Split-detector actions only (lightweight; does not seed task I/O schemas):

```bash
psql "$DSN" -f workflow_engine/sql_pg/wf_split_detector_actions_seed.sql
```

Azure SQL equivalent: [`../sql/wf_split_detector_actions_seed.sql`](../sql/wf_split_detector_actions_seed.sql).

Legacy schema-only seed (requires actions already in DB):

```bash
python workflow_engine/sql/seed_action_schemas.py
```

## Azure Database for PostgreSQL

Use [`deploy_azure.sh`](deploy_azure.sh) from a machine whose IP is allowed in the server firewall. The script applies scripts 1–13 from the table above **plus** portal DDL (`portal_resource_profile.sql`, `portal_workflow_api.sql`, `wf_drop_platform_sample_storage.sql`). Run [`wf_cluster_security_columns.sql`](wf_cluster_security_columns.sql) separately when enabling cluster IP binding.

**Native auth (`dba`):**

```bash
export PGHOST=epimethyl.postgres.database.azure.com
export PGPORT=5432
export PGDATABASE=postgres
export PGUSER=dba
export PGPASSWORD='...'          # store in Key Vault / env, not in git
export PGSSLMODE=require

./workflow_engine/sql_pg/deploy_azure.sh
```

Server FQDN from Azure Portal is `<server-name>.postgres.database.azure.com` (here **`epimethyl.postgres.database.azure.com`**). Deploy into the default database **`postgres`**.

**Microsoft Entra ID:**

```bash
export PGHOST=epimethyl.postgres.database.azure.com
export PGPORT=5432
export PGDATABASE=postgres
export PGUSER='you@epimethyl.com'
export PGPASSWORD="$(az account get-access-token --resource https://ossrdbms-aad.database.windows.net --query accessToken --output tsv)"
export PGSSLMODE=require

./workflow_engine/sql_pg/deploy_azure.sh
```

**Middle-tier env (Delphi / REST gateway):**

```bash
export BACKEND_DB=postgres
export POSTGRES_HOST=epimethyl.postgres.database.azure.com
export POSTGRES_PORT=5432
export POSTGRES_DB=postgres
export POSTGRES_USER=dba
export POSTGRES_PASSWORD='...'
```

After schema deploy, migrate **data** separately (pg_dump/pg_restore or ETL). The scripts above create objects only — use the test bed below for sample workflows.

## Test bed (two-group + MC stability)

Optional PostgreSQL scripts to seed sample workflows and simulate worker execution with task logging (no real `methyl-*` processes).

| Script | Purpose |
|--------|---------|
| [`wf_test_bed_schema.sql`](wf_test_bed_schema.sql) | `test_bed_run`, `test_bed_task_log`, `v_test_bed_task_summary` |
| [`wf_test_bed_worker.sql`](wf_test_bed_worker.sql) | Test worker `simulator-1`, token `test-bed-token` |
| [`wf_two_group_test_seed.sql`](wf_two_group_test_seed.sql) | **TwoGroupTestFlow** — 2 chromosomes, 6 ACTION tasks |
| [`wf_mc_two_group_test_seed.sql`](wf_mc_two_group_test_seed.sql) | **McTwoGroupTestFlow** — 10 MC iterations × 6 + 3 post steps |
| [`wf_test_bed_run.sql`](wf_test_bed_run.sql) | `sp_test_bed_run_workflow`, `sp_test_bed_simulate` |

```bash
./workflow_engine/sql_pg/deploy_test_bed.sh
./workflow_engine/sql_pg/deploy_test_bed.sh --run TwoGroupTestFlow
./workflow_engine/sql_pg/deploy_test_bed.sh --run McTwoGroupTestFlow
```

Inspect results:

```sql
SELECT * FROM wf.v_test_bed_task_summary ORDER BY test_bed_run_id DESC;
SELECT node_key, capability, result_code, output_json
FROM wf.test_bed_task_log
WHERE test_bed_run_id = (SELECT max(id) FROM wf.test_bed_run)
ORDER BY id;
```

Example `context_json`: [`instance_context_examples/two_group_test.json`](instance_context_examples/two_group_test.json), [`mc_two_group_test.json`](instance_context_examples/mc_two_group_test.json).

Production OvR at scale uses **DataDrivenPipeline** / **ValidationPipeline** with FOREACH (deploy `08_foreach_support.sql`). Static test-bed workflows use REPEAT where noted.

## Local container

```bash
docker run -d --name methyl-pg -e POSTGRES_PASSWORD=methyl -e POSTGRES_DB=methylpipeline -p 5432:5432 postgres:17
for f in 00_schema.sql 03_engine_core.sql 05_runtime_parity.sql 06_scope_writepath_parity.sql 07_scope_encoding_parity.sql 01_worker_api.sql 02_repository_api.sql 04_admin.sql wf_action_schema.sql; do
  psql "postgresql://postgres:methyl@localhost:5432/methylpipeline" -f "workflow_engine/sql_pg/$f"
done
```

## REST gateway (Linux production)

Install from repo root:

```bash
source .venv/bin/activate
pip install -e workflow_engine/
```

**Azure SQL (phase 1):**

```bash
export BACKEND_DB=mssql
export AZURE_SQL_SERVER=your-server.database.windows.net
export AZURE_SQL_DB=MethylPipeline
export AZURE_SQL_USER=...
export AZURE_SQL_PASSWORD=...
methyl-gateway --host 0.0.0.0 --port 8080
```

**PostgreSQL (phase 2 / CI):**

```bash
export BACKEND_DB=postgres
export POSTGRES_HOST=localhost POSTGRES_DB=methylpipeline_parity POSTGRES_PASSWORD=methyl
methyl-gateway --host 0.0.0.0 --port 8080
```

Maps [`contracts/openapi.yaml`](../contracts/openapi.yaml) to wf contract objects on either backend. The optional Delphi `MethylWfGateway` Windows service (`WfEngineSrv`) exposes a subset of the same worker/admin routes via UniDAC.

## Connection string (middle-tier)

```
Provider Name=PostgreSQL;Data Source=localhost;Port=5432;Database=methylpipeline;User ID=postgres;Password=methyl;
```

Set `BACKEND_DB=postgres` and `METHYLPIPELINE_DB` (or `POSTGRES_*` env vars — see `WfEngine.Connection.pas`).

## Contract validation

```bash
python workflow_engine/contract/validate_contract.py
```

## Notes

- Result-returning worker APIs are implemented as **functions** returning `TABLE` (PostgreSQL procedures cannot `RETURN QUERY`).
- Object names match the Azure SQL contract in [`../contract/db_objects.yaml`](../contract/db_objects.yaml).
- FOREACH control flow requires SQL runtime parity (`wf_sql_runtime_parity.sql` / `sql_pg` equivalents); the Delphi middle-tier is gateway-only.
