/*
  cfg repository API (Azure SQL): upsert / get / list / publish via result sets.
  JSON payloads use native json parameters and columns (same as wf.* procs).
  CONVERT to nvarchar only where a string is required (content hash).
*/
CREATE OR ALTER PROCEDURE cfg.cfg_repo_upsert
    @kind nvarchar(64),
    @name nvarchar(256),
    @version nvarchar(64) = N'1',
    @status varchar(32) = 'draft',
    @document_json json = NULL,
    @secret_json json = NULL,
    @provider nvarchar(64) = NULL,
    @auth_mode nvarchar(64) = NULL,
    @credential_name nvarchar(256) = NULL,
    @study_id nvarchar(256) = NULL,
    @implementation_status varchar(32) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @empty json = CAST(N'{}' AS json);
    DECLARE @doc json = COALESCE(@document_json, @empty);
    DECLARE @sec json = COALESCE(@secret_json, @document_json, @empty);
    -- HASHBYTES needs a string; convert only for hashing, not for storage.
    DECLARE @hash nvarchar(128) = CONVERT(
        nvarchar(128),
        HASHBYTES('SHA2_256', CONVERT(nvarchar(max), COALESCE(@secret_json, @document_json, @empty))),
        2
    );
    DECLARE @ver nvarchar(64) = COALESCE(NULLIF(@version, N''), N'1');
    DECLARE @st varchar(32) = COALESCE(NULLIF(@status, ''), 'draft');

    IF @kind = N'site'
    BEGIN
        MERGE cfg.site AS t
        USING (SELECT @name AS name, @ver AS version) AS s
        ON t.name = s.name AND t.version = s.version
        WHEN MATCHED THEN UPDATE SET status = @st, content_hash = @hash, document_json = @doc, updated_at_utc = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (name, version, status, content_hash, document_json)
            VALUES (@name, @ver, @st, @hash, @doc);
        SELECT id FROM cfg.site WHERE name = @name AND version = @ver;
        RETURN;
    END
    IF @kind = N'pipeline_profile'
    BEGIN
        MERGE cfg.pipeline_profile AS t
        USING (SELECT @name AS name, @ver AS version) AS s
        ON t.name = s.name AND t.version = s.version
        WHEN MATCHED THEN UPDATE SET status = @st, content_hash = @hash, document_json = @doc, updated_at_utc = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (name, version, status, content_hash, document_json)
            VALUES (@name, @ver, @st, @hash, @doc);
        SELECT id FROM cfg.pipeline_profile WHERE name = @name AND version = @ver;
        RETURN;
    END
    IF @kind = N'domain_program'
    BEGIN
        MERGE cfg.domain_program AS t
        USING (SELECT @name AS name, @ver AS version) AS s
        ON t.name = s.name AND t.version = s.version
        WHEN MATCHED THEN UPDATE SET status = @st, content_hash = @hash, document_json = @doc, updated_at_utc = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (name, version, status, content_hash, document_json)
            VALUES (@name, @ver, @st, @hash, @doc);
        SELECT id FROM cfg.domain_program WHERE name = @name AND version = @ver;
        RETURN;
    END
    IF @kind = N'study'
    BEGIN
        MERGE cfg.study AS t
        USING (SELECT @name AS name, @ver AS version) AS s
        ON t.name = s.name AND t.version = s.version
        WHEN MATCHED THEN UPDATE SET status = @st, content_hash = @hash, document_json = @doc,
            study_id = COALESCE(@study_id, t.study_id), updated_at_utc = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (name, version, status, content_hash, document_json, study_id)
            VALUES (@name, @ver, @st, @hash, @doc, @study_id);
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
            secret_json = @sec,
            updated_at_utc = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (name, version, status, content_hash, provider, auth_mode, secret_json)
            VALUES (@name, @ver, @st, @hash, COALESCE(@provider, N'unknown'), COALESCE(@auth_mode, N'unknown'), @sec);
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
            location_json = @doc,
            credential_name = COALESCE(@credential_name, t.credential_name),
            updated_at_utc = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (name, version, status, content_hash, provider, location_json, credential_name)
            VALUES (@name, @ver, @st, @hash, COALESCE(@provider, N'unknown'), @doc, @credential_name);
        SELECT id FROM cfg.storage_endpoint WHERE name = @name AND version = @ver;
        RETURN;
    END
    IF @kind = N'storage_profile'
    BEGIN
        MERGE cfg.storage_profile AS t
        USING (SELECT @name AS name, @ver AS version) AS s
        ON t.name = s.name AND t.version = s.version
        WHEN MATCHED THEN UPDATE SET status = @st, content_hash = @hash, document_json = @doc, updated_at_utc = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (name, version, status, content_hash, document_json)
            VALUES (@name, @ver, @st, @hash, @doc);
        SELECT id FROM cfg.storage_profile WHERE name = @name AND version = @ver;
        RETURN;
    END
    IF @kind = N'reference_asset'
    BEGIN
        MERGE cfg.reference_asset AS t
        USING (SELECT @name AS name, @ver AS version) AS s
        ON t.name = s.name AND t.version = s.version
        WHEN MATCHED THEN UPDATE SET status = @st, content_hash = @hash, document_json = @doc, updated_at_utc = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (name, version, status, content_hash, document_json)
            VALUES (@name, @ver, @st, @hash, @doc);
        SELECT id FROM cfg.reference_asset WHERE name = @name AND version = @ver;
        RETURN;
    END
    IF @kind = N'action_definition'
    BEGIN
        MERGE cfg.action_definition AS t
        USING (SELECT @name AS name, @ver AS version) AS s
        ON t.name = s.name AND t.version = s.version
        WHEN MATCHED THEN UPDATE SET status = @st, content_hash = @hash, document_json = @doc,
            implementation_status = COALESCE(@implementation_status, 'present'),
            updated_at_utc = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (name, version, status, content_hash, document_json, implementation_status)
            VALUES (@name, @ver, @st, @hash, @doc, COALESCE(@implementation_status, 'present'));
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
    DECLARE @def_id bigint;
    DECLARE @program_id bigint;
    DECLARE @hash nvarchar(128);

    SELECT @def_id = workflow_def_id
    FROM wf.workflow_version
    WHERE id = @workflow_version_id;

    IF @def_id IS NULL
    BEGIN
        RAISERROR(N'workflow_version_id not found', 16, 1);
        RETURN;
    END

    UPDATE cfg.domain_program
    SET compiled_workflow_version_id = @workflow_version_id,
        workflow_def_id = @def_id,
        updated_at_utc = SYSUTCDATETIME()
    WHERE name = @name AND version = @version;

    SELECT @program_id = id, @hash = content_hash
    FROM cfg.domain_program
    WHERE name = @name AND version = @version;

    IF @program_id IS NULL
    BEGIN
        RAISERROR(N'domain_program not found', 16, 1);
        RETURN;
    END

    IF NOT EXISTS (
        SELECT 1 FROM cfg.program_publish
        WHERE domain_program_id = @program_id AND workflow_version_id = @workflow_version_id
    )
    BEGIN
        INSERT INTO cfg.program_publish (domain_program_id, workflow_def_id, workflow_version_id, content_hash)
        VALUES (@program_id, @def_id, @workflow_version_id, @hash);
    END

    SELECT id FROM cfg.domain_program WHERE name = @name AND version = @version;
END
GO

CREATE OR ALTER PROCEDURE cfg.cfg_repo_link_action
    @action_name nvarchar(256),
    @version nvarchar(64) = N'1'
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @wa_id bigint = (SELECT id FROM wf.workflow_action WHERE action_name = @action_name);
    IF @wa_id IS NULL
    BEGIN
        RAISERROR(N'wf.workflow_action not found for action_name', 16, 1);
        RETURN;
    END
    UPDATE cfg.action_definition
    SET workflow_action_id = @wa_id, updated_at_utc = SYSUTCDATETIME()
    WHERE name = @action_name AND version = @version;
    IF @@ROWCOUNT = 0
    BEGIN
        RAISERROR(N'cfg.action_definition not found: %s@%s', 16, 1, @action_name, @version);
        RETURN;
    END
    SELECT id, workflow_action_id FROM cfg.action_definition WHERE name = @action_name AND version = @version;
END
GO

CREATE OR ALTER PROCEDURE cfg.cfg_repo_link_study_instance
    @study_row_id bigint,
    @workflow_instance_id bigint,
    @domain_program_id bigint = NULL,
    @pipeline_profile_id bigint = NULL,
    @site_id bigint = NULL,
    @storage_profile_id bigint = NULL
AS
BEGIN
    SET NOCOUNT ON;
    MERGE cfg.study_instance_link AS t
    USING (SELECT @workflow_instance_id AS workflow_instance_id) AS s
    ON t.workflow_instance_id = s.workflow_instance_id
    WHEN MATCHED THEN UPDATE SET
        study_row_id = @study_row_id,
        domain_program_id = COALESCE(@domain_program_id, t.domain_program_id),
        pipeline_profile_id = COALESCE(@pipeline_profile_id, t.pipeline_profile_id),
        site_id = COALESCE(@site_id, t.site_id),
        storage_profile_id = COALESCE(@storage_profile_id, t.storage_profile_id)
    WHEN NOT MATCHED THEN INSERT (
        study_row_id, workflow_instance_id, domain_program_id, pipeline_profile_id, site_id, storage_profile_id
    ) VALUES (
        @study_row_id, @workflow_instance_id, @domain_program_id, @pipeline_profile_id, @site_id, @storage_profile_id
    );
    SELECT id FROM cfg.study_instance_link WHERE workflow_instance_id = @workflow_instance_id;
END
GO

CREATE OR ALTER PROCEDURE cfg.cfg_repo_link_reference_asset
    @asset_name nvarchar(256),
    @version nvarchar(64) = N'1',
    @storage_endpoint_id bigint = NULL,
    @asset_type nvarchar(64) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE cfg.reference_asset
    SET storage_endpoint_id = COALESCE(@storage_endpoint_id, storage_endpoint_id),
        asset_type = COALESCE(@asset_type, asset_type),
        updated_at_utc = SYSUTCDATETIME()
    WHERE name = @asset_name AND version = @version;
    IF @@ROWCOUNT = 0
    BEGIN
        RAISERROR(N'reference_asset not found: %s@%s', 16, 1, @asset_name, @version);
        RETURN;
    END
    SELECT id, storage_endpoint_id, asset_type
    FROM cfg.reference_asset
    WHERE name = @asset_name AND version = @version;
END
GO

CREATE OR ALTER PROCEDURE cfg.cfg_repo_link_site_asset
    @site_id bigint,
    @reference_asset_id bigint,
    @asset_role nvarchar(64)
AS
BEGIN
    SET NOCOUNT ON;
    MERGE cfg.site_reference_asset AS t
    USING (SELECT @site_id AS site_id, @asset_role AS asset_role) AS s
    ON t.site_id = s.site_id AND t.asset_role = s.asset_role
    WHEN MATCHED THEN UPDATE SET reference_asset_id = @reference_asset_id
    WHEN NOT MATCHED THEN INSERT (site_id, reference_asset_id, asset_role)
        VALUES (@site_id, @reference_asset_id, @asset_role);
    SELECT id FROM cfg.site_reference_asset WHERE site_id = @site_id AND asset_role = @asset_role;
END
GO

CREATE OR ALTER PROCEDURE cfg.cfg_repo_set_study_group
    @study_row_id bigint,
    @role varchar(32),
    @label nvarchar(128),
    @list_filename nvarchar(256)
AS
BEGIN
    SET NOCOUNT ON;
    IF @role NOT IN ('control', 'disease')
    BEGIN
        RAISERROR(N'study_group role must be control or disease', 16, 1);
        RETURN;
    END
    IF NOT EXISTS (SELECT 1 FROM cfg.study WHERE id = @study_row_id)
    BEGIN
        RAISERROR(N'cfg.study not found: %I64d', 16, 1, @study_row_id);
        RETURN;
    END
    MERGE cfg.study_group AS t
    USING (SELECT @study_row_id AS study_row_id, @role AS role, @label AS label) AS s
    ON t.study_row_id = s.study_row_id AND t.role = s.role AND t.label = s.label
    WHEN MATCHED THEN UPDATE SET
        list_filename = @list_filename,
        updated_at_utc = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN INSERT (study_row_id, role, label, list_filename)
        VALUES (@study_row_id, @role, @label, @list_filename);
    SELECT id, study_row_id, role, label, list_filename
    FROM cfg.study_group
    WHERE study_row_id = @study_row_id AND role = @role AND label = @label;
END
GO

CREATE OR ALTER PROCEDURE cfg.cfg_repo_set_study_group_members
    @study_group_id bigint,
    @members_json json
AS
BEGIN
    SET NOCOUNT ON;
    IF NOT EXISTS (SELECT 1 FROM cfg.study_group WHERE id = @study_group_id)
    BEGIN
        RAISERROR(N'cfg.study_group not found: %I64d', 16, 1, @study_group_id);
        RETURN;
    END

    DECLARE @resolved TABLE (
        portal_sample_id int NOT NULL,
        lab_sample_id int NULL,
        processing_sample_key nvarchar(128) NOT NULL
    );

    ;WITH raw AS (
        SELECT
            CAST(JSON_VALUE(j.value, '$.portalSampleId') AS int) AS portal_sample_id,
            CAST(JSON_VALUE(j.value, '$.labSampleId') AS int) AS lab_sample_id,
            NULLIF(LTRIM(RTRIM(JSON_VALUE(j.value, '$.processingSampleKey'))), N'') AS processing_sample_key
        FROM OPENJSON(CONVERT(nvarchar(max), @members_json)) AS j
    )
    INSERT INTO @resolved (portal_sample_id, lab_sample_id, processing_sample_key)
    SELECT
        r.portal_sample_id,
        r.lab_sample_id,
        COALESCE(
            NULLIF(LTRIM(RTRIM(ls.Sample)), N''),
            r.processing_sample_key,
            NULLIF(LTRIM(RTRIM(s.ParticipantID)), N'')
        )
    FROM raw r
    INNER JOIN portal.Samples s ON s.ID = r.portal_sample_id
    LEFT JOIN portal.LabSamples ls ON ls.ID = r.lab_sample_id AND ls.SampleID = r.portal_sample_id;

    IF EXISTS (SELECT 1 FROM @resolved WHERE processing_sample_key IS NULL)
    BEGIN
        RAISERROR(N'cannot resolve processing_sample_key for one or more members', 16, 1);
        RETURN;
    END

    DELETE FROM cfg.study_group_member WHERE study_group_id = @study_group_id;

    INSERT INTO cfg.study_group_member (
        study_group_id, portal_sample_id, lab_sample_id, processing_sample_key
    )
    SELECT @study_group_id, portal_sample_id, lab_sample_id, processing_sample_key
    FROM @resolved;

    UPDATE cfg.study_group SET updated_at_utc = SYSUTCDATETIME() WHERE id = @study_group_id;

    SELECT id, study_group_id, portal_sample_id, lab_sample_id, processing_sample_key
    FROM cfg.study_group_member
    WHERE study_group_id = @study_group_id
    ORDER BY processing_sample_key;
END
GO

CREATE OR ALTER PROCEDURE cfg.cfg_repo_list_study_groups
    @study_row_id bigint
AS
BEGIN
    SET NOCOUNT ON;
    SELECT g.id, g.study_row_id, g.role, g.label, g.list_filename,
           (SELECT COUNT(*) FROM cfg.study_group_member m WHERE m.study_group_id = g.id) AS member_count
    FROM cfg.study_group g
    WHERE g.study_row_id = @study_row_id
    ORDER BY g.role, g.label;
END
GO

CREATE OR ALTER PROCEDURE cfg.cfg_repo_list_study_group_members
    @study_group_id bigint
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id, study_group_id, portal_sample_id, lab_sample_id, processing_sample_key
    FROM cfg.study_group_member
    WHERE study_group_id = @study_group_id
    ORDER BY processing_sample_key;
END
GO

CREATE OR ALTER PROCEDURE cfg.cfg_repo_materialize_study_lists
    @study_row_id bigint,
    @work_root nvarchar(512) = N'/work'
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @study_id nvarchar(256);
    DECLARE @name nvarchar(256);
    DECLARE @doc nvarchar(max);
    DECLARE @data_root nvarchar(1024);
    DECLARE @groups_json nvarchar(max);

    SELECT @study_id = COALESCE(study_id, name), @name = name,
           @doc = CONVERT(nvarchar(max), document_json)
    FROM cfg.study
    WHERE id = @study_row_id;

    IF @name IS NULL
    BEGIN
        RAISERROR(N'cfg.study not found: %I64d', 16, 1, @study_row_id);
        RETURN;
    END

    SET @data_root = @work_root + N'/projects/' + @study_id + N'/data';

    SELECT
        g.id AS study_group_id,
        g.role,
        g.label,
        g.list_filename,
        @data_root + N'/' + g.list_filename AS csv_path,
        (
            SELECT STRING_AGG(m.processing_sample_key, CHAR(10)) WITHIN GROUP (ORDER BY m.processing_sample_key)
            FROM cfg.study_group_member m
            WHERE m.study_group_id = g.id
        ) AS sample_keys
    FROM cfg.study_group g
    WHERE g.study_row_id = @study_row_id
    ORDER BY g.role, g.label;

    /* Hint array for portal; Python methyl-cfg materialize rewrites controls/diseases sample_paths. */
    SELECT @groups_json = COALESCE((
        SELECT g.role AS role, g.label AS label, g.list_filename AS listFilename,
               @data_root + N'/' + g.list_filename AS samplePath
        FROM cfg.study_group g
        WHERE g.study_row_id = @study_row_id
        FOR JSON PATH
    ), N'[]');

    SET @doc = JSON_MODIFY(@doc, '$.cfgStudyGroups', JSON_QUERY(@groups_json));

    UPDATE cfg.study
    SET document_json = CAST(@doc AS json),
        content_hash = CONVERT(nvarchar(128), HASHBYTES('SHA2_256', @doc), 2),
        updated_at_utc = SYSUTCDATETIME()
    WHERE id = @study_row_id;
END
GO

