/*
  MethylPipeline wf schema - Monte Carlo workflow support (additive migration).

  Purpose:
  - Persist Monte Carlo plan metadata per workflow instance.
  - Persist run descriptors for both MC phases:
      1) feature stability search
      2) post-model quality metrics
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'wf.monte_carlo_plan', N'U') IS NULL
BEGIN
    CREATE TABLE wf.monte_carlo_plan (
        workflow_instance_id    BIGINT NOT NULL PRIMARY KEY,
        base_project_path       NVARCHAR(1024) NULL,
        layout_name             NVARCHAR(64) NOT NULL CONSTRAINT DF_mc_plan_layout DEFAULT (N'binary'),
        seed                    INT NULL,
        feature_iterations      INT NOT NULL CONSTRAINT DF_mc_plan_feat DEFAULT (0),
        quality_iterations      INT NOT NULL CONSTRAINT DF_mc_plan_qual DEFAULT (0),
        config_json             NVARCHAR(MAX) NULL,
        created_at_utc          DATETIME2(7) NOT NULL CONSTRAINT DF_mc_plan_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc          DATETIME2(7) NOT NULL CONSTRAINT DF_mc_plan_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_mc_plan_instance FOREIGN KEY (workflow_instance_id)
            REFERENCES wf.workflow_instance(id) ON DELETE CASCADE
    );
END
GO

IF OBJECT_ID(N'wf.monte_carlo_run', N'U') IS NULL
BEGIN
    CREATE TABLE wf.monte_carlo_run (
        id                      BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        workflow_instance_id    BIGINT NOT NULL,
        run_id                  NVARCHAR(128) NOT NULL,
        iteration_no            INT NOT NULL,
        phase_name              NVARCHAR(32) NOT NULL,
        task_config_json        NVARCHAR(MAX) NULL,
        created_at_utc          DATETIME2(7) NOT NULL CONSTRAINT DF_mc_run_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc          DATETIME2(7) NOT NULL CONSTRAINT DF_mc_run_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_mc_run_instance FOREIGN KEY (workflow_instance_id)
            REFERENCES wf.workflow_instance(id) ON DELETE CASCADE,
        CONSTRAINT CK_mc_run_phase CHECK (phase_name IN (N'feature', N'quality')),
        CONSTRAINT UQ_mc_run_instance_run UNIQUE (workflow_instance_id, run_id)
    );
    CREATE INDEX IX_mc_run_instance_phase ON wf.monte_carlo_run(workflow_instance_id, phase_name, iteration_no);
END
GO

CREATE OR ALTER FUNCTION wf.wf_get_scope_variable_json
(
    @workflow_instance_id BIGINT,
    @start_scope_node_execution_id BIGINT,
    @var_name NVARCHAR(128)
)
RETURNS NVARCHAR(MAX)
AS
BEGIN
    DECLARE @cur BIGINT = ISNULL(@start_scope_node_execution_id, 0);
    DECLARE @v NVARCHAR(MAX);
    DECLARE @parent BIGINT;

    WHILE 1 = 1
    BEGIN
        SELECT @v = sv.value_json
        FROM wf.scope_variable AS sv
        WHERE sv.workflow_instance_id = @workflow_instance_id
          AND sv.scope_node_execution_id = @cur
          AND sv.var_name = @var_name;

        IF @v IS NOT NULL
            RETURN @v;

        IF @cur = 0
            BREAK;

        SELECT @parent = ne.parent_node_execution_id
        FROM wf.node_execution AS ne
        WHERE ne.id = @cur;

        SET @cur = ISNULL(@parent, 0);
    END

    RETURN NULL;
END;
GO

CREATE OR ALTER FUNCTION wf.wf_get_scope_variable_int
(
    @workflow_instance_id BIGINT,
    @start_scope_node_execution_id BIGINT,
    @var_name NVARCHAR(128)
)
RETURNS INT
AS
BEGIN
    DECLARE @raw NVARCHAR(MAX) = wf.wf_get_scope_variable_json(
        @workflow_instance_id, @start_scope_node_execution_id, @var_name
    );
    DECLARE @trimmed NVARCHAR(MAX);
    DECLARE @v INT;

    IF @raw IS NULL
        RETURN NULL;

    SET @trimmed = LTRIM(RTRIM(@raw));
    IF LEN(@trimmed) >= 2 AND LEFT(@trimmed, 1) = N'"' AND RIGHT(@trimmed, 1) = N'"'
        SET @trimmed = SUBSTRING(@trimmed, 2, LEN(@trimmed) - 2);

    SET @v = TRY_CONVERT(INT, @trimmed);
    RETURN @v;
END;
GO

