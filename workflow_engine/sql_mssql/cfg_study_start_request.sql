/*
  cfg.study_start_request + portal start-queue API (Azure SQL).

  Portal writes operator intent. Python ops (methyl-study-start drain-requests)
  claims the row, bakes resolvedConfig via finalize_instance_context, then
  calls portal.sp_create_and_start_instance. SQL does not reimplement merge.

  Deploy after portal_study_ops_api.sql (guardrail helpers, link proc).
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF SCHEMA_ID(N'portal') IS NULL
    EXEC(N'CREATE SCHEMA portal');
GO

IF OBJECT_ID(N'cfg.study_start_request', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.study_start_request (
        id                     BIGINT IDENTITY(1,1) NOT NULL,
        study_row_id           BIGINT NOT NULL,
        stage                  NVARCHAR(32) NOT NULL,
        workflow_version_id    BIGINT NOT NULL,
        pipeline_profile_id    BIGINT NULL,
        assay_procedure_id     BIGINT NULL,
        site_id                BIGINT NULL,
        storage_profile_id     BIGINT NULL,
        request_json           json NOT NULL CONSTRAINT DF_ssr_request DEFAULT (N'{}'),
        status                 NVARCHAR(32) NOT NULL CONSTRAINT DF_ssr_status DEFAULT (N'queued'),
        error_message          NVARCHAR(MAX) NULL,
        workflow_instance_id   BIGINT NULL,
        claimed_by             NVARCHAR(256) NULL,
        claimed_at_utc         DATETIME2(7) NULL,
        lease_expires_at_utc   DATETIME2(7) NULL,
        created_by             NVARCHAR(256) NULL,
        created_at_utc         DATETIME2(7) NOT NULL CONSTRAINT DF_ssr_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc         DATETIME2(7) NOT NULL CONSTRAINT DF_ssr_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_study_start_request PRIMARY KEY (id),
        CONSTRAINT FK_ssr_study FOREIGN KEY (study_row_id) REFERENCES cfg.study(id),
        CONSTRAINT CK_ssr_stage CHECK (stage IN (N'sample_prep', N'study_validation')),
        CONSTRAINT CK_ssr_status CHECK (status IN (
            N'draft', N'queued', N'running', N'succeeded', N'failed'
        ))
    );
    CREATE INDEX IX_ssr_status_lease ON cfg.study_start_request(status, lease_expires_at_utc, id);
    CREATE INDEX IX_ssr_study ON cfg.study_start_request(study_row_id);
END
GO

IF OBJECT_ID(N'cfg.study_start_request', N'U') IS NOT NULL
   AND OBJECT_ID(N'wf.workflow_version', N'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_ssr_workflow_version'
   )
BEGIN
    ALTER TABLE cfg.study_start_request
        ADD CONSTRAINT FK_ssr_workflow_version
        FOREIGN KEY (workflow_version_id) REFERENCES wf.workflow_version(id);
END
GO

CREATE OR ALTER FUNCTION portal.fn_study_start_stage(@workflow_name nvarchar(256))
RETURNS nvarchar(32)
AS
BEGIN
    DECLARE @n nvarchar(256) = LOWER(ISNULL(@workflow_name, N''));
    IF @n LIKE N'%sample%prep%' OR @n LIKE N'%sample_prep%'
        RETURN N'sample_prep';
    IF @n LIKE N'%study%validation%' OR @n LIKE N'%validation%lifecycle%'
        RETURN N'study_validation';
    RETURN NULL;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_study_start_stages
    @study_row_id bigint
AS
BEGIN
    SET NOCOUNT ON;

    IF @study_row_id IS NULL OR @study_row_id <= 0
        THROW 50001, N'study_row_id is required.', 1;

    SELECT
        st.stage,
        st.workflow_def_id,
        st.workflow_name,
        st.workflow_version_id,
        st.version_major,
        st.version_minor,
        (
            SELECT COUNT(*)
            FROM cfg.study_instance_link l
            INNER JOIN wf.workflow_instance i ON i.id = l.workflow_instance_id
            INNER JOIN wf.workflow_version v2 ON v2.id = i.workflow_version_id
            INNER JOIN wf.workflow_def d2 ON d2.id = v2.workflow_def_id
            WHERE l.study_row_id = @study_row_id
              AND portal.fn_study_start_stage(d2.name) = st.stage
        ) AS existing_count
    FROM (
        SELECT
            portal.fn_study_start_stage(d.name) AS stage,
            d.id AS workflow_def_id,
            d.name AS workflow_name,
            v.id AS workflow_version_id,
            v.version_major,
            v.version_minor,
            ROW_NUMBER() OVER (
                PARTITION BY portal.fn_study_start_stage(d.name)
                ORDER BY v.is_active DESC, v.version_major DESC, v.version_minor DESC, v.id DESC
            ) AS rn
        FROM wf.workflow_def d
        INNER JOIN wf.workflow_version v ON v.workflow_def_id = d.id
        WHERE v.is_active = 1
          AND v.root_node_id IS NOT NULL
          AND portal.fn_study_start_stage(d.name) IS NOT NULL
    ) st
    WHERE st.rn = 1
    ORDER BY CASE st.stage WHEN N'sample_prep' THEN 0 ELSE 1 END;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_preview_study_start
    @study_row_id bigint,
    @stage nvarchar(32),
    @workflow_version_id bigint = NULL,
    @pipeline_profile nvarchar(256) = NULL,
    @pipeline_procedure nvarchar(256) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF @study_row_id IS NULL OR @study_row_id <= 0
        THROW 50001, N'study_row_id is required.', 1;
    IF @stage NOT IN (N'sample_prep', N'study_validation')
        THROW 50002, N'stage must be sample_prep or study_validation.', 1;
    IF NOT EXISTS (SELECT 1 FROM cfg.study WHERE id = @study_row_id AND status = N'published')
        THROW 50010, N'cfg.study not found or not published.', 1;

    DECLARE @study_name nvarchar(256);
    DECLARE @doc nvarchar(max);
    DECLARE @ver bigint = @workflow_version_id;
    DECLARE @wf_name nvarchar(256);
    DECLARE @def_id bigint;
    DECLARE @major int;
    DECLARE @minor int;
    DECLARE @profile nvarchar(256) = NULLIF(LTRIM(RTRIM(@pipeline_profile)), N'');
    DECLARE @procedure nvarchar(256) = NULLIF(LTRIM(RTRIM(@pipeline_procedure)), N'');
    DECLARE @profile_id bigint;
    DECLARE @assay_id bigint;
    DECLARE @site_id bigint;
    DECLARE @storage_id bigint;
    DECLARE @research nvarchar(64);
    DECLARE @analyte nvarchar(256);
    DECLARE @project_path nvarchar(1024);
    DECLARE @overlay nvarchar(max);
    DECLARE @pinned bit;
    DECLARE @cohort nvarchar(max);
    DECLARE @cohort_caption nvarchar(512);
    DECLARE @storage_caption nvarchar(512);
    DECLARE @ref_caption nvarchar(512);
    DECLARE @guard_caption nvarchar(256);
    DECLARE @sample_count int;
    DECLARE @existing int;
    DECLARE @request nvarchar(max);

    SELECT
        @study_name = s.name,
        @doc = CAST(s.document_json AS nvarchar(max)),
        @profile_id = s.default_pipeline_profile_id,
        @assay_id = s.default_assay_procedure_id
    FROM cfg.study s
    WHERE s.id = @study_row_id;
    IF @doc IS NULL OR ISJSON(@doc) <> 1
        SET @doc = N'{}';

    IF @ver IS NULL
    BEGIN
        SELECT TOP (1)
            @ver = v.id,
            @wf_name = d.name,
            @def_id = d.id,
            @major = v.version_major,
            @minor = v.version_minor
        FROM wf.workflow_def d
        INNER JOIN wf.workflow_version v ON v.workflow_def_id = d.id
        WHERE v.is_active = 1
          AND v.root_node_id IS NOT NULL
          AND portal.fn_study_start_stage(d.name) = @stage
        ORDER BY v.version_major DESC, v.version_minor DESC, v.id DESC;
    END
    ELSE
    BEGIN
        SELECT
            @wf_name = d.name,
            @def_id = d.id,
            @major = v.version_major,
            @minor = v.version_minor
        FROM wf.workflow_version v
        INNER JOIN wf.workflow_def d ON d.id = v.workflow_def_id
        WHERE v.id = @ver;
        IF @wf_name IS NULL
            THROW 50011, N'workflow_version_id not found.', 1;
        IF portal.fn_study_start_stage(@wf_name) <> @stage
            THROW 50012, N'workflow_version_id does not match stage.', 1;
        IF NOT EXISTS (
            SELECT 1 FROM wf.workflow_version v
            WHERE v.id = @ver AND v.is_active = 1 AND v.root_node_id IS NOT NULL
        )
            THROW 50013, N'workflow version is not published with a root node.', 1;
    END

    IF @ver IS NULL
        THROW 50014, N'No published workflow version for this stage.', 1;

    IF @profile IS NULL
        SET @profile = COALESCE(
            (SELECT name FROM cfg.pipeline_profile WHERE id = @profile_id),
            JSON_VALUE(@doc, '$.pipelineProfile')
        );
    IF @procedure IS NULL
        SET @procedure = COALESCE(
            (SELECT name FROM cfg.assay_procedure WHERE id = @assay_id),
            JSON_VALUE(@doc, '$.pipelineProcedure')
        );

    IF @profile IS NOT NULL AND @profile_id IS NULL
        SELECT TOP (1) @profile_id = id
        FROM cfg.pipeline_profile
        WHERE name = @profile AND status = N'published'
        ORDER BY id DESC;
    IF @procedure IS NOT NULL AND @assay_id IS NULL
        SELECT TOP (1) @assay_id = id
        FROM cfg.assay_procedure
        WHERE name = @procedure AND status = N'published'
        ORDER BY id DESC;

    SET @research = JSON_VALUE(@doc, '$.researchMode');
    SET @analyte = COALESCE(
        JSON_VALUE(@doc, '$.regulatory.primary_analyte'),
        JSON_VALUE(@doc, '$.primaryAnalyte')
    );

    SELECT TOP (1) @site_id = id
    FROM cfg.site
    WHERE status = N'published'
    ORDER BY CASE WHEN name = N'default' THEN 0 ELSE 1 END, id DESC;

    SELECT TOP (1)
        @project_path = CONCAT(
            N'/work/projects/',
            COALESCE(NULLIF(LTRIM(RTRIM(s.study_id)), N''), s.name),
            N'/configs/project_',
            s.name,
            N'.json'
        )
    FROM cfg.study s
    WHERE s.id = @study_row_id;

    SET @overlay = COALESCE(JSON_QUERY(@doc, '$.actionConfig'), N'{}');
    IF OBJECT_ID(N'portal.fn_json_guardrail_slice', N'FN') IS NOT NULL
        SET @overlay = portal.fn_json_guardrail_slice(@overlay);
    SET @pinned = CASE
        WHEN @overlay IS NULL OR LTRIM(RTRIM(@overlay)) IN (N'', N'{}') THEN 0
        ELSE 1
    END;
    SET @guard_caption = CASE
        WHEN @pinned = 1 THEN N'Pinned study overlay (edit on Studies -> Guardrails)'
        ELSE N'Inherited from site / profile / procedure'
    END;

    SELECT @cohort = (
        SELECT g.role, g.label,
               (SELECT COUNT(*) FROM cfg.study_group_member m WHERE m.study_group_id = g.id) AS member_count
        FROM cfg.study_group g
        WHERE g.study_row_id = @study_row_id
        FOR JSON PATH
    );
    IF @cohort IS NULL SET @cohort = N'[]';

    SELECT
        @sample_count = COUNT(*),
        @cohort_caption = CONCAT(
            COUNT(DISTINCT g.id), N' group(s), ',
            COUNT(m.id), N' sample(s)'
        )
    FROM cfg.study_group g
    LEFT JOIN cfg.study_group_member m ON m.study_group_id = g.id
    WHERE g.study_row_id = @study_row_id;

    SELECT
        @storage_caption = CONCAT(
            N'FASTQ: ', COALESCE(src.name, N'(unset)'),
            N' | archive: ', COALESCE(dst.name, N'(unset)')
        )
    FROM cfg.study s
    LEFT JOIN cfg.storage_endpoint src
      ON src.id = TRY_CAST(JSON_VALUE(CAST(s.document_json AS nvarchar(max)), '$.storage.fastqSourceEndpointId') AS bigint)
    LEFT JOIN cfg.storage_endpoint dst
      ON dst.id = TRY_CAST(JSON_VALUE(CAST(s.document_json AS nvarchar(max)), '$.storage.sampleDestinationEndpointId') AS bigint)
    WHERE s.id = @study_row_id;

    SET @ref_caption = N'Site reference assets (materialized /work) - not edited here';

    SELECT @existing = COUNT(*)
    FROM cfg.study_instance_link l
    INNER JOIN wf.workflow_instance i ON i.id = l.workflow_instance_id
    INNER JOIN wf.workflow_version v ON v.id = i.workflow_version_id
    INNER JOIN wf.workflow_def d ON d.id = v.workflow_def_id
    WHERE l.study_row_id = @study_row_id
      AND portal.fn_study_start_stage(d.name) = @stage;

    SET @request = (
        SELECT
            @study_row_id AS study_row_id,
            @study_name AS study_name,
            @stage AS stage,
            @ver AS workflow_version_id,
            @wf_name AS workflow_name,
            @profile AS pipelineProfile,
            @procedure AS pipelineProcedure,
            @research AS researchMode,
            @analyte AS primaryAnalyte,
            @project_path AS projectPath,
            JSON_QUERY(COALESCE(@overlay, N'{}')) AS actionConfig,
            JSON_QUERY(@cohort) AS cohort
        FOR JSON PATH, WITHOUT_ARRAY_WRAPPER
    );

    SELECT
        @study_row_id AS study_row_id,
        @study_name AS study_name,
        @stage AS stage,
        @def_id AS workflow_def_id,
        @wf_name AS workflow_name,
        @ver AS workflow_version_id,
        CONCAT(N'v', @major, N'.', @minor) AS version_label,
        @profile AS pipeline_profile,
        @profile_id AS pipeline_profile_id,
        @procedure AS pipeline_procedure,
        @assay_id AS assay_procedure_id,
        @site_id AS site_id,
        @storage_id AS storage_profile_id,
        @research AS research_mode,
        @analyte AS primary_analyte,
        @project_path AS project_path,
        @storage_caption AS storage_caption,
        @ref_caption AS reference_caption,
        @cohort_caption AS cohort_caption,
        @guard_caption AS guardrails_caption,
        @pinned AS guardrails_pinned,
        @cohort AS cohort_json,
        @request AS request_json,
        @existing AS existing_kind_count,
        CAST(1 AS bit) AS eligible;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_request_study_start
    @study_row_id bigint,
    @stage nvarchar(32),
    @workflow_version_id bigint,
    @request_json nvarchar(max),
    @pipeline_profile_id bigint = NULL,
    @assay_procedure_id bigint = NULL,
    @site_id bigint = NULL,
    @storage_profile_id bigint = NULL,
    @created_by nvarchar(256) = NULL,
    @scope_id int = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF @scope_id IS NOT NULL
        THROW 50210, N'Contract quota UI is out of scope; pass NULL @scope_id.', 1;

    IF @study_row_id IS NULL OR @study_row_id <= 0
        THROW 50001, N'study_row_id is required.', 1;
    IF @stage NOT IN (N'sample_prep', N'study_validation')
        THROW 50002, N'stage must be sample_prep or study_validation.', 1;
    IF @workflow_version_id IS NULL OR @workflow_version_id <= 0
        THROW 50003, N'workflow_version_id is required.', 1;
    IF @request_json IS NULL OR ISJSON(@request_json) <> 1 OR LEFT(LTRIM(@request_json), 1) <> N'{'
        THROW 50021, N'request_json must be a JSON object.', 1;
    IF NOT EXISTS (SELECT 1 FROM cfg.study WHERE id = @study_row_id AND status = N'published')
        THROW 50010, N'cfg.study not found or not published.', 1;

    DECLARE @wf_name nvarchar(256);
    SELECT @wf_name = d.name
    FROM wf.workflow_version v
    INNER JOIN wf.workflow_def d ON d.id = v.workflow_def_id
    WHERE v.id = @workflow_version_id
      AND v.is_active = 1
      AND v.root_node_id IS NOT NULL;
    IF @wf_name IS NULL
        THROW 50013, N'workflow version is not published with a root node.', 1;
    IF portal.fn_study_start_stage(@wf_name) <> @stage
        THROW 50012, N'workflow_version_id does not match stage.', 1;

    INSERT INTO cfg.study_start_request (
        study_row_id, stage, workflow_version_id,
        pipeline_profile_id, assay_procedure_id, site_id, storage_profile_id,
        request_json, status, created_by
    )
    VALUES (
        @study_row_id, @stage, @workflow_version_id,
        @pipeline_profile_id, @assay_procedure_id, @site_id, @storage_profile_id,
        CAST(@request_json AS json), N'queued', @created_by
    );

    DECLARE @id bigint = SCOPE_IDENTITY();

    SELECT
        r.id AS request_id,
        r.status,
        r.study_row_id,
        r.stage,
        r.workflow_version_id
    FROM cfg.study_start_request r
    WHERE r.id = @id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_claim_study_start_request
    @claimed_by nvarchar(256),
    @lease_seconds int = 600
AS
BEGIN
    SET NOCOUNT ON;

    IF NULLIF(LTRIM(RTRIM(@claimed_by)), N'') IS NULL
        THROW 50001, N'claimed_by is required.', 1;
    IF @lease_seconds IS NULL OR @lease_seconds < 30
        SET @lease_seconds = 600;

    DECLARE @now datetime2(7) = SYSUTCDATETIME();
    DECLARE @claimed TABLE (id bigint);

    ;WITH cte AS (
        SELECT TOP (1) id
        FROM cfg.study_start_request WITH (UPDLOCK, READPAST, ROWLOCK)
        WHERE status = N'queued'
           OR (status = N'running'
               AND (lease_expires_at_utc IS NULL OR lease_expires_at_utc <= @now))
        ORDER BY id
    )
    UPDATE r
    SET status = N'running',
        claimed_by = @claimed_by,
        claimed_at_utc = @now,
        lease_expires_at_utc = DATEADD(SECOND, @lease_seconds, @now),
        updated_at_utc = @now
    OUTPUT inserted.id INTO @claimed(id)
    FROM cfg.study_start_request r
    INNER JOIN cte ON cte.id = r.id;

    SELECT
        r.id AS request_id,
        r.study_row_id,
        r.stage,
        r.workflow_version_id,
        r.pipeline_profile_id,
        r.assay_procedure_id,
        r.site_id,
        r.storage_profile_id,
        CAST(r.request_json AS nvarchar(max)) AS request_json,
        r.status,
        r.error_message,
        r.workflow_instance_id,
        r.claimed_by,
        r.lease_expires_at_utc
    FROM cfg.study_start_request r
    INNER JOIN @claimed c ON c.id = r.id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_complete_study_start_request
    @request_id bigint,
    @workflow_instance_id bigint
AS
BEGIN
    SET NOCOUNT ON;

    IF @request_id IS NULL OR @request_id <= 0
        THROW 50001, N'request_id is required.', 1;
    IF @workflow_instance_id IS NULL OR @workflow_instance_id <= 0
        THROW 50002, N'workflow_instance_id is required.', 1;

    UPDATE cfg.study_start_request
    SET status = N'succeeded',
        workflow_instance_id = @workflow_instance_id,
        error_message = NULL,
        lease_expires_at_utc = NULL,
        updated_at_utc = SYSUTCDATETIME()
    WHERE id = @request_id
      AND status = N'running';

    IF @@ROWCOUNT = 0
        THROW 50010, N'study_start_request not running.', 1;

    EXEC portal.sp_get_study_start_request @request_id = @request_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_fail_study_start_request
    @request_id bigint,
    @error_message nvarchar(max)
AS
BEGIN
    SET NOCOUNT ON;

    IF @request_id IS NULL OR @request_id <= 0
        THROW 50001, N'request_id is required.', 1;

    UPDATE cfg.study_start_request
    SET status = N'failed',
        error_message = LEFT(COALESCE(@error_message, N'failed'), 4000),
        lease_expires_at_utc = NULL,
        updated_at_utc = SYSUTCDATETIME()
    WHERE id = @request_id
      AND status IN (N'queued', N'running');

    IF @@ROWCOUNT = 0
        THROW 50010, N'study_start_request not queued or running.', 1;

    EXEC portal.sp_get_study_start_request @request_id = @request_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_study_start_request
    @request_id bigint
AS
BEGIN
    SET NOCOUNT ON;

    IF @request_id IS NULL OR @request_id <= 0
        THROW 50001, N'request_id is required.', 1;

    SELECT
        r.id AS request_id,
        r.study_row_id,
        r.stage,
        r.workflow_version_id,
        r.pipeline_profile_id,
        r.assay_procedure_id,
        r.site_id,
        r.storage_profile_id,
        CAST(r.request_json AS nvarchar(max)) AS request_json,
        r.status,
        r.error_message,
        r.workflow_instance_id,
        r.claimed_by,
        r.claimed_at_utc,
        r.lease_expires_at_utc,
        r.created_by,
        r.created_at_utc,
        r.updated_at_utc
    FROM cfg.study_start_request r
    WHERE r.id = @request_id;
END
GO
