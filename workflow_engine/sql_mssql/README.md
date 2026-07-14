# Azure SQL deploy scripts (`sql_mssql/`)

Incremental **wf** schema parity scripts for Azure SQL. Use after the bundled base schema (`MethylPipeline.sql` or `MethylPipelineDB_Script.sql`).

## Automated deploy

```bash
export AZURE_SQL_SERVER=your-server.database.windows.net
export AZURE_SQL_DB=MethylPipeline
export AZURE_SQL_USER=sql-admin
export AZURE_SQL_PASSWORD='...'
export SQLCMD_TRUST_SERVER_CERTIFICATE=1   # optional

chmod +x workflow_engine/sql_mssql/deploy_azure.sh
./workflow_engine/sql_mssql/deploy_azure.sh
```

Optional cluster IP binding:

```bash
./workflow_engine/sql_mssql/deploy_azure.sh --with-cluster-security
```

## Seed action catalog + workflows

Prefer the unified bootstrap (both backends):

```bash
source .venv/bin/activate
bash scripts/bootstrap_distributed_workers.sh --skip-schema   # after deploy_azure.sh
```

Manual seed:

```bash
methyl-export-task-schemas
methyl-export-action-catalog
export BACKEND_DB=mssql
export AZURE_SQL_SERVER=... AZURE_SQL_DB=... AZURE_SQL_USER=... AZURE_SQL_PASSWORD=...
python workflow_engine/sql_mssql/seed_action_catalog.py
bash scripts/deploy_workflow_definitions.sh --api-base http://localhost:8080/v1
```

## Script order (`deploy_azure.sh`)

Applies parity scripts in dependency order, including:

- Runtime / scope / FOREACH parity (`wf_sql_runtime_parity.sql`, `wf_sql_foreach_support.sql`, …)
- Repository API + action schema (`wf_action_schema.sql`, `wf_repo_upsert_workflow_action.sql`, `wf_action_dispatch_metadata.sql`, `wf_repo_create_workflow_graph.sql`)
- Collection bindings (`wf_sql_collection_bindings.sql`) — jsonPath; jsonFile requires gateway-enriched `context_json`
- Portal DDL (`portal_workflow_api.sql`, `portal_resource_profile.sql` after `cfg` tables — seeds archive endpoint refs)
- Config registry (`cfg_*`, including `cfg_portal_api.sql` storage/credential procs)

`wf_repo_upsert_workflow_action.sql` is a 3-arg bootstrap; `wf_action_dispatch_metadata.sql` (applied next) replaces it with the 7-arg upsert that stores `execution_mode` / `cli_tool` / `in_process_handler` / `argv_map`.

## Lightweight action seed (legacy)

[`wf_split_detector_actions_seed.sql`](wf_split_detector_actions_seed.sql) upserts four pipeline actions only (with dispatch metadata). **Do not use for distributed worker testing** — run full `seed_action_catalog.py` instead (37 actions + JSON schemas from `schemas/actions/catalog.json`).

PostgreSQL equivalent: [`../sql_pg/wf_split_detector_actions_seed.sql`](../sql_pg/wf_split_detector_actions_seed.sql).

## Related

- PostgreSQL scripts: [`../sql_pg/README.md`](../sql_pg/README.md)
- Distributed workers bootstrap: [`../../docs/deployment/distributed-workers-bootstrap.md`](../../docs/deployment/distributed-workers-bootstrap.md)
- Engine README: [`../README.md`](../README.md)
