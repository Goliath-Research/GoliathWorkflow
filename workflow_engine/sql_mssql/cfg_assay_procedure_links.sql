/*
  Explicit cfg relationships for assay procedures (Azure SQL).

  Adds:
  - cfg.assay_procedure → default profile + SamplePrep/lifecycle DomainPrograms
  - cfg.study default profile/procedure FKs (alongside document_json keys)
  - cfg.study_instance_link.assay_procedure_id
  - views: cfg.v_assay_procedure, refreshed cfg.v_study_instance
  - cfg.cfg_repo_bind_assay_procedure (resolve names → FKs)
  - cfg.cfg_repo_link_study_instance gains @assay_procedure_id

  Prerequisites:
  - cfg_registry_tables.sql / cfg_process_pack_catalog.sql (cfg.assay_procedure)
  - cfg_wf_relationships.sql (study_instance_link)
  - cfg_repo_api.sql
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'cfg.assay_procedure', N'U') IS NULL
BEGIN
    RAISERROR(N'Prerequisite missing: cfg.assay_procedure (cfg_process_pack_catalog.sql).', 16, 1);
    RETURN;
END
GO

IF OBJECT_ID(N'cfg.study_instance_link', N'U') IS NULL
BEGIN
    RAISERROR(N'Prerequisite missing: cfg.study_instance_link (cfg_wf_relationships.sql).', 16, 1);
    RETURN;
END
GO

/* --- assay_procedure typed edges --- */
IF COL_LENGTH(N'cfg.assay_procedure', N'primary_analyte') IS NULL
    ALTER TABLE cfg.assay_procedure ADD primary_analyte nvarchar(64) NULL;
GO
IF COL_LENGTH(N'cfg.assay_procedure', N'default_pipeline_profile_id') IS NULL
    ALTER TABLE cfg.assay_procedure ADD default_pipeline_profile_id bigint NULL;
GO
IF COL_LENGTH(N'cfg.assay_procedure', N'sample_prep_program_id') IS NULL
    ALTER TABLE cfg.assay_procedure ADD sample_prep_program_id bigint NULL;
GO
IF COL_LENGTH(N'cfg.assay_procedure', N'lifecycle_program_id') IS NULL
    ALTER TABLE cfg.assay_procedure ADD lifecycle_program_id bigint NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_cfg_ap_default_profile'
)
    ALTER TABLE cfg.assay_procedure WITH CHECK
    ADD CONSTRAINT FK_cfg_ap_default_profile
        FOREIGN KEY (default_pipeline_profile_id) REFERENCES cfg.pipeline_profile (id);
GO
IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_cfg_ap_sample_prep'
)
    ALTER TABLE cfg.assay_procedure WITH CHECK
    ADD CONSTRAINT FK_cfg_ap_sample_prep
        FOREIGN KEY (sample_prep_program_id) REFERENCES cfg.domain_program (id);
GO
IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_cfg_ap_lifecycle'
)
    ALTER TABLE cfg.assay_procedure WITH CHECK
    ADD CONSTRAINT FK_cfg_ap_lifecycle
        FOREIGN KEY (lifecycle_program_id) REFERENCES cfg.domain_program (id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'IX_cfg_ap_analyte' AND object_id = OBJECT_ID(N'cfg.assay_procedure')
)
    CREATE INDEX IX_cfg_ap_analyte ON cfg.assay_procedure (primary_analyte);
GO
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'IX_cfg_ap_default_profile' AND object_id = OBJECT_ID(N'cfg.assay_procedure')
)
    CREATE INDEX IX_cfg_ap_default_profile ON cfg.assay_procedure (default_pipeline_profile_id);
GO

/* --- study default FKs --- */
IF COL_LENGTH(N'cfg.study', N'default_pipeline_profile_id') IS NULL
    ALTER TABLE cfg.study ADD default_pipeline_profile_id bigint NULL;
GO
IF COL_LENGTH(N'cfg.study', N'default_assay_procedure_id') IS NULL
    ALTER TABLE cfg.study ADD default_assay_procedure_id bigint NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_cfg_study_default_profile'
)
    ALTER TABLE cfg.study WITH CHECK
    ADD CONSTRAINT FK_cfg_study_default_profile
        FOREIGN KEY (default_pipeline_profile_id) REFERENCES cfg.pipeline_profile (id);
GO
IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_cfg_study_default_assay'
)
    ALTER TABLE cfg.study WITH CHECK
    ADD CONSTRAINT FK_cfg_study_default_assay
        FOREIGN KEY (default_assay_procedure_id) REFERENCES cfg.assay_procedure (id);
GO

/* --- study_instance_link.assay_procedure_id --- */
IF COL_LENGTH(N'cfg.study_instance_link', N'assay_procedure_id') IS NULL
    ALTER TABLE cfg.study_instance_link ADD assay_procedure_id bigint NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_cfg_sil_assay'
)
    ALTER TABLE cfg.study_instance_link WITH CHECK
    ADD CONSTRAINT FK_cfg_sil_assay
        FOREIGN KEY (assay_procedure_id) REFERENCES cfg.assay_procedure (id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'IX_cfg_sil_assay' AND object_id = OBJECT_ID(N'cfg.study_instance_link')
)
    CREATE INDEX IX_cfg_sil_assay ON cfg.study_instance_link (assay_procedure_id);
GO

/* --- views --- */
CREATE OR ALTER VIEW cfg.v_assay_procedure AS
SELECT
    ap.id AS assay_procedure_id,
    ap.name AS procedure_name,
    ap.version AS procedure_version,
    ap.status,
    ap.primary_analyte,
    ap.default_pipeline_profile_id,
    pp.name AS default_pipeline_profile_name,
    ap.sample_prep_program_id,
    sp.name AS sample_prep_program_name,
    ap.lifecycle_program_id,
    lp.name AS lifecycle_program_name,
    JSON_VALUE(ap.document_json, '$.catalog.title') AS catalog_title,
    JSON_VALUE(ap.document_json, '$.catalog.visibility') AS catalog_visibility,
    JSON_VALUE(ap.document_json, '$.catalog.lifecycle') AS catalog_lifecycle
FROM cfg.assay_procedure ap
LEFT JOIN cfg.pipeline_profile pp ON pp.id = ap.default_pipeline_profile_id
LEFT JOIN cfg.domain_program sp ON sp.id = ap.sample_prep_program_id
LEFT JOIN cfg.domain_program lp ON lp.id = ap.lifecycle_program_id;
GO

CREATE OR ALTER VIEW cfg.v_study_instance AS
SELECT
    l.id AS link_id,
    l.study_row_id,
    s.name AS study_name,
    s.study_id,
    l.workflow_instance_id,
    i.status AS instance_status,
    i.workflow_version_id,
    l.domain_program_id,
    p.name AS program_name,
    l.pipeline_profile_id,
    pr.name AS profile_name,
    l.assay_procedure_id,
    ap.name AS assay_procedure_name,
    l.site_id,
    l.created_at_utc
FROM cfg.study_instance_link l
INNER JOIN cfg.study s ON s.id = l.study_row_id
INNER JOIN wf.workflow_instance i ON i.id = l.workflow_instance_id
LEFT JOIN cfg.domain_program p ON p.id = l.domain_program_id
LEFT JOIN cfg.pipeline_profile pr ON pr.id = l.pipeline_profile_id
LEFT JOIN cfg.assay_procedure ap ON ap.id = l.assay_procedure_id;
GO

/* Bind assay_procedure FKs by stable names (used by sync / portal). */
CREATE OR ALTER PROCEDURE cfg.cfg_repo_bind_assay_procedure
    @procedure_name nvarchar(256),
    @procedure_version nvarchar(64) = N'1',
    @primary_analyte nvarchar(64) = NULL,
    @default_pipeline_profile_name nvarchar(256) = NULL,
    @sample_prep_program_name nvarchar(256) = NULL,
    @lifecycle_program_name nvarchar(256) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @ap_id bigint = (
        SELECT TOP (1) id FROM cfg.assay_procedure
        WHERE name = @procedure_name
          AND (@procedure_version IS NULL OR version = @procedure_version)
        ORDER BY id DESC
    );
    IF @ap_id IS NULL
    BEGIN
        RAISERROR(N'cfg.assay_procedure not found: %s', 16, 1, @procedure_name);
        RETURN;
    END;

    DECLARE @profile_id bigint = NULL;
    IF @default_pipeline_profile_name IS NOT NULL AND LTRIM(RTRIM(@default_pipeline_profile_name)) <> N''
        SET @profile_id = (
            SELECT TOP (1) id FROM cfg.pipeline_profile
            WHERE name = @default_pipeline_profile_name
            ORDER BY CASE status WHEN 'published' THEN 0 WHEN 'retired' THEN 1 ELSE 2 END, id DESC
        );

    DECLARE @sp_id bigint = NULL;
    IF @sample_prep_program_name IS NOT NULL AND LTRIM(RTRIM(@sample_prep_program_name)) <> N''
        SET @sp_id = (
            SELECT TOP (1) id FROM cfg.domain_program
            WHERE name = @sample_prep_program_name
            ORDER BY CASE status WHEN 'published' THEN 0 ELSE 1 END, id DESC
        );

    DECLARE @lc_id bigint = NULL;
    IF @lifecycle_program_name IS NOT NULL AND LTRIM(RTRIM(@lifecycle_program_name)) <> N''
        SET @lc_id = (
            SELECT TOP (1) id FROM cfg.domain_program
            WHERE name = @lifecycle_program_name
            ORDER BY CASE status WHEN 'published' THEN 0 ELSE 1 END, id DESC
        );

    UPDATE cfg.assay_procedure
    SET primary_analyte = COALESCE(@primary_analyte, primary_analyte),
        default_pipeline_profile_id = COALESCE(@profile_id, default_pipeline_profile_id),
        sample_prep_program_id = COALESCE(@sp_id, sample_prep_program_id),
        lifecycle_program_id = COALESCE(@lc_id, lifecycle_program_id),
        updated_at_utc = SYSUTCDATETIME()
    WHERE id = @ap_id;

    SELECT
        ap.id,
        ap.name,
        ap.primary_analyte,
        ap.default_pipeline_profile_id,
        ap.sample_prep_program_id,
        ap.lifecycle_program_id
    FROM cfg.assay_procedure ap
    WHERE ap.id = @ap_id;
END
GO

/* Catalog filter prefers typed primary_analyte once links are deployed. */
CREATE OR ALTER PROCEDURE portal.sp_list_assay_procedure_catalog
    @analyte nvarchar(64) = NULL,
    @include_advanced bit = 0
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @analyte_l nvarchar(64) = LOWER(LTRIM(RTRIM(@analyte)));

    SELECT
        p.id,
        p.name,
        p.version,
        p.status,
        JSON_VALUE(p.document_json, '$.catalog.title') AS title,
        JSON_VALUE(p.document_json, '$.catalog.summary') AS summary,
        JSON_VALUE(p.document_json, '$.catalog.visibility') AS visibility,
        JSON_VALUE(p.document_json, '$.catalog.lifecycle') AS lifecycle,
        JSON_VALUE(p.document_json, '$.catalog.family') AS family,
        JSON_VALUE(p.document_json, '$.catalog.replacedBy') AS replaced_by,
        p.primary_analyte,
        p.default_pipeline_profile_id,
        p.sample_prep_program_id,
        p.lifecycle_program_id,
        CAST(JSON_QUERY(p.document_json, '$.analyteExpectation') AS json) AS analyte_expectation,
        JSON_VALUE(p.document_json, '$.pipelineProfile') AS default_pipeline_profile,
        JSON_VALUE(p.document_json, '$.researchMode') AS default_research_mode
    FROM cfg.assay_procedure p
    WHERE p.status = 'published'
      AND JSON_VALUE(p.document_json, '$.catalog.lifecycle') = N'active'
      AND (
            JSON_VALUE(p.document_json, '$.catalog.visibility') = N'operator'
         OR (@include_advanced = 1
             AND JSON_VALUE(p.document_json, '$.catalog.visibility') = N'advanced')
          )
      AND (
            @analyte_l IS NULL OR @analyte_l = N''
         OR LOWER(p.primary_analyte) = @analyte_l
         OR LOWER(JSON_VALUE(p.document_json, '$.analyteExpectation')) = @analyte_l
         OR EXISTS (
                SELECT 1
                FROM OPENJSON(JSON_QUERY(p.document_json, '$.analyteExpectation')) j
                WHERE LOWER(j.[value]) = @analyte_l
            )
          )
    ORDER BY p.name, p.version;
END
GO

/* Extend study-instance link with assay_procedure_id (CREATE OR ALTER full proc). */
CREATE OR ALTER PROCEDURE cfg.cfg_repo_link_study_instance
    @study_row_id bigint,
    @workflow_instance_id bigint,
    @domain_program_id bigint = NULL,
    @pipeline_profile_id bigint = NULL,
    @site_id bigint = NULL,
    @storage_profile_id bigint = NULL,
    @assay_procedure_id bigint = NULL
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
        storage_profile_id = COALESCE(@storage_profile_id, t.storage_profile_id),
        assay_procedure_id = COALESCE(@assay_procedure_id, t.assay_procedure_id)
    WHEN NOT MATCHED THEN INSERT (
        study_row_id, workflow_instance_id, domain_program_id, pipeline_profile_id,
        site_id, storage_profile_id, assay_procedure_id
    ) VALUES (
        @study_row_id, @workflow_instance_id, @domain_program_id, @pipeline_profile_id,
        @site_id, @storage_profile_id, @assay_procedure_id
    );
    SELECT id FROM cfg.study_instance_link WHERE workflow_instance_id = @workflow_instance_id;
END
GO

/* FK-aware study process defaults (overrides bootstrap procs from catalog script). */
CREATE OR ALTER PROCEDURE portal.sp_get_study_process_defaults
    @study_row_id bigint
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        s.id AS study_row_id,
        s.name AS study_name,
        s.version AS study_version,
        COALESCE(
            pp.name,
            JSON_VALUE(s.document_json, '$.pipelineProfile')
        ) AS pipeline_profile,
        COALESCE(
            ap.name,
            JSON_VALUE(s.document_json, '$.pipelineProcedure')
        ) AS pipeline_procedure,
        JSON_VALUE(s.document_json, '$.researchMode') AS research_mode,
        s.default_pipeline_profile_id,
        s.default_assay_procedure_id,
        JSON_VALUE(pp.document_json, '$.catalog.title') AS pipeline_profile_title,
        JSON_VALUE(ap.document_json, '$.catalog.title') AS pipeline_procedure_title
    FROM cfg.study s
    LEFT JOIN cfg.pipeline_profile pp ON pp.id = s.default_pipeline_profile_id
    LEFT JOIN cfg.assay_procedure ap ON ap.id = s.default_assay_procedure_id
    WHERE s.id = @study_row_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_set_study_process_defaults
    @study_row_id bigint,
    @pipeline_profile nvarchar(256) = NULL,
    @pipeline_procedure nvarchar(256) = NULL,
    @research_mode nvarchar(64) = NULL,
    @allow_advanced bit = 0
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS (SELECT 1 FROM cfg.study WHERE id = @study_row_id)
    BEGIN
        RAISERROR(N'cfg.study not found: %I64d', 16, 1, @study_row_id);
        RETURN;
    END;

    DECLARE @profile_id bigint = NULL;
    DECLARE @assay_id bigint = NULL;

    IF @pipeline_profile IS NOT NULL AND LTRIM(RTRIM(@pipeline_profile)) <> N''
    BEGIN
        SELECT TOP (1) @profile_id = p.id
        FROM cfg.pipeline_profile p
        WHERE p.name = @pipeline_profile
          AND p.status = 'published'
          AND JSON_VALUE(p.document_json, '$.catalog.lifecycle') = N'active'
          AND (
                JSON_VALUE(p.document_json, '$.catalog.visibility') = N'operator'
             OR (@allow_advanced = 1
                 AND JSON_VALUE(p.document_json, '$.catalog.visibility') = N'advanced')
              )
        ORDER BY p.id DESC;
        IF @profile_id IS NULL
        BEGIN
            RAISERROR(N'pipeline profile not in operator/advanced catalog: %s', 16, 1, @pipeline_profile);
            RETURN;
        END;
    END;

    IF @pipeline_procedure IS NOT NULL AND LTRIM(RTRIM(@pipeline_procedure)) <> N''
    BEGIN
        SELECT TOP (1) @assay_id = p.id
        FROM cfg.assay_procedure p
        WHERE p.name = @pipeline_procedure
          AND p.status = 'published'
          AND JSON_VALUE(p.document_json, '$.catalog.lifecycle') = N'active'
          AND (
                JSON_VALUE(p.document_json, '$.catalog.visibility') = N'operator'
             OR (@allow_advanced = 1
                 AND JSON_VALUE(p.document_json, '$.catalog.visibility') = N'advanced')
              )
        ORDER BY p.id DESC;
        IF @assay_id IS NULL
        BEGIN
            RAISERROR(N'assay procedure not in operator/advanced catalog: %s', 16, 1, @pipeline_procedure);
            RETURN;
        END;
    END;

    DECLARE @doc json = (
        SELECT document_json FROM cfg.study WHERE id = @study_row_id
    );
    IF @doc IS NULL
        SET @doc = CAST(N'{}' AS json);

    IF @pipeline_profile IS NOT NULL
        SET @doc = CAST(JSON_MODIFY(@doc, '$.pipelineProfile',
            CASE WHEN LTRIM(RTRIM(@pipeline_profile)) = N'' THEN NULL ELSE @pipeline_profile END) AS json);
    IF @pipeline_procedure IS NOT NULL
        SET @doc = CAST(JSON_MODIFY(@doc, '$.pipelineProcedure',
            CASE WHEN LTRIM(RTRIM(@pipeline_procedure)) = N'' THEN NULL ELSE @pipeline_procedure END) AS json);
    IF @research_mode IS NOT NULL
        SET @doc = CAST(JSON_MODIFY(@doc, '$.researchMode',
            CASE WHEN LTRIM(RTRIM(@research_mode)) = N'' THEN NULL ELSE @research_mode END) AS json);

    UPDATE cfg.study
    SET document_json = @doc,
        content_hash = CONVERT(nvarchar(128), HASHBYTES('SHA2_256', CONVERT(nvarchar(max), @doc)), 2),
        default_pipeline_profile_id = CASE
            WHEN @pipeline_profile IS NULL THEN default_pipeline_profile_id
            WHEN LTRIM(RTRIM(@pipeline_profile)) = N'' THEN NULL
            ELSE @profile_id
        END,
        default_assay_procedure_id = CASE
            WHEN @pipeline_procedure IS NULL THEN default_assay_procedure_id
            WHEN LTRIM(RTRIM(@pipeline_procedure)) = N'' THEN NULL
            ELSE @assay_id
        END,
        updated_at_utc = SYSUTCDATETIME()
    WHERE id = @study_row_id;

    EXEC portal.sp_get_study_process_defaults @study_row_id = @study_row_id;
END
GO
