/*
  MethylPipeline wf schema - align JSON payload columns to native json (Azure SQL).

  Azure json is RFC 4627: objects and arrays only. Scalars (42, "hello", true, null)
  are valid JSON values (RFC 8259) and valid PostgreSQL jsonb, but Msg 13609 on
  CAST/ALTER to json:

      Unexpected character '"' at position 0
      Unexpected character '1' at position 0

  Before ALTER, scalar fragments are boxed as {"$mp.v": <value>}. Readers unbox via
  wf.wf_json_unbox so SQL still sees the original fragment. Objects/arrays stay as-is.

  Safe to re-run: skips ALTER when the column is already json.
  Prerequisites: wf_scope_variables.sql (or MethylPipeline.sql fragment helper).
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

CREATE OR ALTER FUNCTION wf.wf_json_box(@frag nvarchar(max))
RETURNS json
AS
BEGIN
    IF @frag IS NULL
        RETURN CAST(N'{"$mp.v":null}' AS json);

    DECLARE @t nvarchar(max) = LTRIM(RTRIM(@frag));
    IF ISJSON(@t, OBJECT) = 1 OR ISJSON(@t, ARRAY) = 1
        RETURN CAST(@t AS json);

    IF ISJSON(@t, VALUE) = 1
        RETURN CAST(CONCAT(N'{"$mp.v":', @t, N'}') AS json);

    RETURN CAST(CONCAT(N'{"$mp.v":', wf.wf_json_fragment_from_string(@t), N'}') AS json);
END;
GO

CREATE OR ALTER FUNCTION wf.wf_json_unbox(@doc nvarchar(max))
RETURNS nvarchar(max)
AS
BEGIN
    IF @doc IS NULL
        RETURN NULL;

    IF ISJSON(@doc, OBJECT) <> 1
        RETURN @doc;

    DECLARE @val nvarchar(max);
    DECLARE @typ int;
    SELECT @val = [value], @typ = [type]
    FROM OPENJSON(@doc)
    WHERE [key] = N'$mp.v';

    IF @typ IS NULL
        RETURN @doc;
    IF @typ = 0
        RETURN N'null';
    IF @typ = 1
        RETURN wf.wf_json_fragment_from_string(@val);
    IF @typ = 2
        RETURN @val;
    IF @typ = 3
        RETURN LOWER(@val);
    IF @typ IN (4, 5)
        RETURN JSON_QUERY(@doc, N'$."$mp.v"');
    RETURN @val;
END;
GO

IF OBJECT_ID(N'wf.scope_variable', N'U') IS NOT NULL
   AND EXISTS (
       SELECT 1
       FROM sys.columns AS c
       INNER JOIN sys.types AS t ON t.user_type_id = c.user_type_id
       WHERE c.object_id = OBJECT_ID(N'wf.scope_variable')
         AND c.name = N'value_json'
         AND t.name <> N'json'
   )
BEGIN
    UPDATE wf.scope_variable
    SET value_json = CONVERT(nvarchar(max), wf.wf_json_box(CAST(value_json AS nvarchar(max))));

    ALTER TABLE wf.scope_variable
        ALTER COLUMN value_json json NOT NULL;
    PRINT N'Aligned wf.scope_variable.value_json to json.';
END
GO

IF OBJECT_ID(N'wf.execution_context', N'U') IS NOT NULL
   AND EXISTS (
       SELECT 1
       FROM sys.columns AS c
       INNER JOIN sys.types AS t ON t.user_type_id = c.user_type_id
       WHERE c.object_id = OBJECT_ID(N'wf.execution_context')
         AND c.name = N'context_value_json'
         AND t.name <> N'json'
   )
BEGIN
    UPDATE wf.execution_context
    SET context_value_json = CONVERT(nvarchar(max), wf.wf_json_box(CAST(context_value_json AS nvarchar(max))))
    WHERE context_value_json IS NOT NULL;

    ALTER TABLE wf.execution_context
        ALTER COLUMN context_value_json json NULL;
    PRINT N'Aligned wf.execution_context.context_value_json to json.';
END
GO

CREATE OR ALTER PROCEDURE wf.wf_seed_execution_context
    @node_execution_id BIGINT,
    @workflow_instance_id BIGINT,
    @workflow_node_id BIGINT,
    @parent_node_execution_id BIGINT NULL,
    @iteration_no INT,
    @sequence_index INT NULL,
    @parallel_index INT NULL
AS
BEGIN
    SET NOCOUNT ON;

    DELETE FROM wf.execution_context WHERE node_execution_id = @node_execution_id;

    INSERT INTO wf.execution_context (node_execution_id, context_key, context_value_json)
    VALUES (@node_execution_id, N'ctx.iterationNo', wf.wf_json_box(CAST(@iteration_no AS NVARCHAR(32))));

    IF @sequence_index IS NOT NULL
        INSERT INTO wf.execution_context (node_execution_id, context_key, context_value_json)
        VALUES (@node_execution_id, N'ctx.sequenceIndex', wf.wf_json_box(CAST(@sequence_index AS NVARCHAR(32))));

    IF @parallel_index IS NOT NULL
        INSERT INTO wf.execution_context (node_execution_id, context_key, context_value_json)
        VALUES (@node_execution_id, N'ctx.parallelIndex', wf.wf_json_box(CAST(@parallel_index AS NVARCHAR(32))));

    IF @parent_node_execution_id IS NOT NULL
    BEGIN
        DECLARE @prc INT;
        SELECT @prc = result_code FROM wf.node_execution WHERE id = @parent_node_execution_id;
        INSERT INTO wf.execution_context (node_execution_id, context_key, context_value_json)
        VALUES (@node_execution_id, N'ctx.parent.resultCode', wf.wf_json_box(CAST(@prc AS NVARCHAR(32))));
    END
END;
GO
