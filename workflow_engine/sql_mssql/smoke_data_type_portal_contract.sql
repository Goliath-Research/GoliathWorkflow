/*
  Smoke: Portal contract after wf.data_type cutover (Azure SQL).

  Run after deploy_azure.sh (+ seed_action_catalog / methyl-cfg sync-actions):

    sqlcmd ... -i workflow_engine/sql_mssql/smoke_data_type_portal_contract.sql

  Expected:
    - sp_list_workflow_actions exposes input_type_id / input_type_name /
      has_input_schema / input_schema_json
    - sp_list_data_types / sp_get_data_type exist
    - workflow_action rows have type FKs after seed
    - workflow_action_schema may be empty (legacy; seeding retired)
*/
SET NOCOUNT ON;

PRINT N'=== portal.sp_list_workflow_actions result columns ===';
SELECT c.name AS column_name, c.system_type_name, c.column_ordinal
FROM sys.dm_exec_describe_first_result_set(
    N'EXEC portal.sp_list_workflow_actions', NULL, 0) AS c
ORDER BY c.column_ordinal;

PRINT N'=== portal.sp_get_workflow_action columns ===';
SELECT c.name AS column_name, c.column_ordinal
FROM sys.dm_exec_describe_first_result_set(
    N'EXEC portal.sp_get_workflow_action @action_name = N''sample.methyl_qc''', NULL, 0) AS c
ORDER BY c.column_ordinal;

PRINT N'=== portal data_type procs ===';
SELECT OBJECT_ID(N'portal.sp_list_data_types', N'P') AS sp_list_data_types_id,
       OBJECT_ID(N'portal.sp_get_data_type', N'P') AS sp_get_data_type_id,
       OBJECT_ID(N'wf.wf_repo_project_data_type_schema_json', N'FN') AS project_fn_id;

PRINT N'=== wf.workflow_action type FK coverage ===';
SELECT
    COUNT(*) AS actions,
    SUM(CASE WHEN input_type_id IS NOT NULL THEN 1 ELSE 0 END) AS with_input_type,
    SUM(CASE WHEN output_type_id IS NOT NULL THEN 1 ELSE 0 END) AS with_output_type
FROM wf.workflow_action;

PRINT N'=== legacy workflow_action_schema row count ===';
SELECT COUNT(*) AS schema_blob_rows FROM wf.workflow_action_schema;

PRINT N'=== sample actions (via proc) ===';
EXEC portal.sp_list_workflow_actions @implemented_only = 1;
GO
