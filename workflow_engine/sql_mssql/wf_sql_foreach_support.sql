/*
  MethylPipeline wf schema - FOREACH control-flow node (generic runtime).

  Adds:
  - workflow_node columns: foreach_collection_var, foreach_item_var, foreach_index_var, foreach_parallel
  - CK_wn_node_type extended with FOREACH
  - wf.wf_json_array_length
  - wf.wf_foreach_bind_iteration
  - wf.wf_foreach_continue / wf.wf_foreach_parallel_continue
  - wf.wf_foreach_route_continue (sequential/parallel dispatch; called by base engine procs)
  - wf.wf_engine_continue_parent (FOREACH routing)
  - wf.wf_engine_on_action_complete (FOREACH parent on direct BODY action)
  - wf.wf_engine_activate (FOREACH activation + BODY item bind hook)
  - wf.wf_resolve_token (var.name[n], ctx.item, ctx.index)

  Prerequisites:
  - Base wf schema, wf_scope_variables.sql, wf_scope_readpath.sql
  - wf_sql_runtime_parity.sql, wf_sql_branch_parity.sql, wf_sql_scope_writepath_parity.sql

  Deploy AFTER wf_sql_scope_writepath_parity.sql.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'wf.scope_variable', N'U') IS NULL
   OR OBJECT_ID(N'wf.wf_open_scope', N'P') IS NULL
BEGIN
    RAISERROR(N'Prerequisite missing: deploy wf_scope_variables and wf_sql_scope_writepath_parity first.', 16, 1);
    RETURN;
END
GO

IF COL_LENGTH('wf.workflow_node', 'foreach_collection_var') IS NULL
BEGIN
    ALTER TABLE wf.workflow_node ADD foreach_collection_var NVARCHAR(128) NULL;
END
GO

IF COL_LENGTH('wf.workflow_node', 'foreach_item_var') IS NULL
BEGIN
    ALTER TABLE wf.workflow_node ADD foreach_item_var NVARCHAR(128) NULL;
END
GO

IF COL_LENGTH('wf.workflow_node', 'foreach_index_var') IS NULL
BEGIN
    ALTER TABLE wf.workflow_node ADD foreach_index_var NVARCHAR(128) NULL;
END
GO

IF COL_LENGTH('wf.workflow_node', 'foreach_parallel') IS NULL
BEGIN
    ALTER TABLE wf.workflow_node ADD foreach_parallel BIT NOT NULL CONSTRAINT DF_wn_foreach_parallel DEFAULT (0);
END
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_wn_node_type' AND parent_object_id = OBJECT_ID(N'wf.workflow_node')
)
BEGIN
    ALTER TABLE wf.workflow_node DROP CONSTRAINT CK_wn_node_type;
END
GO

ALTER TABLE wf.workflow_node
  ADD CONSTRAINT CK_wn_node_type CHECK (
    [node_type] = N'ACTION' OR [node_type] = N'SEQUENCE' OR [node_type] = N'PARALLEL'
    OR [node_type] = N'IF' OR [node_type] = N'SWITCH' OR [node_type] = N'REPEAT'
    OR [node_type] = N'WHILE' OR [node_type] = N'FOREACH'
  );
GO

CREATE OR ALTER FUNCTION wf.wf_json_array_length(@json NVARCHAR(MAX))
RETURNS INT
AS
BEGIN
    IF @json IS NULL OR LTRIM(RTRIM(@json)) = N'' OR ISJSON(@json) <> 1
        RETURN NULL;

    IF LEFT(LTRIM(@json), 1) <> N'['
        RETURN NULL;

    RETURN (SELECT COUNT(*) FROM OPENJSON(@json));
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_foreach_bind_iteration
    @workflow_instance_id BIGINT,
    @scope_node_execution_id BIGINT,
    @collection_scope_exec_id BIGINT,
    @collection_var NVARCHAR(128),
    @item_var NVARCHAR(128),
    @index_var NVARCHAR(128),
    @zero_based_index INT
AS
BEGIN
    SET NOCOUNT ON;

    IF @collection_var IS NULL OR LTRIM(RTRIM(@collection_var)) = N''
        RETURN;

    IF @item_var IS NULL OR LTRIM(RTRIM(@item_var)) = N''
        SET @item_var = N'item';

    IF @index_var IS NULL OR LTRIM(RTRIM(@index_var)) = N''
        SET @index_var = N'index';

    DECLARE @coll NVARCHAR(MAX) = wf.wf_get_scope_variable_json(
        @workflow_instance_id, @collection_scope_exec_id, @collection_var);

    DECLARE @jp NVARCHAR(32) = CONCAT(N'$[', CAST(@zero_based_index AS NVARCHAR(32)), N']');
    DECLARE @elem NVARCHAR(MAX) = JSON_QUERY(@coll, @jp);

    IF @elem IS NULL
        SET @elem = JSON_VALUE(@coll, @jp);

    IF @elem IS NULL
        SET @elem = N'null';
    ELSE IF ISJSON(@elem) = 0
    BEGIN
        DECLARE @bi BIGINT = TRY_CONVERT(BIGINT, @elem);
        IF @bi IS NOT NULL AND CAST(@bi AS NVARCHAR(50)) = LTRIM(RTRIM(@elem))
            SET @elem = CAST(@bi AS NVARCHAR(50));
        ELSE
            SET @elem = wf.wf_json_fragment_from_string(@elem);
    END

    EXEC wf.wf_set_scope_variable
        @workflow_instance_id = @workflow_instance_id,
        @scope_node_execution_id = @scope_node_execution_id,
        @var_name = @item_var,
        @value_json = wf.wf_json_box(@elem);

    DECLARE @json_idx json = wf.wf_json_box(CAST(@zero_based_index AS nvarchar(32)));
    EXEC wf.wf_set_scope_variable
        @workflow_instance_id = @workflow_instance_id,
        @scope_node_execution_id = @scope_node_execution_id,
        @var_name = @index_var,
        @value_json = @json_idx;

    IF @elem IS NOT NULL AND LEFT(LTRIM(@elem), 1) = N'{'
    BEGIN
        DECLARE @fk NVARCHAR(128);
        DECLARE @fv NVARCHAR(MAX);
        DECLARE @ft INT;

        DECLARE fk CURSOR LOCAL FAST_FORWARD FOR
            SELECT [key], [value], [type] FROM OPENJSON(@elem);

        OPEN fk;
        FETCH NEXT FROM fk INTO @fk, @fv, @ft;
        WHILE @@FETCH_STATUS = 0
        BEGIN
            IF @fk IS NOT NULL AND @fk <> @item_var AND @fk <> @index_var
            BEGIN
                DECLARE @frag NVARCHAR(MAX);
                IF @ft IN (4, 5)
                    SET @frag = JSON_QUERY(@elem, CONCAT(N'$.', QUOTENAME(@fk, '"')));
                ELSE IF @ft = 1
                    SET @frag = wf.wf_json_fragment_from_string(@fv);
                ELSE IF @ft = 3
                    SET @frag = LOWER(@fv);
                ELSE IF @ft = 2
                    SET @frag = @fv;
                ELSE
                    SET @frag = ISNULL(@fv, N'null');

                EXEC wf.wf_set_scope_variable
                    @workflow_instance_id = @workflow_instance_id,
                    @scope_node_execution_id = @scope_node_execution_id,
                    @var_name = @fk,
                    @value_json = wf.wf_json_box(@frag);
            END
            FETCH NEXT FROM fk INTO @fk, @fv, @ft;
        END
        CLOSE fk;
        DEALLOCATE fk;
    END
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_try_bind_foreach_body
    @workflow_instance_id BIGINT,
    @workflow_node_id BIGINT,
    @parent_node_execution_id BIGINT,
    @scope_node_execution_id BIGINT,
    @iteration_no INT
AS
BEGIN
    SET NOCOUNT ON;

    IF @parent_node_execution_id IS NULL
        RETURN;

    DECLARE @parent_node_id BIGINT;
    DECLARE @parent_type VARCHAR(32);

    SELECT @parent_node_id = ne.workflow_node_id, @parent_type = wn.node_type
    FROM wf.node_execution AS ne
    INNER JOIN wf.workflow_node AS wn ON wn.id = ne.workflow_node_id
    WHERE ne.id = @parent_node_execution_id;

    IF @parent_type <> N'FOREACH'
        RETURN;

    IF NOT EXISTS (
        SELECT 1
        FROM wf.workflow_edge
        WHERE parent_node_id = @parent_node_id
          AND child_node_id = @workflow_node_id
          AND branch_kind = N'BODY'
    )
        RETURN;

    DECLARE @coll NVARCHAR(128);
    DECLARE @item NVARCHAR(128);
    DECLARE @idx NVARCHAR(128);

    SELECT
        @coll = foreach_collection_var,
        @item = foreach_item_var,
        @idx = foreach_index_var
    FROM wf.workflow_node
    WHERE id = @parent_node_id;

    DECLARE @zbi INT = CASE WHEN @iteration_no < 1 THEN 0 ELSE @iteration_no - 1 END;

    EXEC wf.wf_foreach_bind_iteration
        @workflow_instance_id = @workflow_instance_id,
        @scope_node_execution_id = @scope_node_execution_id,
        @collection_scope_exec_id = @parent_node_execution_id,
        @collection_var = @coll,
        @item_var = @item,
        @index_var = @idx,
        @zero_based_index = @zbi;
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_foreach_continue
    @foreach_execution_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @inst BIGINT;
    DECLARE @ctl BIGINT;
    DECLARE @ls BIGINT;
    DECLARE @cur INT;
    DECLARE @max INT;

    SELECT @inst = workflow_instance_id, @ctl = workflow_node_id
    FROM wf.node_execution WHERE id = @foreach_execution_id;

    SELECT TOP (1)
        @ls = id,
        @cur = current_iteration,
        @max = repeat_target_count
    FROM wf.loop_state
    WHERE scope_node_execution_id = @foreach_execution_id;

    IF @ls IS NULL
    BEGIN
        UPDATE wf.node_execution SET status = N'FAILED', engine_error_code = 10009, ended_at_utc = SYSUTCDATETIME() WHERE id = @foreach_execution_id;
        UPDATE wf.workflow_instance SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME() WHERE id = @inst;
        RETURN;
    END

    SET @cur += 1;
    UPDATE wf.loop_state SET current_iteration = @cur WHERE id = @ls;

    IF @cur >= @max
    BEGIN
        UPDATE wf.node_execution SET status = N'SUCCEEDED', ended_at_utc = SYSUTCDATETIME() WHERE id = @foreach_execution_id;
        EXEC wf.wf_engine_on_composite_complete @node_execution_id = @foreach_execution_id;
        RETURN;
    END

    DECLARE @body BIGINT;
    SELECT TOP (1) @body = child_node_id
    FROM wf.workflow_edge
    WHERE parent_node_id = @ctl AND branch_kind = N'BODY'
    ORDER BY child_order ASC;

    IF @body IS NULL
    BEGIN
        UPDATE wf.node_execution SET status = N'FAILED', engine_error_code = 10010, ended_at_utc = SYSUTCDATETIME() WHERE id = @foreach_execution_id;
        UPDATE wf.workflow_instance SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME() WHERE id = @inst;
        RETURN;
    END

    DECLARE @next_iter INT = @cur + 1;
    EXEC wf.wf_engine_activate
        @workflow_instance_id = @inst,
        @workflow_node_id = @body,
        @parent_node_execution_id = @foreach_execution_id,
        @iteration_no = @next_iter,
        @sequence_index = NULL,
        @parallel_index = NULL;
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_foreach_parallel_continue
    @foreach_execution_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @inst BIGINT;
    DECLARE @max INT;

    SELECT @inst = workflow_instance_id FROM wf.node_execution WHERE id = @foreach_execution_id;

    SELECT TOP (1) @max = repeat_target_count
    FROM wf.loop_state
    WHERE scope_node_execution_id = @foreach_execution_id;

    IF @max IS NULL
    BEGIN
        UPDATE wf.node_execution SET status = N'FAILED', engine_error_code = 10009, ended_at_utc = SYSUTCDATETIME() WHERE id = @foreach_execution_id;
        UPDATE wf.workflow_instance SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME() WHERE id = @inst;
        RETURN;
    END

    IF EXISTS (
        SELECT 1 FROM wf.node_execution
        WHERE parent_node_execution_id = @foreach_execution_id AND status = N'FAILED'
    )
    BEGIN
        UPDATE wf.node_execution SET status = N'FAILED', ended_at_utc = SYSUTCDATETIME() WHERE id = @foreach_execution_id;
        UPDATE wf.workflow_instance SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME() WHERE id = @inst;
        RETURN;
    END

    /* Count finished children directly from node_execution — no shared counter, no lost-update race.
       Each child's terminal status is committed before this proc is called. */
    DECLARE @finished INT = (
        SELECT COUNT(*)
        FROM wf.node_execution
        WHERE parent_node_execution_id = @foreach_execution_id
          AND status IN (N'SUCCEEDED', N'FAILED', N'SKIPPED', N'CANCELLED')
    );

    IF @finished < @max
        RETURN;

    UPDATE wf.node_execution SET status = N'SUCCEEDED', ended_at_utc = SYSUTCDATETIME() WHERE id = @foreach_execution_id;
    EXEC wf.wf_engine_on_composite_complete @node_execution_id = @foreach_execution_id;
END;
GO

/* Single dispatch seam for FOREACH continuation.

   The base schema scripts (MethylPipeline.sql / MethylPipelineDB_Script.sql) predate
   FOREACH and cannot reference wf.workflow_node.foreach_parallel, so they route here
   instead. Keeping the column read in one place means re-running a base script can no
   longer strand a FOREACH parent in PENDING while its BODY children are SUCCEEDED. */
CREATE OR ALTER PROCEDURE wf.wf_foreach_route_continue
    @foreach_execution_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @parallel BIT;

    SELECT @parallel = ISNULL(wn.foreach_parallel, 0)
    FROM wf.node_execution AS ne
    INNER JOIN wf.workflow_node AS wn ON wn.id = ne.workflow_node_id
    WHERE ne.id = @foreach_execution_id;

    IF @parallel = 1
        EXEC wf.wf_foreach_parallel_continue @foreach_execution_id = @foreach_execution_id;
    ELSE
        EXEC wf.wf_foreach_continue @foreach_execution_id = @foreach_execution_id;
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_engine_continue_parent
    @parent_node_execution_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @pnode BIGINT;
    DECLARE @ptype VARCHAR(32);

    SELECT @pnode = ne.workflow_node_id, @ptype = wn.node_type
    FROM wf.node_execution AS ne
    INNER JOIN wf.workflow_node AS wn ON wn.id = ne.workflow_node_id
    WHERE ne.id = @parent_node_execution_id;

    IF @ptype = N'SEQUENCE'
        EXEC wf.wf_sequence_continue @sequence_execution_id = @parent_node_execution_id;

    ELSE IF @ptype = N'PARALLEL'
        EXEC wf.wf_parallel_continue @parallel_execution_id = @parent_node_execution_id;

    ELSE IF @ptype IN (N'IF', N'SWITCH')
    BEGIN
        UPDATE wf.node_execution SET status = N'SUCCEEDED', ended_at_utc = SYSUTCDATETIME() WHERE id = @parent_node_execution_id;
        EXEC wf.wf_engine_on_composite_complete @node_execution_id = @parent_node_execution_id;
    END

    ELSE IF @ptype = N'REPEAT'
        EXEC wf.wf_repeat_continue @repeat_execution_id = @parent_node_execution_id;

    ELSE IF @ptype = N'WHILE'
        EXEC wf.wf_while_continue @while_execution_id = @parent_node_execution_id;

    ELSE IF @ptype = N'FOREACH'
        EXEC wf.wf_foreach_route_continue @foreach_execution_id = @parent_node_execution_id;
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
        DECLARE @lbr INT;
        DECLARE @base NVARCHAR(128);
        DECLARE @idxs NVARCHAR(32);
        DECLARE @idxn INT;
        DECLARE @arr_path NVARCHAR(32);
        DECLARE @bi BIGINT;

        IF LTRIM(RTRIM(@var_name)) = N''
        BEGIN
            SET @failed = 1;
            SET @fail_code = 10002;
            SET @fail_msg = N'Empty scope variable name.';
            RETURN;
        END

        SET @lbr = CHARINDEX(N'[', @var_name);
        IF @lbr > 0 AND RIGHT(@var_name, 1) = N']'
        BEGIN
            SET @base = LTRIM(RTRIM(LEFT(@var_name, @lbr - 1)));
            SET @idxs = SUBSTRING(@var_name, @lbr + 1, LEN(@var_name) - @lbr - 1);
            SET @idxn = TRY_CONVERT(INT, @idxs);

            IF @base = N'' OR @idxn IS NULL
            BEGIN
                SET @failed = 1;
                SET @fail_code = 10002;
                SET @fail_msg = N'Invalid indexed scope variable reference.';
                RETURN;
            END

            SET @vv = wf.wf_get_scope_variable_json(@workflow_instance_id, @node_execution_id, @base);
            IF @vv IS NULL OR wf.wf_json_array_length(@vv) IS NULL
            BEGIN
                SET @failed = 1;
                SET @fail_code = 10001;
                SET @fail_msg = N'Missing or non-array scope variable: ' + @base;
                RETURN;
            END

            SET @arr_path = CONCAT(N'$[', CAST(@idxn AS NVARCHAR(32)), N']');
            SET @out_fragment = JSON_QUERY(@vv, @arr_path);
            IF @out_fragment IS NULL
                SET @out_fragment = JSON_VALUE(@vv, @arr_path);
            IF @out_fragment IS NULL
                SET @out_fragment = N'null';
            ELSE IF ISJSON(@out_fragment) = 0
            BEGIN
                SET @bi = TRY_CONVERT(BIGINT, @out_fragment);
                IF @bi IS NOT NULL AND CAST(@bi AS NVARCHAR(50)) = LTRIM(RTRIM(@out_fragment))
                    SET @out_fragment = CAST(@bi AS NVARCHAR(50));
                ELSE
                    SET @out_fragment = wf.wf_json_fragment_from_string(@out_fragment);
            END
            RETURN;
        END

        SET @vv = wf.wf_get_scope_variable_json(@workflow_instance_id, @node_execution_id, @var_name);
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

    IF @token IN (N'ctx.item', N'ctx.index')
    BEGIN
        DECLARE @ctx_var NVARCHAR(128) = CASE @token WHEN N'ctx.item' THEN N'item' ELSE N'index' END;
        SET @vv = wf.wf_get_scope_variable_json(@workflow_instance_id, @node_execution_id, @ctx_var);
        IF @vv IS NULL
        BEGIN
            SET @failed = 1;
            SET @fail_code = 10001;
            SET @fail_msg = N'Missing FOREACH context value for ' + @token;
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

            /* FOREACH BODY → direct ACTION: bind item/index scope vars before input resolution. */
            IF @parent_ntype = N'FOREACH'
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

                EXEC wf.wf_try_bind_foreach_body
                    @workflow_instance_id = @workflow_instance_id,
                    @workflow_node_id = @workflow_node_id,
                    @parent_node_execution_id = @parent_node_execution_id,
                    @scope_node_execution_id = @ne_id,
                    @iteration_no = @iteration_no;
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

    EXEC wf.wf_open_scope
        @workflow_instance_id = @workflow_instance_id,
        @from_scope_exec_id = ISNULL(@parent_node_execution_id, 0),
        @to_scope_exec_id = @pex,
        @workflow_node_id = @workflow_node_id;

    EXEC wf.wf_try_bind_foreach_body
        @workflow_instance_id = @workflow_instance_id,
        @workflow_node_id = @workflow_node_id,
        @parent_node_execution_id = @parent_node_execution_id,
        @scope_node_execution_id = @pex,
        @iteration_no = @iteration_no;

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

    IF @node_type = N'FOREACH'
    BEGIN
        DECLARE @fcoll NVARCHAR(128);
        DECLARE @fpar BIT;
        DECLARE @coll_json NVARCHAR(MAX);
        DECLARE @flen INT;
        DECLARE @fbody BIGINT;
        DECLARE @fi INT;

        SELECT
            @fcoll = foreach_collection_var,
            @fpar = ISNULL(foreach_parallel, 0)
        FROM wf.workflow_node
        WHERE id = @workflow_node_id;

        IF @fcoll IS NULL OR LTRIM(RTRIM(@fcoll)) = N''
        BEGIN
            UPDATE wf.node_execution SET status = N'FAILED', engine_error_code = 10011, engine_error_message = N'FOREACH missing collection variable.', ended_at_utc = SYSUTCDATETIME() WHERE id = @pex;
            UPDATE wf.workflow_instance SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME() WHERE id = @workflow_instance_id;
            RETURN;
        END

        SET @coll_json = wf.wf_get_scope_variable_json(@workflow_instance_id, @pex, @fcoll);
        SET @flen = wf.wf_json_array_length(@coll_json);

        IF @flen IS NULL
        BEGIN
            UPDATE wf.node_execution SET status = N'FAILED', engine_error_code = 10011, engine_error_message = N'FOREACH collection is not a JSON array.', ended_at_utc = SYSUTCDATETIME() WHERE id = @pex;
            UPDATE wf.workflow_instance SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME() WHERE id = @workflow_instance_id;
            RETURN;
        END

        IF @flen = 0
        BEGIN
            UPDATE wf.node_execution SET status = N'SUCCEEDED', ended_at_utc = SYSUTCDATETIME() WHERE id = @pex;
            EXEC wf.wf_engine_on_composite_complete @node_execution_id = @pex;
            RETURN;
        END

        SELECT TOP (1) @fbody = child_node_id
        FROM wf.workflow_edge
        WHERE parent_node_id = @workflow_node_id AND branch_kind = N'BODY'
        ORDER BY child_order ASC;

        IF @fbody IS NULL
        BEGIN
            UPDATE wf.node_execution SET status = N'FAILED', engine_error_code = 10010, engine_error_message = N'FOREACH missing BODY child.', ended_at_utc = SYSUTCDATETIME() WHERE id = @pex;
            UPDATE wf.workflow_instance SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME() WHERE id = @workflow_instance_id;
            RETURN;
        END

        INSERT INTO wf.loop_state (workflow_instance_id, control_node_id, scope_node_execution_id, current_iteration, repeat_target_count)
        VALUES (@workflow_instance_id, @workflow_node_id, @pex, 0, @flen);

        IF @fpar = 1
        BEGIN
            SET @fi = 0;
            WHILE @fi < @flen
            BEGIN
                EXEC wf.wf_engine_activate
                    @workflow_instance_id = @workflow_instance_id,
                    @workflow_node_id = @fbody,
                    @parent_node_execution_id = @pex,
                    @iteration_no = @fi + 1,
                    @sequence_index = NULL,
                    @parallel_index = @fi;
                SET @fi += 1;
            END
            RETURN;
        END

        EXEC wf.wf_engine_activate
            @workflow_instance_id = @workflow_instance_id,
            @workflow_node_id = @fbody,
            @parent_node_execution_id = @pex,
            @iteration_no = 1,
            @sequence_index = NULL,
            @parallel_index = NULL;
        RETURN;
    END
END;
GO

PRINT N'wf_sql_foreach_support.sql applied.';
GO
