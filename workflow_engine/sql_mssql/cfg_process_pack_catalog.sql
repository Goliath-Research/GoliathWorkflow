/*
  Process-pack catalog for portal Study / Start-run UX (Azure SQL).

  - Ensures cfg.assay_procedure exists (also declared in cfg_registry_tables.sql).
  - Portal list/get + operator catalog pickers for pipeline profiles and assay procedures.
  - Study process defaults (pipelineProfile / pipelineProcedure / researchMode) on cfg.study.

  Prerequisites:
  - cfg_schema.sql, cfg_registry_tables.sql (cfg.pipeline_profile, cfg.study)
  - cfg_repo_api.sql with assay_procedure kind wired (upsert/publish)
  - portal schema

  Deploy:
    sqlcmd ... -i workflow_engine/sql_mssql/cfg_process_pack_catalog.sql
  Or via deploy_azure.sh (listed after cfg_portal_api.sql).
  Then seed rows:
    python scripts/sync_cfg_profiles_and_action_catalog.py --backend mssql --skip-seed
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF SCHEMA_ID(N'cfg') IS NULL
BEGIN
    RAISERROR(N'Prerequisite missing: cfg schema (cfg_schema.sql).', 16, 1);
    RETURN;
END
GO

IF SCHEMA_ID(N'portal') IS NULL
    EXEC(N'CREATE SCHEMA portal');
GO

IF OBJECT_ID(N'cfg.pipeline_profile', N'U') IS NULL
BEGIN
    RAISERROR(N'Prerequisite missing: cfg.pipeline_profile (cfg_registry_tables.sql).', 16, 1);
    RETURN;
END
GO

IF OBJECT_ID(N'cfg.assay_procedure', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.assay_procedure (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        name nvarchar(256) NOT NULL,
        version nvarchar(64) NOT NULL CONSTRAINT DF_cfg_ap_version_ppc DEFAULT (N'1'),
        status varchar(32) NOT NULL CONSTRAINT DF_cfg_ap_status_ppc DEFAULT ('draft'),
        content_hash nvarchar(128) NOT NULL,
        document_json json NOT NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_ap_created_ppc DEFAULT (SYSUTCDATETIME()),
        updated_at_utc datetime2(3) NULL,
        CONSTRAINT uq_cfg_assay_procedure_name_version UNIQUE (name, version),
        CONSTRAINT ck_cfg_assay_procedure_status CHECK (status IN ('draft', 'published', 'retired'))
    );
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_pipeline_profiles
    @published_only bit = 0
AS
BEGIN
    SET NOCOUNT ON;
    /* Platform -> Process packs -> Pipeline profiles (native json). */
    SELECT
        p.id,
        p.name,
        p.version,
        p.status,
        p.content_hash,
        p.document_json AS document_json,
        p.created_at_utc,
        p.updated_at_utc
    FROM cfg.pipeline_profile p
    WHERE (@published_only = 0 OR p.status = 'published')
    ORDER BY p.name, p.version;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_pipeline_profile
    @name nvarchar(256),
    @version nvarchar(64) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (1)
        p.id,
        p.name,
        p.version,
        p.status,
        p.content_hash,
        p.document_json AS document_json,
        p.created_at_utc,
        p.updated_at_utc
    FROM cfg.pipeline_profile p
    WHERE p.name = @name
      AND (@version IS NULL OR p.version = @version)
    ORDER BY p.id DESC;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_pipeline_profile_catalog
    @include_advanced bit = 0
AS
BEGIN
    SET NOCOUNT ON;
    /* Operator Start-wizard picker — no full actionConfig blob. */
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
        CAST(JSON_QUERY(p.document_json, '$.catalog.researchModes') AS json) AS research_modes
    FROM cfg.pipeline_profile p
    WHERE p.status = 'published'
      AND JSON_VALUE(p.document_json, '$.catalog.lifecycle') = N'active'
      AND (
            JSON_VALUE(p.document_json, '$.catalog.visibility') = N'operator'
         OR (@include_advanced = 1
             AND JSON_VALUE(p.document_json, '$.catalog.visibility') = N'advanced')
          )
    ORDER BY
        CASE JSON_VALUE(p.document_json, '$.catalog.family')
            WHEN N'samd' THEN 0
            WHEN N'staged' THEN 1
            ELSE 2
        END,
        p.name,
        p.version;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_assay_procedures
    @published_only bit = 0
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        p.id,
        p.name,
        p.version,
        p.status,
        p.content_hash,
        p.document_json AS document_json,
        p.created_at_utc,
        p.updated_at_utc
    FROM cfg.assay_procedure p
    WHERE (@published_only = 0 OR p.status = 'published')
    ORDER BY p.name, p.version;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_assay_procedure
    @name nvarchar(256),
    @version nvarchar(64) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (1)
        p.id,
        p.name,
        p.version,
        p.status,
        p.content_hash,
        p.document_json AS document_json,
        p.created_at_utc,
        p.updated_at_utc
    FROM cfg.assay_procedure p
    WHERE p.name = @name
      AND (@version IS NULL OR p.version = @version)
    ORDER BY p.id DESC;
END
GO

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

CREATE OR ALTER PROCEDURE portal.sp_get_study_process_defaults
    @study_row_id bigint
AS
BEGIN
    SET NOCOUNT ON;
    /* Bootstrap shape (document_json only). FK-aware version is in cfg_assay_procedure_links.sql.
       OUTER APPLY TOP (1) mirrors PG LATERAL … LIMIT 1 — (name, version) is unique, not name alone. */
    SELECT
        s.id AS study_row_id,
        s.name AS study_name,
        s.version AS study_version,
        JSON_VALUE(s.document_json, '$.pipelineProfile') AS pipeline_profile,
        JSON_VALUE(s.document_json, '$.pipelineProcedure') AS pipeline_procedure,
        JSON_VALUE(s.document_json, '$.researchMode') AS research_mode,
        JSON_VALUE(pp.document_json, '$.catalog.title') AS pipeline_profile_title,
        JSON_VALUE(ap.document_json, '$.catalog.title') AS pipeline_procedure_title
    FROM cfg.study s
    OUTER APPLY (
        SELECT TOP (1) p.document_json
        FROM cfg.pipeline_profile p
        WHERE p.name = JSON_VALUE(s.document_json, '$.pipelineProfile')
          AND p.status IN ('published', 'retired')
        ORDER BY p.id DESC
    ) pp
    OUTER APPLY (
        SELECT TOP (1) a.document_json
        FROM cfg.assay_procedure a
        WHERE a.name = JSON_VALUE(s.document_json, '$.pipelineProcedure')
          AND a.status IN ('published', 'retired')
        ORDER BY a.id DESC
    ) ap
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
    /* Bootstrap shape. FK-aware version is in cfg_assay_procedure_links.sql. */

    IF NOT EXISTS (SELECT 1 FROM cfg.study WHERE id = @study_row_id)
    BEGIN
        RAISERROR(N'cfg.study not found: %I64d', 16, 1, @study_row_id);
        RETURN;
    END;

    IF @pipeline_profile IS NOT NULL AND LTRIM(RTRIM(@pipeline_profile)) <> N''
    BEGIN
        IF NOT EXISTS (
            SELECT 1
            FROM cfg.pipeline_profile p
            WHERE p.name = @pipeline_profile
              AND p.status = 'published'
              AND JSON_VALUE(p.document_json, '$.catalog.lifecycle') = N'active'
              AND (
                    JSON_VALUE(p.document_json, '$.catalog.visibility') = N'operator'
                 OR (@allow_advanced = 1
                     AND JSON_VALUE(p.document_json, '$.catalog.visibility') = N'advanced')
                  )
        )
        BEGIN
            RAISERROR(N'pipeline profile not in operator/advanced catalog: %s', 16, 1, @pipeline_profile);
            RETURN;
        END;
    END;

    IF @pipeline_procedure IS NOT NULL AND LTRIM(RTRIM(@pipeline_procedure)) <> N''
    BEGIN
        IF NOT EXISTS (
            SELECT 1
            FROM cfg.assay_procedure p
            WHERE p.name = @pipeline_procedure
              AND p.status = 'published'
              AND JSON_VALUE(p.document_json, '$.catalog.lifecycle') = N'active'
              AND (
                    JSON_VALUE(p.document_json, '$.catalog.visibility') = N'operator'
                 OR (@allow_advanced = 1
                     AND JSON_VALUE(p.document_json, '$.catalog.visibility') = N'advanced')
                  )
        )
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
        updated_at_utc = SYSUTCDATETIME()
    WHERE id = @study_row_id;

    EXEC portal.sp_get_study_process_defaults @study_row_id = @study_row_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_upsert_pipeline_profile
    @name nvarchar(256),
    @version nvarchar(64),
    @status varchar(32) = 'draft',
    @document_json json
AS
BEGIN
    SET NOCOUNT ON;
    EXEC cfg.cfg_repo_upsert
        @kind = N'pipeline_profile',
        @name = @name,
        @version = @version,
        @status = @status,
        @document_json = @document_json;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_publish_pipeline_profile
    @name nvarchar(256),
    @version nvarchar(64)
AS
BEGIN
    SET NOCOUNT ON;
    EXEC cfg.cfg_repo_publish
        @kind = N'pipeline_profile',
        @name = @name,
        @version = @version;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_upsert_assay_procedure
    @name nvarchar(256),
    @version nvarchar(64),
    @status varchar(32) = 'draft',
    @document_json json
AS
BEGIN
    SET NOCOUNT ON;
    EXEC cfg.cfg_repo_upsert
        @kind = N'assay_procedure',
        @name = @name,
        @version = @version,
        @status = @status,
        @document_json = @document_json;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_publish_assay_procedure
    @name nvarchar(256),
    @version nvarchar(64)
AS
BEGIN
    SET NOCOUNT ON;
    EXEC cfg.cfg_repo_publish
        @kind = N'assay_procedure',
        @name = @name,
        @version = @version;
END
GO
