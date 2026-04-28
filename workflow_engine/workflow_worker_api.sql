/*
  Workflow Engine - Worker API and activation/completion logic (SQL Server).
  Dependencies: workflow_definition.sql, workflow_runtime.sql, workflow_constraints_indexes.sql
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.sp_worker_fail_task', N'P') IS NOT NULL DROP PROCEDURE dbo.sp_worker_fail_task;
IF OBJECT_ID(N'dbo.sp_worker_heartbeat', N'P') IS NOT NULL DROP PROCEDURE dbo.sp_worker_heartbeat;
IF OBJECT_ID(N'dbo.sp_worker_submit_result', N'P') IS NOT NULL DROP PROCEDURE dbo.sp_worker_submit_result;
IF OBJECT_ID(N'dbo.sp_worker_request_task', N'P') IS NOT NULL DROP PROCEDURE dbo.sp_worker_request_task;
IF OBJECT_ID(N'dbo.sp_start_workflow_instance', N'P') IS NOT NULL DROP PROCEDURE dbo.sp_start_workflow_instance;
GO

/* ---- Constants (engine error codes) ---- */
-- 10001: required binding / placeholder missing
-- 10002: unsupported placeholder expression

GO

CREATE OR ALTER FUNCTION dbo.wf_json_fragment_from_string(@s NVARCHAR(MAX))
RETURNS NVARCHAR(MAX)
AS
BEGIN
    RETURN N'"' + REPLACE(REPLACE(REPLACE(@s, N'\', N'\\'), N'"', N'\"'), CHAR(10), N'\n') + N'"';
END;
GO

CREATE OR ALTER FUNCTION dbo.wf_try_task_result_code(@workflow_instance_id BIGINT, @node_key NVARCHAR(128))
RETURNS INT
AS
BEGIN
    DECLARE @r INT;
    SELECT TOP (1) @r = ne.result_code
    FROM dbo.node_execution AS ne
    INNER JOIN dbo.workflow_node AS wn ON wn.id = ne.workflow_node_id
    WHERE ne.workflow_instance_id = @workflow_instance_id
      AND wn.node_key = @node_key
      AND ne.status = N'SUCCEEDED'
    ORDER BY ne.ended_at_utc DESC, ne.id DESC;
    RETURN @r;
END;
GO

CREATE OR ALTER FUNCTION dbo.wf_try_task_output_json(@workflow_instance_id BIGINT, @node_key NVARCHAR(128), @jsonPath NVARCHAR(4000))
RETURNS NVARCHAR(MAX)
AS
BEGIN
    DECLARE @out NVARCHAR(MAX);
    SELECT TOP (1) @out = ne.output_json
    FROM dbo.node_execution AS ne
    INNER JOIN dbo.workflow_node AS wn ON wn.id = ne.workflow_node_id
    WHERE ne.workflow_instance_id = @workflow_instance_id
      AND wn.node_key = @node_key
      AND ne.status = N'SUCCEEDED'
    ORDER BY ne.ended_at_utc DESC, ne.id DESC;

    IF @out IS NULL RETURN NULL;

    IF @jsonPath IS NULL OR LTRIM(RTRIM(@jsonPath)) = N'' RETURN @out;

    IF LEFT(@jsonPath, 1) <> N'$' SET @jsonPath = N'$.' + @jsonPath;

    DECLARE @jq NVARCHAR(MAX) = JSON_QUERY(@out, @jsonPath);
    IF @jq IS NOT NULL RETURN @jq;

    DECLARE @jv NVARCHAR(MAX) = JSON_VALUE(@out, @jsonPath);
    IF @jv IS NULL RETURN NULL;

    DECLARE @bi BIGINT = TRY_CONVERT(BIGINT, @jv);
    IF @bi IS NOT NULL AND CAST(@bi AS NVARCHAR(50)) = LTRIM(RTRIM(@jv))
        RETURN CAST(@bi AS NVARCHAR(50));

    RETURN dbo.wf_json_fragment_from_string(@jv);
END;
GO

CREATE OR ALTER PROCEDURE dbo.wf_seed_execution_context
    @node_execution_id BIGINT,
    @workflow_instance_id BIGINT,
    @workflow_node_id BIGINT,
    @parent_node_execution_id BIGINT NULL,
    @iteration_no INT,
    @sequence_index INT NULL,
    @parallel_index INT NULL
AS
BEGIN
    SET NOCOUNT ON;

    DELETE FROM dbo.execution_context WHERE node_execution_id = @node_execution_id;

    INSERT INTO dbo.execution_context (node_execution_id, context_key, context_value_json)
    VALUES (@node_execution_id, N'ctx.iterationNo', CAST(@iteration_no AS NVARCHAR(32)));

    IF @sequence_index IS NOT NULL
        INSERT INTO dbo.execution_context (node_execution_id, context_key, context_value_json)
        VALUES (@node_execution_id, N'ctx.sequenceIndex', CAST(@sequence_index AS NVARCHAR(32)));

    IF @parallel_index IS NOT NULL
        INSERT INTO dbo.execution_context (node_execution_id, context_key, context_value_json)
        VALUES (@node_execution_id, N'ctx.parallelIndex', CAST(@parallel_index AS NVARCHAR(32)));

    IF @parent_node_execution_id IS NOT NULL
    BEGIN
        DECLARE @prc INT;
        SELECT @prc = result_code FROM dbo.node_execution WHERE id = @parent_node_execution_id;
        INSERT INTO dbo.execution_context (node_execution_id, context_key, context_value_json)
        VALUES (@node_execution_id, N'ctx.parent.resultCode', CAST(@prc AS NVARCHAR(32)));
    END
END;
GO

CREATE OR ALTER PROCEDURE dbo.wf_resolve_token
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
            DECLARE @rc INT = dbo.wf_try_task_result_code(@workflow_instance_id, @nk);
            SET @out_fragment = CAST(@rc AS NVARCHAR(32));
            RETURN;
        END

        IF LEFT(@tail, 7) = N'output.'
        BEGIN
            DECLARE @jp NVARCHAR(4000) = SUBSTRING(@tail, 8, 4000);
            DECLARE @jq NVARCHAR(MAX) = dbo.wf_try_task_output_json(@workflow_instance_id, @nk, @jp);
            SET @out_fragment = @jq;
            RETURN;
        END

        SET @failed = 1;
        SET @fail_code = 10002;
        SET @fail_msg = N'Unsupported ctx.task tail.';
        RETURN;
    END

    IF LEFT(@token, 4) = N'ctx.'
    BEGIN
        DECLARE @v NVARCHAR(MAX);
        SELECT @v = context_value_json
        FROM dbo.execution_context
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

CREATE OR ALTER PROCEDURE dbo.wf_resolve_placeholders
    @text NVARCHAR(MAX),
    @node_execution_id BIGINT,
    @workflow_instance_id BIGINT,
    @resolved NVARCHAR(MAX) OUTPUT,
    @failed BIT OUTPUT,
    @fail_code INT OUTPUT,
    @fail_msg NVARCHAR(1024) OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET @resolved = @text;
    SET @failed = 0;

    DECLARE @start INT;
    DECLARE @end INT;
    DECLARE @token NVARCHAR(1024);
    DECLARE @frag NVARCHAR(MAX);
    DECLARE @tf BIT;
    DECLARE @fc INT;
    DECLARE @fm NVARCHAR(1024);

    WHILE CHARINDEX(N'${', @resolved) > 0
    BEGIN
        SET @start = CHARINDEX(N'${', @resolved);
        SET @end = CHARINDEX(N'}', @resolved, @start + 2);
        IF @end = 0 BREAK;

        SET @token = SUBSTRING(@resolved, @start + 2, @end - (@start + 2));

        EXEC dbo.wf_resolve_token
            @token = @token,
            @node_execution_id = @node_execution_id,
            @workflow_instance_id = @workflow_instance_id,
            @out_fragment = @frag OUTPUT,
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

        SET @resolved = STUFF(@resolved, @start, @end - @start + 1, ISNULL(@frag, N'null'));
    END
END;
GO

CREATE OR ALTER PROCEDURE dbo.wf_build_input_json_for_action
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
    IF EXISTS (SELECT 1 FROM dbo.workflow_input_template WHERE workflow_node_id = @workflow_node_id)
        SELECT @template = template_json FROM dbo.workflow_input_template WHERE workflow_node_id = @workflow_node_id;

    DECLARE @cur NVARCHAR(MAX);
    DECLARE @tf BIT;
    DECLARE @fc INT;
    DECLARE @fm NVARCHAR(1024);

    EXEC dbo.wf_resolve_placeholders
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
        FROM dbo.workflow_input_binding
        WHERE workflow_node_id = @workflow_node_id
        ORDER BY id;

    OPEN c;
    FETCH NEXT FROM c INTO @bid, @path, @expr, @req;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        DECLARE @frag NVARCHAR(MAX);

        EXEC dbo.wf_resolve_placeholders
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

        IF LEFT(@path, 1) <> N'$' SET @path = N'$.' + @path;

        IF ISNULL(@frag, N'') = N'' SET @frag = N'null';

        IF ISJSON(@frag) = 1
            SET @cur = JSON_MODIFY(@cur, @path, JSON_QUERY(@frag));
        ELSE
            SET @cur = JSON_MODIFY(@cur, @path, JSON_QUERY(dbo.wf_json_fragment_from_string(@frag)));

        FETCH NEXT FROM c INTO @bid, @path, @expr, @req;
    END

    CLOSE c;
    DEALLOCATE c;

    SET @final_json = @cur;
END;
GO

CREATE OR ALTER PROCEDURE dbo.wf_engine_activate
    @workflow_instance_id BIGINT,
    @workflow_node_id BIGINT,
    @parent_node_execution_id BIGINT NULL,
    @iteration_no INT = 0,
    @sequence_index INT NULL,
    @parallel_index INT NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @node_type VARCHAR(32);
    DECLARE @version_id BIGINT;
    DECLARE @node_key NVARCHAR(128);

    SELECT @node_type = node_type, @version_id = workflow_version_id, @node_key = node_key
    FROM dbo.workflow_node
    WHERE id = @workflow_node_id;

    IF @node_type IS NULL RETURN;

    IF @node_type = N'ACTION'
    BEGIN
        DECLARE @ne_id BIGINT;
        INSERT INTO dbo.node_execution (
            workflow_instance_id, workflow_node_id, status, attempt_no,
            parent_node_execution_id, iteration_no, available_at_utc
        )
        VALUES (
            @workflow_instance_id, @workflow_node_id, N'READY', 1,
            @parent_node_execution_id, @iteration_no, SYSUTCDATETIME()
        );
        SET @ne_id = SCOPE_IDENTITY();

        EXEC dbo.wf_seed_execution_context
            @node_execution_id = @ne_id,
            @workflow_instance_id = @workflow_instance_id,
            @workflow_node_id = @workflow_node_id,
            @parent_node_execution_id = @parent_node_execution_id,
            @iteration_no = @iteration_no,
            @sequence_index = @sequence_index,
            @parallel_index = @parallel_index;

        DECLARE @fj NVARCHAR(MAX);
        DECLARE @failed BIT;
        DECLARE @fc INT;
        DECLARE @fm NVARCHAR(1024);

        EXEC dbo.wf_build_input_json_for_action
            @node_execution_id = @ne_id,
            @workflow_instance_id = @workflow_instance_id,
            @workflow_node_id = @workflow_node_id,
            @final_json = @fj OUTPUT,
            @failed = @failed OUTPUT,
            @fail_code = @fc OUTPUT,
            @fail_msg = @fm OUTPUT;

        IF @failed = 1
        BEGIN
            UPDATE dbo.node_execution
            SET status = N'FAILED',
                engine_error_code = @fc,
                engine_error_message = @fm,
                ended_at_utc = SYSUTCDATETIME()
            WHERE id = @ne_id;

            UPDATE dbo.workflow_instance
            SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME()
            WHERE id = @workflow_instance_id;

            RETURN;
        END

        UPDATE dbo.node_execution SET input_json = @fj WHERE id = @ne_id;
        RETURN;
    END

    /* Composite: create RUNNING execution row */
    DECLARE @pex BIGINT;
    INSERT INTO dbo.node_execution (
        workflow_instance_id, workflow_node_id, status, attempt_no,
        parent_node_execution_id, iteration_no, started_at_utc, available_at_utc
    )
    VALUES (
        @workflow_instance_id, @workflow_node_id, N'RUNNING', 1,
        @parent_node_execution_id, @iteration_no, SYSUTCDATETIME(), SYSUTCDATETIME()
    );
    SET @pex = SCOPE_IDENTITY();

    IF @node_type = N'SEQUENCE'
    BEGIN
        DECLARE @child1 BIGINT;
        SELECT TOP (1) @child1 = child_node_id
        FROM dbo.workflow_edge
        WHERE parent_node_id = @workflow_node_id
        ORDER BY child_order ASC;

        IF @child1 IS NULL
        BEGIN
            UPDATE dbo.node_execution SET status = N'SUCCEEDED', ended_at_utc = SYSUTCDATETIME() WHERE id = @pex;
            EXEC dbo.wf_engine_on_composite_complete @node_execution_id = @pex;
            RETURN;
        END

        DECLARE @ord INT = 0;
        SELECT TOP (1) @ord = child_order FROM dbo.workflow_edge WHERE parent_node_id = @workflow_node_id ORDER BY child_order ASC;

        EXEC dbo.wf_engine_activate
            @workflow_instance_id = @workflow_instance_id,
            @workflow_node_id = @child1,
            @parent_node_execution_id = @pex,
            @iteration_no = @iteration_no,
            @sequence_index = @ord,
            @parallel_index = NULL;
        RETURN;
    END

    IF @node_type = N'PARALLEL'
    BEGIN
        DECLARE @cid BIGINT;
        DECLARE @pidx INT = 0;
        DECLARE pc CURSOR LOCAL FAST_FORWARD FOR
            SELECT child_node_id
            FROM dbo.workflow_edge
            WHERE parent_node_id = @workflow_node_id
            ORDER BY child_order ASC;

        OPEN pc;
        FETCH NEXT FROM pc INTO @cid;

        WHILE @@FETCH_STATUS = 0
        BEGIN
            EXEC dbo.wf_engine_activate
                @workflow_instance_id = @workflow_instance_id,
                @workflow_node_id = @cid,
                @parent_node_execution_id = @pex,
                @iteration_no = @iteration_no,
                @sequence_index = NULL,
                @parallel_index = @pidx;

            SET @pidx += 1;
            FETCH NEXT FROM pc INTO @cid;
        END

        CLOSE pc;
        DEALLOCATE pc;
        RETURN;
    END

    IF @node_type = N'IF'
    BEGIN
        DECLARE @cref NVARCHAR(128);
        SELECT @cref = condition_ref_node_key FROM dbo.workflow_node WHERE id = @workflow_node_id;

        DECLARE @cond INT = dbo.wf_try_task_result_code(@workflow_instance_id, @cref);
        DECLARE @pick VARCHAR(32) = CASE WHEN @cond IS NOT NULL AND @cond <> 0 THEN N'THEN' ELSE N'ELSE' END;

        DECLARE @ifchild BIGINT;
        SELECT TOP (1) @ifchild = child_node_id
        FROM dbo.workflow_edge
        WHERE parent_node_id = @workflow_node_id AND branch_kind = @pick
        ORDER BY child_order ASC;

        IF @ifchild IS NULL
        BEGIN
            UPDATE dbo.node_execution SET status = N'FAILED', engine_error_code = 10003, engine_error_message = N'Missing IF branch.', ended_at_utc = SYSUTCDATETIME() WHERE id = @pex;
            UPDATE dbo.workflow_instance SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME() WHERE id = @workflow_instance_id;
            RETURN;
        END

        EXEC dbo.wf_engine_activate
            @workflow_instance_id = @workflow_instance_id,
            @workflow_node_id = @ifchild,
            @parent_node_execution_id = @pex,
            @iteration_no = @iteration_no,
            @sequence_index = NULL,
            @parallel_index = NULL;
        RETURN;
    END

    IF @node_type = N'SWITCH'
    BEGIN
        DECLARE @sref NVARCHAR(128);
        SELECT @sref = switch_ref_node_key FROM dbo.workflow_node WHERE id = @workflow_node_id;

        DECLARE @sv INT = dbo.wf_try_task_result_code(@workflow_instance_id, @sref);

        DECLARE @swchild BIGINT;
        SELECT TOP (1) @swchild = child_node_id
        FROM dbo.workflow_edge
        WHERE parent_node_id = @workflow_node_id AND branch_kind = N'CASE' AND switch_case_value = @sv
        ORDER BY child_order ASC;

        IF @swchild IS NULL
            SELECT TOP (1) @swchild = child_node_id
            FROM dbo.workflow_edge
            WHERE parent_node_id = @workflow_node_id AND branch_kind = N'DEFAULT'
            ORDER BY child_order ASC;

        IF @swchild IS NULL
        BEGIN
            UPDATE dbo.node_execution SET status = N'FAILED', engine_error_code = 10004, engine_error_message = N'Missing SWITCH case.', ended_at_utc = SYSUTCDATETIME() WHERE id = @pex;
            UPDATE dbo.workflow_instance SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME() WHERE id = @workflow_instance_id;
            RETURN;
        END

        EXEC dbo.wf_engine_activate
            @workflow_instance_id = @workflow_instance_id,
            @workflow_node_id = @swchild,
            @parent_node_execution_id = @pex,
            @iteration_no = @iteration_no,
            @sequence_index = NULL,
            @parallel_index = NULL;
        RETURN;
    END

    IF @node_type = N'REPEAT'
    BEGIN
        DECLARE @rcount INT;
        SELECT @rcount = repeat_count FROM dbo.workflow_node WHERE id = @workflow_node_id;

        IF @rcount IS NULL OR @rcount < 1 SET @rcount = 1;

        INSERT INTO dbo.loop_state (workflow_instance_id, control_node_id, scope_node_execution_id, current_iteration, repeat_target_count)
        VALUES (@workflow_instance_id, @workflow_node_id, @pex, 0, @rcount);

        DECLARE @body BIGINT;
        SELECT TOP (1) @body = child_node_id FROM dbo.workflow_edge WHERE parent_node_id = @workflow_node_id AND branch_kind = N'BODY' ORDER BY child_order ASC;

        IF @body IS NULL
        BEGIN
            UPDATE dbo.node_execution SET status = N'FAILED', engine_error_code = 10005, ended_at_utc = SYSUTCDATETIME() WHERE id = @pex;
            UPDATE dbo.workflow_instance SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME() WHERE id = @workflow_instance_id;
            RETURN;
        END

        EXEC dbo.wf_engine_activate
            @workflow_instance_id = @workflow_instance_id,
            @workflow_node_id = @body,
            @parent_node_execution_id = @pex,
            @iteration_no = 1,
            @sequence_index = NULL,
            @parallel_index = NULL;
        RETURN;
    END

    IF @node_type = N'WHILE'
    BEGIN
        DECLARE @wbody BIGINT;
        SELECT TOP (1) @wbody = child_node_id FROM dbo.workflow_edge WHERE parent_node_id = @workflow_node_id AND branch_kind = N'BODY' ORDER BY child_order ASC;

        IF @wbody IS NULL
        BEGIN
            UPDATE dbo.node_execution SET status = N'FAILED', engine_error_code = 10006, ended_at_utc = SYSUTCDATETIME() WHERE id = @pex;
            UPDATE dbo.workflow_instance SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME() WHERE id = @workflow_instance_id;
            RETURN;
        END

        DECLARE @wcref NVARCHAR(128);
        SELECT @wcref = condition_ref_node_key FROM dbo.workflow_node WHERE id = @workflow_node_id;

        DECLARE @wcond INT = dbo.wf_try_task_result_code(@workflow_instance_id, @wcref);

        IF @wcond IS NULL OR @wcond = 0
        BEGIN
            UPDATE dbo.node_execution SET status = N'SUCCEEDED', ended_at_utc = SYSUTCDATETIME() WHERE id = @pex;
            EXEC dbo.wf_engine_on_composite_complete @node_execution_id = @pex;
            RETURN;
        END

        EXEC dbo.wf_engine_activate
            @workflow_instance_id = @workflow_instance_id,
            @workflow_node_id = @wbody,
            @parent_node_execution_id = @pex,
            @iteration_no = 1,
            @sequence_index = NULL,
            @parallel_index = NULL;
        RETURN;
    END
END;
GO

CREATE OR ALTER PROCEDURE dbo.wf_engine_on_composite_complete
    @node_execution_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @parent BIGINT;
    DECLARE @inst BIGINT;
    SELECT @parent = parent_node_execution_id, @inst = workflow_instance_id FROM dbo.node_execution WHERE id = @node_execution_id;

    IF @parent IS NULL
    BEGIN
        UPDATE dbo.workflow_instance
        SET status = N'COMPLETED', completed_at_utc = SYSUTCDATETIME()
        WHERE id = @inst AND status = N'RUNNING';
        RETURN;
    END

    EXEC dbo.wf_engine_continue_parent @parent_node_execution_id = @parent;
END;
GO

CREATE OR ALTER PROCEDURE dbo.wf_engine_continue_parent
    @parent_node_execution_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @pnode BIGINT;
    DECLARE @ptype VARCHAR(32);
    SELECT @pnode = ne.workflow_node_id, @ptype = wn.node_type
    FROM dbo.node_execution AS ne
    INNER JOIN dbo.workflow_node AS wn ON wn.id = ne.workflow_node_id
    WHERE ne.id = @parent_node_execution_id;

    IF @ptype = N'SEQUENCE'
        EXEC dbo.wf_sequence_continue @sequence_execution_id = @parent_node_execution_id;

    ELSE IF @ptype = N'PARALLEL'
        EXEC dbo.wf_parallel_continue @parallel_execution_id = @parent_node_execution_id;

    ELSE IF @ptype IN (N'IF', N'SWITCH')
    BEGIN
        UPDATE dbo.node_execution SET status = N'SUCCEEDED', ended_at_utc = SYSUTCDATETIME() WHERE id = @parent_node_execution_id;
        EXEC dbo.wf_engine_on_composite_complete @node_execution_id = @parent_node_execution_id;
    END

    ELSE IF @ptype = N'REPEAT'
        EXEC dbo.wf_repeat_continue @repeat_execution_id = @parent_node_execution_id;

    ELSE IF @ptype = N'WHILE'
        EXEC dbo.wf_while_continue @while_execution_id = @parent_node_execution_id;
END;
GO

CREATE OR ALTER PROCEDURE dbo.wf_sequence_continue
    @sequence_execution_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @inst BIGINT;
    DECLARE @seq_node BIGINT;
    SELECT @inst = workflow_instance_id, @seq_node = workflow_node_id FROM dbo.node_execution WHERE id = @sequence_execution_id;

    DECLARE @last_child_ne BIGINT;
    SELECT TOP (1) @last_child_ne = ne.id
    FROM dbo.node_execution AS ne
    WHERE ne.parent_node_execution_id = @sequence_execution_id AND ne.status IN (N'SUCCEEDED', N'FAILED', N'SKIPPED')
    ORDER BY ne.ended_at_utc DESC, ne.id DESC;

    DECLARE @last_status VARCHAR(32);
    DECLARE @last_child_wn BIGINT;
    SELECT @last_child_wn = workflow_node_id, @last_status = status FROM dbo.node_execution WHERE id = @last_child_ne;

    IF @last_status = N'FAILED'
    BEGIN
        UPDATE dbo.node_execution SET status = N'FAILED', ended_at_utc = SYSUTCDATETIME() WHERE id = @sequence_execution_id;
        UPDATE dbo.workflow_instance SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME() WHERE id = @inst;
        RETURN;
    END

    DECLARE @next_order INT;
    SELECT @next_order = e.child_order + 1
    FROM dbo.workflow_edge AS e
    WHERE e.parent_node_id = @seq_node AND e.child_node_id = @last_child_wn;

    DECLARE @next_child BIGINT;
    SELECT TOP (1) @next_child = child_node_id
    FROM dbo.workflow_edge
    WHERE parent_node_id = @seq_node AND child_order = @next_order;

    IF @next_child IS NULL
    BEGIN
        UPDATE dbo.node_execution SET status = N'SUCCEEDED', ended_at_utc = SYSUTCDATETIME() WHERE id = @sequence_execution_id;
        EXEC dbo.wf_engine_on_composite_complete @node_execution_id = @sequence_execution_id;
        RETURN;
    END

    EXEC dbo.wf_engine_activate
        @workflow_instance_id = @inst,
        @workflow_node_id = @next_child,
        @parent_node_execution_id = @sequence_execution_id,
        @iteration_no = (SELECT iteration_no FROM dbo.node_execution WHERE id = @sequence_execution_id),
        @sequence_index = @next_order,
        @parallel_index = NULL;
END;
GO

CREATE OR ALTER PROCEDURE dbo.wf_parallel_continue
    @parallel_execution_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @inst BIGINT;
    DECLARE @pnode BIGINT;
    SELECT @inst = workflow_instance_id, @pnode = workflow_node_id FROM dbo.node_execution WHERE id = @parallel_execution_id;

    DECLARE @total INT = (SELECT COUNT(*) FROM dbo.workflow_edge WHERE parent_node_id = @pnode);

    DECLARE @finished INT = (
        SELECT COUNT(*)
        FROM dbo.node_execution AS ne
        WHERE ne.parent_node_execution_id = @parallel_execution_id
          AND ne.status IN (N'SUCCEEDED', N'FAILED', N'SKIPPED', N'CANCELLED')
    );

    IF @finished < @total RETURN;

    IF EXISTS (
        SELECT 1 FROM dbo.node_execution
        WHERE parent_node_execution_id = @parallel_execution_id AND status = N'FAILED'
    )
    BEGIN
        UPDATE dbo.node_execution SET status = N'FAILED', ended_at_utc = SYSUTCDATETIME() WHERE id = @parallel_execution_id;
        UPDATE dbo.workflow_instance SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME() WHERE id = @inst;
        RETURN;
    END

    UPDATE dbo.node_execution SET status = N'SUCCEEDED', ended_at_utc = SYSUTCDATETIME() WHERE id = @parallel_execution_id;
    EXEC dbo.wf_engine_on_composite_complete @node_execution_id = @parallel_execution_id;
END;
GO

CREATE OR ALTER PROCEDURE dbo.wf_repeat_continue
    @repeat_execution_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @inst BIGINT;
    DECLARE @ctl BIGINT;
    SELECT @inst = workflow_instance_id, @ctl = workflow_node_id FROM dbo.node_execution WHERE id = @repeat_execution_id;

    DECLARE @ls BIGINT;
    DECLARE @cur INT;
    DECLARE @max INT;
    SELECT TOP (1)
        @ls = id,
        @cur = current_iteration,
        @max = repeat_target_count
    FROM dbo.loop_state
    WHERE scope_node_execution_id = @repeat_execution_id;

    IF @ls IS NULL
    BEGIN
        UPDATE dbo.node_execution SET status = N'FAILED', engine_error_code = 10007, ended_at_utc = SYSUTCDATETIME() WHERE id = @repeat_execution_id;
        UPDATE dbo.workflow_instance SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME() WHERE id = @inst;
        RETURN;
    END

    SET @cur += 1;
    UPDATE dbo.loop_state SET current_iteration = @cur WHERE id = @ls;

    IF @cur >= @max
    BEGIN
        UPDATE dbo.node_execution SET status = N'SUCCEEDED', ended_at_utc = SYSUTCDATETIME() WHERE id = @repeat_execution_id;
        EXEC dbo.wf_engine_on_composite_complete @node_execution_id = @repeat_execution_id;
        RETURN;
    END

    DECLARE @body BIGINT;
    SELECT TOP (1) @body = child_node_id FROM dbo.workflow_edge WHERE parent_node_id = @ctl AND branch_kind = N'BODY' ORDER BY child_order ASC;

    EXEC dbo.wf_engine_activate
        @workflow_instance_id = @inst,
        @workflow_node_id = @body,
        @parent_node_execution_id = @repeat_execution_id,
        @iteration_no = @cur + 1,
        @sequence_index = NULL,
        @parallel_index = NULL;
END;
GO

CREATE OR ALTER PROCEDURE dbo.wf_while_continue
    @while_execution_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @inst BIGINT;
    DECLARE @ctl BIGINT;
    SELECT @inst = workflow_instance_id, @ctl = workflow_node_id FROM dbo.node_execution WHERE id = @while_execution_id;

    DECLARE @wcref NVARCHAR(128);
    SELECT @wcref = condition_ref_node_key FROM dbo.workflow_node WHERE id = @ctl;

    DECLARE @wcond INT = dbo.wf_try_task_result_code(@workflow_instance_id, @wcref);

    IF @wcond IS NULL OR @wcond = 0
    BEGIN
        UPDATE dbo.node_execution SET status = N'SUCCEEDED', ended_at_utc = SYSUTCDATETIME() WHERE id = @while_execution_id;
        EXEC dbo.wf_engine_on_composite_complete @node_execution_id = @while_execution_id;
        RETURN;
    END

    DECLARE @iter INT = ISNULL((SELECT MAX(iteration_no) FROM dbo.node_execution WHERE parent_node_execution_id = @while_execution_id AND workflow_node_id = (
        SELECT TOP (1) child_node_id FROM dbo.workflow_edge WHERE parent_node_id = @ctl AND branch_kind = N'BODY' ORDER BY child_order ASC
    )), 0);

    DECLARE @wbody BIGINT;
    SELECT TOP (1) @wbody = child_node_id FROM dbo.workflow_edge WHERE parent_node_id = @ctl AND branch_kind = N'BODY' ORDER BY child_order ASC;

    EXEC dbo.wf_engine_activate
        @workflow_instance_id = @inst,
        @workflow_node_id = @wbody,
        @parent_node_execution_id = @while_execution_id,
        @iteration_no = @iter + 1,
        @sequence_index = NULL,
        @parallel_index = NULL;
END;
GO

CREATE OR ALTER PROCEDURE dbo.wf_engine_on_action_complete
    @action_execution_id BIGINT,
    @result_code INT,
    @output_json NVARCHAR(MAX) NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @inst BIGINT;
    DECLARE @wn BIGINT;
    DECLARE @parent BIGINT;

    SELECT @inst = workflow_instance_id, @wn = workflow_node_id, @parent = parent_node_execution_id
    FROM dbo.node_execution WHERE id = @action_execution_id;

    IF @result_code < 0
    BEGIN
        UPDATE dbo.node_execution
        SET status = N'FAILED',
            result_code = @result_code,
            output_json = @output_json,
            ended_at_utc = SYSUTCDATETIME(),
            engine_error_code = @result_code
        WHERE id = @action_execution_id;

        DELETE FROM dbo.task_lease WHERE node_execution_id = @action_execution_id;

        UPDATE dbo.workflow_instance
        SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME()
        WHERE id = @inst;

        RETURN;
    END

    UPDATE dbo.node_execution
    SET status = N'SUCCEEDED',
        result_code = @result_code,
        output_json = @output_json,
        ended_at_utc = SYSUTCDATETIME()
    WHERE id = @action_execution_id;

    DELETE FROM dbo.task_lease WHERE node_execution_id = @action_execution_id;

    IF @parent IS NULL
    BEGIN
        UPDATE dbo.workflow_instance SET status = N'COMPLETED', completed_at_utc = SYSUTCDATETIME() WHERE id = @inst;
        RETURN;
    END

    DECLARE @ptype VARCHAR(32);
    SELECT @ptype = wn.node_type
    FROM dbo.node_execution AS ne
    INNER JOIN dbo.workflow_node AS wn ON wn.id = ne.workflow_node_id
    WHERE ne.id = @parent;

    IF @ptype = N'SEQUENCE'
        EXEC dbo.wf_sequence_continue @sequence_execution_id = @parent;

    ELSE IF @ptype = N'PARALLEL'
        EXEC dbo.wf_parallel_continue @parallel_execution_id = @parent;

    ELSE IF @ptype IN (N'IF', N'SWITCH')
    BEGIN
        UPDATE dbo.node_execution SET status = N'SUCCEEDED', ended_at_utc = SYSUTCDATETIME() WHERE id = @parent;
        EXEC dbo.wf_engine_on_composite_complete @node_execution_id = @parent;
    END

    ELSE IF @ptype = N'REPEAT'
        EXEC dbo.wf_repeat_continue @repeat_execution_id = @parent;

    ELSE IF @ptype = N'WHILE'
        EXEC dbo.wf_while_continue @while_execution_id = @parent;
END;
GO

CREATE OR ALTER PROCEDURE dbo.sp_start_workflow_instance
    @workflow_instance_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @vid BIGINT;
    DECLARE @root BIGINT;

    SELECT @vid = workflow_version_id FROM dbo.workflow_instance WHERE id = @workflow_instance_id;
    SELECT @root = root_node_id FROM dbo.workflow_version WHERE id = @vid;

    IF @root IS NULL
        THROW 50001, N'Workflow version has no root_node_id.', 1;

    UPDATE dbo.workflow_instance
    SET status = N'RUNNING', started_at_utc = SYSUTCDATETIME()
    WHERE id = @workflow_instance_id;

    EXEC dbo.wf_engine_activate
        @workflow_instance_id = @workflow_instance_id,
        @workflow_node_id = @root,
        @parent_node_execution_id = NULL,
        @iteration_no = 0,
        @sequence_index = NULL,
        @parallel_index = NULL;
END;
GO

CREATE OR ALTER PROCEDURE dbo.sp_worker_request_task
    @worker_id NVARCHAR(128),
    @capability NVARCHAR(128) NULL,
    @max_lease_seconds INT = 300
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @now DATETIME2(7) = SYSUTCDATETIME();
    DECLARE @lease_end DATETIME2(7) = DATEADD(SECOND, @max_lease_seconds, @now);
    DECLARE @wid NVARCHAR(128) = NULLIF(LTRIM(RTRIM(@worker_id)), N'');

    IF @wid IS NULL
        THROW 50002, N'worker_id is required.', 1;

    BEGIN TRANSACTION;

    DECLARE @picked_ids TABLE (id BIGINT);

    ;WITH cte AS (
        SELECT TOP (1) ne.id
        FROM dbo.node_execution AS ne WITH (ROWLOCK, READPAST, UPDLOCK)
        INNER JOIN dbo.workflow_node AS wn ON wn.id = ne.workflow_node_id
        INNER JOIN dbo.workflow_action AS wa ON wa.id = wn.workflow_action_id
        INNER JOIN dbo.workflow_instance AS wi ON wi.id = ne.workflow_instance_id
        WHERE ne.status = N'READY'
          AND wn.node_type = N'ACTION'
          AND wi.status = N'RUNNING'
          AND (ne.available_at_utc IS NULL OR ne.available_at_utc <= @now)
          AND (@capability IS NULL OR wa.capability = @capability OR wa.capability IS NULL)
        ORDER BY ne.available_at_utc ASC, ne.id ASC
    )
    UPDATE ne
    SET status = N'RUNNING',
        started_at_utc = @now
    OUTPUT inserted.id INTO @picked_ids(id)
    FROM dbo.node_execution AS ne
    INNER JOIN cte ON cte.id = ne.id;

    DECLARE @picked BIGINT;
    SELECT @picked = id FROM @picked_ids;

    IF @picked IS NULL
    BEGIN
        ROLLBACK TRANSACTION;
        RETURN;
    END

    ;MERGE dbo.task_lease AS t
    USING (SELECT @picked AS node_execution_id) AS s ON (t.node_execution_id = s.node_execution_id)
    WHEN MATCHED THEN
        UPDATE SET worker_id = @wid, lease_expires_at_utc = @lease_end, heartbeat_at_utc = @now
    WHEN NOT MATCHED THEN
        INSERT (node_execution_id, worker_id, lease_expires_at_utc, heartbeat_at_utc)
        VALUES (@picked, @wid, @lease_end, @now);

    COMMIT TRANSACTION;

    SELECT
        ne.id AS node_execution_id,
        ne.workflow_instance_id,
        wn.node_key,
        wa.action_name,
        wa.capability,
        ne.attempt_no,
        ne.input_json,
        ne.iteration_no
    FROM dbo.node_execution AS ne
    INNER JOIN dbo.workflow_node AS wn ON wn.id = ne.workflow_node_id
    INNER JOIN dbo.workflow_action AS wa ON wa.id = wn.workflow_action_id
    WHERE ne.id = @picked;
END;
GO

CREATE OR ALTER PROCEDURE dbo.sp_worker_submit_result
    @node_execution_id BIGINT,
    @worker_id NVARCHAR(128),
    @result_code INT,
    @output_json NVARCHAR(MAX) NULL,
    @accepted BIT OUTPUT,
    @instance_status VARCHAR(32) OUTPUT,
    @next_ready_count INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    SET @accepted = 0;
    SET @next_ready_count = 0;
    SET @instance_status = NULL;

    DECLARE @wid NVARCHAR(128) = NULLIF(LTRIM(RTRIM(@worker_id)), N'');
    IF @wid IS NULL THROW 50002, N'worker_id is required.', 1;

    BEGIN TRANSACTION;

    DECLARE @lease_worker NVARCHAR(128);
    SELECT @lease_worker = worker_id FROM dbo.task_lease WITH (UPDLOCK, HOLDLOCK) WHERE node_execution_id = @node_execution_id;

    IF @lease_worker IS NULL OR @lease_worker <> @wid
    BEGIN
        ROLLBACK TRANSACTION;
        RETURN;
    END

    DECLARE @cur_status VARCHAR(32);
    SELECT @cur_status = status FROM dbo.node_execution WITH (UPDLOCK, HOLDLOCK) WHERE id = @node_execution_id;

    IF @cur_status <> N'RUNNING'
    BEGIN
        ROLLBACK TRANSACTION;
        RETURN;
    END

    EXEC dbo.wf_engine_on_action_complete
        @action_execution_id = @node_execution_id,
        @result_code = @result_code,
        @output_json = @output_json;

    SET @accepted = 1;

    SELECT @instance_status = status FROM dbo.workflow_instance WHERE id = (SELECT workflow_instance_id FROM dbo.node_execution WHERE id = @node_execution_id);

    SELECT @next_ready_count = COUNT(*)
    FROM dbo.node_execution
    WHERE workflow_instance_id = (SELECT workflow_instance_id FROM dbo.node_execution WHERE id = @node_execution_id)
      AND status = N'READY';

    COMMIT TRANSACTION;
END;
GO

CREATE OR ALTER PROCEDURE dbo.sp_worker_heartbeat
    @node_execution_id BIGINT,
    @worker_id NVARCHAR(128),
    @extend_seconds INT = 300
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @wid NVARCHAR(128) = NULLIF(LTRIM(RTRIM(@worker_id)), N'');
    IF @wid IS NULL THROW 50002, N'worker_id is required.', 1;

    DECLARE @now DATETIME2(7) = SYSUTCDATETIME();

    UPDATE tl
    SET lease_expires_at_utc = DATEADD(SECOND, @extend_seconds, @now),
        heartbeat_at_utc = @now
    FROM dbo.task_lease AS tl
    WHERE tl.node_execution_id = @node_execution_id AND tl.worker_id = @wid;

    SELECT @@ROWCOUNT AS rows_updated;
END;
GO

CREATE OR ALTER PROCEDURE dbo.sp_worker_fail_task
    @node_execution_id BIGINT,
    @worker_id NVARCHAR(128),
    @error_code INT,
    @error_message NVARCHAR(1024) NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @wid NVARCHAR(128) = NULLIF(LTRIM(RTRIM(@worker_id)), N'');
    IF @wid IS NULL THROW 50002, N'worker_id is required.', 1;

    IF NOT EXISTS (
        SELECT 1 FROM dbo.task_lease WHERE node_execution_id = @node_execution_id AND worker_id = @wid
    )
        RETURN;

    UPDATE dbo.node_execution
    SET status = N'FAILED',
        engine_error_code = @error_code,
        engine_error_message = @error_message,
        ended_at_utc = SYSUTCDATETIME()
    WHERE id = @node_execution_id AND status = N'RUNNING';

    DELETE FROM dbo.task_lease WHERE node_execution_id = @node_execution_id;

    UPDATE dbo.workflow_instance
    SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME()
    WHERE id = (SELECT workflow_instance_id FROM dbo.node_execution WHERE id = @node_execution_id);
END;
GO
