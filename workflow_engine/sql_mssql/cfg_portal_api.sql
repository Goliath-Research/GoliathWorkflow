/*
  Portal-facing DomainProgram tree CRUD against cfg.domain_program.
  JSON parameters and columns use native json (aligned with wf.* APIs).
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
    SELECT TOP 1
           id,
           name,
           version,
           status,
           content_hash,
           document_json,
           CAST(NULL AS json) AS secret_redacted,
           CAST(
               CONCAT(
                   N'{"compiledWorkflowVersionId":',
                   COALESCE(CAST(compiled_workflow_version_id AS nvarchar(32)), N'null'),
                   N'}'
               ) AS json
           ) AS extra
    FROM cfg.domain_program
    WHERE name = @name AND (@version IS NULL OR version = @version)
    ORDER BY id DESC;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_upsert_domain_program
    @name nvarchar(256),
    @version nvarchar(64),
    @status varchar(32),
    @document_json json
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
    SELECT TOP 1
           id,
           name,
           version,
           status,
           content_hash,
           document_json,
           CAST(NULL AS json) AS secret_redacted,
           CAST(
               CONCAT(
                   N'{"implementationStatus":"',
                   implementation_status,
                   N'"}'
               ) AS json
           ) AS extra
    FROM cfg.action_definition
    WHERE name = @name AND (@version IS NULL OR version = @version)
    ORDER BY id DESC;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_set_study_group
    @study_row_id bigint,
    @role varchar(32),
    @label nvarchar(128),
    @list_filename nvarchar(256)
AS
BEGIN
    SET NOCOUNT ON;
    EXEC cfg.cfg_repo_set_study_group
        @study_row_id = @study_row_id,
        @role = @role,
        @label = @label,
        @list_filename = @list_filename;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_set_study_group_members
    @study_group_id bigint,
    @members_json json
AS
BEGIN
    SET NOCOUNT ON;
    EXEC cfg.cfg_repo_set_study_group_members
        @study_group_id = @study_group_id,
        @members_json = @members_json;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_study_groups
    @study_row_id bigint
AS
BEGIN
    SET NOCOUNT ON;
    EXEC cfg.cfg_repo_list_study_groups @study_row_id = @study_row_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_study_group_members
    @study_group_id bigint
AS
BEGIN
    SET NOCOUNT ON;
    EXEC cfg.cfg_repo_list_study_group_members @study_group_id = @study_group_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_materialize_study_lists
    @study_row_id bigint,
    @work_root nvarchar(512) = N'/work'
AS
BEGIN
    SET NOCOUNT ON;
    EXEC cfg.cfg_repo_materialize_study_lists
        @study_row_id = @study_row_id,
        @work_root = @work_root;
END
GO

/* Picker: portal samples (+ optional lab runs) for study enrollment UI. */
CREATE OR ALTER PROCEDURE portal.sp_list_samples_for_study_enrollment
    @customer_id int = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        s.ID AS portal_sample_id,
        s.PatientID,
        s.CustomerID,
        s.DiseaseID,
        ls.ID AS lab_sample_id,
        ls.Sample AS processing_sample_key,
        ls.BatchID
    FROM portal.Samples s
    LEFT JOIN portal.LabSamples ls ON ls.SampleID = s.ID
    WHERE (@customer_id IS NULL OR s.CustomerID = @customer_id)
    ORDER BY s.ID, ls.ID;
END
GO

/*
  Storage accounts + credentials (DB SoT for EpiPortal).
  Lab/infra admins upsert+publish; list/get never return secret bodies.
  RBAC enforcement lives in EpiPortal (lab_admin vs infrastructure_admin).
*/

CREATE OR ALTER PROCEDURE portal.sp_list_storage_endpoints
    @published_only bit = 1
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        e.id,
        e.name,
        e.version,
        e.status,
        e.content_hash,
        e.provider,
        e.credential_name,
        e.location_json
    FROM cfg.storage_endpoint e
    WHERE (@published_only = 0 OR e.status = 'published')
    ORDER BY e.name, e.version;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_storage_endpoint
    @name nvarchar(256),
    @version nvarchar(64) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 1
        e.id,
        e.name,
        e.version,
        e.status,
        e.content_hash,
        e.provider,
        e.credential_name,
        e.location_json
    FROM cfg.storage_endpoint e
    WHERE e.name = @name AND (@version IS NULL OR e.version = @version)
    ORDER BY e.id DESC;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_upsert_storage_endpoint
    @name nvarchar(256),
    @version nvarchar(64),
    @status varchar(32),
    @location_json json,
    @provider nvarchar(64) = NULL,
    @credential_name nvarchar(256) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    EXEC cfg.cfg_repo_upsert
        @kind = N'storage_endpoint',
        @name = @name,
        @version = @version,
        @status = @status,
        @document_json = @location_json,
        @provider = @provider,
        @credential_name = @credential_name;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_publish_storage_endpoint
    @name nvarchar(256),
    @version nvarchar(64)
AS
BEGIN
    SET NOCOUNT ON;
    EXEC cfg.cfg_repo_publish
        @kind = N'storage_endpoint',
        @name = @name,
        @version = @version;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_credentials
    @published_only bit = 1
AS
BEGIN
    SET NOCOUNT ON;
    /* Redacted: no secret_json */
    SELECT
        c.id,
        c.name,
        c.version,
        c.status,
        c.content_hash,
        c.provider,
        c.auth_mode
    FROM cfg.credential c
    WHERE (@published_only = 0 OR c.status = 'published')
    ORDER BY c.name, c.version;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_credential
    @name nvarchar(256),
    @version nvarchar(64) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    /* Redacted: never return secret_json to portal list/get */
    SELECT TOP 1
        c.id,
        c.name,
        c.version,
        c.status,
        c.content_hash,
        c.provider,
        c.auth_mode
    FROM cfg.credential c
    WHERE c.name = @name AND (@version IS NULL OR c.version = @version)
    ORDER BY c.id DESC;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_upsert_credential
    @name nvarchar(256),
    @version nvarchar(64),
    @status varchar(32),
    @secret_json json,
    @provider nvarchar(64) = NULL,
    @auth_mode nvarchar(64) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @am nvarchar(64) = @auth_mode;
    IF @am IS NULL
        SET @am = JSON_VALUE(CONVERT(nvarchar(max), @secret_json), '$.authMode');
    EXEC cfg.cfg_repo_upsert
        @kind = N'credential',
        @name = @name,
        @version = @version,
        @status = @status,
        @secret_json = @secret_json,
        @provider = @provider,
        @auth_mode = @am;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_publish_credential
    @name nvarchar(256),
    @version nvarchar(64)
AS
BEGIN
    SET NOCOUNT ON;
    EXEC cfg.cfg_repo_publish
        @kind = N'credential',
        @name = @name,
        @version = @version;
END
GO
