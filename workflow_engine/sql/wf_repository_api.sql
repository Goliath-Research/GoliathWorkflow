/*
  MethylPipeline wf schema - T-SQL repository API (middle-tier persistence).
  Dialect-neutral wrappers for WfEngine.Repository.
  Prerequisites: base wf schema (MethylPipeline.sql).
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_set_instance_status
    @instance_id BIGINT,
    @status VARCHAR(32)
AS
BEGIN
    SET NOCOUNT ON;
    IF @status IN (N'COMPLETED', N'FAILED', N'CANCELLED')
        UPDATE wf.workflow_instance
        SET status = @status, completed_at_utc = ISNULL(completed_at_utc, SYSUTCDATETIME())
        WHERE id = @instance_id;
    ELSE IF @status = N'RUNNING'
        UPDATE wf.workflow_instance
        SET status = @status, started_at_utc = ISNULL(started_at_utc, SYSUTCDATETIME())
        WHERE id = @instance_id;
    ELSE
        UPDATE wf.workflow_instance SET status = @status WHERE id = @instance_id;
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_create_workflow_instance
    @version_id BIGINT,
    @context_json NVARCHAR(MAX) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO wf.workflow_instance (workflow_version_id, status, context_json)
    OUTPUT INSERTED.id
    VALUES (@version_id, N'CREATED', CASE WHEN @context_json IS NULL THEN NULL ELSE CAST(@context_json AS json) END);
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_insert_node_execution
    @workflow_instance_id BIGINT,
    @workflow_node_id BIGINT,
    @status VARCHAR(32),
    @attempt_no INT,
    @parent_node_execution_id BIGINT = NULL,
    @iteration_no INT = 0,
    @input_json NVARCHAR(MAX) = NULL,
    @set_available_now BIT = 0,
    @set_started_now BIT = 0
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO wf.node_execution (
        workflow_instance_id, workflow_node_id, status, attempt_no,
        parent_node_execution_id, iteration_no, input_json, available_at_utc, started_at_utc
    )
    OUTPUT INSERTED.id
    VALUES (
        @workflow_instance_id, @workflow_node_id, @status, @attempt_no,
        @parent_node_execution_id, @iteration_no,
        CASE WHEN @input_json IS NULL THEN NULL ELSE CAST(@input_json AS json) END,
        CASE WHEN @set_available_now = 1 THEN SYSUTCDATETIME() ELSE NULL END,
        CASE WHEN @set_started_now = 1 THEN SYSUTCDATETIME() ELSE NULL END
    );
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_update_node_execution_status
    @execution_id BIGINT,
    @status VARCHAR(32),
    @output_json NVARCHAR(MAX) = NULL,
    @has_result_code BIT = 0,
    @result_code INT = NULL,
    @engine_error_code INT = 0,
    @engine_error_message NVARCHAR(1024) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE wf.node_execution
    SET status = @status,
        output_json = CASE WHEN @output_json IS NULL THEN NULL ELSE CAST(@output_json AS json) END,
        ended_at_utc = SYSUTCDATETIME(),
        result_code = CASE WHEN @has_result_code = 1 THEN @result_code ELSE result_code END,
        engine_error_code = CASE WHEN @engine_error_code <> 0 THEN @engine_error_code ELSE engine_error_code END,
        engine_error_message = CASE WHEN @engine_error_code <> 0 THEN @engine_error_message ELSE engine_error_message END
    WHERE id = @execution_id;
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_insert_loop_state
    @workflow_instance_id BIGINT,
    @control_node_id BIGINT,
    @scope_node_execution_id BIGINT,
    @current_iteration INT,
    @repeat_target_count INT
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO wf.loop_state (
        workflow_instance_id, control_node_id, scope_node_execution_id,
        current_iteration, repeat_target_count
    )
    OUTPUT INSERTED.id
    VALUES (@workflow_instance_id, @control_node_id, @scope_node_execution_id, @current_iteration, @repeat_target_count);
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_get_running_instances
    @max_count INT = 50
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@max_count) id FROM wf.workflow_instance WHERE status = N'RUNNING' ORDER BY id;
END;
GO

CREATE OR ALTER FUNCTION wf.wf_repo_try_latest_task_result_code(
    @instance_id BIGINT,
    @node_key NVARCHAR(128)
)
RETURNS TABLE (found BIT, result_code INT)
AS
RETURN (
    SELECT TOP (1) CAST(1 AS BIT), ne.result_code
    FROM wf.node_execution AS ne
    INNER JOIN wf.workflow_node AS wn ON wn.id = ne.workflow_node_id
    WHERE ne.workflow_instance_id = @instance_id
      AND wn.node_key = @node_key
      AND ne.status = N'SUCCEEDED'
    ORDER BY ne.ended_at_utc DESC, ne.id DESC
);
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_upsert_monte_carlo_plan
    @instance_id BIGINT,
    @base_project_path NVARCHAR(1024),
    @layout NVARCHAR(64),
    @seed INT,
    @feature_iterations INT,
    @quality_iterations INT,
    @config_json NVARCHAR(MAX) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS (SELECT 1 FROM wf.monte_carlo_plan WHERE workflow_instance_id = @instance_id)
        UPDATE wf.monte_carlo_plan
        SET base_project_path = @base_project_path, layout_name = @layout, seed = @seed,
            feature_iterations = @feature_iterations, quality_iterations = @quality_iterations,
            config_json = @config_json, updated_at_utc = SYSUTCDATETIME()
        WHERE workflow_instance_id = @instance_id;
    ELSE
        INSERT INTO wf.monte_carlo_plan (
            workflow_instance_id, base_project_path, layout_name, seed,
            feature_iterations, quality_iterations, config_json
        ) VALUES (
            @instance_id, @base_project_path, @layout, @seed,
            @feature_iterations, @quality_iterations, @config_json
        );
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_upsert_monte_carlo_run
    @instance_id BIGINT,
    @run_id NVARCHAR(128),
    @iteration_no INT,
    @phase NVARCHAR(32),
    @task_config_json NVARCHAR(MAX) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS (SELECT 1 FROM wf.monte_carlo_run WHERE workflow_instance_id = @instance_id AND run_id = @run_id)
        UPDATE wf.monte_carlo_run
        SET iteration_no = @iteration_no, phase_name = @phase, task_config_json = @task_config_json,
            updated_at_utc = SYSUTCDATETIME()
        WHERE workflow_instance_id = @instance_id AND run_id = @run_id;
    ELSE
        INSERT INTO wf.monte_carlo_run (workflow_instance_id, run_id, iteration_no, phase_name, task_config_json)
        VALUES (@instance_id, @run_id, @iteration_no, @phase, @task_config_json);
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_set_scope_variable
    @instance_id BIGINT,
    @scope_exec_id BIGINT,
    @var_name NVARCHAR(128),
    @value_json NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS (
        SELECT 1 FROM wf.scope_variable
        WHERE workflow_instance_id = @instance_id
          AND scope_node_execution_id = @scope_exec_id
          AND var_name = @var_name
    )
        UPDATE wf.scope_variable
        SET value_json = @value_json, updated_at_utc = SYSUTCDATETIME()
        WHERE workflow_instance_id = @instance_id
          AND scope_node_execution_id = @scope_exec_id
          AND var_name = @var_name;
    ELSE
        INSERT INTO wf.scope_variable (workflow_instance_id, scope_node_execution_id, var_name, value_json)
        VALUES (@instance_id, @scope_exec_id, @var_name, @value_json);
END;
GO
