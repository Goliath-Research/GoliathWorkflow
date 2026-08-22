/*
  MethylPipeline wf schema - SQL branch parity with Delphi scope semantics.

  Purpose:
  - Make IF/SWITCH/WHILE resolve from scope variables first (condition_var/switch_var),
    then fall back to *_ref_node_key task result behavior.

  Prerequisite:
  - wf_scope_readpath.sql (for wf.wf_get_scope_variable_int helper)
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

CREATE OR ALTER PROCEDURE wf.wf_while_continue
    @while_execution_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @inst BIGINT;
    DECLARE @ctl BIGINT;
    DECLARE @cvar NVARCHAR(128);
    DECLARE @wcref NVARCHAR(128);
    DECLARE @wcond INT;

    SELECT @inst = workflow_instance_id, @ctl = workflow_node_id
    FROM wf.node_execution
    WHERE id = @while_execution_id;

    SELECT @cvar = condition_var, @wcref = condition_ref_node_key
    FROM wf.workflow_node
    WHERE id = @ctl;

    IF ISNULL(LTRIM(RTRIM(@cvar)), N'') <> N''
        SET @wcond = wf.wf_get_scope_variable_int(@inst, @while_execution_id, @cvar);

    IF @wcond IS NULL AND ISNULL(LTRIM(RTRIM(@wcref)), N'') <> N''
        SET @wcond = wf.wf_try_task_result_code(@inst, @wcref);

    IF @wcond IS NULL OR @wcond = 0
    BEGIN
        UPDATE wf.node_execution
        SET status = N'SUCCEEDED', ended_at_utc = SYSUTCDATETIME()
        WHERE id = @while_execution_id;
        EXEC wf.wf_engine_on_composite_complete @node_execution_id = @while_execution_id;
        RETURN;
    END

    DECLARE @iter INT = ISNULL(
        (
            SELECT MAX(iteration_no)
            FROM wf.node_execution
            WHERE parent_node_execution_id = @while_execution_id
              AND workflow_node_id = (
                  SELECT TOP (1) child_node_id
                  FROM wf.workflow_edge
                  WHERE parent_node_id = @ctl AND branch_kind = N'BODY'
                  ORDER BY child_order ASC
              )
        ),
        0
    );

    DECLARE @wbody BIGINT;
    SELECT TOP (1) @wbody = child_node_id
    FROM wf.workflow_edge
    WHERE parent_node_id = @ctl AND branch_kind = N'BODY'
    ORDER BY child_order ASC;

    SET @iter = @iter + 1;
    EXEC wf.wf_engine_activate
        @workflow_instance_id = @inst,
        @workflow_node_id = @wbody,
        @parent_node_execution_id = @while_execution_id,
        @iteration_no = @iter,
        @sequence_index = NULL,
        @parallel_index = NULL;
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_engine_activate
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

    IF NOT EXISTS (
        SELECT 1 FROM wf.workflow_instance
        WHERE id = @workflow_instance_id AND status = N'RUNNING'
    )
        RETURN;

    DECLARE @node_type VARCHAR(32);
    DECLARE @version_id BIGINT;
    DECLARE @node_key NVARCHAR(128);

    SELECT @node_type = node_type, @version_id = workflow_version_id, @node_key = node_key
    FROM wf.workflow_node
    WHERE id = @workflow_node_id;

    IF @node_type IS NULL RETURN;

    IF @node_type = N'ACTION'
    BEGIN
        DECLARE @ne_id BIGINT;
        INSERT INTO wf.node_execution (
            workflow_instance_id, workflow_node_id, status, attempt_no,
            parent_node_execution_id, iteration_no, available_at_utc
        )
        VALUES (
            @workflow_instance_id, @workflow_node_id, N'READY', 1,
            @parent_node_execution_id, @iteration_no, SYSUTCDATETIME()
        );
        SET @ne_id = SCOPE_IDENTITY();

        EXEC wf.wf_seed_execution_context
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

        EXEC wf.wf_build_input_json_for_action
            @node_execution_id = @ne_id,
            @workflow_instance_id = @workflow_instance_id,
            @workflow_node_id = @workflow_node_id,
            @final_json = @fj OUTPUT,
            @failed = @failed OUTPUT,
            @fail_code = @fc OUTPUT,
            @fail_msg = @fm OUTPUT;

        IF @failed = 1
        BEGIN
            UPDATE wf.node_execution
            SET status = N'FAILED',
                engine_error_code = @fc,
                engine_error_message = @fm,
                ended_at_utc = SYSUTCDATETIME()
            WHERE id = @ne_id;

            UPDATE wf.workflow_instance
            SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME()
            WHERE id = @workflow_instance_id;
            RETURN;
        END

        UPDATE wf.node_execution
        SET input_json = CAST(@fj AS json)
        WHERE id = @ne_id;
        RETURN;
    END

    DECLARE @pex BIGINT;
    INSERT INTO wf.node_execution (
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
        FROM wf.workflow_edge
        WHERE parent_node_id = @workflow_node_id
        ORDER BY child_order ASC;

        IF @child1 IS NULL
        BEGIN
            UPDATE wf.node_execution SET status = N'SUCCEEDED', ended_at_utc = SYSUTCDATETIME() WHERE id = @pex;
            EXEC wf.wf_engine_on_composite_complete @node_execution_id = @pex;
            RETURN;
        END

        DECLARE @ord INT = 0;
        SELECT TOP (1) @ord = child_order
        FROM wf.workflow_edge
        WHERE parent_node_id = @workflow_node_id
        ORDER BY child_order ASC;

        EXEC wf.wf_engine_activate
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
            FROM wf.workflow_edge
            WHERE parent_node_id = @workflow_node_id
            ORDER BY child_order ASC;

        OPEN pc;
        FETCH NEXT FROM pc INTO @cid;
        WHILE @@FETCH_STATUS = 0
        BEGIN
            EXEC wf.wf_engine_activate
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
        DECLARE @cvar NVARCHAR(128);
        DECLARE @cond INT;
        DECLARE @scope_for_cond BIGINT = ISNULL(@parent_node_execution_id, 0);
        DECLARE @pick VARCHAR(32);

        SELECT @cref = condition_ref_node_key, @cvar = condition_var
        FROM wf.workflow_node
        WHERE id = @workflow_node_id;

        IF ISNULL(LTRIM(RTRIM(@cvar)), N'') <> N''
            SET @cond = wf.wf_get_scope_variable_int(@workflow_instance_id, @scope_for_cond, @cvar);
        IF @cond IS NULL AND ISNULL(LTRIM(RTRIM(@cref)), N'') <> N''
            SET @cond = wf.wf_try_task_result_code(@workflow_instance_id, @cref);

        SET @pick = CASE WHEN @cond IS NOT NULL AND @cond <> 0 THEN N'THEN' ELSE N'ELSE' END;

        DECLARE @ifchild BIGINT;
        SELECT TOP (1) @ifchild = child_node_id
        FROM wf.workflow_edge
        WHERE parent_node_id = @workflow_node_id AND branch_kind = @pick
        ORDER BY child_order ASC;

        IF @ifchild IS NULL
        BEGIN
            UPDATE wf.node_execution SET status = N'FAILED', engine_error_code = 10003, engine_error_message = N'Missing IF branch.', ended_at_utc = SYSUTCDATETIME() WHERE id = @pex;
            UPDATE wf.workflow_instance SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME() WHERE id = @workflow_instance_id;
            RETURN;
        END

        EXEC wf.wf_engine_activate
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
        DECLARE @svar NVARCHAR(128);
        DECLARE @sv INT;
        DECLARE @scope_for_switch BIGINT = ISNULL(@parent_node_execution_id, 0);

        SELECT @sref = switch_ref_node_key, @svar = switch_var
        FROM wf.workflow_node
        WHERE id = @workflow_node_id;

        IF ISNULL(LTRIM(RTRIM(@svar)), N'') <> N''
            SET @sv = wf.wf_get_scope_variable_int(@workflow_instance_id, @scope_for_switch, @svar);
        IF @sv IS NULL AND ISNULL(LTRIM(RTRIM(@sref)), N'') <> N''
            SET @sv = wf.wf_try_task_result_code(@workflow_instance_id, @sref);

        DECLARE @swchild BIGINT;
        SELECT TOP (1) @swchild = child_node_id
        FROM wf.workflow_edge
        WHERE parent_node_id = @workflow_node_id AND branch_kind = N'CASE' AND switch_case_value = @sv
        ORDER BY child_order ASC;

        IF @swchild IS NULL
            SELECT TOP (1) @swchild = child_node_id
            FROM wf.workflow_edge
            WHERE parent_node_id = @workflow_node_id AND branch_kind = N'DEFAULT'
            ORDER BY child_order ASC;

        IF @swchild IS NULL
        BEGIN
            UPDATE wf.node_execution SET status = N'FAILED', engine_error_code = 10004, engine_error_message = N'Missing SWITCH case.', ended_at_utc = SYSUTCDATETIME() WHERE id = @pex;
            UPDATE wf.workflow_instance SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME() WHERE id = @workflow_instance_id;
            RETURN;
        END

        EXEC wf.wf_engine_activate
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
        SELECT @rcount = repeat_count FROM wf.workflow_node WHERE id = @workflow_node_id;
        IF @rcount IS NULL OR @rcount < 1 SET @rcount = 1;

        INSERT INTO wf.loop_state (workflow_instance_id, control_node_id, scope_node_execution_id, current_iteration, repeat_target_count)
        VALUES (@workflow_instance_id, @workflow_node_id, @pex, 0, @rcount);

        DECLARE @body BIGINT;
        SELECT TOP (1) @body = child_node_id
        FROM wf.workflow_edge
        WHERE parent_node_id = @workflow_node_id AND branch_kind = N'BODY'
        ORDER BY child_order ASC;

        IF @body IS NULL
        BEGIN
            UPDATE wf.node_execution SET status = N'FAILED', engine_error_code = 10005, ended_at_utc = SYSUTCDATETIME() WHERE id = @pex;
            UPDATE wf.workflow_instance SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME() WHERE id = @workflow_instance_id;
            RETURN;
        END

        EXEC wf.wf_engine_activate
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
        DECLARE @wcref NVARCHAR(128);
        DECLARE @wcvar NVARCHAR(128);
        DECLARE @wcond INT;
        DECLARE @scope_for_while BIGINT = ISNULL(@parent_node_execution_id, 0);

        SELECT TOP (1) @wbody = child_node_id
        FROM wf.workflow_edge
        WHERE parent_node_id = @workflow_node_id AND branch_kind = N'BODY'
        ORDER BY child_order ASC;

        IF @wbody IS NULL
        BEGIN
            UPDATE wf.node_execution SET status = N'FAILED', engine_error_code = 10006, ended_at_utc = SYSUTCDATETIME() WHERE id = @pex;
            UPDATE wf.workflow_instance SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME() WHERE id = @workflow_instance_id;
            RETURN;
        END

        SELECT @wcref = condition_ref_node_key, @wcvar = condition_var
        FROM wf.workflow_node
        WHERE id = @workflow_node_id;

        IF ISNULL(LTRIM(RTRIM(@wcvar)), N'') <> N''
            SET @wcond = wf.wf_get_scope_variable_int(@workflow_instance_id, @scope_for_while, @wcvar);
        IF @wcond IS NULL AND ISNULL(LTRIM(RTRIM(@wcref)), N'') <> N''
            SET @wcond = wf.wf_try_task_result_code(@workflow_instance_id, @wcref);

        IF @wcond IS NULL OR @wcond = 0
        BEGIN
            UPDATE wf.node_execution SET status = N'SUCCEEDED', ended_at_utc = SYSUTCDATETIME() WHERE id = @pex;
            EXEC wf.wf_engine_on_composite_complete @node_execution_id = @pex;
            RETURN;
        END

        EXEC wf.wf_engine_activate
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

