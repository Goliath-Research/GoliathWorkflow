/*
  MethylPipeline wf schema - align JSON payload columns to native json (Azure SQL).

  Migrates legacy NVARCHAR(MAX)/text-style JSON storage on scope and execution context.
  Safe to re-run: skips when column types are already json.

  Prerequisites:
  - wf_scope_variables.sql
  - Base wf schema (execution_context)
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'wf.scope_variable', N'U') IS NOT NULL
   AND EXISTS (
       SELECT 1
       FROM sys.columns AS c
       INNER JOIN sys.types AS t ON t.user_type_id = c.user_type_id
       WHERE c.object_id = OBJECT_ID(N'wf.scope_variable')
         AND c.name = N'value_json'
         AND t.name <> N'json'
   )
BEGIN
    ALTER TABLE wf.scope_variable
        ALTER COLUMN value_json json NOT NULL;
    PRINT N'Aligned wf.scope_variable.value_json to json.';
END
GO

IF OBJECT_ID(N'wf.execution_context', N'U') IS NOT NULL
   AND EXISTS (
       SELECT 1
       FROM sys.columns AS c
       INNER JOIN sys.types AS t ON t.user_type_id = c.user_type_id
       WHERE c.object_id = OBJECT_ID(N'wf.execution_context')
         AND c.name = N'context_value_json'
         AND t.name <> N'json'
   )
BEGIN
    ALTER TABLE wf.execution_context
        ALTER COLUMN context_value_json json NULL;
    PRINT N'Aligned wf.execution_context.context_value_json to json.';
END
GO

/*
  After this script, wf.scope_variable.value_json is native json.
  wf.wf_repo_set_scope_variable and wf.wf_set_scope_variable detect the column
  type at runtime (CONVERT json → nvarchar, then CAST back when the column is json).
*/

/*
  After this script, wf.scope_variable.value_json is native json.
  wf.wf_repo_set_scope_variable and wf.wf_set_scope_variable detect the column
  type at runtime (CONVERT json → nvarchar, then CAST back when the column is json).
  Re-deploy those procs from wf_repository_api.sql / wf_sql_scope_writepath_parity.sql
  if they still assign @value_json directly to the column.
*/
