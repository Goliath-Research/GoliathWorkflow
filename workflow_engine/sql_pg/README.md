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

## Local container

```bash
docker run -d --name methyl-pg -e POSTGRES_PASSWORD=methyl -e POSTGRES_DB=methylpipeline -p 5432:5432 postgres:17
for f in 00_schema.sql 03_engine_core.sql 05_runtime_parity.sql 06_scope_writepath_parity.sql 07_scope_encoding_parity.sql 01_worker_api.sql 02_repository_api.sql 04_admin.sql; do
  psql "postgresql://postgres:methyl@localhost:5432/methylpipeline" -f "workflow_engine/sql_pg/$f"
done
```

## REST gateway (Linux / CI)

```bash
export POSTGRES_PASSWORD=methyl POSTGRES_DB=methylpipeline_parity
python workflow_engine/rest/gateway.py --port 8080
```

Maps [`contracts/openapi.yaml`](../contracts/openapi.yaml) to PostgreSQL wf objects. Delphi `WfEngineSrv /rest port=8080` exposes the same routes via UniDAC.

## Connection string (middle-tier)

```
Provider Name=PostgreSQL;Data Source=localhost;Port=5432;Database=methylpipeline;User ID=postgres;Password=methyl;
```

Set `BACKEND_DB=postgres` and `METHYLPIPELINE_DB` (or `POSTGRES_*` env vars — see `WfEngine.DbAuth.pas`).

## Contract validation

```bash
python workflow_engine/contract/validate_contract.py
```

## Notes

- Result-returning worker APIs are implemented as **functions** returning `TABLE` (PostgreSQL procedures cannot `RETURN QUERY`).
- Object names match the Azure SQL contract in [`../contract/db_objects.yaml`](../contract/db_objects.yaml).
- `wf_sql_foreach_support.sql` is not yet ported; FOREACH control flow remains Delphi-first.
