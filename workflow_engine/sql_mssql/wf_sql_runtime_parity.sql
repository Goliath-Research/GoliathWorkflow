/*
  MethylPipeline wf schema - SQL-only runtime parity with Delphi resolver behavior.

  Purpose:
  - Initialize instance scope variables from workflow_instance.context_json in SQL runtime.
  - Support ${var.*} placeholders in SQL wf_resolve_token.
  - Inject action input payloads via workflow_input_template and ${var.*} placeholders only.

  Prerequisites:
  - Base wf schema deployed (MethylPipeline_*.sql)
  - wf_scope_variables.sql (scope_variable table)
  - wf_scope_readpath.sql (wf_get_scope_variable_json/int helper functions)
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'wf.scope_variable', N'U') IS NULL
   OR OBJECT_ID(N'wf.wf_get_scope_variable_json', N'FN') IS NULL
BEGIN
    RAISERROR(N'Prerequisite missing: run wf_scope_variables.sql and wf_scope_readpath.sql first.', 16, 1);
    RETURN;
END
GO

CREATE OR ALTER PROCEDURE wf.wf_init_instance_scope_from_context
    @workflow_instance_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @ctx NVARCHAR(MAX);
    SELECT @ctx = CAST(context_json AS NVARCHAR(MAX))
    FROM wf.workflow_instance
    WHERE id = @workflow_instance_id;

    DELETE FROM wf.scope_variable
    WHERE workflow_instance_id = @workflow_instance_id
      AND scope_node_execution_id = 0;

    IF @ctx IS NULL OR LTRIM(RTRIM(@ctx)) = N'' OR ISJSON(@ctx) <> 1
        RETURN;

    IF LEFT(LTRIM(@ctx), 1) <> N'{'
        RETURN;

    INSERT INTO wf.scope_variable (workflow_instance_id, scope_node_execution_id, var_name, value_json)
    SELECT
      @workflow_instance_id,
      0,
      j.[key],
      wf.wf_json_box(
      CASE j.[type]
        WHEN 0 THEN N'null'
        WHEN 1 THEN wf.wf_json_fragment_from_string(j.[value])
        WHEN 2 THEN j.[value]
        WHEN 3 THEN LOWER(j.[value])
        WHEN 4 THEN JSON_QUERY(@ctx, CONCAT(N'$.', QUOTENAME(j.[key], '"')))
        WHEN 5 THEN JSON_QUERY(@ctx, CONCAT(N'$.', QUOTENAME(j.[key], '"')))
        ELSE wf.wf_json_fragment_from_string(j.[value])
      END)
    FROM OPENJSON(@ctx) AS j;
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_resolve_token
    @token NVARCHAR(1024),
    @node_execution_id BIGINT,
    @workflow_instance_id BIGINT,
    @out_fragment NVARCHAR(MAX) OUTPUT,
    @failed BIT OUTPUT,
    @fail_code INT OUTPUT,
    @fail_msg NVARCHAR(1024) OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET @failed = 0;
    SET @fail_code = NULL;
    SET @fail_msg = NULL;

    IF CHARINDEX(N' ', @token) > 0 OR CHARINDEX(N'+', @token) > 0 OR CHARINDEX(N'(', @token) > 0
    BEGIN
        SET @failed = 1;
        SET @fail_code = 10002;
        SET @fail_msg = N'Unsupported placeholder expression.';
        RETURN;
    END

    IF LEFT(@token, 9) = N'ctx.task.'
    BEGIN
        DECLARE @rest NVARCHAR(1024) = SUBSTRING(@token, 10, 4000);
        DECLARE @dot INT = CHARINDEX(N'.', @rest);
        DECLARE @nk NVARCHAR(128);
        DECLARE @tail NVARCHAR(1024);

        IF @dot = 0
        BEGIN
            SET @failed = 1;
            SET @fail_code = 10002;
            SET @fail_msg = N'Invalid ctx.task reference.';
            RETURN;
        END

        SET @nk = LEFT(@rest, @dot - 1);
        SET @tail = SUBSTRING(@rest, @dot + 1, 4000);

        IF @tail = N'resultCode'
        BEGIN
            DECLARE @rc INT = wf.wf_try_task_result_code(@workflow_instance_id, @nk);
            SET @out_fragment = CAST(@rc AS NVARCHAR(32));
            RETURN;
        END

        IF LEFT(@tail, 7) = N'output.'
        BEGIN
            DECLARE @jp NVARCHAR(4000) = SUBSTRING(@tail, 8, 4000);
            DECLARE @jq NVARCHAR(MAX) = wf.wf_try_task_output_json(@workflow_instance_id, @nk, @jp);
            SET @out_fragment = @jq;
            RETURN;
        END

        SET @failed = 1;
        SET @fail_code = 10002;
        SET @fail_msg = N'Unsupported ctx.task tail.';
        RETURN;
    END

    IF LEFT(@token, 4) = N'var.'
    BEGIN
        DECLARE @var_name NVARCHAR(128) = SUBSTRING(@token, 5, 4000);
        DECLARE @vv NVARCHAR(MAX);
        IF LTRIM(RTRIM(@var_name)) = N''
        BEGIN
            SET @failed = 1;
            SET @fail_code = 10002;
            SET @fail_msg = N'Empty scope variable name.';
            RETURN;
        END

        SET @vv = wf.wf_get_scope_variable_json(@workflow_instance_id, @node_execution_id, @var_name);
        IF @vv IS NULL AND @var_name IN (N'sampleDestination', N'h5Destination', N'rejectReason')
        BEGIN
            SET @out_fragment = N'null';
            RETURN;
        END
        IF @vv IS NULL
        BEGIN
            SET @failed = 1;
            SET @fail_code = 10001;
            SET @fail_msg = N'Missing scope variable: ' + @var_name;
            RETURN;
        END

        SET @out_fragment = @vv;
        RETURN;
    END

    IF LEFT(@token, 4) = N'ctx.'
    BEGIN
        DECLARE @v NVARCHAR(MAX);
        SELECT @v = wf.wf_json_unbox(CAST(context_value_json AS nvarchar(max)))
        FROM wf.execution_context
        WHERE node_execution_id = @node_execution_id AND context_key = @token;

        IF @v IS NULL
        BEGIN
            SET @failed = 1;
            SET @fail_code = 10001;
            SET @fail_msg = N'Missing context value for ' + @token;
            RETURN;
        END

        SET @out_fragment = @v;
        RETURN;
    END

    SET @failed = 1;
    SET @fail_code = 10002;
    SET @fail_msg = N'Unsupported token.';
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_build_input_json_for_action
    @node_execution_id BIGINT,
    @workflow_instance_id BIGINT,
    @workflow_node_id BIGINT,
    @final_json NVARCHAR(MAX) OUTPUT,
    @failed BIT OUTPUT,
    @fail_code INT OUTPUT,
    @fail_msg NVARCHAR(1024) OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET @failed = 0;

    DECLARE @template NVARCHAR(MAX) = N'{}';
    IF EXISTS (SELECT 1 FROM wf.workflow_input_template WHERE workflow_node_id = @workflow_node_id)
        SELECT @template = CAST(template_json AS NVARCHAR(MAX)) FROM wf.workflow_input_template WHERE workflow_node_id = @workflow_node_id;

    DECLARE @cur NVARCHAR(MAX);
    DECLARE @tf BIT;
    DECLARE @fc INT;
    DECLARE @fm NVARCHAR(1024);

    EXEC wf.wf_resolve_placeholders
        @text = @template,
        @node_execution_id = @node_execution_id,
        @workflow_instance_id = @workflow_instance_id,
        @resolved = @cur OUTPUT,
        @failed = @tf OUTPUT,
        @fail_code = @fc OUTPUT,
        @fail_msg = @fm OUTPUT;

    IF @tf = 1
    BEGIN
        SET @failed = 1;
        SET @fail_code = @fc;
        SET @fail_msg = @fm;
        RETURN;
    END

    IF ISJSON(@cur) = 0
    BEGIN
        SET @failed = 1;
        SET @fail_code = 10008;
        SET @fail_msg = N'Template JSON is invalid after placeholder resolution.';
        RETURN;
    END

    DECLARE @bid BIGINT;
    DECLARE @path NVARCHAR(1024);
    DECLARE @expr NVARCHAR(1024);
    DECLARE @req BIT;

    DECLARE c CURSOR LOCAL FAST_FORWARD FOR
        SELECT id, target_json_path, source_expr, is_required
        FROM wf.workflow_input_binding
        WHERE workflow_node_id = @workflow_node_id
        ORDER BY id;

    OPEN c;
    FETCH NEXT FROM c INTO @bid, @path, @expr, @req;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        DECLARE @frag NVARCHAR(MAX);

        EXEC wf.wf_resolve_placeholders
            @text = @expr,
            @node_execution_id = @node_execution_id,
            @workflow_instance_id = @workflow_instance_id,
            @resolved = @frag OUTPUT,
            @failed = @tf OUTPUT,
            @fail_code = @fc OUTPUT,
            @fail_msg = @fm OUTPUT;

        IF @tf = 1 AND @req = 1
        BEGIN
            SET @failed = 1;
            SET @fail_code = @fc;
            SET @fail_msg = @fm;
            CLOSE c;
            DEALLOCATE c;
            RETURN;
        END

        IF @tf = 1 AND (@req = 0 OR @req IS NULL)
            SET @frag = N'null';

        IF LEFT(@path, 1) <> N'$'
            SET @path = N'$.' + @path;
        IF ISNULL(@frag, N'') = N''
            SET @frag = N'null';

        IF ISJSON(@frag) = 1
            SET @cur = JSON_MODIFY(@cur, @path, JSON_QUERY(@frag));
        ELSE
            SET @cur = JSON_MODIFY(@cur, @path, JSON_QUERY(wf.wf_json_fragment_from_string(@frag)));

        FETCH NEXT FROM c INTO @bid, @path, @expr, @req;
    END

    CLOSE c;
    DEALLOCATE c;

    SET @final_json = @cur;
END;
GO

CREATE OR ALTER PROCEDURE wf.sp_start_workflow_instance
    @workflow_instance_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @vid BIGINT;
    DECLARE @root BIGINT;

    SELECT @vid = workflow_version_id FROM wf.workflow_instance WHERE id = @workflow_instance_id;
    SELECT @root = root_node_id FROM wf.workflow_version WHERE id = @vid;

    IF @root IS NULL
        THROW 50001, N'Workflow version has no root_node_id.', 1;

    UPDATE wf.workflow_instance
    SET
      status = N'RUNNING',
      started_at_utc = SYSUTCDATETIME()
    WHERE id = @workflow_instance_id;

    EXEC wf.wf_init_instance_scope_from_context
      @workflow_instance_id = @workflow_instance_id;

    IF OBJECT_ID(N'wf.wf_resolve_collection_bindings', N'P') IS NOT NULL
        EXEC wf.wf_resolve_collection_bindings
            @workflow_instance_id = @workflow_instance_id;

    EXEC wf.wf_engine_activate
        @workflow_instance_id = @workflow_instance_id,
        @workflow_node_id = @root,
        @parent_node_execution_id = NULL,
        @iteration_no = 0,
        @sequence_index = NULL,
        @parallel_index = NULL;
END;
GO

