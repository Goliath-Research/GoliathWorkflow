/*
  Workflow Engine - Sample workflow + verification queries (SQL Server).
  Run after: workflow_definition.sql, workflow_runtime.sql, workflow_constraints_indexes.sql, workflow_worker_api.sql
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF EXISTS (SELECT 1 FROM dbo.workflow_def WHERE name = N'DemoFlow')
BEGIN
    PRINT N'Seed skipped: DemoFlow already exists.';
END
ELSE
BEGIN
    DECLARE @def_id BIGINT;
    DECLARE @ver_id BIGINT;

    INSERT INTO dbo.workflow_def (name, description)
    VALUES (N'DemoFlow', N'Demonstrates SEQUENCE, IF, SWITCH, PARALLEL, REPEAT with JSON templates.');

    SET @def_id = SCOPE_IDENTITY();

    INSERT INTO dbo.workflow_version (workflow_def_id, version_major, version_minor, is_active, root_node_id)
    VALUES (@def_id, 1, 0, 1, NULL);

    SET @ver_id = SCOPE_IDENTITY();

    INSERT INTO dbo.workflow_action (action_name, capability, payload_schema_ref) VALUES
        (N'demo.echo', N'demo', NULL),
        (N'demo.branch', N'demo', NULL),
        (N'demo.parallel', N'demo', NULL),
        (N'demo.repeat', N'demo', NULL);

    DECLARE @act_echo BIGINT = (SELECT id FROM dbo.workflow_action WHERE action_name = N'demo.echo');
    DECLARE @act_branch BIGINT = (SELECT id FROM dbo.workflow_action WHERE action_name = N'demo.branch');
    DECLARE @act_parallel BIGINT = (SELECT id FROM dbo.workflow_action WHERE action_name = N'demo.parallel');
    DECLARE @act_repeat BIGINT = (SELECT id FROM dbo.workflow_action WHERE action_name = N'demo.repeat');

    DECLARE @n_root BIGINT;
    DECLARE @n_cond BIGINT;
    DECLARE @n_if BIGINT;
    DECLARE @n_then BIGINT;
    DECLARE @n_else BIGINT;
    DECLARE @n_sw_sel BIGINT;
    DECLARE @n_sw BIGINT;
    DECLARE @n_sw_case BIGINT;
    DECLARE @n_sw_def BIGINT;
    DECLARE @n_par BIGINT;
    DECLARE @n_pa BIGINT;
    DECLARE @n_pb BIGINT;
    DECLARE @n_rep BIGINT;
    DECLARE @n_body BIGINT;

    INSERT INTO dbo.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key)
    VALUES (@ver_id, N'SEQUENCE', N'root', NULL, NULL, NULL, NULL);
    SET @n_root = SCOPE_IDENTITY();

    INSERT INTO dbo.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key)
    VALUES (@ver_id, N'ACTION', N'cond', @act_echo, NULL, NULL, NULL);
    SET @n_cond = SCOPE_IDENTITY();

    INSERT INTO dbo.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key)
    VALUES (@ver_id, N'IF', N'gate_if', NULL, NULL, N'cond', NULL);
    SET @n_if = SCOPE_IDENTITY();

    INSERT INTO dbo.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key)
    VALUES (@ver_id, N'ACTION', N'then_act', @act_branch, NULL, NULL, NULL);
    SET @n_then = SCOPE_IDENTITY();

    INSERT INTO dbo.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key)
    VALUES (@ver_id, N'ACTION', N'else_act', @act_branch, NULL, NULL, NULL);
    SET @n_else = SCOPE_IDENTITY();

    INSERT INTO dbo.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key)
    VALUES (@ver_id, N'ACTION', N'sw_sel', @act_echo, NULL, NULL, NULL);
    SET @n_sw_sel = SCOPE_IDENTITY();

    INSERT INTO dbo.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key)
    VALUES (@ver_id, N'SWITCH', N'switch1', NULL, NULL, NULL, N'sw_sel');
    SET @n_sw = SCOPE_IDENTITY();

    INSERT INTO dbo.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key)
    VALUES (@ver_id, N'ACTION', N'sw_case2', @act_branch, NULL, NULL, NULL);
    SET @n_sw_case = SCOPE_IDENTITY();

    INSERT INTO dbo.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key)
    VALUES (@ver_id, N'ACTION', N'sw_default', @act_branch, NULL, NULL, NULL);
    SET @n_sw_def = SCOPE_IDENTITY();

    INSERT INTO dbo.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key)
    VALUES (@ver_id, N'PARALLEL', N'par', NULL, NULL, NULL, NULL);
    SET @n_par = SCOPE_IDENTITY();

    INSERT INTO dbo.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key)
    VALUES (@ver_id, N'ACTION', N'par_a', @act_parallel, NULL, NULL, NULL);
    SET @n_pa = SCOPE_IDENTITY();

    INSERT INTO dbo.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key)
    VALUES (@ver_id, N'ACTION', N'par_b', @act_parallel, NULL, NULL, NULL);
    SET @n_pb = SCOPE_IDENTITY();

    INSERT INTO dbo.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key)
    VALUES (@ver_id, N'REPEAT', N'repeater', NULL, 3, NULL, NULL);
    SET @n_rep = SCOPE_IDENTITY();

    INSERT INTO dbo.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key)
    VALUES (@ver_id, N'ACTION', N'rep_body', @act_repeat, NULL, NULL, NULL);
    SET @n_body = SCOPE_IDENTITY();

    INSERT INTO dbo.workflow_edge (parent_node_id, child_node_id, child_order, branch_kind, switch_case_value, is_default)
    VALUES
        (@n_root, @n_cond, 0, N'SEQUENCE', NULL, 0),
        (@n_root, @n_if, 1, N'SEQUENCE', NULL, 0),
        (@n_root, @n_sw_sel, 2, N'SEQUENCE', NULL, 0),
        (@n_root, @n_sw, 3, N'SEQUENCE', NULL, 0),
        (@n_root, @n_par, 4, N'SEQUENCE', NULL, 0),
        (@n_root, @n_rep, 5, N'SEQUENCE', NULL, 0);

    INSERT INTO dbo.workflow_edge (parent_node_id, child_node_id, child_order, branch_kind, switch_case_value, is_default)
    VALUES
        (@n_if, @n_then, 0, N'THEN', NULL, 0),
        (@n_if, @n_else, 1, N'ELSE', NULL, 0);

    INSERT INTO dbo.workflow_edge (parent_node_id, child_node_id, child_order, branch_kind, switch_case_value, is_default)
    VALUES
        (@n_sw, @n_sw_case, 0, N'CASE', 2, 0),
        (@n_sw, @n_sw_def, 1, N'DEFAULT', NULL, 1);

    INSERT INTO dbo.workflow_edge (parent_node_id, child_node_id, child_order, branch_kind, switch_case_value, is_default)
    VALUES
        (@n_par, @n_pa, 0, N'PARALLEL', NULL, 0),
        (@n_par, @n_pb, 1, N'PARALLEL', NULL, 0);

    INSERT INTO dbo.workflow_edge (parent_node_id, child_node_id, child_order, branch_kind, switch_case_value, is_default)
    VALUES
        (@n_rep, @n_body, 0, N'BODY', NULL, 0);

    UPDATE dbo.workflow_version SET root_node_id = @n_root WHERE id = @ver_id;

    INSERT INTO dbo.workflow_input_template (workflow_node_id, template_json)
    VALUES
        (@n_cond, N'{"phase":"cond","note":"${ctx.sequenceIndex}"}'),
        (@n_sw_sel, N'{"phase":"switch_select"}'),
        (@n_pa, N'{"lane":"a","parallelIndex":${ctx.parallelIndex},"pick":${ctx.task.cond.resultCode}}'),
        (@n_pb, N'{"lane":"b","parallelIndex":${ctx.parallelIndex},"pick":${ctx.task.cond.resultCode}}'),
        (@n_body, N'{"iteration":${ctx.iterationNo},"prevSwitch":${ctx.task.sw_sel.resultCode}}');

END
GO

/* ---- Verification helpers (manual execution) ---- */
/*
DECLARE @i BIGINT;
INSERT INTO dbo.workflow_instance(workflow_version_id) VALUES ((SELECT TOP (1) id FROM dbo.workflow_version ORDER BY id DESC));
SET @i = SCOPE_IDENTITY();
EXEC dbo.sp_start_workflow_instance @workflow_instance_id = @i;

DECLARE @accepted BIT, @st VARCHAR(32), @nr INT;
DECLARE @wid NVARCHAR(128) = N'worker-1';

WHILE EXISTS (SELECT 1 FROM dbo.node_execution WHERE workflow_instance_id=@i AND status IN (N'READY',N'RUNNING'))
BEGIN
  DECLARE @ne BIGINT;
  DECLARE @cap NVARCHAR(128) = NULL;

  -- Claim
  CREATE TABLE #t (node_execution_id BIGINT, workflow_instance_id BIGINT, node_key NVARCHAR(128), action_name NVARCHAR(256), capability NVARCHAR(128), attempt_no INT, input_json NVARCHAR(MAX), iteration_no INT);
  INSERT INTO #t EXEC dbo.sp_worker_request_task @worker_id=@wid, @capability=@cap, @max_lease_seconds=300;
  IF NOT EXISTS (SELECT 1 FROM #t) BREAK;

  SELECT TOP (1) @ne = node_execution_id FROM #t;

  -- Simulate success: cond=7 (non-zero THEN), sw_sel=2 (CASE), others=1
  DECLARE @nk NVARCHAR(128) = (SELECT node_key FROM dbo.node_execution ne JOIN dbo.workflow_node wn ON wn.id=ne.workflow_node_id WHERE ne.id=@ne);
  DECLARE @rc INT = CASE @nk
    WHEN N'cond' THEN 7
    WHEN N'sw_sel' THEN 2
    ELSE 1
  END;

  EXEC dbo.sp_worker_submit_result @node_execution_id=@ne, @worker_id=@wid, @result_code=@rc, @output_json=N'{"ok":true}', @accepted=@accepted OUTPUT, @instance_status=@st OUTPUT, @next_ready_count=@nr OUTPUT;
  DROP TABLE #t;
END

SELECT status, node_key=wn.node_key, ne.status, ne.result_code, ne.input_json
FROM dbo.node_execution ne
JOIN dbo.workflow_node wn ON wn.id = ne.workflow_node_id
WHERE ne.workflow_instance_id = @i
ORDER BY ne.id;
*/
