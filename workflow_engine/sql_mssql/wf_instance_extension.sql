/*
  MethylPipeline wf schema - generic instance extension storage (additive migration).

  Optional audit/metadata keyed by (workflow_instance_id, extension_key).
  Extension authors namespace keys (e.g. methylvalidation.plan).

  Prerequisites:
  - Base wf schema (workflow_instance)
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'wf.instance_extension', N'U') IS NULL
BEGIN
    CREATE TABLE wf.instance_extension (
        workflow_instance_id    BIGINT NOT NULL,
        extension_key           NVARCHAR(128) NOT NULL,
        data_json               json NULL,
        created_at_utc          DATETIME2(7) NOT NULL CONSTRAINT DF_ie_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc          DATETIME2(7) NOT NULL CONSTRAINT DF_ie_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_instance_extension PRIMARY KEY (workflow_instance_id, extension_key),
        CONSTRAINT FK_ie_instance FOREIGN KEY (workflow_instance_id)
            REFERENCES wf.workflow_instance(id) ON DELETE CASCADE
    );
    CREATE INDEX IX_ie_instance ON wf.instance_extension(workflow_instance_id);
END
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_upsert_instance_extension
    @instance_id BIGINT,
    @extension_key NVARCHAR(128),
    @data_json json = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF @extension_key IS NULL OR LTRIM(RTRIM(@extension_key)) = N''
        RETURN;

    IF EXISTS (
        SELECT 1 FROM wf.instance_extension
        WHERE workflow_instance_id = @instance_id AND extension_key = @extension_key
    )
        UPDATE wf.instance_extension
        SET data_json = @data_json, updated_at_utc = SYSUTCDATETIME()
        WHERE workflow_instance_id = @instance_id AND extension_key = @extension_key;
    ELSE
        INSERT INTO wf.instance_extension (workflow_instance_id, extension_key, data_json)
        VALUES (@instance_id, @extension_key, @data_json);
END;
GO

CREATE OR ALTER FUNCTION wf.wf_repo_get_instance_extension
(
    @instance_id BIGINT,
    @extension_key NVARCHAR(128)
)
RETURNS json
AS
BEGIN
    DECLARE @data json;

    SELECT @data = ie.data_json
    FROM wf.instance_extension AS ie
    WHERE ie.workflow_instance_id = @instance_id
      AND ie.extension_key = @extension_key;

    RETURN @data;
END;
GO
