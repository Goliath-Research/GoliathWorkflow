# Live schema inventory (Azure SQL vs PostgreSQL)

Captured: `2026-08-16T18:44:10.730125+00:00`

Controlled schemas: `wf`, `cfg`, `portal`, `RBAC`, `Meta`, `Contract`, `Onboarding`.
The `e_portal` schema was dropped (Azure SQL already gone; PostgreSQL `epimethyl` dropped 2026-08-22).

## Azure SQL (`MethylPipeline`)

- `wf`: 28 tables, 80 routines
- `cfg`: 19 tables, 14 routines
- `portal`: 25 tables, 118 routines
- `RBAC`: 15 tables, 9 routines
- `Meta`: 9 tables, 17 routines
- `Contract`: 6 tables, 4 routines
- `Onboarding`: 4 tables, 1 routines

## PostgreSQL (`epimethyl`)

- `wf`: 30 tables, 82 routines
- `cfg`: 20 tables, 18 routines
- `portal`: 25 tables, 101 routines
- `RBAC`: 15 tables, 9 routines
- `Meta`: 9 tables, 17 routines
- `Contract`: 6 tables, 4 routines
- `Onboarding`: 4 tables, 1 routines

> Note: the Azure PG database named `postgres` is a stale older wf-only deploy. Canonical parity target is **`epimethyl`**.

## Gaps (MSSQL − PostgreSQL)

### `tables_mssql_only` (0)

_none_

### `tables_postgres_only` (1)

- `cfg.node_config`

### `routines_mssql_only` (32)

- `portal.fngetdiseasejsonschema`
- `portal.sp_set_worker_desired_state`
- `portal.spcollectiondelete`
- `portal.spcollectionitemdelete`
- `portal.spcollectionitemlist`
- `portal.spcollectionitemsave`
- `portal.spcollectionlist`
- `portal.spcollectionsave`
- `portal.spdiseasefieldcontractdelete`
- `portal.spdiseasefieldcontractgettargetcolumns`
- `portal.spdiseasefieldcontractimportfromtarget`
- `portal.spdiseasefieldcontractlist`
- `portal.spdiseasefieldcontractsave`
- `portal.spgetcollectionitemsformapping`
- `portal.spgetimportfieldsfordisease`
- `portal.spsampleimportcommit`
- `portal.spsampleimportcreatebatch`
- `portal.spsampleimportstagerows`
- `portal.spsampleimportvalidate`
- `wf.sp_worker_submit_result_broken`
- `wf.sp_worker_submit_result_ntext`
- `wf.wf_apply_validation_plan`
- `wf.wf_fix_quoted_var_placeholders`
- `wf.wf_foreach_route_continue`
- `wf.wf_json_box`
- `wf.wf_json_encode_openjson`
- `wf.wf_json_unbox`
- `wf.wf_repo_add_workflow_version`
- `wf.wf_repo_merge_instance_context`
- `wf.wf_repo_project_data_type_schema_json`
- `wf.wf_repo_set_action_input_ready`

### `routines_postgres_only` (5)

- `portal._drop_if_proc`
- `portal.sp_list_data_type_fields`
- `wf.wf_repo_list_data_type_fields`
- `wf.wf_sha256_text`
- `wf.wf_stamp_affinity_key`

Cross-schema FKs: MSSQL=33, PostgreSQL=34

