/*
  Layered SamplePrep guardrail editors (Azure SQL).
  Site persists the full published window; profile / procedure persist a sparse overlay.
  Study GET/SET remain in portal_study_ops_api.sql (schema_id study_action_config_overlay).

  Prerequisites: portal_study_ops_api.sql (fn_json_deep_merge, fn_json_sparse_diff,
  fn_json_guardrail_slice), cfg.site / pipeline_profile / assay_procedure.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

CREATE OR ALTER FUNCTION portal.fn_json_default_site_action_config()
RETURNS nvarchar(max)
AS
BEGIN
    DECLARE @ac nvarchar(max) = N'{}';
    SELECT TOP (1)
        @ac = CAST(COALESCE(JSON_QUERY(CAST(document_json AS nvarchar(max)), '$.actionConfig'), N'{}') AS nvarchar(max))
    FROM cfg.site
    WHERE status = 'published'
    ORDER BY CASE WHEN name = N'default' THEN 0 ELSE 1 END, id DESC;
    IF @ac IS NULL OR ISJSON(@ac) <> 1
        SET @ac = N'{}';
    RETURN @ac;
END
GO

CREATE OR ALTER FUNCTION portal.fn_json_profile_action_config(@profile_name nvarchar(256))
RETURNS nvarchar(max)
AS
BEGIN
    DECLARE @ac nvarchar(max) = N'{}';
    IF @profile_name IS NULL OR LTRIM(RTRIM(@profile_name)) = N''
        RETURN N'{}';
    SELECT TOP (1)
        @ac = CAST(COALESCE(JSON_QUERY(CAST(document_json AS nvarchar(max)), '$.actionConfig'), N'{}') AS nvarchar(max))
    FROM cfg.pipeline_profile
    WHERE name = @profile_name AND status IN ('published', 'retired')
    ORDER BY id DESC;
    IF @ac IS NULL OR ISJSON(@ac) <> 1
        SET @ac = N'{}';
    RETURN @ac;
END
GO

CREATE OR ALTER FUNCTION portal.fn_json_full_window_ok(@doc nvarchar(max))
RETURNS bit
AS
BEGIN
    IF @doc IS NULL OR ISJSON(@doc) <> 1
        RETURN 0;
    IF JSON_VALUE(@doc, '$.alignment_qc.core_guardrails.min_pf_percent') IS NULL RETURN 0;
    IF JSON_VALUE(@doc, '$.alignment_qc.core_guardrails.min_q30_percent') IS NULL RETURN 0;
    IF JSON_VALUE(@doc, '$.alignment_qc.core_guardrails.min_mean_quality') IS NULL RETURN 0;
    IF JSON_VALUE(@doc, '$.alignment_qc.core_guardrails.min_quality_post20') IS NULL RETURN 0;
    IF JSON_VALUE(@doc, '$.alignment_qc.core_guardrails.max_at_dropout') IS NULL RETURN 0;
    IF JSON_VALUE(@doc, '$.alignment_qc.core_guardrails.max_gc_dropout') IS NULL RETURN 0;
    IF JSON_VALUE(@doc, '$.alignment_qc.core_guardrails.median_insert_min_bp') IS NULL RETURN 0;
    IF JSON_VALUE(@doc, '$.alignment_qc.core_guardrails.median_insert_max_bp') IS NULL RETURN 0;
    IF JSON_VALUE(@doc, '$.alignment_qc.core_guardrails.max_deamination_qscore') IS NULL RETURN 0;
    IF JSON_VALUE(@doc, '$.alignment_qc.core_guardrails.min_oxog_qscore') IS NULL RETURN 0;
    IF JSON_VALUE(@doc, '$.extraction_qc.guardrails.min_cpg_weighted_mean_coverage') IS NULL RETURN 0;
    IF JSON_VALUE(@doc, '$.extraction_qc.guardrails.max_chh_methylation_level') IS NULL RETURN 0;
    IF JSON_VALUE(@doc, '$.extraction_qc.guardrails.max_chg_methylation_level') IS NULL RETURN 0;
    IF JSON_VALUE(@doc, '$.extraction_qc.guardrails.min_autosomal_coverage_uniformity_ratio') IS NULL RETURN 0;
    IF JSON_VALUE(@doc, '$.extraction_qc.guardrails.max_discard_fraction') IS NULL RETURN 0;
    RETURN 1;
END
GO

CREATE OR ALTER FUNCTION portal.fn_json_replace_guardrail_keys(
    @existing nvarchar(max),
    @qc nvarchar(max)
)
RETURNS nvarchar(max)
AS
BEGIN
    DECLARE @new nvarchar(max) = @existing;
    IF @new IS NULL OR ISJSON(@new) <> 1 OR LEFT(LTRIM(@new), 1) <> N'{'
        SET @new = N'{}';
    SET @new = JSON_MODIFY(@new, '$.alignment_qc', NULL);
    SET @new = JSON_MODIFY(@new, '$.extraction_qc', NULL);
    IF @qc IS NULL OR ISJSON(@qc) <> 1 OR LEFT(LTRIM(@qc), 1) <> N'{'
        RETURN @new;

    DECLARE @key nvarchar(400);
    DECLARE @val nvarchar(max);
    DECLARE @type int;
    DECLARE @path nvarchar(500);

    DECLARE c CURSOR LOCAL FAST_FORWARD FOR
        SELECT [key], [value], [type] FROM OPENJSON(@qc);
    OPEN c;
    FETCH NEXT FROM c INTO @key, @val, @type;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        IF @type <> 0
        BEGIN
            SET @path = N'$.' + QUOTENAME(@key, N'"');
            IF @type IN (4, 5)
                SET @new = JSON_MODIFY(@new, @path, JSON_QUERY(@val));
            ELSE IF @type = 1
                SET @new = JSON_MODIFY(@new, @path, @val);
            ELSE IF @type IN (2, 3)
            BEGIN
                SET @new = JSON_MODIFY(@new, @path, N'__mp_json_token__');
                SET @new = REPLACE(@new, N'"__mp_json_token__"', @val);
            END
        END
        FETCH NEXT FROM c INTO @key, @val, @type;
    END
    CLOSE c;
    DEALLOCATE c;
    RETURN @new;
END
GO

CREATE OR ALTER FUNCTION portal.fn_guardrail_draft_version(
    @status varchar(32),
    @version nvarchar(64)
)
RETURNS nvarchar(64)
AS
BEGIN
    DECLARE @ver nvarchar(64) = COALESCE(NULLIF(LTRIM(RTRIM(@version)), N''), N'1');
    IF LOWER(COALESCE(@status, '')) = 'draft'
        RETURN @ver;
    RETURN @ver + N'-draft';
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_site_guardrails_editor
    @site_row_id bigint
AS
BEGIN
    SET NOCOUNT ON;
    IF @site_row_id IS NULL OR @site_row_id <= 0
        THROW 50001, N'site_row_id is required.', 1;
    IF NOT EXISTS (SELECT 1 FROM cfg.site WHERE id = @site_row_id)
        THROW 50010, N'cfg.site not found.', 1;

    DECLARE @name nvarchar(256);
    DECLARE @doc nvarchar(max);
    SELECT
        @name = s.name,
        @doc = CAST(s.document_json AS nvarchar(max))
    FROM cfg.site s
    WHERE s.id = @site_row_id;
    IF @doc IS NULL OR ISJSON(@doc) <> 1
        SET @doc = N'{}';

    SELECT
        @site_row_id AS site_row_id,
        @name AS site_name,
        N'sample_prep_guardrails' AS schema_id,
        portal.fn_json_guardrail_slice(
            COALESCE(JSON_QUERY(@doc, '$.actionConfig'), N'{}')
        ) AS effective_guardrails;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_set_site_guardrails_editor
    @site_row_id bigint,
    @edited_effective nvarchar(max)
AS
BEGIN
    SET NOCOUNT ON;
    IF @site_row_id IS NULL OR @site_row_id <= 0
        THROW 50001, N'site_row_id is required.', 1;
    IF NOT EXISTS (SELECT 1 FROM cfg.site WHERE id = @site_row_id)
        THROW 50010, N'cfg.site not found.', 1;
    IF @edited_effective IS NULL OR ISJSON(@edited_effective) <> 1
        OR LEFT(LTRIM(@edited_effective), 1) <> N'{'
        THROW 50021, N'edited_effective must be a JSON object (full working document).', 1;

    DECLARE @doc nvarchar(max) = (
        SELECT CAST(document_json AS nvarchar(max)) FROM cfg.site WHERE id = @site_row_id
    );
    IF @doc IS NULL OR ISJSON(@doc) <> 1
        SET @doc = N'{}';

    DECLARE @existing nvarchar(max) = COALESCE(JSON_QUERY(@doc, '$.actionConfig'), N'{}');
    DECLARE @edited nvarchar(max) = portal.fn_json_guardrail_slice(@edited_effective);
    IF portal.fn_json_full_window_ok(@edited) = 0
        THROW 50022, N'site guardrails require the full published window.', 1;

    DECLARE @new nvarchar(max) = portal.fn_json_replace_guardrail_keys(@existing, @edited);
    SET @doc = JSON_MODIFY(@doc, '$.actionConfig', JSON_QUERY(@new));

    UPDATE cfg.site
    SET document_json = CAST(@doc AS json),
        content_hash = CONVERT(nvarchar(128), HASHBYTES('SHA2_256', @doc), 2),
        updated_at_utc = SYSUTCDATETIME()
    WHERE id = @site_row_id;

    EXEC portal.sp_get_site_guardrails_editor @site_row_id = @site_row_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_profile_guardrails_editor
    @pipeline_profile_id bigint
AS
BEGIN
    SET NOCOUNT ON;
    IF @pipeline_profile_id IS NULL OR @pipeline_profile_id <= 0
        THROW 50001, N'pipeline_profile_id is required.', 1;
    IF NOT EXISTS (SELECT 1 FROM cfg.pipeline_profile WHERE id = @pipeline_profile_id)
        THROW 50010, N'cfg.pipeline_profile not found.', 1;

    DECLARE @name nvarchar(256);
    DECLARE @version nvarchar(64);
    DECLARE @status varchar(32);
    DECLARE @doc nvarchar(max);
    DECLARE @site_name nvarchar(256);
    SELECT
        @name = p.name,
        @version = p.version,
        @status = p.status,
        @doc = CAST(p.document_json AS nvarchar(max))
    FROM cfg.pipeline_profile p
    WHERE p.id = @pipeline_profile_id;
    IF @doc IS NULL OR ISJSON(@doc) <> 1
        SET @doc = N'{}';

    SELECT TOP (1) @site_name = name
    FROM cfg.site
    WHERE status = 'published'
    ORDER BY CASE WHEN name = N'default' THEN 0 ELSE 1 END, id DESC;

    DECLARE @inherited nvarchar(max) = portal.fn_json_guardrail_slice(
        portal.fn_json_default_site_action_config()
    );
    DECLARE @overlay nvarchar(max) = portal.fn_json_guardrail_slice(
        COALESCE(JSON_QUERY(@doc, '$.actionConfig'), N'{}')
    );

    SELECT
        @pipeline_profile_id AS pipeline_profile_id,
        @name AS pipeline_profile,
        @version AS version,
        @status AS status,
        @site_name AS site_name,
        N'sample_prep_guardrails_overlay' AS schema_id,
        @inherited AS inherited_guardrails,
        @overlay AS profile_guardrail_overlay,
        portal.fn_json_deep_merge(@inherited, @overlay) AS effective_guardrails;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_set_profile_guardrails_editor
    @pipeline_profile_id bigint,
    @edited_effective nvarchar(max)
AS
BEGIN
    SET NOCOUNT ON;
    IF @pipeline_profile_id IS NULL OR @pipeline_profile_id <= 0
        THROW 50001, N'pipeline_profile_id is required.', 1;
    IF NOT EXISTS (SELECT 1 FROM cfg.pipeline_profile WHERE id = @pipeline_profile_id)
        THROW 50010, N'cfg.pipeline_profile not found.', 1;
    IF @edited_effective IS NULL OR ISJSON(@edited_effective) <> 1
        OR LEFT(LTRIM(@edited_effective), 1) <> N'{'
        THROW 50021, N'edited_effective must be a JSON object (full working document).', 1;

    DECLARE @name nvarchar(256);
    DECLARE @version nvarchar(64);
    DECLARE @status varchar(32);
    DECLARE @doc nvarchar(max);
    SELECT
        @name = name,
        @version = version,
        @status = status,
        @doc = CAST(document_json AS nvarchar(max))
    FROM cfg.pipeline_profile WHERE id = @pipeline_profile_id;
    IF @doc IS NULL OR ISJSON(@doc) <> 1
        SET @doc = N'{}';

    DECLARE @existing nvarchar(max) = COALESCE(JSON_QUERY(@doc, '$.actionConfig'), N'{}');
    DECLARE @inherited nvarchar(max) = portal.fn_json_guardrail_slice(
        portal.fn_json_default_site_action_config()
    );
    DECLARE @edited nvarchar(max) = portal.fn_json_guardrail_slice(@edited_effective);
    DECLARE @diff nvarchar(max) = portal.fn_json_sparse_diff(@inherited, @edited);
    DECLARE @new nvarchar(max) = portal.fn_json_replace_guardrail_keys(@existing, @diff);
    SET @doc = JSON_MODIFY(@doc, '$.actionConfig', JSON_QUERY(@new));

    DECLARE @save_version nvarchar(64) = portal.fn_guardrail_draft_version(@status, @version);
    DECLARE @doc_json json = CAST(@doc AS json);
    DECLARE @ids TABLE (id bigint);
    INSERT INTO @ids (id)
    EXEC cfg.cfg_repo_upsert
        @kind = N'pipeline_profile',
        @name = @name,
        @version = @save_version,
        @status = 'draft',
        @document_json = @doc_json;

    DECLARE @new_id bigint = (SELECT TOP (1) id FROM @ids);
    EXEC portal.sp_get_profile_guardrails_editor @pipeline_profile_id = @new_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_assay_procedure_guardrails_editor
    @assay_procedure_id bigint
AS
BEGIN
    SET NOCOUNT ON;
    IF @assay_procedure_id IS NULL OR @assay_procedure_id <= 0
        THROW 50001, N'assay_procedure_id is required.', 1;
    IF NOT EXISTS (SELECT 1 FROM cfg.assay_procedure WHERE id = @assay_procedure_id)
        THROW 50010, N'cfg.assay_procedure not found.', 1;

    DECLARE @name nvarchar(256);
    DECLARE @version nvarchar(64);
    DECLARE @status varchar(32);
    DECLARE @doc nvarchar(max);
    DECLARE @site_name nvarchar(256);
    SELECT
        @name = a.name,
        @version = a.version,
        @status = a.status,
        @doc = CAST(a.document_json AS nvarchar(max))
    FROM cfg.assay_procedure a
    WHERE a.id = @assay_procedure_id;
    IF @doc IS NULL OR ISJSON(@doc) <> 1
        SET @doc = N'{}';

    SELECT TOP (1) @site_name = name
    FROM cfg.site
    WHERE status = 'published'
    ORDER BY CASE WHEN name = N'default' THEN 0 ELSE 1 END, id DESC;

    DECLARE @profile_name nvarchar(256) = JSON_VALUE(@doc, '$.pipelineProfile');
    DECLARE @inherited nvarchar(max) = portal.fn_json_deep_merge(
        portal.fn_json_guardrail_slice(portal.fn_json_default_site_action_config()),
        portal.fn_json_guardrail_slice(portal.fn_json_profile_action_config(@profile_name))
    );
    DECLARE @overlay nvarchar(max) = portal.fn_json_guardrail_slice(
        COALESCE(JSON_QUERY(@doc, '$.actionConfig'), N'{}')
    );

    SELECT
        @assay_procedure_id AS assay_procedure_id,
        @name AS pipeline_procedure,
        @version AS version,
        @status AS status,
        @profile_name AS pipeline_profile,
        @site_name AS site_name,
        N'sample_prep_guardrails_overlay' AS schema_id,
        @inherited AS inherited_guardrails,
        @overlay AS procedure_guardrail_overlay,
        portal.fn_json_deep_merge(@inherited, @overlay) AS effective_guardrails;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_set_assay_procedure_guardrails_editor
    @assay_procedure_id bigint,
    @edited_effective nvarchar(max)
AS
BEGIN
    SET NOCOUNT ON;
    IF @assay_procedure_id IS NULL OR @assay_procedure_id <= 0
        THROW 50001, N'assay_procedure_id is required.', 1;
    IF NOT EXISTS (SELECT 1 FROM cfg.assay_procedure WHERE id = @assay_procedure_id)
        THROW 50010, N'cfg.assay_procedure not found.', 1;
    IF @edited_effective IS NULL OR ISJSON(@edited_effective) <> 1
        OR LEFT(LTRIM(@edited_effective), 1) <> N'{'
        THROW 50021, N'edited_effective must be a JSON object (full working document).', 1;

    DECLARE @name nvarchar(256);
    DECLARE @version nvarchar(64);
    DECLARE @status varchar(32);
    DECLARE @doc nvarchar(max);
    SELECT
        @name = name,
        @version = version,
        @status = status,
        @doc = CAST(document_json AS nvarchar(max))
    FROM cfg.assay_procedure WHERE id = @assay_procedure_id;
    IF @doc IS NULL OR ISJSON(@doc) <> 1
        SET @doc = N'{}';

    DECLARE @existing nvarchar(max) = COALESCE(JSON_QUERY(@doc, '$.actionConfig'), N'{}');
    DECLARE @profile_name nvarchar(256) = JSON_VALUE(@doc, '$.pipelineProfile');
    DECLARE @inherited nvarchar(max) = portal.fn_json_deep_merge(
        portal.fn_json_guardrail_slice(portal.fn_json_default_site_action_config()),
        portal.fn_json_guardrail_slice(portal.fn_json_profile_action_config(@profile_name))
    );
    DECLARE @edited nvarchar(max) = portal.fn_json_guardrail_slice(@edited_effective);
    DECLARE @diff nvarchar(max) = portal.fn_json_sparse_diff(@inherited, @edited);
    DECLARE @new nvarchar(max) = portal.fn_json_replace_guardrail_keys(@existing, @diff);
    SET @doc = JSON_MODIFY(@doc, '$.actionConfig', JSON_QUERY(@new));

    DECLARE @save_version nvarchar(64) = portal.fn_guardrail_draft_version(@status, @version);
    DECLARE @doc_json json = CAST(@doc AS json);
    DECLARE @ids TABLE (id bigint);
    INSERT INTO @ids (id)
    EXEC cfg.cfg_repo_upsert
        @kind = N'assay_procedure',
        @name = @name,
        @version = @save_version,
        @status = 'draft',
        @document_json = @doc_json;

    DECLARE @new_id bigint = (SELECT TOP (1) id FROM @ids);
    EXEC portal.sp_get_assay_procedure_guardrails_editor @assay_procedure_id = @new_id;
END
GO
