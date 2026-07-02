/*
  Portal workflow repository API (Azure SQL).
  EpiPortal calls these procs directly — never the REST gateway.

  Prerequisites: wf repository API, portal schema, wf.workflow_def.source column.
*/

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'portal')
BEGIN
    EXEC(N'CREATE SCHEMA portal');
END
GO

IF COL_LENGTH('wf.workflow_def', 'source') IS NULL
BEGIN
    ALTER TABLE wf.workflow_def
    ADD source varchar(32) NOT NULL
        CONSTRAINT DF_workflow_def_source DEFAULT ('system');
END
GO

IF OBJECT_ID(N'portal.sp_list_workflow_actions', N'P') IS NOT NULL
    DROP PROCEDURE portal.sp_list_workflow_actions;
GO
CREATE PROCEDURE portal.sp_list_workflow_actions
AS
BEGIN
    SET NOCOUNT ON;
    SELECT action_name, capability, has_input_schema, has_output_schema
    FROM wf.wf_repo_list_actions();
END
GO

IF OBJECT_ID(N'portal.sp_get_action_schema', N'P') IS NOT NULL
    DROP PROCEDURE portal.sp_get_action_schema;
GO
CREATE PROCEDURE portal.sp_get_action_schema
    @action_name nvarchar(256),
    @direction varchar(16)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT *
    FROM wf.wf_repo_get_action_schema(@action_name, @direction);
END
GO

IF OBJECT_ID(N'portal.sp_list_workflow_definitions', N'P') IS NOT NULL
    DROP PROCEDURE portal.sp_list_workflow_definitions;
GO
CREATE PROCEDURE portal.sp_list_workflow_definitions
    @source_filter varchar(32) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT wd.id AS workflow_def_id,
           wd.name,
           COALESCE(wd.source, 'system') AS source,
           wv.id AS workflow_version_id,
           wv.version_major,
           wv.version_minor
    FROM wf.workflow_def wd
    OUTER APPLY (
        SELECT TOP 1 id, version_major, version_minor
        FROM wf.workflow_version
        WHERE workflow_def_id = wd.id AND is_active = 1
        ORDER BY version_major DESC, version_minor DESC
    ) wv
    WHERE @source_filter IS NULL OR COALESCE(wd.source, 'system') = @source_filter
    ORDER BY wd.name;
END
GO

IF OBJECT_ID(N'portal.sp_create_workflow_graph', N'P') IS NOT NULL
    DROP PROCEDURE portal.sp_create_workflow_graph;
GO
CREATE PROCEDURE portal.sp_create_workflow_graph
    @spec nvarchar(max)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @node nvarchar(max);
    DECLARE @action_name nvarchar(256);
    DECLARE @nodes nvarchar(max) = JSON_QUERY(@spec, '$.nodes');
    DECLARE @i int = 0;
    DECLARE @n int = (SELECT COUNT(*) FROM OPENJSON(@nodes));

    WHILE @i < @n
    BEGIN
        SET @node = JSON_QUERY(@nodes, CONCAT('$[', @i, ']'));
        SET @action_name = JSON_VALUE(@node, '$.action');
        IF @action_name IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM wf.workflow_action WHERE action_name = @action_name
        )
            THROW 50020, N'Unknown action in workflow graph', 1;
        SET @i += 1;
    END

    DECLARE @result TABLE (
        workflow_def_id bigint,
        workflow_version_id bigint,
        root_node_id bigint,
        name nvarchar(256)
    );

    DECLARE @spec_json json = CAST(@spec AS json);

    INSERT INTO @result
    EXEC wf.wf_repo_create_workflow_graph @spec = @spec_json;

    UPDATE wf.workflow_def
    SET source = N'portal'
    WHERE id = (SELECT TOP 1 workflow_def_id FROM @result);

    SELECT * FROM @result;
END
GO

IF OBJECT_ID(N'portal.sp_create_and_start_instance', N'P') IS NOT NULL
    DROP PROCEDURE portal.sp_create_and_start_instance;
GO
CREATE PROCEDURE portal.sp_create_and_start_instance
    @workflow_version_id bigint,
    @context_json nvarchar(max) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @instance_id bigint;
    DECLARE @ctx json = TRY_CAST(@context_json AS json);

    CREATE TABLE #created (id bigint);
    INSERT INTO #created (id)
    EXEC wf.wf_repo_create_workflow_instance
        @version_id = @workflow_version_id,
        @context_json = @ctx;

    SELECT TOP 1 @instance_id = id FROM #created;

    EXEC wf.sp_start_workflow_instance @workflow_instance_id = @instance_id;

    EXEC wf.wf_repo_get_workflow_instance @instance_id = @instance_id;
END
GO

IF OBJECT_ID(N'portal.sp_get_instance_tasks', N'P') IS NOT NULL
    DROP PROCEDURE portal.sp_get_instance_tasks;
GO
CREATE PROCEDURE portal.sp_get_instance_tasks
    @workflow_instance_id bigint
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ne.id AS node_execution_id,
           ne.status,
           ne.result_code,
           ne.attempt_no,
           wn.node_key,
           wa.action_name,
           wa.capability,
           ne.input_json,
           ne.output_json,
           ne.started_at_utc,
           ne.ended_at_utc AS completed_at_utc
    FROM wf.node_execution ne
    INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
    LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
    WHERE ne.workflow_instance_id = @workflow_instance_id
    ORDER BY ne.id;
END
GO

PRINT N'portal workflow API deployed (Azure SQL).';
GO
