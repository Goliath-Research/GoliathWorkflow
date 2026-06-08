/*
  MethylPipeline wf schema — canonical JSON-value encoding (additive).

  Problem:
    wf.scope_variable.value_json is designed to store a JSON *value* (not a JSON *object
    wrapping* a value). The JSON encoding IS the type signal:

      integer  → bare number   e.g. 42
      float    → bare number   e.g. 3.14
      boolean  → bare keyword  e.g. true / false
      null     → bare keyword  null
      string   → quoted JSON   e.g. "hello"
      array    → JSON array    e.g. ["a","b"]
      object   → JSON object   e.g. {"k":"v"}

    OPENJSON already provides this type discriminator (type 0=null, 1=string, 2=number,
    3=bool, 4=array, 5=object), so no {"value":…,"type":"…"} wrapper is needed.

    The bug is that multiple write-paths duplicated the number-vs-string decision with
    slightly different logic, leading to integers occasionally stored as JSON strings
    ("42" instead of 42).  wf_get_scope_variable_int then needed an unquoting hack.

  Fix:
    - wf.wf_json_encode_scalar      single canonical encoder for a raw scalar value
    - wf.wf_json_encode_openjson    single canonical encoder from OPENJSON output columns
    - wf_get_scope_variable_int     simplified: no unquoting hack, strict JSON number parse
    - wf_foreach_bind_iteration     replace ad-hoc type switch with wf_json_encode_openjson
    - wf_apply_output_bindings      replace ad-hoc integer check with wf_json_encode_scalar
    - wf_sql_runtime_parity init    replace type switch with wf_json_encode_openjson

  Deploy AFTER wf_sql_foreach_support.sql.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'wf.scope_variable', N'U') IS NULL
BEGIN
    RAISERROR(N'Prerequisite missing: deploy wf_scope_variables first.', 16, 1);
    RETURN;
END
GO

/*
  wf_json_encode_scalar
  ---------------------
  Encodes a raw T-SQL string that was extracted from JSON via JSON_VALUE
  (which strips the JSON encoding) back into a proper JSON value fragment.

  Rules:
    - NULL                 → 'null'
    - Bare integer string  → bare number literal   (42 not "42")
    - Bare decimal string  → bare number literal   (3.14 not "3.14")
    - 'true'/'false'       → bare boolean literal
    - Anything else        → JSON-quoted string
*/
CREATE OR ALTER FUNCTION wf.wf_json_encode_scalar(@raw_value NVARCHAR(MAX))
RETURNS NVARCHAR(MAX)
AS
BEGIN
    IF @raw_value IS NULL
        RETURN N'null';

    DECLARE @trimmed NVARCHAR(MAX) = LTRIM(RTRIM(@raw_value));

    IF @trimmed = N'true' OR @trimmed = N'false'
        RETURN @trimmed;

    DECLARE @as_bigint BIGINT = TRY_CONVERT(BIGINT, @trimmed);
    IF @as_bigint IS NOT NULL AND CAST(@as_bigint AS NVARCHAR(50)) = @trimmed
        RETURN @trimmed;

    DECLARE @as_float FLOAT = TRY_CONVERT(FLOAT, @trimmed);
    IF @as_float IS NOT NULL
    BEGIN
        DECLARE @rounded NVARCHAR(50) = CAST(@as_float AS NVARCHAR(50));
        IF @rounded = @trimmed
            RETURN @trimmed;
    END

    RETURN wf.wf_json_fragment_from_string(@raw_value);
END;
GO

/*
  wf_json_encode_openjson
  -----------------------
  Encodes a value+type pair as returned by OPENJSON into a proper JSON value fragment.
  Pass the parent JSON document and the key to retrieve arrays/objects directly.

  @openjson_value   the [value] column from OPENJSON
  @openjson_type    the [type]  column from OPENJSON (0=null,1=str,2=num,3=bool,4=arr,5=obj)
  @source_json      the source JSON document (used for type 4/5 to retrieve via JSON_QUERY)
  @source_key       the key name within @source_json for array/object retrieval
*/
CREATE OR ALTER FUNCTION wf.wf_json_encode_openjson(
    @openjson_value NVARCHAR(MAX),
    @openjson_type  INT,
    @source_json    NVARCHAR(MAX),
    @source_key     NVARCHAR(128)
)
RETURNS NVARCHAR(MAX)
AS
BEGIN
    IF @openjson_type = 0 OR @openjson_value IS NULL
        RETURN N'null';

    IF @openjson_type = 1
        RETURN wf.wf_json_fragment_from_string(@openjson_value);

    IF @openjson_type = 2
        RETURN @openjson_value;

    IF @openjson_type = 3
        RETURN LOWER(@openjson_value);

    IF @openjson_type IN (4, 5)
    BEGIN
        IF @source_json IS NOT NULL AND @source_key IS NOT NULL
            RETURN JSON_QUERY(@source_json, CONCAT(N'$.', QUOTENAME(@source_key, '"')));
        RETURN @openjson_value;
    END

    RETURN wf.wf_json_fragment_from_string(@openjson_value);
END;
GO

/*
  Simplified wf_get_scope_variable_int: no unquoting hack needed when the write-path
  encodes numbers correctly as bare JSON number literals.
  Keeps backward compatibility: still handles quoted numbers in old data via TRY_CONVERT.
*/
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

    IF @raw IS NULL
        RETURN NULL;

    DECLARE @trimmed NVARCHAR(MAX) = LTRIM(RTRIM(@raw));

    /* Bare JSON number (correct encoding). */
    DECLARE @v INT = TRY_CONVERT(INT, @trimmed);
    IF @v IS NOT NULL
        RETURN @v;

    /* Legacy: JSON string wrapping a number, e.g. "42" stored in old data. */
    IF LEN(@trimmed) >= 2 AND LEFT(@trimmed, 1) = N'"' AND RIGHT(@trimmed, 1) = N'"'
        RETURN TRY_CONVERT(INT, SUBSTRING(@trimmed, 2, LEN(@trimmed) - 2));

    RETURN NULL;
END;
GO

/*
  Replace ad-hoc type CASE in wf_foreach_bind_iteration with wf_json_encode_openjson.
*/
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

    /* JSON_QUERY returns structured values (arrays/objects); JSON_VALUE returns scalars. */
    DECLARE @elem NVARCHAR(MAX) = JSON_QUERY(@coll, @jp);
    DECLARE @is_scalar BIT = 0;

    IF @elem IS NULL
    BEGIN
        SET @elem = wf.wf_json_encode_scalar(JSON_VALUE(@coll, @jp));
        SET @is_scalar = 1;
    END

    IF @elem IS NULL
        SET @elem = N'null';

    /* Store the item variable. */
    EXEC wf.wf_set_scope_variable
        @workflow_instance_id = @workflow_instance_id,
        @scope_node_execution_id = @scope_node_execution_id,
        @var_name = @item_var,
        @value_json = @elem;

    /* Store the index as a bare JSON integer. */
    DECLARE @json_idx json = CAST(@zero_based_index AS NVARCHAR(32));
    EXEC wf.wf_set_scope_variable
        @workflow_instance_id = @workflow_instance_id,
        @scope_node_execution_id = @scope_node_execution_id,
        @var_name = @index_var,
        @value_json = @json_idx;

    /* Flatten object keys into scope. */
    IF @is_scalar = 0 AND @elem IS NOT NULL AND LEFT(LTRIM(@elem), 1) = N'{'
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
                DECLARE @json_val json = wf.wf_json_encode_openjson(@fv, @ft, @elem, @fk);
                EXEC wf.wf_set_scope_variable
                    @workflow_instance_id = @workflow_instance_id,
                    @scope_node_execution_id = @scope_node_execution_id,
                    @var_name = @fk,
                    @value_json = @json_val;
            END
            FETCH NEXT FROM fk INTO @fk, @fv, @ft;
        END
        CLOSE fk;
        DEALLOCATE fk;
    END
END;
GO

/*
  Replace ad-hoc integer check in wf_apply_output_bindings with wf_json_encode_scalar.
*/
CREATE OR ALTER PROCEDURE wf.wf_apply_output_bindings
    @action_execution_id BIGINT,
    @result_code INT,
    @output_json NVARCHAR(MAX) NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @inst BIGINT;
    DECLARE @wn BIGINT;
    DECLARE @parent BIGINT;
    DECLARE @oj NVARCHAR(MAX) = @output_json;

    SELECT @inst = workflow_instance_id,
           @wn = workflow_node_id,
           @parent = parent_node_execution_id
    FROM wf.node_execution
    WHERE id = @action_execution_id;

    IF @wn IS NULL
        RETURN;

    SET @oj = NULLIF(NULLIF(LTRIM(RTRIM(@oj)), N''), N'null');

    DECLARE @scope_exec BIGINT = wf.wf_scope_write_exec_id(@action_execution_id, @parent);

    DECLARE @var_name NVARCHAR(128);
    DECLARE @source_kind VARCHAR(32);
    DECLARE @source_path NVARCHAR(1024);
    DECLARE @frag NVARCHAR(MAX);
    DECLARE @jp NVARCHAR(1024);

    DECLARE bind_cur CURSOR LOCAL FAST_FORWARD FOR
        SELECT var_name, source_kind, source_json_path
        FROM wf.variable_output_binding
        WHERE workflow_node_id = @wn;

    OPEN bind_cur;
    FETCH NEXT FROM bind_cur INTO @var_name, @source_kind, @source_path;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        IF @source_kind = N'result_code'
        BEGIN
            /* result_code is always an integer — store as bare JSON number. */
            SET @frag = CAST(ISNULL(@result_code, 0) AS NVARCHAR(32));
        END
        ELSE IF @source_kind = N'output_path'
        BEGIN
            IF @oj IS NULL OR ISJSON(@oj) <> 1
            BEGIN
                SET @frag = N'null';
            END
            ELSE
            BEGIN
                SET @jp = ISNULL(LTRIM(RTRIM(@source_path)), N'');
                IF @jp = N''
                BEGIN
                    SET @frag = @oj;
                END
                ELSE
                BEGIN
                    IF LEFT(@jp, 1) <> N'$'
                        SET @jp = N'$.' + @jp;

                    SET @frag = JSON_QUERY(@oj, @jp);
                    IF @frag IS NULL
                        SET @frag = wf.wf_json_encode_scalar(JSON_VALUE(@oj, @jp));
                    IF @frag IS NULL
                        SET @frag = N'null';
                END
            END
        END
        ELSE
            SET @frag = N'null';

        EXEC wf.wf_set_scope_variable
            @workflow_instance_id = @inst,
            @scope_node_execution_id = @scope_exec,
            @var_name = @var_name,
            @value_json = @frag;

        FETCH NEXT FROM bind_cur INTO @var_name, @source_kind, @source_path;
    END
    CLOSE bind_cur;
    DEALLOCATE bind_cur;
END;
GO

/*
  Replace ad-hoc type CASE in wf_init_instance_scope_from_context with
  wf_json_encode_openjson so context_json scalars also use canonical encoding.
*/
CREATE OR ALTER PROCEDURE wf.wf_init_instance_scope_from_context
    @workflow_instance_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @ctx NVARCHAR(MAX);
    SELECT @ctx = CAST(context_json AS NVARCHAR(MAX))
    FROM wf.workflow_instance
    WHERE id = @workflow_instance_id;

    DELETE FROM wf.scope_variable
    WHERE workflow_instance_id = @workflow_instance_id
      AND scope_node_execution_id = 0;

    IF @ctx IS NULL OR LTRIM(RTRIM(@ctx)) = N'' OR ISJSON(@ctx) <> 1
        RETURN;

    IF LEFT(LTRIM(@ctx), 1) <> N'{'
        RETURN;

    INSERT INTO wf.scope_variable (workflow_instance_id, scope_node_execution_id, var_name, value_json)
    SELECT
        @workflow_instance_id,
        0,
        j.[key],
        wf.wf_json_encode_openjson(j.[value], j.[type], @ctx, j.[key])
    FROM OPENJSON(@ctx) AS j;
END;
GO

PRINT N'wf_sql_scope_encoding_parity.sql applied.';
GO
