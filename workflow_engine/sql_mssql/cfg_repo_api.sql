/*
  cfg repository API (Azure SQL): upsert / get / list / publish via result sets.
*/
CREATE OR ALTER PROCEDURE cfg.cfg_repo_upsert
    @kind nvarchar(64),
    @name nvarchar(256),
    @version nvarchar(64) = N'1',
    @status varchar(32) = 'draft',
    @document_json nvarchar(max) = NULL,
    @secret_json nvarchar(max) = NULL,
    @provider nvarchar(64) = NULL,
    @auth_mode nvarchar(64) = NULL,
    @credential_name nvarchar(256) = NULL,
    @study_id nvarchar(256) = NULL,
    @implementation_status varchar(32) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @hash nvarchar(128) = CONVERT(nvarchar(128), HASHBYTES('SHA2_256', COALESCE(@document_json, @secret_json, N'{}')), 2);
    DECLARE @ver nvarchar(64) = COALESCE(NULLIF(@version, N''), N'1');
    DECLARE @st varchar(32) = COALESCE(NULLIF(@status, ''), 'draft');
    DECLARE @id bigint;

    IF @kind = N'site'
    BEGIN
        MERGE cfg.site AS t
        USING (SELECT @name AS name, @ver AS version) AS s
        ON t.name = s.name AND t.version = s.version
        WHEN MATCHED THEN UPDATE SET status = @st, content_hash = @hash, document_json = @document_json, updated_at_utc = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (name, version, status, content_hash, document_json)
            VALUES (@name, @ver, @st, @hash, @document_json);
        SELECT id FROM cfg.site WHERE name = @name AND version = @ver;
        RETURN;
    END
    IF @kind = N'pipeline_profile'
    BEGIN
        MERGE cfg.pipeline_profile AS t
        USING (SELECT @name AS name, @ver AS version) AS s
        ON t.name = s.name AND t.version = s.version
        WHEN MATCHED THEN UPDATE SET status = @st, content_hash = @hash, document_json = @document_json, updated_at_utc = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (name, version, status, content_hash, document_json)
            VALUES (@name, @ver, @st, @hash, @document_json);
        SELECT id FROM cfg.pipeline_profile WHERE name = @name AND version = @ver;
        RETURN;
    END
    IF @kind = N'domain_program'
    BEGIN
        MERGE cfg.domain_program AS t
        USING (SELECT @name AS name, @ver AS version) AS s
        ON t.name = s.name AND t.version = s.version
        WHEN MATCHED THEN UPDATE SET status = @st, content_hash = @hash, document_json = @document_json, updated_at_utc = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (name, version, status, content_hash, document_json)
            VALUES (@name, @ver, @st, @hash, @document_json);
        SELECT id FROM cfg.domain_program WHERE name = @name AND version = @ver;
        RETURN;
    END
    IF @kind = N'study'
    BEGIN
        MERGE cfg.study AS t
        USING (SELECT @name AS name, @ver AS version) AS s
        ON t.name = s.name AND t.version = s.version
        WHEN MATCHED THEN UPDATE SET status = @st, content_hash = @hash, document_json = @document_json,
            study_id = COALESCE(@study_id, t.study_id), updated_at_utc = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (name, version, status, content_hash, document_json, study_id)
            VALUES (@name, @ver, @st, @hash, @document_json, @study_id);
        SELECT id FROM cfg.study WHERE name = @name AND version = @ver;
        RETURN;
    END
    IF @kind = N'credential'
    BEGIN
        MERGE cfg.credential AS t
        USING (SELECT @name AS name, @ver AS version) AS s
        ON t.name = s.name AND t.version = s.version
        WHEN MATCHED THEN UPDATE SET status = @st, content_hash = @hash,
            provider = COALESCE(@provider, N'unknown'),
            auth_mode = COALESCE(@auth_mode, N'unknown'),
            secret_json = COALESCE(@secret_json, @document_json),
            updated_at_utc = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (name, version, status, content_hash, provider, auth_mode, secret_json)
            VALUES (@name, @ver, @st, @hash, COALESCE(@provider, N'unknown'), COALESCE(@auth_mode, N'unknown'), COALESCE(@secret_json, @document_json));
        SELECT id FROM cfg.credential WHERE name = @name AND version = @ver;
        RETURN;
    END
    IF @kind = N'storage_endpoint'
    BEGIN
        MERGE cfg.storage_endpoint AS t
        USING (SELECT @name AS name, @ver AS version) AS s
        ON t.name = s.name AND t.version = s.version
        WHEN MATCHED THEN UPDATE SET status = @st, content_hash = @hash,
            provider = COALESCE(@provider, N'unknown'),
            location_json = @document_json,
            credential_name = COALESCE(@credential_name, t.credential_name),
            updated_at_utc = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (name, version, status, content_hash, provider, location_json, credential_name)
            VALUES (@name, @ver, @st, @hash, COALESCE(@provider, N'unknown'), @document_json, @credential_name);
        SELECT id FROM cfg.storage_endpoint WHERE name = @name AND version = @ver;
        RETURN;
    END
    IF @kind = N'storage_profile'
    BEGIN
        MERGE cfg.storage_profile AS t
        USING (SELECT @name AS name, @ver AS version) AS s
        ON t.name = s.name AND t.version = s.version
        WHEN MATCHED THEN UPDATE SET status = @st, content_hash = @hash, document_json = @document_json, updated_at_utc = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (name, version, status, content_hash, document_json)
            VALUES (@name, @ver, @st, @hash, @document_json);
        SELECT id FROM cfg.storage_profile WHERE name = @name AND version = @ver;
        RETURN;
    END
    IF @kind = N'reference_asset'
    BEGIN
        MERGE cfg.reference_asset AS t
        USING (SELECT @name AS name, @ver AS version) AS s
        ON t.name = s.name AND t.version = s.version
        WHEN MATCHED THEN UPDATE SET status = @st, content_hash = @hash, document_json = @document_json, updated_at_utc = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (name, version, status, content_hash, document_json)
            VALUES (@name, @ver, @st, @hash, @document_json);
        SELECT id FROM cfg.reference_asset WHERE name = @name AND version = @ver;
        RETURN;
    END
    IF @kind = N'action_definition'
    BEGIN
        MERGE cfg.action_definition AS t
        USING (SELECT @name AS name, @ver AS version) AS s
        ON t.name = s.name AND t.version = s.version
        WHEN MATCHED THEN UPDATE SET status = @st, content_hash = @hash, document_json = @document_json,
            implementation_status = COALESCE(@implementation_status, 'present'),
            updated_at_utc = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (name, version, status, content_hash, document_json, implementation_status)
            VALUES (@name, @ver, @st, @hash, @document_json, COALESCE(@implementation_status, 'present'));
        SELECT id FROM cfg.action_definition WHERE name = @name AND version = @ver;
        RETURN;
    END;

    RAISERROR(N'unknown cfg kind', 16, 1);
    RETURN;
END
GO

CREATE OR ALTER PROCEDURE cfg.cfg_repo_publish
    @kind nvarchar(64),
    @name nvarchar(256),
    @version nvarchar(64)
AS
BEGIN
    SET NOCOUNT ON;
    IF @kind = N'site' BEGIN UPDATE cfg.site SET status = 'published', updated_at_utc = SYSUTCDATETIME() WHERE name = @name AND version = @version; SELECT id FROM cfg.site WHERE name = @name AND version = @version; RETURN; END
    IF @kind = N'pipeline_profile' BEGIN UPDATE cfg.pipeline_profile SET status = 'published', updated_at_utc = SYSUTCDATETIME() WHERE name = @name AND version = @version; SELECT id FROM cfg.pipeline_profile WHERE name = @name AND version = @version; RETURN; END
    IF @kind = N'domain_program' BEGIN UPDATE cfg.domain_program SET status = 'published', updated_at_utc = SYSUTCDATETIME() WHERE name = @name AND version = @version; SELECT id FROM cfg.domain_program WHERE name = @name AND version = @version; RETURN; END
    IF @kind = N'study' BEGIN UPDATE cfg.study SET status = 'published', updated_at_utc = SYSUTCDATETIME() WHERE name = @name AND version = @version; SELECT id FROM cfg.study WHERE name = @name AND version = @version; RETURN; END
    IF @kind = N'credential' BEGIN UPDATE cfg.credential SET status = 'published', updated_at_utc = SYSUTCDATETIME() WHERE name = @name AND version = @version; SELECT id FROM cfg.credential WHERE name = @name AND version = @version; RETURN; END
    IF @kind = N'storage_endpoint' BEGIN UPDATE cfg.storage_endpoint SET status = 'published', updated_at_utc = SYSUTCDATETIME() WHERE name = @name AND version = @version; SELECT id FROM cfg.storage_endpoint WHERE name = @name AND version = @version; RETURN; END
    IF @kind = N'storage_profile' BEGIN UPDATE cfg.storage_profile SET status = 'published', updated_at_utc = SYSUTCDATETIME() WHERE name = @name AND version = @version; SELECT id FROM cfg.storage_profile WHERE name = @name AND version = @version; RETURN; END
    IF @kind = N'reference_asset' BEGIN UPDATE cfg.reference_asset SET status = 'published', updated_at_utc = SYSUTCDATETIME() WHERE name = @name AND version = @version; SELECT id FROM cfg.reference_asset WHERE name = @name AND version = @version; RETURN; END
    IF @kind = N'action_definition' BEGIN UPDATE cfg.action_definition SET status = 'published', updated_at_utc = SYSUTCDATETIME() WHERE name = @name AND version = @version; SELECT id FROM cfg.action_definition WHERE name = @name AND version = @version; RETURN; END

    RAISERROR(N'unknown cfg kind', 16, 1);
    RETURN;
END
GO

CREATE OR ALTER PROCEDURE cfg.cfg_repo_set_compiled_version
    @name nvarchar(256),
    @version nvarchar(64),
    @workflow_version_id bigint
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE cfg.domain_program
    SET compiled_workflow_version_id = @workflow_version_id, updated_at_utc = SYSUTCDATETIME()
    WHERE name = @name AND version = @version;
    SELECT id FROM cfg.domain_program WHERE name = @name AND version = @version;
END
GO
