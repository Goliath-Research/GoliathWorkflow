/*
  Catalog-driven claim concurrency on wf.workflow_action.

  Columns (seeded from action catalog ``dispatch``):
    - max_per_worker   NULL = unlimited concurrent leases of this action on one worker
    - exclusive_worker 1 = while this action is leased, worker takes no other claim

  Engine stays process-agnostic: it only reads these columns. Deploy after
  wf_action_dispatch_metadata.sql (widens upsert from 7-arg to 9-arg).
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

-- Repeated from wf_action_dispatch_metadata.sql so this script also applies standalone
-- (the procedure and function below reference these columns at CREATE time).
IF COL_LENGTH('wf.workflow_action', 'execution_mode') IS NULL
    ALTER TABLE wf.workflow_action ADD execution_mode nvarchar(32) NULL;
GO
IF COL_LENGTH('wf.workflow_action', 'cli_tool') IS NULL
    ALTER TABLE wf.workflow_action ADD cli_tool nvarchar(256) NULL;
GO
IF COL_LENGTH('wf.workflow_action', 'in_process_handler') IS NULL
    ALTER TABLE wf.workflow_action ADD in_process_handler nvarchar(256) NULL;
GO
IF COL_LENGTH('wf.workflow_action', 'argv_map') IS NULL
    ALTER TABLE wf.workflow_action ADD argv_map json NULL;
GO

IF COL_LENGTH('wf.workflow_action', 'max_per_worker') IS NULL
    ALTER TABLE wf.workflow_action ADD max_per_worker INT NULL;
GO
IF COL_LENGTH('wf.workflow_action', 'exclusive_worker') IS NULL
    ALTER TABLE wf.workflow_action ADD exclusive_worker BIT NOT NULL
        CONSTRAINT DF_workflow_action_exclusive_worker DEFAULT (0);
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_upsert_workflow_action
    @action_name NVARCHAR(256),
    @capability NVARCHAR(128) = NULL,
    @payload_schema_ref NVARCHAR(512) = NULL,
    @execution_mode NVARCHAR(32) = NULL,
    @cli_tool NVARCHAR(256) = NULL,
    @in_process_handler NVARCHAR(256) = NULL,
    @argv_map json = NULL,
    @max_per_worker INT = NULL,
    @exclusive_worker BIT = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF @action_name IS NULL OR LTRIM(RTRIM(@action_name)) = N''
        RETURN;

    IF EXISTS (SELECT 1 FROM wf.workflow_action WHERE action_name = @action_name)
        UPDATE wf.workflow_action
        SET capability = @capability,
            payload_schema_ref = COALESCE(@payload_schema_ref, payload_schema_ref),
            execution_mode = COALESCE(@execution_mode, execution_mode),
            cli_tool = COALESCE(@cli_tool, cli_tool),
            in_process_handler = COALESCE(@in_process_handler, in_process_handler),
            argv_map = COALESCE(@argv_map, argv_map),
            max_per_worker = @max_per_worker,
            exclusive_worker = ISNULL(@exclusive_worker, 0)
        WHERE action_name = @action_name;
    ELSE
        INSERT INTO wf.workflow_action (
            action_name, capability, payload_schema_ref,
            execution_mode, cli_tool, in_process_handler, argv_map,
            max_per_worker, exclusive_worker
        )
        VALUES (
            @action_name, @capability, @payload_schema_ref,
            @execution_mode, @cli_tool, @in_process_handler, @argv_map,
            @max_per_worker, ISNULL(@exclusive_worker, 0)
        );
END;
GO

CREATE OR ALTER FUNCTION wf.wf_repo_list_actions()
RETURNS TABLE
AS
RETURN
(
    SELECT
        a.action_name,
        a.capability,
        CAST(CASE WHEN si.workflow_action_id IS NOT NULL THEN 1 ELSE 0 END AS bit) AS has_input_schema,
        CAST(CASE WHEN so.workflow_action_id IS NOT NULL THEN 1 ELSE 0 END AS bit) AS has_output_schema,
        a.execution_mode,
        a.cli_tool,
        a.in_process_handler,
        a.argv_map,
        a.max_per_worker,
        a.exclusive_worker
    FROM wf.workflow_action AS a
    LEFT JOIN wf.workflow_action_schema AS si
        ON si.workflow_action_id = a.id AND si.direction = N'input'
    LEFT JOIN wf.workflow_action_schema AS so
        ON so.workflow_action_id = a.id AND so.direction = N'output'
);
GO
