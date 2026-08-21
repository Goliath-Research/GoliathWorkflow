/*
  Catalog-driven soft worker affinity on wf.workflow_action / wf.node_execution.

  Columns (seeded from action catalog ``dispatch``):
    - affinity_key_field     name of an input_json field (opaque); NULL = no affinity
    - prefer_previous_worker soft stickiness to last completer of the same key
    - prefer_continue_group  prefer READY rows whose key already has SUCCEEDED work

  Runtime columns on wf.node_execution:
    - affinity_key             stamped at ACTION activation from input_json
    - completed_by_worker_id   set on claim; retained after lease delete

  Engine stays process-agnostic: it only reads these columns. Deploy after
  wf_action_dispatch_concurrency.sql and wf_worker_desired_state.sql
  (widens upsert from 9-arg to 12-arg; replaces activate + claim SPs).
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF COL_LENGTH('wf.workflow_action', 'affinity_key_field') IS NULL
    ALTER TABLE wf.workflow_action ADD affinity_key_field NVARCHAR(128) NULL;
GO
IF COL_LENGTH('wf.workflow_action', 'prefer_previous_worker') IS NULL
    ALTER TABLE wf.workflow_action ADD prefer_previous_worker BIT NOT NULL
        CONSTRAINT DF_workflow_action_prefer_previous_worker DEFAULT (0);
GO
IF COL_LENGTH('wf.workflow_action', 'prefer_continue_group') IS NULL
    ALTER TABLE wf.workflow_action ADD prefer_continue_group BIT NOT NULL
        CONSTRAINT DF_workflow_action_prefer_continue_group DEFAULT (0);
GO

IF COL_LENGTH('wf.node_execution', 'affinity_key') IS NULL
    ALTER TABLE wf.node_execution ADD affinity_key NVARCHAR(256) NULL;
GO
IF COL_LENGTH('wf.node_execution', 'completed_by_worker_id') IS NULL
    ALTER TABLE wf.node_execution ADD completed_by_worker_id BIGINT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE name = N'FK_ne_completed_by_worker' AND parent_object_id = OBJECT_ID(N'wf.node_execution')
)
BEGIN
    ALTER TABLE wf.node_execution WITH NOCHECK
    ADD CONSTRAINT FK_ne_completed_by_worker
        FOREIGN KEY (completed_by_worker_id) REFERENCES wf.worker(id);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_ne_instance_affinity_status' AND object_id = OBJECT_ID(N'wf.node_execution')
)
BEGIN
    CREATE INDEX IX_ne_instance_affinity_status
        ON wf.node_execution (workflow_instance_id, affinity_key, status)
        INCLUDE (completed_by_worker_id, ended_at_utc)
        WHERE affinity_key IS NOT NULL;
END
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
    @exclusive_worker BIT = NULL,
    @affinity_key_field NVARCHAR(128) = NULL,
    @prefer_previous_worker BIT = NULL,
    @prefer_continue_group BIT = NULL
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
            exclusive_worker = ISNULL(@exclusive_worker, 0),
            affinity_key_field = @affinity_key_field,
            prefer_previous_worker = ISNULL(@prefer_previous_worker, 0),
            prefer_continue_group = ISNULL(@prefer_continue_group, 0)
        WHERE action_name = @action_name;
    ELSE
        INSERT INTO wf.workflow_action (
            action_name, capability, payload_schema_ref,
            execution_mode, cli_tool, in_process_handler, argv_map,
            max_per_worker, exclusive_worker,
            affinity_key_field, prefer_previous_worker, prefer_continue_group
        )
        VALUES (
            @action_name, @capability, @payload_schema_ref,
            @execution_mode, @cli_tool, @in_process_handler, @argv_map,
            @max_per_worker, ISNULL(@exclusive_worker, 0),
            @affinity_key_field, ISNULL(@prefer_previous_worker, 0),
            ISNULL(@prefer_continue_group, 0)
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
        a.exclusive_worker,
        a.affinity_key_field,
        a.prefer_previous_worker,
        a.prefer_continue_group
    FROM wf.workflow_action AS a
    LEFT JOIN wf.workflow_action_schema AS si
        ON si.workflow_action_id = a.id AND si.direction = N'input'
    LEFT JOIN wf.workflow_action_schema AS so
        ON so.workflow_action_id = a.id AND so.direction = N'output'
);
GO


CREATE OR ALTER PROCEDURE wf.wf_engine_activate
    @workflow_instance_id BIGINT,
    @workflow_node_id BIGINT,
    @parent_node_execution_id BIGINT = NULL,
    @iteration_no INT = 0,
    @sequence_index INT = NULL,
    @parallel_index INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @node_type VARCHAR(32);
    DECLARE @version_id BIGINT;
    DECLARE @node_key NVARCHAR(128);

    -- Resolve the definition node we are about to activate.
    SELECT @node_type = node_type, @version_id = workflow_version_id, @node_key = node_key
    FROM wf.workflow_node
    WHERE id = @workflow_node_id;

    IF @node_type IS NULL RETURN;

    -- ========================================================================
    -- ACTION leaf: create READY task for a worker (does NOT recurse).
    -- ========================================================================
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

        -- Isolate ACTION scope under PARALLEL / FOREACH so each branch/item
        -- has its own copy of parent scope variables (siblings must not share
        -- mutable scope). Aligned with MethylPipeline wf_sql_foreach_support.
        IF @parent_node_execution_id IS NOT NULL
        BEGIN
            DECLARE @parent_ntype VARCHAR(32);
            SELECT @parent_ntype = wn.node_type
            FROM wf.node_execution AS ne
            INNER JOIN wf.workflow_node AS wn ON wn.id = ne.workflow_node_id
            WHERE ne.id = @parent_node_execution_id;

            IF @parent_ntype IN (N'PARALLEL', N'FOREACH')
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

            -- FOREACH BODY that is a direct ACTION: bind item/index onto this
            -- ACTION's scope before building input_json.
            IF @parent_ntype = N'FOREACH'
            BEGIN
                EXEC wf.wf_try_bind_foreach_body
                    @workflow_instance_id = @workflow_instance_id,
                    @workflow_node_id = @workflow_node_id,
                    @parent_node_execution_id = @parent_node_execution_id,
                    @scope_node_execution_id = @ne_id,
                    @iteration_no = @iteration_no;
            END
        END

        -- Seed execution_context (paths, indices, parent linkage) for workers.
        EXEC wf.wf_seed_execution_context
            @node_execution_id = @ne_id,
            @workflow_instance_id = @workflow_instance_id,
            @workflow_node_id = @workflow_node_id,
            @parent_node_execution_id = @parent_node_execution_id,
            @iteration_no = @iteration_no,
            @sequence_index = @sequence_index,
            @parallel_index = @parallel_index;

        -- Resolve input_template + input_bindings into the final input_json.
        -- Failure here fails the whole instance (cannot run without inputs).
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

        -- Task is now READY with input_json; a worker will claim it via lease.

        UPDATE wf.node_execution SET input_json = CAST(@fj AS json) WHERE id = @ne_id;

        /* Soft affinity: copy opaque key from a catalog-declared input_json field. */
        DECLARE @aff_field NVARCHAR(128);
        SELECT @aff_field = wa.affinity_key_field
        FROM wf.workflow_node AS wn
        INNER JOIN wf.workflow_action AS wa ON wa.id = wn.workflow_action_id
        WHERE wn.id = @workflow_node_id;

        IF @aff_field IS NOT NULL
           AND @aff_field LIKE N'[A-Za-z_]%'
           AND @aff_field NOT LIKE N'%[^A-Za-z0-9_]%'
        BEGIN
            UPDATE wf.node_execution
            SET affinity_key = LEFT(JSON_VALUE(@fj, N'$.' + @aff_field), 256)
            WHERE id = @ne_id;
        END

        RETURN;
    END

    -- ========================================================================
    -- COMPOSITE node: create PENDING execution (open, not claimed work), open
    -- scope, then dispatch children according to node_type. Completion is
    -- handled later by wf_engine_on_composite_complete / continue_parent.
    -- started_at_utc stays NULL — wall-clock of composites must not inflate
    -- ACTION / SLA metrics (use available_at_utc / ended_at_utc if needed).
    -- ========================================================================
    DECLARE @pex BIGINT;
    INSERT INTO wf.node_execution (
        workflow_instance_id, workflow_node_id, status, attempt_no,
        parent_node_execution_id, iteration_no, available_at_utc
    )
    VALUES (
        @workflow_instance_id, @workflow_node_id, N'PENDING', 1,
        @parent_node_execution_id, @iteration_no, SYSUTCDATETIME()
    );
    SET @pex = SCOPE_IDENTITY();

    -- Inherit parent scope variables into this composite's scope, then apply
    -- node_scope_default for this definition node.
    -- (Pass variable as-is: EXEC named args cannot take ISNULL(...).
    --  wf_open_scope already does ISNULL(@from_scope_exec_id, 0).)
    EXEC wf.wf_open_scope
        @workflow_instance_id = @workflow_instance_id,
        @from_scope_exec_id = @parent_node_execution_id,
        @to_scope_exec_id = @pex,
        @workflow_node_id = @workflow_node_id;

    -- If THIS composite is the BODY child of a FOREACH, bind item/index onto
    -- its newly opened scope (covers SEQUENCE/PARALLEL/IF under FOREACH).
    EXEC wf.wf_try_bind_foreach_body
        @workflow_instance_id = @workflow_instance_id,
        @workflow_node_id = @workflow_node_id,
        @parent_node_execution_id = @parent_node_execution_id,
        @scope_node_execution_id = @pex,
        @iteration_no = @iteration_no;

    -- ------------------------------------------------------------------------
    -- SEQUENCE: activate only the first child (by child_order). The next
    -- sibling is activated later by continue_parent when this child completes.
    -- ------------------------------------------------------------------------
    IF @node_type = N'SEQUENCE'
    BEGIN
        DECLARE @child1 BIGINT;
        SELECT TOP (1) @child1 = child_node_id
        FROM wf.workflow_edge
        WHERE parent_node_id = @workflow_node_id
        ORDER BY child_order ASC;

        IF @child1 IS NULL
        BEGIN
            -- Empty SEQUENCE succeeds immediately and bubbles up.
            UPDATE wf.node_execution SET status = N'SUCCEEDED', ended_at_utc = SYSUTCDATETIME() WHERE id = @pex;
            EXEC wf.wf_engine_on_composite_complete @node_execution_id = @pex;
            RETURN;
        END

        DECLARE @ord INT = 0;
        SELECT TOP (1) @ord = child_order FROM wf.workflow_edge WHERE parent_node_id = @workflow_node_id ORDER BY child_order ASC;

        EXEC wf.wf_engine_activate
            @workflow_instance_id = @workflow_instance_id,
            @workflow_node_id = @child1,
            @parent_node_execution_id = @pex,
            @iteration_no = @iteration_no,
            @sequence_index = @ord,
            @parallel_index = NULL;
        RETURN;
    END

    -- ------------------------------------------------------------------------
    -- PARALLEL: activate ALL children now (fan-out). Composite completes when
    -- every child has succeeded (join handled in on_composite_complete path).
    -- ------------------------------------------------------------------------
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

    -- ------------------------------------------------------------------------
    -- IF: evaluate condition_ref_node_key result code; pick THEN (non-zero)
    -- or ELSE (zero/null). Missing branch fails the instance.
    -- ------------------------------------------------------------------------
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
        SELECT TOP (1) @body = child_node_id FROM wf.workflow_edge WHERE parent_node_id = @workflow_node_id AND branch_kind = N'BODY' ORDER BY child_order ASC;

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

    -- ------------------------------------------------------------------------
    -- WHILE: evaluate condition first. If false/null, succeed immediately;
    -- otherwise activate BODY (iteration 1). Re-check on each continue.
    -- ------------------------------------------------------------------------
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
        DECLARE @fiter INT;  -- 1-based iteration for EXEC (cannot pass @fi+1 inline)

        SELECT
            @fcoll = foreach_collection_var,
            @fpar = ISNULL(foreach_parallel, 0)
        FROM wf.workflow_node
        WHERE id = @workflow_node_id;

        IF @fcoll IS NULL OR LTRIM(RTRIM(@fcoll)) = N''
        BEGIN
            UPDATE wf.node_execution
            SET status = N'FAILED',
                engine_error_code = 10011,
                engine_error_message = N'FOREACH missing collection variable.',
                ended_at_utc = SYSUTCDATETIME()
            WHERE id = @pex;
            UPDATE wf.workflow_instance
            SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME()
            WHERE id = @workflow_instance_id;
            RETURN;
        END

        -- Collection must already be in THIS composite's scope (inherited /
        -- defaults applied by wf_open_scope above).
        SET @coll_json = wf.wf_get_scope_variable_json(@workflow_instance_id, @pex, @fcoll);
        SET @flen = wf.wf_json_array_length(@coll_json);

        IF @flen IS NULL
        BEGIN
            UPDATE wf.node_execution
            SET status = N'FAILED',
                engine_error_code = 10011,
                engine_error_message = N'FOREACH collection is not a JSON array.',
                ended_at_utc = SYSUTCDATETIME()
            WHERE id = @pex;
            UPDATE wf.workflow_instance
            SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME()
            WHERE id = @workflow_instance_id;
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
            UPDATE wf.node_execution
            SET status = N'FAILED',
                engine_error_code = 10010,
                engine_error_message = N'FOREACH missing BODY child.',
                ended_at_utc = SYSUTCDATETIME()
            WHERE id = @pex;
            UPDATE wf.workflow_instance
            SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME()
            WHERE id = @workflow_instance_id;
            RETURN;
        END

        -- Track progress: current_iteration starts at 0; target = array length.
        INSERT INTO wf.loop_state (
            workflow_instance_id, control_node_id, scope_node_execution_id,
            current_iteration, repeat_target_count
        )
        VALUES (@workflow_instance_id, @workflow_node_id, @pex, 0, @flen);

        IF @fpar = 1
        BEGIN
            -- Parallel FOREACH: activate BODY once per item immediately.
            SET @fi = 0;
            WHILE @fi < @flen
            BEGIN
                SET @fiter = @fi + 1;  -- EXEC named args cannot take @fi + 1
                EXEC wf.wf_engine_activate
                    @workflow_instance_id = @workflow_instance_id,
                    @workflow_node_id = @fbody,
                    @parent_node_execution_id = @pex,
                    @iteration_no = @fiter,
                    @sequence_index = NULL,
                    @parallel_index = @fi;
                SET @fi += 1;
            END
            RETURN;
        END

        -- Sequential FOREACH: only the first item now; continue_parent does the rest.
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


CREATE OR ALTER PROCEDURE wf.sp_worker_request_task
    @worker_id BIGINT,
    @worker_token NVARCHAR(4000),
    @capability NVARCHAR(128) NULL,
    @max_lease_seconds INT = 300
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    EXEC wf.wf_worker_authenticate @worker_id = @worker_id, @worker_token = @worker_token;

    DECLARE @now DATETIME2(7) = SYSUTCDATETIME();
    DECLARE @lease_end DATETIME2(7) = DATEADD(SECOND, @max_lease_seconds, @now);
    DECLARE @worker_capabilities json;
    DECLARE @is_omnibus BIT;
    DECLARE @reclaim_cutoff DATETIME2(7) = DATEADD(SECOND, -60, @now);
    DECLARE @desired_state VARCHAR(32) = N'ACTIVE';
    DECLARE @command VARCHAR(32) = N'NONE';

    IF EXISTS (
        SELECT 1
        FROM wf.node_execution AS ne
        LEFT JOIN wf.task_lease AS l ON l.node_execution_id = ne.id
        WHERE ne.status = N'RUNNING'
          AND (
                l.node_execution_id IS NULL
             OR l.lease_expires_at_utc <= @reclaim_cutoff
          )
    )
    BEGIN
        EXEC wf.sp_reclaim_expired_leases @grace_seconds = 60, @quiet = 1;
    END

    SELECT
        @worker_capabilities = w.capabilities,
        @desired_state = COALESCE(w.desired_state, N'ACTIVE')
    FROM wf.worker AS w
    WHERE w.id = @worker_id;

    SET @command = CASE @desired_state
        WHEN N'DRAINING' THEN N'DRAIN'
        WHEN N'STOPPING' THEN N'STOP'
        ELSE N'NONE'
    END;

    IF @desired_state IN (N'DRAINING', N'STOPPING')
    BEGIN
        SELECT
            CAST(NULL AS BIGINT) AS node_execution_id,
            CAST(NULL AS BIGINT) AS workflow_instance_id,
            CAST(NULL AS NVARCHAR(256)) AS node_key,
            CAST(NULL AS NVARCHAR(256)) AS action_name,
            CAST(NULL AS NVARCHAR(128)) AS capability,
            CAST(NULL AS INT) AS attempt_no,
            CAST(NULL AS json) AS input_json,
            CAST(NULL AS INT) AS iteration_no,
            @desired_state AS desired_state,
            @command AS command;
        RETURN;
    END

    -- Catalog dispatch: exclusive_worker action already leased â†’ no further claims.
    IF EXISTS (
        SELECT 1
        FROM wf.task_lease AS tl
        INNER JOIN wf.node_execution AS ne ON ne.id = tl.node_execution_id
        INNER JOIN wf.workflow_node AS wn ON wn.id = ne.workflow_node_id
        INNER JOIN wf.workflow_action AS wa ON wa.id = wn.workflow_action_id
        WHERE tl.worker_id = @worker_id
          AND ne.status = N'RUNNING'
          AND ISNULL(wa.exclusive_worker, 0) = 1
    )
    BEGIN
        SELECT
            CAST(NULL AS BIGINT) AS node_execution_id,
            CAST(NULL AS BIGINT) AS workflow_instance_id,
            CAST(NULL AS NVARCHAR(256)) AS node_key,
            CAST(NULL AS NVARCHAR(256)) AS action_name,
            CAST(NULL AS NVARCHAR(128)) AS capability,
            CAST(NULL AS INT) AS attempt_no,
            CAST(NULL AS json) AS input_json,
            CAST(NULL AS INT) AS iteration_no,
            @desired_state AS desired_state,
            @command AS command;
        RETURN;
    END

    SET @is_omnibus = wf.wf_worker_is_omnibus(@worker_capabilities);

    IF @capability IS NOT NULL
       AND @is_omnibus = 0
       AND wf.wf_worker_capability_allowed(@worker_capabilities, @capability) = 0
    BEGIN
        SELECT
            CAST(NULL AS BIGINT) AS node_execution_id,
            CAST(NULL AS BIGINT) AS workflow_instance_id,
            CAST(NULL AS NVARCHAR(256)) AS node_key,
            CAST(NULL AS NVARCHAR(256)) AS action_name,
            CAST(NULL AS NVARCHAR(128)) AS capability,
            CAST(NULL AS INT) AS attempt_no,
            CAST(NULL AS json) AS input_json,
            CAST(NULL AS INT) AS iteration_no,
            @desired_state AS desired_state,
            @command AS command;
        RETURN;
    END

    BEGIN TRANSACTION;

    DECLARE @picked_ids TABLE (id BIGINT);

    ;WITH cte AS (
        SELECT TOP (1) ne.id
        FROM wf.node_execution AS ne WITH (ROWLOCK, READPAST, UPDLOCK)
        INNER JOIN wf.workflow_node AS wn ON wn.id = ne.workflow_node_id
        INNER JOIN wf.workflow_action AS wa ON wa.id = wn.workflow_action_id
        INNER JOIN wf.workflow_instance AS wi ON wi.id = ne.workflow_instance_id
        WHERE ne.status = N'READY'
          AND ne.input_json IS NOT NULL
          AND wn.node_type = N'ACTION'
          AND wi.status = N'RUNNING'
          AND (ne.available_at_utc IS NULL OR ne.available_at_utc <= @now)
          AND wf.wf_worker_capability_allowed(@worker_capabilities, wa.capability) = 1
          AND (
              @capability IS NULL
              OR wa.capability = @capability
              OR wa.capability IS NULL
          )
          -- exclusive_worker candidate requires an idle worker (no RUNNING leases,
          -- including expired-but-not-yet-reclaimed ones after a restart).
          AND (
              ISNULL(wa.exclusive_worker, 0) = 0
              OR NOT EXISTS (
                  SELECT 1
                  FROM wf.task_lease AS tl_idle
                  INNER JOIN wf.node_execution AS ne_idle ON ne_idle.id = tl_idle.node_execution_id
                  WHERE tl_idle.worker_id = @worker_id
                    AND ne_idle.status = N'RUNNING'
              )
          )
          -- max_per_worker: cap concurrent RUNNING leases of this action.
          AND (
              wa.max_per_worker IS NULL
              OR (
                  SELECT COUNT(*)
                  FROM wf.task_lease AS tl_cap
                  INNER JOIN wf.node_execution AS ne_cap ON ne_cap.id = tl_cap.node_execution_id
                  INNER JOIN wf.workflow_node AS wn_cap ON wn_cap.id = ne_cap.workflow_node_id
                  WHERE tl_cap.worker_id = @worker_id
                    AND ne_cap.status = N'RUNNING'
                    AND wn_cap.workflow_action_id = wa.id
              ) < wa.max_per_worker
          )
        -- Exclusive GPU actions (idle workers only; busy workers already filtered
        -- them out) outrank older trim/QC FIFO so Clara is not starved.
        -- Then soft affinity: continue an affinity group; prefer last completer.
        -- Actions without affinity flags keep FIFO on the remaining arms.
        ORDER BY
            CASE WHEN ISNULL(wa.exclusive_worker, 0) = 1
                 THEN 0 ELSE 1 END,
            CASE WHEN wa.prefer_continue_group = 1
                  AND ne.affinity_key IS NOT NULL
                  AND EXISTS (
                      SELECT 1 FROM wf.node_execution AS x
                      WHERE x.workflow_instance_id = ne.workflow_instance_id
                        AND x.affinity_key = ne.affinity_key
                        AND x.status = N'SUCCEEDED')
                 THEN 0 ELSE 1 END,
            CASE WHEN wa.prefer_previous_worker = 1
                  AND ne.affinity_key IS NOT NULL
                  AND EXISTS (
                      SELECT 1 FROM wf.node_execution AS prev
                      WHERE prev.workflow_instance_id = ne.workflow_instance_id
                        AND prev.affinity_key = ne.affinity_key
                        AND prev.status = N'SUCCEEDED'
                        AND prev.completed_by_worker_id = @worker_id
                        AND prev.ended_at_utc = (
                            SELECT MAX(p2.ended_at_utc)
                            FROM wf.node_execution AS p2
                            WHERE p2.workflow_instance_id = ne.workflow_instance_id
                              AND p2.affinity_key = ne.affinity_key
                              AND p2.status = N'SUCCEEDED'))
                 THEN 0 ELSE 1 END,
            ne.available_at_utc ASC,
            ne.id ASC
    )
    UPDATE ne
    SET status = N'RUNNING',
        started_at_utc = @now,
        completed_by_worker_id = @worker_id,
        engine_error_code = NULL,
        engine_error_message = NULL
    OUTPUT inserted.id INTO @picked_ids(id)
    FROM wf.node_execution AS ne
    INNER JOIN cte ON cte.id = ne.id;

    DECLARE @picked BIGINT;
    SELECT @picked = id FROM @picked_ids;

    IF @picked IS NULL
    BEGIN
        ROLLBACK TRANSACTION;
        SELECT
            CAST(NULL AS BIGINT) AS node_execution_id,
            CAST(NULL AS BIGINT) AS workflow_instance_id,
            CAST(NULL AS NVARCHAR(256)) AS node_key,
            CAST(NULL AS NVARCHAR(256)) AS action_name,
            CAST(NULL AS NVARCHAR(128)) AS capability,
            CAST(NULL AS INT) AS attempt_no,
            CAST(NULL AS json) AS input_json,
            CAST(NULL AS INT) AS iteration_no,
            @desired_state AS desired_state,
            @command AS command;
        RETURN;
    END

    ;MERGE wf.task_lease AS t
    USING (SELECT @picked AS node_execution_id) AS s ON (t.node_execution_id = s.node_execution_id)
    WHEN MATCHED THEN
        UPDATE SET worker_id = @worker_id, lease_expires_at_utc = @lease_end, heartbeat_at_utc = @now
    WHEN NOT MATCHED THEN
        INSERT (node_execution_id, worker_id, lease_expires_at_utc, heartbeat_at_utc)
        VALUES (@picked, @worker_id, @lease_end, @now);

    COMMIT TRANSACTION;

    SELECT
        ne.id AS node_execution_id,
        ne.workflow_instance_id,
        wn.node_key,
        wa.action_name,
        wa.capability,
        ne.attempt_no,
        ne.input_json,
        ne.iteration_no,
        @desired_state AS desired_state,
        @command AS command
    FROM wf.node_execution AS ne
    INNER JOIN wf.workflow_node AS wn ON wn.id = ne.workflow_node_id
    INNER JOIN wf.workflow_action AS wa ON wa.id = wn.workflow_action_id
    WHERE ne.id = @picked;
END
GO
