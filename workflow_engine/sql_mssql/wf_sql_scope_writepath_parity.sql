/*
  MethylPipeline wf schema - SQL write-path scope parity with Delphi WfEngine.Scope.

  Implements:
  - wf.wf_set_scope_variable          UPSERT into wf.scope_variable
  - wf.wf_open_scope                  Copy parent scope + apply node_scope_default
  - wf.wf_scope_write_exec_id         Resolve scope root for ACTION output bindings
  - wf.wf_apply_output_bindings       variable_output_binding -> scope_variable
  - wf.wf_engine_on_action_complete   extended to call wf_apply_output_bindings
  - wf.wf_engine_activate             extended: OpenScope on composites; scope copy for ACTION under PARALLEL

  Prerequisites:
  - Base wf schema (MethylPipeline.sql)
  - wf_scope_variables.sql
  - wf_scope_readpath.sql
  - wf_sql_runtime_parity.sql
  - wf_sql_branch_parity.sql
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'wf.scope_variable', N'U') IS NULL
   OR OBJECT_ID(N'wf.variable_output_binding', N'U') IS NULL
   OR OBJECT_ID(N'wf.wf_resolve_placeholders', N'P') IS NULL
BEGIN
    RAISERROR(N'Prerequisite missing: deploy wf_scope_variables, wf_scope_readpath, wf_sql_runtime_parity, wf_sql_branch_parity first.', 16, 1);
    RETURN;
END
GO

CREATE OR ALTER PROCEDURE wf.wf_set_scope_variable
    @workflow_instance_id BIGINT,
    @scope_node_execution_id BIGINT,
    @var_name NVARCHAR(128),
    @value_json json
AS
BEGIN
    SET NOCOUNT ON;

    IF @var_name IS NULL OR LTRIM(RTRIM(@var_name)) = N''
        RETURN;

    MERGE wf.scope_variable AS t
    USING (
        SELECT
            @workflow_instance_id AS workflow_instance_id,
            ISNULL(@scope_node_execution_id, 0) AS scope_node_execution_id,
            @var_name AS var_name,
            @value_json AS value_json
    ) AS s
    ON t.workflow_instance_id = s.workflow_instance_id
       AND t.scope_node_execution_id = s.scope_node_execution_id
       AND t.var_name = s.var_name
    WHEN MATCHED THEN
        UPDATE SET
            value_json = s.value_json,
            updated_at_utc = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN
        INSERT (workflow_instance_id, scope_node_execution_id, var_name, value_json)
        VALUES (s.workflow_instance_id, s.scope_node_execution_id, s.var_name, s.value_json);
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_open_scope
    @workflow_instance_id BIGINT,
    @from_scope_exec_id BIGINT,
    @to_scope_exec_id BIGINT,
    @workflow_node_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @from_scope BIGINT = ISNULL(@from_scope_exec_id, 0);
    DECLARE @to_scope BIGINT = ISNULL(@to_scope_exec_id, 0);

    IF @from_scope <> @to_scope
    BEGIN
        INSERT INTO wf.scope_variable (workflow_instance_id, scope_node_execution_id, var_name, value_json)
        SELECT
            sv.workflow_instance_id,
            @to_scope,
            sv.var_name,
            sv.value_json
        FROM wf.scope_variable AS sv
        WHERE sv.workflow_instance_id = @workflow_instance_id
          AND sv.scope_node_execution_id = @from_scope
          AND NOT EXISTS (
              SELECT 1
              FROM wf.scope_variable AS x
              WHERE x.workflow_instance_id = @workflow_instance_id
                AND x.scope_node_execution_id = @to_scope
                AND x.var_name = sv.var_name
          );
    END

    DECLARE @def_var NVARCHAR(128);
    DECLARE @def_expr NVARCHAR(1024);
    DECLARE @resolved NVARCHAR(MAX);
    DECLARE @failed BIT;
    DECLARE @fc INT;
    DECLARE @fm NVARCHAR(1024);

    DECLARE def_cur CURSOR LOCAL FAST_FORWARD FOR
        SELECT var_name, default_expr
        FROM wf.node_scope_default
        WHERE workflow_node_id = @workflow_node_id;

    OPEN def_cur;
    FETCH NEXT FROM def_cur INTO @def_var, @def_expr;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        EXEC wf.wf_resolve_placeholders
            @text = @def_expr,
            @node_execution_id = @to_scope,
            @workflow_instance_id = @workflow_instance_id,
            @resolved = @resolved OUTPUT,
            @failed = @failed OUTPUT,
            @fail_code = @fc OUTPUT,
            @fail_msg = @fm OUTPUT;

        IF @failed = 0
            EXEC wf.wf_set_scope_variable
                @workflow_instance_id = @workflow_instance_id,
                @scope_node_execution_id = @to_scope,
                @var_name = @def_var,
                @value_json = @resolved;

        FETCH NEXT FROM def_cur INTO @def_var, @def_expr;
    END
    CLOSE def_cur;
    DEALLOCATE def_cur;
END;
GO

CREATE OR ALTER FUNCTION wf.wf_scope_write_exec_id
(
    @action_execution_id BIGINT,
    @parent_node_execution_id BIGINT NULL
)
RETURNS BIGINT
AS
BEGIN
    IF @parent_node_execution_id IS NULL
        RETURN 0;

    DECLARE @parent_node_type VARCHAR(32);
    SELECT @parent_node_type = wn.node_type
    FROM wf.node_execution AS ne
    INNER JOIN wf.workflow_node AS wn ON wn.id = ne.workflow_node_id
    WHERE ne.id = @parent_node_execution_id;

    IF @parent_node_type = N'PARALLEL'
        RETURN @action_execution_id;

    RETURN @parent_node_execution_id;
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_apply_output_bindings
    @action_execution_id BIGINT,
    @result_code INT,
    @output_json NVARCHAR(MAX) NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @inst BIGINT;
    DECLARE @wn BIGINT;
    DECLARE @parent BIGINT;
    DECLARE @scope_exec BIGINT;
    DECLARE @oj NVARCHAR(MAX) = @output_json;

    SELECT @inst = workflow_instance_id,
           @wn = workflow_node_id,
           @parent = parent_node_execution_id
    FROM wf.node_execution
    WHERE id = @action_execution_id;

    IF @wn IS NULL
        RETURN;

    SET @scope_exec = wf.wf_scope_write_exec_id(@action_execution_id, @parent);

    DECLARE @var_name NVARCHAR(128);
    DECLARE @source_kind VARCHAR(32);
    DECLARE @source_path NVARCHAR(1024);
    DECLARE @frag NVARCHAR(MAX);
    DECLARE @jp NVARCHAR(1024);
    DECLARE @bi BIGINT;

    DECLARE bind_cur CURSOR LOCAL FAST_FORWARD FOR
        SELECT var_name, source_kind, source_json_path
        FROM wf.variable_output_binding
        WHERE workflow_node_id = @wn;

    OPEN bind_cur;
    FETCH NEXT FROM bind_cur INTO @var_name, @source_kind, @source_path;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        IF @source_kind = N'result_code'
        BEGIN
            SET @frag = CAST(ISNULL(@result_code, 0) AS NVARCHAR(32));
        END
        ELSE IF @source_kind = N'output_path'
        BEGIN
            IF @oj IS NULL OR LTRIM(RTRIM(@oj)) = N'' OR ISJSON(@oj) <> 1
                SET @frag = N'null';
            ELSE
            BEGIN
                SET @jp = @source_path;
                IF @jp IS NULL OR LTRIM(RTRIM(@jp)) = N''
                    SET @frag = @oj;
                ELSE
                BEGIN
                    IF LEFT(LTRIM(@jp), 1) <> N'$'
                        SET @jp = N'$.' + @jp;
                    SET @frag = JSON_QUERY(@oj, @jp);
                    IF @frag IS NULL
                        SET @frag = JSON_VALUE(@oj, @jp);
                    IF @frag IS NULL
                        SET @frag = N'null';
                    ELSE IF ISJSON(@frag) = 0
                    BEGIN
                        SET @bi = TRY_CONVERT(BIGINT, @frag);
                        IF @bi IS NOT NULL AND CAST(@bi AS NVARCHAR(50)) = LTRIM(RTRIM(@frag))
                            SET @frag = CAST(@bi AS NVARCHAR(50));
                        ELSE
                            SET @frag = wf.wf_json_fragment_from_string(@frag);
                    END
                END
            END
        END
        ELSE
            SET @frag = N'null';

        EXEC wf.wf_set_scope_variable
            @workflow_instance_id = @inst,
            @scope_node_execution_id = @scope_exec,
            @var_name = @var_name,
            @value_json = @frag;

        FETCH NEXT FROM bind_cur INTO @var_name, @source_kind, @source_path;
    END
    CLOSE bind_cur;
    DEALLOCATE bind_cur;
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_engine_on_action_complete
    @action_execution_id BIGINT,
    @result_code INT,
    @output_json NVARCHAR(MAX) NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @inst BIGINT;
    DECLARE @wn BIGINT;
    DECLARE @parent BIGINT;
    DECLARE @oj NVARCHAR(MAX) = CASE
        WHEN @output_json IS NULL THEN NULL
        WHEN LTRIM(RTRIM(@output_json)) = N'' THEN NULL
        ELSE @output_json
    END;

    SELECT @inst = workflow_instance_id, @wn = workflow_node_id, @parent = parent_node_execution_id
    FROM wf.node_execution WHERE id = @action_execution_id;

    IF @result_code < 0
    BEGIN
        UPDATE wf.node_execution
        SET status = N'FAILED',
            result_code = @result_code,
            output_json = @oj,
            ended_at_utc = SYSUTCDATETIME(),
            engine_error_code = @result_code
        WHERE id = @action_execution_id;

        DELETE FROM wf.task_lease WHERE node_execution_id = @action_execution_id;

        -- Node failed; leave instance RUNNING so sibling FOREACH tasks remain claimable.
        RETURN;
    END

    UPDATE wf.node_execution
    SET status = N'SUCCEEDED',
        result_code = @result_code,
        output_json = @oj,
        ended_at_utc = SYSUTCDATETIME()
    WHERE id = @action_execution_id;

    DELETE FROM wf.task_lease WHERE node_execution_id = @action_execution_id;

    -- Bind action outputs into FOREACH/sample scope (qcPass, qcPath, …).
    EXEC wf.wf_apply_output_bindings
        @action_execution_id = @action_execution_id,
        @result_code = @result_code,
        @output_json = @oj;

    IF @parent IS NULL
    BEGIN
        UPDATE wf.workflow_instance SET status = N'COMPLETED', completed_at_utc = SYSUTCDATETIME() WHERE id = @inst;
        RETURN;
    END

    DECLARE @ptype VARCHAR(32);
    SELECT @ptype = wn.node_type
    FROM wf.node_execution AS ne
    INNER JOIN wf.workflow_node AS wn ON wn.id = ne.workflow_node_id
    WHERE ne.id = @parent;

    IF @ptype = N'SEQUENCE'
        EXEC wf.wf_sequence_continue @sequence_execution_id = @parent;

    ELSE IF @ptype = N'PARALLEL'
        EXEC wf.wf_parallel_continue @parallel_execution_id = @parent;

    ELSE IF @ptype IN (N'IF', N'SWITCH')
    BEGIN
        UPDATE wf.node_execution SET status = N'SUCCEEDED', ended_at_utc = SYSUTCDATETIME() WHERE id = @parent;
        EXEC wf.wf_engine_on_composite_complete @node_execution_id = @parent;
    END

    ELSE IF @ptype = N'REPEAT'
        EXEC wf.wf_repeat_continue @repeat_execution_id = @parent;

    ELSE IF @ptype = N'WHILE'
        EXEC wf.wf_while_continue @while_execution_id = @parent;

    ELSE IF @ptype = N'FOREACH'
        EXEC wf.wf_foreach_route_continue @foreach_execution_id = @parent;
END;
GO

/*
  Full wf_engine_activate with OpenScope on composite nodes and PARALLEL child scope copy.
  Replaces wf_sql_branch_parity version when this script is deployed.
  NOTE: Prefer deploying wf_engine_activate from wf_sql_foreach_support.sql on Azure
  (FOREACH + condition_var). This copy is the OpenScope/PARALLEL write-path baseline.
*/
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

        IF @parent_node_execution_id IS NOT NULL
        BEGIN
            DECLARE @parent_ntype VARCHAR(32);
            SELECT @parent_ntype = wn.node_type
            FROM wf.node_execution AS ne
            INNER JOIN wf.workflow_node AS wn ON wn.id = ne.workflow_node_id
            WHERE ne.id = @parent_node_execution_id;

            IF @parent_ntype = N'PARALLEL'
            BEGIN
                INSERT INTO wf.scope_variable (workflow_instance_id, scope_node_execution_id, var_name, value_json)
                SELECT
                    sv.workflow_instance_id,
                    @ne_id,
                    sv.var_name,
                    sv.value_json
                FROM wf.scope_variable AS sv
                WHERE sv.workflow_instance_id = @workflow_instance_id
                  AND sv.scope_node_execution_id = @parent_node_execution_id;
            END
        END

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

    DECLARE @scope int = ISNULL(@parent_node_execution_id, 0);
    EXEC wf.wf_open_scope
        @workflow_instance_id = @workflow_instance_id,
        @from_scope_exec_id = @scope,
        @to_scope_exec_id = @pex,
        @workflow_node_id = @workflow_node_id;

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
        DECLARE @scope_for_cond BIGINT = @pex;
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
        DECLARE @scope_for_switch BIGINT = @pex;

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
        DECLARE @scope_for_while BIGINT = @pex;

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

PRINT N'wf_sql_scope_writepath_parity.sql applied.';
GO
