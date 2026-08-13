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
    @context_json json = NULL
AS
BEGIN
    SET NOCOUNT ON;

    /*
      ACTION templates bind ${var.executionScopeId}. Portal SQL starts often skip
      Python finalize_instance_context, so bake a scope key here when absent.
      Prefer a caller-provided id (from finalize); otherwise hash context_json.
    */
    DECLARE @ctx json = COALESCE(@context_json, CAST(N'{}' AS json));
    DECLARE @set_key nvarchar(64) = COALESCE(
        NULLIF(LTRIM(RTRIM(JSON_VALUE(CAST(@ctx AS nvarchar(max)), N'$.executionScopeId'))), N''),
        NULLIF(LTRIM(RTRIM(JSON_VALUE(CAST(@ctx AS nvarchar(max)), N'$.hyperparamSetId'))), N'')
    );
    IF @set_key IS NULL
    BEGIN
        /* HASHBYTES is limited to 8000 bytes; CAST json → nvarchar, then left-truncate. */
        SET @set_key = LOWER(CONVERT(nvarchar(64), HASHBYTES(
            'SHA2_256',
            LEFT(CAST(@ctx AS nvarchar(max)), 4000)
        ), 2));
        SET @set_key = LEFT(@set_key, 32);
        SET @ctx = CAST(JSON_MODIFY(CAST(@ctx AS nvarchar(max)), N'$.executionScopeId', @set_key) AS json);
        SET @ctx = CAST(JSON_MODIFY(CAST(@ctx AS nvarchar(max)), N'$.hyperparamSetId', @set_key) AS json);
    END
    ELSE
    BEGIN
        /* Keep legacy alias in sync when only one side is present (blank = missing). */
        IF NULLIF(LTRIM(RTRIM(JSON_VALUE(CAST(@ctx AS nvarchar(max)), N'$.executionScopeId'))), N'') IS NULL
            SET @ctx = CAST(JSON_MODIFY(CAST(@ctx AS nvarchar(max)), N'$.executionScopeId', @set_key) AS json);
        IF NULLIF(LTRIM(RTRIM(JSON_VALUE(CAST(@ctx AS nvarchar(max)), N'$.hyperparamSetId'))), N'') IS NULL
            SET @ctx = CAST(JSON_MODIFY(CAST(@ctx AS nvarchar(max)), N'$.hyperparamSetId', @set_key) AS json);
    END

    /*
      Study analyte (cfg.study.default_analyte / document regulatory) wins over
      DomainProgram fixture seeds (historically primaryAnalyte=cfdna).
    */
    DECLARE @project_path nvarchar(512) = JSON_VALUE(CAST(@ctx AS nvarchar(max)), N'$.projectPath');
    DECLARE @analyte nvarchar(128) = NULL;
    IF @project_path IS NOT NULL AND OBJECT_ID(N'cfg.study', N'U') IS NOT NULL
    BEGIN
        SELECT TOP 1
            @analyte = COALESCE(
                an.name,
                JSON_VALUE(CAST(s.document_json AS nvarchar(max)), N'$.regulatory.primary_analyte')
            )
        FROM cfg.study AS s
        LEFT JOIN cfg.analyte AS an ON an.id = s.default_analyte_id
        WHERE s.status = 'published'
          AND (
                (s.study_id IS NOT NULL AND CHARINDEX(s.study_id, @project_path) > 0)
             OR (
                    JSON_VALUE(CAST(s.document_json AS nvarchar(max)), N'$.output_base') IS NOT NULL
                AND CHARINDEX(
                        JSON_VALUE(CAST(s.document_json AS nvarchar(max)), N'$.output_base'),
                        @project_path
                    ) = 1
                )
          )
        ORDER BY s.id DESC;
    END
    IF @analyte IS NOT NULL AND LTRIM(RTRIM(@analyte)) <> N''
    BEGIN
        /* Match Python apply_study_analyte: lowercase, hyphen → underscore. */
        SET @analyte = REPLACE(LOWER(LTRIM(RTRIM(@analyte))), N'-', N'_');
        SET @ctx = CAST(JSON_MODIFY(CAST(@ctx AS nvarchar(max)), N'$.primaryAnalyte', @analyte) AS json);
        SET @ctx = CAST(
            JSON_MODIFY(
                CAST(@ctx AS nvarchar(max)),
                N'$.isCfdna',
                CAST(
                    CASE WHEN @analyte IN (N'cfdna', N'cf_dna', N'plasma_cfdna', N'plasma', N'cell_free_dna')
                         THEN 1 ELSE 0 END AS bit
                )
            ) AS json
        );
    END

    DECLARE @created TABLE (id bigint);
    INSERT INTO wf.workflow_instance (workflow_version_id, status, context_json)
    OUTPUT INSERTED.id INTO @created
    VALUES (@version_id, N'CREATED', @ctx);

    DECLARE @instance_id bigint = (SELECT TOP 1 id FROM @created);

    /* Best-effort: register opaque execution_scope when the helper exists. */
    IF OBJECT_ID(N'wf.wf_apply_execution_scope', N'P') IS NOT NULL
    BEGIN
        EXEC wf.wf_apply_execution_scope
            @workflow_instance_id = @instance_id,
            @set_key = @set_key,
            @display_name = NULL,
            @config_json = NULL,
            @persist_extension = 1;
    END

    SELECT id FROM @created;
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_insert_node_execution
    @workflow_instance_id BIGINT,
    @workflow_node_id BIGINT,
    @status VARCHAR(32),
    @attempt_no INT,
    @parent_node_execution_id BIGINT = NULL,
    @iteration_no INT = 0,
    @input_json json = NULL,
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
        @input_json,
        CASE WHEN @set_available_now = 1 THEN SYSUTCDATETIME() ELSE NULL END,
        CASE WHEN @set_started_now = 1 THEN SYSUTCDATETIME() ELSE NULL END
    );
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_update_node_execution_status
    @execution_id BIGINT,
    @status VARCHAR(32),
    @output_json json = NULL,
    @has_result_code BIT = 0,
    @result_code INT = NULL,
    @engine_error_code INT = 0,
    @engine_error_message NVARCHAR(1024) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE wf.node_execution
    SET status = @status,
        output_json = @output_json,
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

CREATE OR ALTER PROCEDURE wf.wf_repo_get_workflow_instance
    @instance_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id, workflow_version_id, status
    FROM wf.workflow_instance
    WHERE id = @instance_id;
END;
GO

CREATE OR ALTER FUNCTION wf.wf_repo_try_latest_task_result_code(
    @instance_id BIGINT,
    @node_key NVARCHAR(128)
)
RETURNS TABLE
AS
RETURN
(
    SELECT TOP (1) CAST(1 AS BIT) AS found, ne.result_code
    FROM wf.node_execution AS ne
    INNER JOIN wf.workflow_node AS wn ON wn.id = ne.workflow_node_id
    WHERE ne.workflow_instance_id = @instance_id
      AND wn.node_key = @node_key
      AND ne.status = N'SUCCEEDED'
    ORDER BY ne.ended_at_utc DESC, ne.id DESC
);
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_set_scope_variable
    @instance_id BIGINT,
    @scope_exec_id BIGINT,
    @var_name NVARCHAR(128),
    @value_json json
AS
BEGIN
    SET NOCOUNT ON;
    /* Live wf.scope_variable.value_json is nvarchar(max); Azure SQL forbids
       implicit json → nvarchar. CONVERT is required (Msg 257). */
    DECLARE @value_text nvarchar(max) = CONVERT(nvarchar(max), @value_json);
    IF EXISTS (
        SELECT 1 FROM wf.scope_variable
        WHERE workflow_instance_id = @instance_id
          AND scope_node_execution_id = @scope_exec_id
          AND var_name = @var_name
    )
        UPDATE wf.scope_variable
        SET value_json = @value_text, updated_at_utc = SYSUTCDATETIME()
        WHERE workflow_instance_id = @instance_id
          AND scope_node_execution_id = @scope_exec_id
          AND var_name = @var_name;
    ELSE
        INSERT INTO wf.scope_variable (workflow_instance_id, scope_node_execution_id, var_name, value_json)
        VALUES (@instance_id, @scope_exec_id, @var_name, @value_text);
END;
GO
