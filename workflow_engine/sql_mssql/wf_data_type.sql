/*
  Explicit wf data type registry (no JSON Schema blobs).

  Types are composed of kinds + fields (+ enum values). Action I/O points at
  wf.data_type via workflow_action.input_type_id / output_type_id.

  The only JSON Schema column that remains intentional elsewhere is portal
  sample-extras / disease field contracts (flexible covariates).

  Prerequisites: base wf.workflow_action
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'wf.workflow_action', N'U') IS NULL
BEGIN
    RAISERROR(N'Prerequisite missing: wf.workflow_action.', 16, 1);
    RETURN;
END
GO

IF OBJECT_ID(N'wf.data_type', N'U') IS NULL
BEGIN
    CREATE TABLE wf.data_type (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        name nvarchar(256) NOT NULL,
        version nvarchar(64) NOT NULL CONSTRAINT DF_wf_dt_version DEFAULT (N'1'),
        status varchar(32) NOT NULL CONSTRAINT DF_wf_dt_status DEFAULT ('published'),
        kind varchar(32) NOT NULL,
        element_type_id bigint NULL,
        content_hash nvarchar(128) NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_wf_dt_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc datetime2(3) NULL,
        CONSTRAINT uq_wf_data_type_name_version UNIQUE (name, version),
        CONSTRAINT ck_wf_data_type_status CHECK (status IN ('draft', 'published', 'retired')),
        CONSTRAINT ck_wf_data_type_kind CHECK (
            kind IN ('string', 'int', 'bool', 'number', 'datetime', 'bytes', 'enum', 'object', 'array', 'any')
        )
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_wf_dt_element_type'
)
    ALTER TABLE wf.data_type WITH CHECK
    ADD CONSTRAINT FK_wf_dt_element_type
        FOREIGN KEY (element_type_id) REFERENCES wf.data_type (id);
GO

IF OBJECT_ID(N'wf.data_type_field', N'U') IS NULL
BEGIN
    CREATE TABLE wf.data_type_field (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        data_type_id bigint NOT NULL,
        field_name nvarchar(256) NOT NULL,
        field_type_id bigint NOT NULL,
        required bit NOT NULL CONSTRAINT DF_wf_dtf_required DEFAULT (0),
        ordinal int NOT NULL CONSTRAINT DF_wf_dtf_ordinal DEFAULT (0),
        CONSTRAINT uq_wf_dtf_name UNIQUE (data_type_id, field_name),
        CONSTRAINT FK_wf_dtf_owner FOREIGN KEY (data_type_id)
            REFERENCES wf.data_type (id) ON DELETE CASCADE,
        CONSTRAINT FK_wf_dtf_field_type FOREIGN KEY (field_type_id)
            REFERENCES wf.data_type (id)
    );
    CREATE INDEX IX_wf_dtf_owner ON wf.data_type_field (data_type_id);
END
GO

IF OBJECT_ID(N'wf.data_type_enum_value', N'U') IS NULL
BEGIN
    CREATE TABLE wf.data_type_enum_value (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        data_type_id bigint NOT NULL,
        value nvarchar(256) NOT NULL,
        ordinal int NOT NULL CONSTRAINT DF_wf_dtev_ordinal DEFAULT (0),
        CONSTRAINT uq_wf_dtev_value UNIQUE (data_type_id, value),
        CONSTRAINT FK_wf_dtev_owner FOREIGN KEY (data_type_id)
            REFERENCES wf.data_type (id) ON DELETE CASCADE
    );
END
GO

/* Action I/O type FKs */
IF COL_LENGTH(N'wf.workflow_action', N'input_type_id') IS NULL
    ALTER TABLE wf.workflow_action ADD input_type_id bigint NULL;
GO
IF COL_LENGTH(N'wf.workflow_action', N'output_type_id') IS NULL
    ALTER TABLE wf.workflow_action ADD output_type_id bigint NULL;
GO
IF COL_LENGTH(N'wf.workflow_action', N'implementation_status') IS NULL
    ALTER TABLE wf.workflow_action ADD implementation_status varchar(32) NULL;
GO
IF COL_LENGTH(N'wf.workflow_action', N'can_pause') IS NULL
    ALTER TABLE wf.workflow_action ADD can_pause bit NOT NULL CONSTRAINT DF_wf_wa_can_pause DEFAULT (0);
GO
IF COL_LENGTH(N'wf.workflow_action', N'can_continue') IS NULL
    ALTER TABLE wf.workflow_action ADD can_continue bit NOT NULL CONSTRAINT DF_wf_wa_can_continue DEFAULT (0);
GO
IF COL_LENGTH(N'wf.workflow_action', N'can_stop') IS NULL
    ALTER TABLE wf.workflow_action ADD can_stop bit NOT NULL CONSTRAINT DF_wf_wa_can_stop DEFAULT (1);
GO

IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_wf_wa_input_type')
    ALTER TABLE wf.workflow_action WITH CHECK
    ADD CONSTRAINT FK_wf_wa_input_type
        FOREIGN KEY (input_type_id) REFERENCES wf.data_type (id);
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_wf_wa_output_type')
    ALTER TABLE wf.workflow_action WITH CHECK
    ADD CONSTRAINT FK_wf_wa_output_type
        FOREIGN KEY (output_type_id) REFERENCES wf.data_type (id);
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_upsert_data_type
    @name nvarchar(256),
    @version nvarchar(64) = N'1',
    @status varchar(32) = 'published',
    @kind varchar(32),
    @element_type_name nvarchar(256) = NULL,
    @element_type_version nvarchar(64) = N'1',
    @content_hash nvarchar(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @ver nvarchar(64) = COALESCE(NULLIF(@version, N''), N'1');
    DECLARE @st varchar(32) = COALESCE(NULLIF(@status, ''), 'published');
    DECLARE @element_id bigint = NULL;

    IF @element_type_name IS NOT NULL AND LTRIM(RTRIM(@element_type_name)) <> N''
        SET @element_id = (
            SELECT TOP (1) id FROM wf.data_type
            WHERE name = @element_type_name
              AND (@element_type_version IS NULL OR version = @element_type_version)
            ORDER BY id DESC
        );

    MERGE wf.data_type AS t
    USING (SELECT @name AS name, @ver AS version) AS s
    ON t.name = s.name AND t.version = s.version
    WHEN MATCHED THEN UPDATE SET
        status = @st,
        kind = @kind,
        element_type_id = COALESCE(@element_id, t.element_type_id),
        content_hash = COALESCE(@content_hash, t.content_hash),
        updated_at_utc = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN INSERT (name, version, status, kind, element_type_id, content_hash)
        VALUES (@name, @ver, @st, @kind, @element_id, @content_hash);

    SELECT id, name, version, status, kind, element_type_id
    FROM wf.data_type
    WHERE name = @name AND version = @ver;
END
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_replace_data_type_fields
    @type_name nvarchar(256),
    @type_version nvarchar(64) = N'1',
    @fields_json json
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @type_id bigint = (
        SELECT TOP (1) id FROM wf.data_type
        WHERE name = @type_name AND version = COALESCE(NULLIF(@type_version, N''), N'1')
        ORDER BY id DESC
    );
    IF @type_id IS NULL
    BEGIN
        RAISERROR(N'wf.data_type not found: %s', 16, 1, @type_name);
        RETURN;
    END;

    DELETE FROM wf.data_type_field WHERE data_type_id = @type_id;

    ;WITH raw AS (
        SELECT
            CAST(JSON_VALUE(j.value, '$.field_name') AS nvarchar(256)) AS field_name,
            CAST(JSON_VALUE(j.value, '$.field_type_name') AS nvarchar(256)) AS field_type_name,
            CAST(COALESCE(JSON_VALUE(j.value, '$.field_type_version'), N'1') AS nvarchar(64)) AS field_type_version,
            CAST(COALESCE(JSON_VALUE(j.value, '$.required'), N'0') AS bit) AS required,
            CAST(COALESCE(JSON_VALUE(j.value, '$.ordinal'), N'0') AS int) AS ordinal
        FROM OPENJSON(CONVERT(nvarchar(max), @fields_json)) AS j
    )
    INSERT INTO wf.data_type_field (data_type_id, field_name, field_type_id, required, ordinal)
    SELECT
        @type_id,
        r.field_name,
        ft.id,
        r.required,
        r.ordinal
    FROM raw r
    CROSS APPLY (
        SELECT TOP (1) t.id
        FROM wf.data_type t
        WHERE t.name = r.field_type_name
          AND t.version = r.field_type_version
        ORDER BY t.id DESC
    ) ft
    WHERE r.field_name IS NOT NULL AND r.field_type_name IS NOT NULL;

    SELECT id, data_type_id, field_name, field_type_id, required, ordinal
    FROM wf.data_type_field
    WHERE data_type_id = @type_id
    ORDER BY ordinal, field_name;
END
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_replace_data_type_enum_values
    @type_name nvarchar(256),
    @type_version nvarchar(64) = N'1',
    @values_json json
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @type_id bigint = (
        SELECT TOP (1) id FROM wf.data_type
        WHERE name = @type_name AND version = COALESCE(NULLIF(@type_version, N''), N'1')
        ORDER BY id DESC
    );
    IF @type_id IS NULL
    BEGIN
        RAISERROR(N'wf.data_type not found: %s', 16, 1, @type_name);
        RETURN;
    END;

    DELETE FROM wf.data_type_enum_value WHERE data_type_id = @type_id;

    INSERT INTO wf.data_type_enum_value (data_type_id, value, ordinal)
    SELECT
        @type_id,
        CAST(j.[value] AS nvarchar(256)),
        CAST(j.[key] AS int)
    FROM OPENJSON(CONVERT(nvarchar(max), @values_json)) AS j;

    SELECT id, data_type_id, value, ordinal
    FROM wf.data_type_enum_value
    WHERE data_type_id = @type_id
    ORDER BY ordinal, value;
END
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_bind_action_types
    @action_name nvarchar(256),
    @input_type_name nvarchar(256) = NULL,
    @output_type_name nvarchar(256) = NULL,
    @type_version nvarchar(64) = N'1',
    @implementation_status varchar(32) = NULL,
    @can_pause bit = NULL,
    @can_continue bit = NULL,
    @can_stop bit = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @action_id bigint = (
        SELECT id FROM wf.workflow_action WHERE action_name = @action_name
    );
    IF @action_id IS NULL
    BEGIN
        RAISERROR(N'wf.workflow_action not found: %s', 16, 1, @action_name);
        RETURN;
    END;

    DECLARE @in_id bigint = NULL;
    DECLARE @out_id bigint = NULL;
    IF @input_type_name IS NOT NULL AND LTRIM(RTRIM(@input_type_name)) <> N''
        SET @in_id = (
            SELECT TOP (1) id FROM wf.data_type
            WHERE name = @input_type_name AND version = COALESCE(NULLIF(@type_version, N''), N'1')
            ORDER BY id DESC
        );
    IF @output_type_name IS NOT NULL AND LTRIM(RTRIM(@output_type_name)) <> N''
        SET @out_id = (
            SELECT TOP (1) id FROM wf.data_type
            WHERE name = @output_type_name AND version = COALESCE(NULLIF(@type_version, N''), N'1')
            ORDER BY id DESC
        );

    UPDATE wf.workflow_action
    SET input_type_id = COALESCE(@in_id, input_type_id),
        output_type_id = COALESCE(@out_id, output_type_id),
        implementation_status = COALESCE(@implementation_status, implementation_status),
        can_pause = COALESCE(@can_pause, can_pause),
        can_continue = COALESCE(@can_continue, can_continue),
        can_stop = COALESCE(@can_stop, can_stop)
    WHERE id = @action_id;

    SELECT
        a.id,
        a.action_name,
        a.input_type_id,
        a.output_type_id,
        tin.name AS input_type_name,
        tout.name AS output_type_name,
        a.implementation_status,
        a.can_pause,
        a.can_continue,
        a.can_stop
    FROM wf.workflow_action a
    LEFT JOIN wf.data_type tin ON tin.id = a.input_type_id
    LEFT JOIN wf.data_type tout ON tout.id = a.output_type_id
    WHERE a.id = @action_id;
END
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_list_data_types
    @published_only bit = 1
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        t.id,
        t.name,
        t.version,
        t.status,
        t.kind,
        t.element_type_id,
        et.name AS element_type_name,
        t.content_hash,
        t.created_at_utc,
        t.updated_at_utc,
        (
            SELECT COUNT(*) FROM wf.data_type_field f WHERE f.data_type_id = t.id
        ) AS field_count
    FROM wf.data_type t
    LEFT JOIN wf.data_type et ON et.id = t.element_type_id
    WHERE (@published_only = 0 OR t.status = 'published')
    ORDER BY t.name, t.version;
END
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_get_data_type
    @name nvarchar(256),
    @version nvarchar(64) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @type_id bigint = (
        SELECT TOP (1) id FROM wf.data_type
        WHERE name = @name
          AND (@version IS NULL OR version = @version)
        ORDER BY id DESC
    );

    SELECT
        t.id,
        t.name,
        t.version,
        t.status,
        t.kind,
        t.element_type_id,
        et.name AS element_type_name,
        t.content_hash,
        t.created_at_utc,
        t.updated_at_utc
    FROM wf.data_type t
    LEFT JOIN wf.data_type et ON et.id = t.element_type_id
    WHERE t.id = @type_id;

    SELECT
        f.id,
        f.field_name,
        f.field_type_id,
        ft.name AS field_type_name,
        ft.kind AS field_type_kind,
        f.required,
        f.ordinal
    FROM wf.data_type_field f
    INNER JOIN wf.data_type ft ON ft.id = f.field_type_id
    WHERE f.data_type_id = @type_id
    ORDER BY f.ordinal, f.field_name;

    SELECT e.id, e.value, e.ordinal
    FROM wf.data_type_enum_value e
    WHERE e.data_type_id = @type_id
    ORDER BY e.ordinal, e.value;
END
GO

/* Portal wrappers */
IF SCHEMA_ID(N'portal') IS NULL
    EXEC(N'CREATE SCHEMA portal');
GO

CREATE OR ALTER PROCEDURE portal.sp_list_data_types
    @published_only bit = 1
AS
BEGIN
    SET NOCOUNT ON;
    EXEC wf.wf_repo_list_data_types @published_only = @published_only;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_data_type
    @name nvarchar(256),
    @version nvarchar(64) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    EXEC wf.wf_repo_get_data_type @name = @name, @version = @version;
END
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_list_data_type_fields
    @name nvarchar(256),
    @version nvarchar(64) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @type_id bigint = (
        SELECT TOP (1) id FROM wf.data_type
        WHERE name = @name
          AND (@version IS NULL OR version = @version)
        ORDER BY id DESC
    );

    SELECT
        f.id,
        f.field_name,
        f.field_type_id,
        ft.name AS field_type_name,
        ft.kind AS field_type_kind,
        f.required,
        f.ordinal
    FROM wf.data_type_field f
    INNER JOIN wf.data_type ft ON ft.id = f.field_type_id
    WHERE f.data_type_id = @type_id
    ORDER BY f.ordinal, f.field_name;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_data_type_fields
    @name nvarchar(256),
    @version nvarchar(64) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    EXEC wf.wf_repo_list_data_type_fields @name = @name, @version = @version;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_workflow_actions
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        a.id,
        a.action_name,
        a.capability,
        a.execution_mode,
        a.cli_tool,
        a.in_process_handler,
        a.implementation_status,
        a.can_pause,
        a.can_continue,
        a.can_stop,
        a.input_type_id,
        tin.name AS input_type_name,
        a.output_type_id,
        tout.name AS output_type_name
    FROM wf.workflow_action a
    LEFT JOIN wf.data_type tin ON tin.id = a.input_type_id
    LEFT JOIN wf.data_type tout ON tout.id = a.output_type_id
    ORDER BY a.action_name;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_workflow_action
    @action_name nvarchar(256)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        a.id,
        a.action_name,
        a.capability,
        a.execution_mode,
        a.cli_tool,
        a.in_process_handler,
        a.implementation_status,
        a.can_pause,
        a.can_continue,
        a.can_stop,
        a.input_type_id,
        tin.name AS input_type_name,
        a.output_type_id,
        tout.name AS output_type_name
    FROM wf.workflow_action a
    LEFT JOIN wf.data_type tin ON tin.id = a.input_type_id
    LEFT JOIN wf.data_type tout ON tout.id = a.output_type_id
    WHERE a.action_name = @action_name;
END
GO

/* Deprecated: keep get_action_schema for Config Editor, prefer data_type fields.
   When workflow_action_schema rows are absent, synthesize a minimal object schema. */
CREATE OR ALTER FUNCTION wf.wf_repo_get_action_schema
(
    @action_name NVARCHAR(256),
    @direction NVARCHAR(16)
)
RETURNS TABLE
AS
RETURN
(
    SELECT
        a.action_name,
        @direction AS direction,
        CASE WHEN @direction = N'input' THEN tin.name ELSE tout.name END AS schema_id,
        CASE
            WHEN s.schema_json IS NOT NULL THEN s.schema_json
            ELSE CAST(N'{"type":"object","title":"' +
                COALESCE(CASE WHEN @direction = N'input' THEN tin.name ELSE tout.name END, @action_name) +
                N'"}' AS json)
        END AS schema_json
    FROM wf.workflow_action AS a
    LEFT JOIN wf.data_type tin ON tin.id = a.input_type_id
    LEFT JOIN wf.data_type tout ON tout.id = a.output_type_id
    LEFT JOIN wf.workflow_action_schema AS s
        ON s.workflow_action_id = a.id AND s.direction = @direction
    WHERE a.action_name = @action_name
);
GO
