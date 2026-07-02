/*
  Workflow Engine (wf schema) - Tree example seed for Delphi runtime walkthrough.

  Prerequisites:
  - Base wf schema deployed (MethylPipeline_*.sql or equivalent)
  - Scoped variable migration applied (wf_scope_variables.sql)

  Creates workflow def: DelphiTreeFlow
  Tree shape matches WORKFLOW_ENGINE_DELPHI.md:
    RootSeq -> LoadInput -> BranchPar(IF + SWITCH) -> RetryRepeat -> PollWhile -> Publish
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF COL_LENGTH('wf.workflow_node', 'condition_var') IS NULL
   OR COL_LENGTH('wf.workflow_node', 'switch_var') IS NULL
   OR OBJECT_ID(N'wf.node_scope_default', N'U') IS NULL
   OR OBJECT_ID(N'wf.variable_output_binding', N'U') IS NULL
BEGIN
    RAISERROR(N'Prerequisite missing: run wf_scope_variables.sql first.', 16, 1);
    RETURN;
END
GO

IF EXISTS (SELECT 1 FROM wf.workflow_def WHERE name = N'DelphiTreeFlow')
BEGIN
    PRINT N'Seed skipped: wf.workflow_def "DelphiTreeFlow" already exists.';
END
ELSE
BEGIN
    DECLARE @def_id BIGINT;
    DECLARE @ver_id BIGINT;

    MERGE wf.workflow_action AS t
    USING (VALUES
      (N'delphi.load_input', N'demo'),
      (N'delphi.qc_task', N'demo'),
      (N'delphi.skip_qc', N'demo'),
      (N'delphi.normalize_a', N'demo'),
      (N'delphi.normalize_b', N'demo'),
      (N'delphi.normalize_default', N'demo'),
      (N'delphi.align_chunk', N'demo'),
      (N'delphi.fetch_page', N'demo'),
      (N'delphi.publish', N'demo')
    ) AS s(action_name, capability)
    ON t.action_name = s.action_name
    WHEN NOT MATCHED THEN
      INSERT (action_name, capability, payload_schema_ref)
      VALUES (s.action_name, s.capability, NULL);

    INSERT INTO wf.workflow_def (name, description)
    VALUES (
      N'DelphiTreeFlow',
      N'Exercises SEQUENCE, PARALLEL, IF, SWITCH, REPEAT, WHILE with scope/output bindings.'
    );
    SET @def_id = SCOPE_IDENTITY();

    INSERT INTO wf.workflow_version (workflow_def_id, version_major, version_minor, is_active, root_node_id)
    VALUES (@def_id, 1, 0, 1, NULL);
    SET @ver_id = SCOPE_IDENTITY();

    DECLARE
      @n_root BIGINT, @n_load BIGINT, @n_par BIGINT, @n_if BIGINT, @n_qc BIGINT, @n_skip BIGINT,
      @n_switch BIGINT, @n_norm_a BIGINT, @n_norm_b BIGINT, @n_norm_def BIGINT,
      @n_repeat BIGINT, @n_align BIGINT, @n_while BIGINT, @n_fetch BIGINT, @n_publish BIGINT;

    DECLARE
      @a_load BIGINT = (SELECT id FROM wf.workflow_action WHERE action_name = N'delphi.load_input'),
      @a_qc BIGINT = (SELECT id FROM wf.workflow_action WHERE action_name = N'delphi.qc_task'),
      @a_skip BIGINT = (SELECT id FROM wf.workflow_action WHERE action_name = N'delphi.skip_qc'),
      @a_norm_a BIGINT = (SELECT id FROM wf.workflow_action WHERE action_name = N'delphi.normalize_a'),
      @a_norm_b BIGINT = (SELECT id FROM wf.workflow_action WHERE action_name = N'delphi.normalize_b'),
      @a_norm_def BIGINT = (SELECT id FROM wf.workflow_action WHERE action_name = N'delphi.normalize_default'),
      @a_align BIGINT = (SELECT id FROM wf.workflow_action WHERE action_name = N'delphi.align_chunk'),
      @a_fetch BIGINT = (SELECT id FROM wf.workflow_action WHERE action_name = N'delphi.fetch_page'),
      @a_publish BIGINT = (SELECT id FROM wf.workflow_action WHERE action_name = N'delphi.publish');

    INSERT INTO wf.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key, condition_var, switch_var)
    VALUES (@ver_id, N'SEQUENCE', N'root_seq', NULL, NULL, NULL, NULL, NULL, NULL);
    SET @n_root = SCOPE_IDENTITY();

    INSERT INTO wf.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key, condition_var, switch_var)
    VALUES (@ver_id, N'ACTION', N'load_input', @a_load, NULL, NULL, NULL, NULL, NULL);
    SET @n_load = SCOPE_IDENTITY();

    INSERT INTO wf.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key, condition_var, switch_var)
    VALUES (@ver_id, N'PARALLEL', N'branch_par', NULL, NULL, NULL, NULL, NULL, NULL);
    SET @n_par = SCOPE_IDENTITY();

    INSERT INTO wf.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key, condition_var, switch_var)
    VALUES (@ver_id, N'IF', N'gate_if', NULL, NULL, NULL, NULL, N'shouldRunQc', NULL);
    SET @n_if = SCOPE_IDENTITY();

    INSERT INTO wf.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key, condition_var, switch_var)
    VALUES (@ver_id, N'ACTION', N'qc_task', @a_qc, NULL, NULL, NULL, NULL, NULL);
    SET @n_qc = SCOPE_IDENTITY();

    INSERT INTO wf.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key, condition_var, switch_var)
    VALUES (@ver_id, N'ACTION', N'skip_qc', @a_skip, NULL, NULL, NULL, NULL, NULL);
    SET @n_skip = SCOPE_IDENTITY();

    INSERT INTO wf.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key, condition_var, switch_var)
    VALUES (@ver_id, N'SWITCH', N'mode_switch', NULL, NULL, NULL, NULL, NULL, N'mode');
    SET @n_switch = SCOPE_IDENTITY();

    INSERT INTO wf.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key, condition_var, switch_var)
    VALUES (@ver_id, N'ACTION', N'normalize_a', @a_norm_a, NULL, NULL, NULL, NULL, NULL);
    SET @n_norm_a = SCOPE_IDENTITY();

    INSERT INTO wf.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key, condition_var, switch_var)
    VALUES (@ver_id, N'ACTION', N'normalize_b', @a_norm_b, NULL, NULL, NULL, NULL, NULL);
    SET @n_norm_b = SCOPE_IDENTITY();

    INSERT INTO wf.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key, condition_var, switch_var)
    VALUES (@ver_id, N'ACTION', N'normalize_default', @a_norm_def, NULL, NULL, NULL, NULL, NULL);
    SET @n_norm_def = SCOPE_IDENTITY();

    INSERT INTO wf.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key, condition_var, switch_var)
    VALUES (@ver_id, N'REPEAT', N'retry_repeat', NULL, 3, NULL, NULL, NULL, NULL);
    SET @n_repeat = SCOPE_IDENTITY();

    INSERT INTO wf.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key, condition_var, switch_var)
    VALUES (@ver_id, N'ACTION', N'align_chunk', @a_align, NULL, NULL, NULL, NULL, NULL);
    SET @n_align = SCOPE_IDENTITY();

    INSERT INTO wf.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key, condition_var, switch_var)
    VALUES (@ver_id, N'WHILE', N'poll_while', NULL, NULL, NULL, NULL, N'hasMorePages', NULL);
    SET @n_while = SCOPE_IDENTITY();

    INSERT INTO wf.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key, condition_var, switch_var)
    VALUES (@ver_id, N'ACTION', N'fetch_page', @a_fetch, NULL, NULL, NULL, NULL, NULL);
    SET @n_fetch = SCOPE_IDENTITY();

    INSERT INTO wf.workflow_node (workflow_version_id, node_type, node_key, workflow_action_id, repeat_count, condition_ref_node_key, switch_ref_node_key, condition_var, switch_var)
    VALUES (@ver_id, N'ACTION', N'publish', @a_publish, NULL, NULL, NULL, NULL, NULL);
    SET @n_publish = SCOPE_IDENTITY();

    INSERT INTO wf.workflow_edge (parent_node_id, child_node_id, child_order, branch_kind, switch_case_value, is_default)
    VALUES
      (@n_root, @n_load, 0, N'SEQUENCE', NULL, 0),
      (@n_root, @n_par, 1, N'SEQUENCE', NULL, 0),
      (@n_root, @n_repeat, 2, N'SEQUENCE', NULL, 0),
      (@n_root, @n_while, 3, N'SEQUENCE', NULL, 0),
      (@n_root, @n_publish, 4, N'SEQUENCE', NULL, 0),
      (@n_par, @n_if, 0, N'PARALLEL', NULL, 0),
      (@n_par, @n_switch, 1, N'PARALLEL', NULL, 0),
      (@n_if, @n_qc, 0, N'THEN', NULL, 0),
      (@n_if, @n_skip, 1, N'ELSE', NULL, 0),
      (@n_switch, @n_norm_a, 0, N'CASE', 1, 0),
      (@n_switch, @n_norm_b, 1, N'CASE', 2, 0),
      (@n_switch, @n_norm_def, 2, N'DEFAULT', NULL, 1),
      (@n_repeat, @n_align, 0, N'BODY', NULL, 0),
      (@n_while, @n_fetch, 0, N'BODY', NULL, 0);

    UPDATE wf.workflow_version
    SET root_node_id = @n_root
    WHERE id = @ver_id;

    INSERT INTO wf.workflow_input_template (workflow_node_id, template_json)
    VALUES
      (@n_load, N'{"stage":"load","sampleId":"${var.sampleId}","seqIdx":${ctx.sequenceIndex}}'),
      (@n_qc, N'{"task":"qc","shouldRun":${var.shouldRunQc},"parallelIdx":${ctx.parallelIndex}}'),
      (@n_skip, N'{"task":"qc_skip","shouldRun":${var.shouldRunQc}}'),
      (@n_norm_a, N'{"mode":${var.mode},"branch":"A","parallelIdx":${ctx.parallelIndex}}'),
      (@n_norm_b, N'{"mode":${var.mode},"branch":"B","parallelIdx":${ctx.parallelIndex}}'),
      (@n_norm_def, N'{"mode":${var.mode},"branch":"DEFAULT","parallelIdx":${ctx.parallelIndex}}'),
      (@n_align, N'{"task":"align","iteration":${ctx.iterationNo}}'),
      (@n_fetch, N'{"task":"fetch","iteration":${ctx.iterationNo},"hasMoreBefore":${var.hasMorePages}}'),
      (@n_publish, N'{"task":"publish","sampleId":"${var.sampleId}"}');

    INSERT INTO wf.workflow_input_binding (workflow_node_id, target_json_path, source_expr, is_required)
    VALUES
      (@n_publish, N'$.modeFinal', N'${var.mode}', 0),
      (@n_publish, N'$.qcDecision', N'${var.shouldRunQc}', 0),
      (@n_publish, N'$.pagesRemaining', N'${var.hasMorePages}', 0);

    INSERT INTO wf.variable_output_binding (workflow_node_id, var_name, source_kind, source_json_path)
    VALUES
      (@n_load, N'shouldRunQc', N'result_code', NULL),
      (@n_fetch, N'hasMorePages', N'result_code', NULL);

    PRINT N'Seed complete: DelphiTreeFlow created.';
END
GO

/* ---- Optional execution notes ----

Suggested instance context_json:
  {"sampleId":"S-001","mode":2,"shouldRunQc":1,"hasMorePages":1}

Expected worker result-code behavior for a deterministic walkthrough:
  - load_input: return 1 (THEN branch)
  - fetch_page: return 1 first, then 0 (terminate WHILE)
  - all others: return 1

This produces:
  - IF -> qc_task
  - SWITCH(mode=2) -> normalize_b
  - REPEAT body align_chunk exactly 3 iterations
  - WHILE body fetch_page exactly 2 iterations
*/

