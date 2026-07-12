/*
  Portal-facing DomainProgram tree CRUD against cfg.domain_program.
*/
CREATE OR ALTER PROCEDURE portal.sp_list_domain_programs
    @published_only bit = 0
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id, name, version, status, content_hash
    FROM cfg.domain_program
    WHERE (@published_only = 0 OR status = 'published')
    ORDER BY name, version;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_domain_program
    @name nvarchar(256),
    @version nvarchar(64) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 1 id, name, version, status, content_hash, document_json AS document_json,
           CAST(NULL AS nvarchar(max)) AS secret_redacted,
           CONCAT(N'{"compiledWorkflowVersionId":', COALESCE(CAST(compiled_workflow_version_id AS nvarchar(32)), N'null'), N'}') AS extra
    FROM cfg.domain_program
    WHERE name = @name AND (@version IS NULL OR version = @version)
    ORDER BY id DESC;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_upsert_domain_program
    @name nvarchar(256),
    @version nvarchar(64),
    @status varchar(32),
    @document_json nvarchar(max)
AS
BEGIN
    SET NOCOUNT ON;
    EXEC cfg.cfg_repo_upsert
        @kind = N'domain_program',
        @name = @name,
        @version = @version,
        @status = @status,
        @document_json = @document_json;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_cfg_actions
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id, name, version, status, content_hash
    FROM cfg.action_definition
    ORDER BY name, version;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_cfg_action
    @name nvarchar(256),
    @version nvarchar(64) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 1 id, name, version, status, content_hash, document_json,
           CAST(NULL AS nvarchar(max)) AS secret_redacted,
           CONCAT(N'{"implementationStatus":"', implementation_status, N'"}') AS extra
    FROM cfg.action_definition
    WHERE name = @name AND (@version IS NULL OR version = @version)
    ORDER BY id DESC;
END
GO
