/*
  MethylPipeline wf schema - scope variable read-path helpers.

  Provides parent-chain lookup used by placeholder resolution, FOREACH seeding,
  and IF/SWITCH/WHILE condition reads.

  Prerequisites:
  - wf_scope_variables.sql (wf.scope_variable)
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'wf.scope_variable', N'U') IS NULL
BEGIN
    RAISERROR(N'Prerequisite missing: deploy wf_scope_variables.sql first.', 16, 1);
    RETURN;
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
        SELECT @v = wf.wf_json_unbox(CAST(sv.value_json AS NVARCHAR(MAX)))
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
    IF @v IS NOT NULL
        RETURN @v;

    /* JSON boolean literals for IF/WHILE condition_var evaluation. */
    IF LOWER(@trimmed) IN (N'true', N'1')
        RETURN 1;
    IF LOWER(@trimmed) IN (N'false', N'0', N'null')
        RETURN 0;

    RETURN NULL;
END;
GO
