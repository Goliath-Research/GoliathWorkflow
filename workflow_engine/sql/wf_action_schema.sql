/*
  MethylPipeline wf schema - workflow action JSON Schema storage.

  Stores input_json / output_json JSON Schema documents per workflow_action.
  Populated from schemas/tasks/*.schema.json via seed_action_schemas.py.

  Prerequisites:
  - Base wf schema (workflow_action)
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'wf.workflow_action', N'U') IS NULL
BEGIN
    RAISERROR(N'Prerequisite missing: base wf schema not deployed.', 16, 1);
    RETURN;
END
GO

IF OBJECT_ID(N'wf.workflow_action_schema', N'U') IS NULL
BEGIN
    CREATE TABLE wf.workflow_action_schema (
        workflow_action_id    BIGINT NOT NULL,
        direction             VARCHAR(16) NOT NULL,
        schema_json           json NOT NULL,
        schema_id             NVARCHAR(256) NULL,
        updated_at_utc        DATETIME2(7) NOT NULL CONSTRAINT DF_was_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_workflow_action_schema PRIMARY KEY (workflow_action_id, direction),
        CONSTRAINT FK_was_action FOREIGN KEY (workflow_action_id)
            REFERENCES wf.workflow_action(id) ON DELETE CASCADE,
        CONSTRAINT CK_was_direction CHECK (direction IN (N'input', N'output'))
    );
    CREATE INDEX IX_was_action ON wf.workflow_action_schema(workflow_action_id);
END
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_upsert_action_schema
    @action_name NVARCHAR(256),
    @direction NVARCHAR(16),
    @schema_json json,
    @schema_id NVARCHAR(256) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF @action_name IS NULL OR LTRIM(RTRIM(@action_name)) = N''
        OR @direction IS NULL OR @direction NOT IN (N'input', N'output')
        OR @schema_json IS NULL
        RETURN;

    DECLARE @action_id BIGINT = (
        SELECT id FROM wf.workflow_action WHERE action_name = @action_name
    );
    IF @action_id IS NULL
        RETURN;

    IF EXISTS (
        SELECT 1 FROM wf.workflow_action_schema
        WHERE workflow_action_id = @action_id AND direction = @direction
    )
        UPDATE wf.workflow_action_schema
        SET schema_json = @schema_json,
            schema_id = @schema_id,
            updated_at_utc = SYSUTCDATETIME()
        WHERE workflow_action_id = @action_id AND direction = @direction;
    ELSE
        INSERT INTO wf.workflow_action_schema (workflow_action_id, direction, schema_json, schema_id)
        VALUES (@action_id, @direction, @schema_json, @schema_id);

    IF @direction = N'input' AND @schema_id IS NOT NULL
        UPDATE wf.workflow_action
        SET payload_schema_ref = @schema_id
        WHERE id = @action_id;
END;
GO

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
        s.direction,
        s.schema_id,
        s.schema_json
    FROM wf.workflow_action AS a
    INNER JOIN wf.workflow_action_schema AS s
        ON s.workflow_action_id = a.id
    WHERE a.action_name = @action_name
      AND s.direction = @direction
);
GO

CREATE OR ALTER FUNCTION wf.wf_repo_list_actions()
RETURNS TABLE
AS
RETURN
(
    SELECT
        a.action_name,
        a.capability,
        CAST(CASE WHEN si.workflow_action_id IS NOT NULL THEN 1 ELSE 0 END AS bit) AS has_input_schema,
        CAST(CASE WHEN so.workflow_action_id IS NOT NULL THEN 1 ELSE 0 END AS bit) AS has_output_schema
    FROM wf.workflow_action AS a
    LEFT JOIN wf.workflow_action_schema AS si
        ON si.workflow_action_id = a.id AND si.direction = N'input'
    LEFT JOIN wf.workflow_action_schema AS so
        ON so.workflow_action_id = a.id AND so.direction = N'output'
);
GO
