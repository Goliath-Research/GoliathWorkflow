/*
  Example: wire DemoFlow cond/switch nodes to scoped variables.
  Adjust node ids if your DemoFlow definition differs.
*/

SET NOCOUNT ON;
GO

DECLARE @ver_id BIGINT = (
    SELECT TOP (1) wv.id FROM wf.workflow_version wv
    INNER JOIN wf.workflow_def wd ON wd.id = wv.workflow_def_id
    WHERE wd.name = N'DemoFlow' ORDER BY wv.id DESC
);

IF @ver_id IS NULL
BEGIN
    RAISERROR(N'DemoFlow version not found.', 16, 1);
    RETURN;
END

DECLARE @n_cond BIGINT = (SELECT id FROM wf.workflow_node WHERE workflow_version_id = @ver_id AND node_key = N'cond');
DECLARE @n_sw_sel BIGINT = (SELECT id FROM wf.workflow_node WHERE workflow_version_id = @ver_id AND node_key = N'sw_sel');
DECLARE @n_switch BIGINT = (SELECT id FROM wf.workflow_node WHERE workflow_version_id = @ver_id AND node_key = N'switch1');
DECLARE @n_gate_if BIGINT = (SELECT id FROM wf.workflow_node WHERE workflow_version_id = @ver_id AND node_key = N'gate_if');

/* cond ACTION publishes selector for downstream IF/SWITCH */
IF @n_cond IS NOT NULL
BEGIN
    MERGE wf.variable_output_binding AS t
    USING (SELECT @n_cond AS workflow_node_id, N'selector' AS var_name) AS s
    ON (t.workflow_node_id = s.workflow_node_id AND t.var_name = s.var_name)
    WHEN NOT MATCHED THEN
        INSERT (workflow_node_id, var_name, source_kind, source_json_path)
        VALUES (@n_cond, N'selector', N'result_code', NULL);
END

/* sw_sel publishes switchValue */
IF @n_sw_sel IS NOT NULL
BEGIN
    MERGE wf.variable_output_binding AS t
    USING (SELECT @n_sw_sel AS workflow_node_id, N'switchValue' AS var_name) AS s
    ON (t.workflow_node_id = s.workflow_node_id AND t.var_name = s.var_name)
    WHEN NOT MATCHED THEN
        INSERT (workflow_node_id, var_name, source_kind, source_json_path)
        VALUES (@n_sw_sel, N'switchValue', N'result_code', NULL);
END

IF @n_gate_if IS NOT NULL
    UPDATE wf.workflow_node SET condition_var = N'selector' WHERE id = @n_gate_if;

IF @n_switch IS NOT NULL
    UPDATE wf.workflow_node SET switch_var = N'switchValue' WHERE id = @n_switch;

/* Downstream ACTION templates may reference ${var.selector} or ${var.switchValue}
   after the publishing tasks complete (see README). */

PRINT N'Scope variable example bindings applied to DemoFlow.';
GO
