/*
  Study operator SQL contracts (Azure SQL).

  Link / storage / next-run actionConfig overlay, instance header + config
  snapshot, sample×stage progress, and run/task fail-cancel-stop.

  Deploy after portal_contract_api.sql, portal_study_pipeline_api.sql,
  portal_ops_recovery_api.sql, wf_worker_desired_state.sql.

  Operator engine_error_code:
    4097 OPERATOR_CANCELLED
    4098 OPERATOR_FAILED
    4099 WORKER_STOPPED (existing in-flight abort)
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF COL_LENGTH(N'wf.node_execution', N'stop_requested') IS NULL
BEGIN
    ALTER TABLE wf.node_execution ADD stop_requested bit NOT NULL
        CONSTRAINT DF_ne_stop_requested DEFAULT (0);
END
GO

IF SCHEMA_ID(N'portal') IS NULL
    EXEC(N'CREATE SCHEMA portal');
GO

CREATE OR ALTER FUNCTION portal.fn_redact_json_credentials(@payload nvarchar(max))
RETURNS nvarchar(max)
AS
BEGIN
    IF @payload IS NULL OR ISJSON(@payload) <> 1
        RETURN @payload;

    DECLARE @j nvarchar(max) = @payload;
    SET @j = JSON_MODIFY(@j, '$.credentials', NULL);
    SET @j = JSON_MODIFY(@j, '$.fastqSource.credentials', NULL);
    SET @j = JSON_MODIFY(@j, '$.fastqStorage.credentials', NULL);
    SET @j = JSON_MODIFY(@j, '$.sampleDestination.credentials', NULL);
    SET @j = JSON_MODIFY(@j, '$.sampleStorage.credentials', NULL);
    SET @j = JSON_MODIFY(@j, '$.h5Destination.credentials', NULL);
    SET @j = JSON_MODIFY(@j, '$.h5Storage.credentials', NULL);

    IF JSON_QUERY(@j, '$.samples') IS NOT NULL
    BEGIN
        DECLARE @parts nvarchar(max);
        SELECT @parts = STRING_AGG(
            portal.fn_redact_json_credentials(s.[value]),
            N','
        ) WITHIN GROUP (ORDER BY TRY_CAST(s.[key] AS int))
        FROM OPENJSON(@j, '$.samples') s;
        SET @j = JSON_MODIFY(
            @j,
            '$.samples',
            JSON_QUERY(CONCAT(N'[', ISNULL(@parts, N''), N']'))
        );
    END

    RETURN @j;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_link_study_instance
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

    IF @study_row_id IS NULL OR @study_row_id <= 0
        THROW 50001, N'study_row_id is required.', 1;
    IF @workflow_instance_id IS NULL OR @workflow_instance_id <= 0
        THROW 50001, N'workflow_instance_id is required.', 1;
    IF NOT EXISTS (SELECT 1 FROM cfg.study WHERE id = @study_row_id)
        THROW 50010, N'cfg.study not found.', 1;
    IF NOT EXISTS (SELECT 1 FROM wf.workflow_instance WHERE id = @workflow_instance_id)
        THROW 50010, N'workflow_instance not found.', 1;

    EXEC cfg.cfg_repo_link_study_instance
        @study_row_id = @study_row_id,
        @workflow_instance_id = @workflow_instance_id,
        @domain_program_id = @domain_program_id,
        @pipeline_profile_id = @pipeline_profile_id,
        @site_id = @site_id,
        @storage_profile_id = @storage_profile_id,
        @assay_procedure_id = @assay_procedure_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_study_storage
    @study_row_id bigint
AS
BEGIN
    SET NOCOUNT ON;

    IF @study_row_id IS NULL OR @study_row_id <= 0
        THROW 50001, N'study_row_id is required.', 1;

    SELECT
        s.id AS study_row_id,
        s.name AS study_name,
        TRY_CAST(JSON_VALUE(CAST(s.document_json AS nvarchar(max)), '$.storage.fastqSourceEndpointId') AS bigint)
            AS fastq_source_endpoint_id,
        src.name AS fastq_source_name,
        src.provider AS fastq_source_provider,
        src.status AS fastq_source_status,
        TRY_CAST(JSON_VALUE(CAST(s.document_json AS nvarchar(max)), '$.storage.sampleDestinationEndpointId') AS bigint)
            AS sample_destination_endpoint_id,
        dst.name AS sample_destination_name,
        dst.provider AS sample_destination_provider,
        dst.status AS sample_destination_status
    FROM cfg.study s
    LEFT JOIN cfg.storage_endpoint src
        ON src.id = TRY_CAST(JSON_VALUE(CAST(s.document_json AS nvarchar(max)), '$.storage.fastqSourceEndpointId') AS bigint)
    LEFT JOIN cfg.storage_endpoint dst
        ON dst.id = TRY_CAST(JSON_VALUE(CAST(s.document_json AS nvarchar(max)), '$.storage.sampleDestinationEndpointId') AS bigint)
    WHERE s.id = @study_row_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_set_study_storage
    @study_row_id bigint,
    @fastq_source_endpoint_id bigint = NULL,
    @sample_destination_endpoint_id bigint = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF @study_row_id IS NULL OR @study_row_id <= 0
        THROW 50001, N'study_row_id is required.', 1;
    IF NOT EXISTS (SELECT 1 FROM cfg.study WHERE id = @study_row_id)
        THROW 50010, N'cfg.study not found.', 1;

    IF @fastq_source_endpoint_id IS NOT NULL
       AND NOT EXISTS (
            SELECT 1 FROM cfg.storage_endpoint
            WHERE id = @fastq_source_endpoint_id AND status = N'published'
       )
        THROW 50021, N'fastq_source_endpoint_id must be a published storage endpoint.', 1;

    IF @sample_destination_endpoint_id IS NOT NULL
       AND NOT EXISTS (
            SELECT 1 FROM cfg.storage_endpoint
            WHERE id = @sample_destination_endpoint_id AND status = N'published'
       )
        THROW 50021, N'sample_destination_endpoint_id must be a published storage endpoint.', 1;

    DECLARE @doc nvarchar(max) = (
        SELECT CAST(document_json AS nvarchar(max)) FROM cfg.study WHERE id = @study_row_id
    );
    IF @doc IS NULL OR ISJSON(@doc) <> 1
        SET @doc = N'{}';
    IF JSON_QUERY(@doc, '$.storage') IS NULL
        SET @doc = JSON_MODIFY(@doc, '$.storage', JSON_QUERY(N'{}'));

    SET @doc = JSON_MODIFY(@doc, '$.storage.fastqSourceEndpointId', @fastq_source_endpoint_id);
    SET @doc = JSON_MODIFY(@doc, '$.storage.sampleDestinationEndpointId', @sample_destination_endpoint_id);

    UPDATE cfg.study
    SET document_json = CAST(@doc AS json),
        content_hash = CONVERT(nvarchar(128), HASHBYTES('SHA2_256', @doc), 2),
        updated_at_utc = SYSUTCDATETIME()
    WHERE id = @study_row_id;

    EXEC portal.sp_get_study_storage @study_row_id = @study_row_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_study_action_config_overlay
    @study_row_id bigint
AS
BEGIN
    SET NOCOUNT ON;

    IF @study_row_id IS NULL OR @study_row_id <= 0
        THROW 50001, N'study_row_id is required.', 1;

    SELECT
        s.id AS study_row_id,
        s.name AS study_name,
        CAST(COALESCE(JSON_QUERY(CAST(s.document_json AS nvarchar(max)), '$.actionConfig'), N'{}') AS nvarchar(max))
            AS action_config_overlay
    FROM cfg.study s
    WHERE s.id = @study_row_id;
END
GO

-- Replace study document_json.actionConfig with the supplied nested object.
-- HPO promote must merge dotted trial overrides first (fn_apply_dotted_action_config);
-- do not pass trial overrides_json here or sibling guardrails are wiped.
CREATE OR ALTER PROCEDURE portal.sp_set_study_action_config_overlay
    @study_row_id bigint,
    @action_config_overlay nvarchar(max)
AS
BEGIN
    SET NOCOUNT ON;

    IF @study_row_id IS NULL OR @study_row_id <= 0
        THROW 50001, N'study_row_id is required.', 1;
    IF NOT EXISTS (SELECT 1 FROM cfg.study WHERE id = @study_row_id)
        THROW 50010, N'cfg.study not found.', 1;
    IF @action_config_overlay IS NULL OR ISJSON(@action_config_overlay) <> 1
        THROW 50021, N'action_config_overlay must be a JSON object.', 1;
    IF LEFT(LTRIM(@action_config_overlay), 1) <> N'{'
        THROW 50021, N'action_config_overlay must be a JSON object.', 1;

    DECLARE @doc nvarchar(max) = (
        SELECT CAST(document_json AS nvarchar(max)) FROM cfg.study WHERE id = @study_row_id
    );
    IF @doc IS NULL OR ISJSON(@doc) <> 1
        SET @doc = N'{}';

    SET @doc = JSON_MODIFY(@doc, '$.actionConfig', JSON_QUERY(@action_config_overlay));

    UPDATE cfg.study
    SET document_json = CAST(@doc AS json),
        content_hash = CONVERT(nvarchar(128), HASHBYTES('SHA2_256', @doc), 2),
        updated_at_utc = SYSUTCDATETIME()
    WHERE id = @study_row_id;

    EXEC portal.sp_get_study_action_config_overlay @study_row_id = @study_row_id;
END
GO

CREATE OR ALTER FUNCTION portal.fn_json_deep_merge(
    @base nvarchar(max),
    @overlay nvarchar(max)
)
RETURNS nvarchar(max)
AS
BEGIN
    DECLARE @result nvarchar(max);
    IF @overlay IS NULL OR ISJSON(@overlay) <> 1 OR LEFT(LTRIM(@overlay), 1) <> N'{'
        RETURN CASE
            WHEN @base IS NULL OR ISJSON(@base) <> 1 OR LEFT(LTRIM(@base), 1) <> N'{' THEN N'{}'
            ELSE @base
        END;
    SET @result = CASE
        WHEN @base IS NULL OR ISJSON(@base) <> 1 OR LEFT(LTRIM(@base), 1) <> N'{' THEN N'{}'
        ELSE @base
    END;

    DECLARE @key nvarchar(400);
    DECLARE @val nvarchar(max);
    DECLARE @type int;
    DECLARE @path nvarchar(500);
    DECLARE @child nvarchar(max);

    DECLARE c CURSOR LOCAL FAST_FORWARD FOR
        SELECT [key], [value], [type] FROM OPENJSON(@overlay);
    OPEN c;
    FETCH NEXT FROM c INTO @key, @val, @type;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @path = N'$.' + QUOTENAME(@key, N'"');
        IF @type = 0
            SET @result = JSON_MODIFY(@result, @path, NULL);
        ELSE IF @type = 5 AND JSON_QUERY(@result, @path) IS NOT NULL
        BEGIN
            SET @child = portal.fn_json_deep_merge(JSON_QUERY(@result, @path), @val);
            SET @result = JSON_MODIFY(@result, @path, JSON_QUERY(@child));
        END
        ELSE IF @type IN (4, 5)
            SET @result = JSON_MODIFY(@result, @path, JSON_QUERY(@val));
        ELSE IF @type = 1
            SET @result = JSON_MODIFY(@result, @path, @val);
        ELSE IF @type IN (2, 3)
        BEGIN
            SET @result = JSON_MODIFY(@result, @path, N'__mp_json_token__');
            SET @result = REPLACE(@result, N'"__mp_json_token__"', @val);
        END
        FETCH NEXT FROM c INTO @key, @val, @type;
    END
    CLOSE c;
    DEALLOCATE c;
    RETURN @result;
END
GO

CREATE OR ALTER FUNCTION portal.fn_json_sparse_diff(
    @baseline nvarchar(max),
    @edited nvarchar(max)
)
RETURNS nvarchar(max)
AS
BEGIN
    DECLARE @base nvarchar(max) = @baseline;
    DECLARE @edit nvarchar(max) = @edited;
    DECLARE @result nvarchar(max) = N'{}';
    DECLARE @key nvarchar(400);
    DECLARE @eval nvarchar(max);
    DECLARE @etype int;
    DECLARE @bval nvarchar(max);
    DECLARE @btype int;
    DECLARE @path nvarchar(500);
    DECLARE @child nvarchar(max);

    IF @base IS NULL OR ISJSON(@base) <> 1 OR LEFT(LTRIM(@base), 1) <> N'{'
        SET @base = N'{}';
    IF @edit IS NULL OR ISJSON(@edit) <> 1 OR LEFT(LTRIM(@edit), 1) <> N'{'
        SET @edit = N'{}';

    DECLARE c CURSOR LOCAL FAST_FORWARD FOR
        SELECT [key], [value], [type] FROM OPENJSON(@edit);
    OPEN c;
    FETCH NEXT FROM c INTO @key, @eval, @etype;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @path = N'$.' + QUOTENAME(@key, N'"');
        SET @bval = NULL;
        SET @btype = NULL;
        SELECT @bval = [value], @btype = [type]
        FROM OPENJSON(@base)
        WHERE [key] = @key;

        IF @etype = 0
        BEGIN
            IF @btype IS NOT NULL
            BEGIN
                SET @result = JSON_MODIFY(@result, @path, N'__mp_json_null__');
                SET @result = REPLACE(@result, N'"__mp_json_null__"', N'null');
            END
        END
        ELSE IF @etype = 5 AND @btype = 5
        BEGIN
            SET @child = portal.fn_json_sparse_diff(@bval, @eval);
            IF @child IS NOT NULL AND @child <> N'{}'
                SET @result = JSON_MODIFY(@result, @path, JSON_QUERY(@child));
        END
        ELSE IF @btype IS NULL OR @btype <> @etype OR ISNULL(@bval, N'') <> ISNULL(@eval, N'')
        BEGIN
            IF @etype = 1
                SET @result = JSON_MODIFY(@result, @path, @eval);
            ELSE IF @etype IN (2, 3)
            BEGIN
                SET @result = JSON_MODIFY(@result, @path, N'__mp_json_token__');
                SET @result = REPLACE(@result, N'"__mp_json_token__"', @eval);
            END
            ELSE IF @etype IN (4, 5)
                SET @result = JSON_MODIFY(@result, @path, JSON_QUERY(@eval));
        END
        FETCH NEXT FROM c INTO @key, @eval, @etype;
    END
    CLOSE c;
    DEALLOCATE c;

    DECLARE d CURSOR LOCAL FAST_FORWARD FOR
        SELECT [key] FROM OPENJSON(@base);
    OPEN d;
    FETCH NEXT FROM d INTO @key;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM OPENJSON(@edit) WHERE [key] = @key)
        BEGIN
            SET @path = N'$.' + QUOTENAME(@key, N'"');
            SET @result = JSON_MODIFY(@result, @path, N'__mp_json_null__');
            SET @result = REPLACE(@result, N'"__mp_json_null__"', N'null');
        END
        FETCH NEXT FROM d INTO @key;
    END
    CLOSE d;
    DEALLOCATE d;
    RETURN @result;
END
GO

CREATE OR ALTER FUNCTION portal.fn_json_guardrail_slice(@action_config nvarchar(max))
RETURNS nvarchar(max)
AS
BEGIN
    DECLARE @src nvarchar(max) = @action_config;
    DECLARE @out nvarchar(max) = N'{}';
    DECLARE @aq nvarchar(max);
    DECLARE @eq nvarchar(max);

    IF @src IS NULL OR ISJSON(@src) <> 1 OR LEFT(LTRIM(@src), 1) <> N'{'
        RETURN N'{}';

    SET @aq = JSON_QUERY(@src, '$.alignment_qc');
    IF @aq IS NOT NULL
    BEGIN
        SET @aq = JSON_MODIFY(@aq, '$.sample_paths', NULL);
        SET @aq = JSON_MODIFY(@aq, '$.output_dir', NULL);
        SET @aq = JSON_MODIFY(@aq, '$.validate_schema', NULL);
        SET @aq = JSON_MODIFY(@aq, '$.genome_fasta', NULL);
        SET @aq = JSON_MODIFY(@aq, '$.reference_fasta', NULL);
        SET @out = JSON_MODIFY(@out, '$.alignment_qc', JSON_QUERY(@aq));
    END

    SET @eq = JSON_QUERY(@src, '$.extraction_qc');
    IF @eq IS NOT NULL
    BEGIN
        SET @eq = JSON_MODIFY(@eq, '$.sample_paths', NULL);
        SET @out = JSON_MODIFY(@out, '$.extraction_qc', JSON_QUERY(@eq));
    END
    RETURN @out;
END
GO

CREATE OR ALTER FUNCTION portal.fn_study_guardrails_inherited(@study_row_id bigint)
RETURNS nvarchar(max)
AS
BEGIN
    DECLARE @doc nvarchar(max);
    DECLARE @site nvarchar(max) = N'{}';
    DECLARE @profile nvarchar(max) = N'{}';
    DECLARE @procedure nvarchar(max) = N'{}';
    DECLARE @profile_name nvarchar(256);
    DECLARE @procedure_name nvarchar(256);

    SELECT @doc = CAST(document_json AS nvarchar(max))
    FROM cfg.study
    WHERE id = @study_row_id;
    IF @doc IS NULL OR ISJSON(@doc) <> 1
        SET @doc = N'{}';

    SET @profile_name = JSON_VALUE(@doc, '$.pipelineProfile');
    SET @procedure_name = JSON_VALUE(@doc, '$.pipelineProcedure');

    SELECT TOP (1) @site = CAST(COALESCE(JSON_QUERY(CAST(document_json AS nvarchar(max)), '$.actionConfig'), N'{}') AS nvarchar(max))
    FROM cfg.site
    WHERE status = 'published'
    ORDER BY CASE WHEN name = N'default' THEN 0 ELSE 1 END, id DESC;

    IF @profile_name IS NOT NULL AND @profile_name <> N''
    BEGIN
        SELECT TOP (1) @profile = CAST(COALESCE(JSON_QUERY(CAST(document_json AS nvarchar(max)), '$.actionConfig'), N'{}') AS nvarchar(max))
        FROM cfg.pipeline_profile
        WHERE name = @profile_name AND status IN ('published', 'retired')
        ORDER BY id DESC;
    END

    IF @procedure_name IS NOT NULL AND @procedure_name <> N''
    BEGIN
        SELECT TOP (1) @procedure = CAST(COALESCE(JSON_QUERY(CAST(document_json AS nvarchar(max)), '$.actionConfig'), N'{}') AS nvarchar(max))
        FROM cfg.assay_procedure
        WHERE name = @procedure_name AND status IN ('published', 'retired')
        ORDER BY id DESC;
    END

    RETURN portal.fn_json_deep_merge(
        portal.fn_json_deep_merge(
            portal.fn_json_guardrail_slice(@site),
            portal.fn_json_guardrail_slice(@profile)
        ),
        portal.fn_json_guardrail_slice(@procedure)
    );
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_study_guardrails_editor
    @study_row_id bigint
AS
BEGIN
    SET NOCOUNT ON;

    IF @study_row_id IS NULL OR @study_row_id <= 0
        THROW 50001, N'study_row_id is required.', 1;
    IF NOT EXISTS (SELECT 1 FROM cfg.study WHERE id = @study_row_id)
        THROW 50010, N'cfg.study not found.', 1;

    DECLARE @doc nvarchar(max);
    DECLARE @name nvarchar(256);
    DECLARE @overlay nvarchar(max);
    DECLARE @inherited nvarchar(max);
    DECLARE @site_name nvarchar(256);

    SELECT
        @name = s.name,
        @doc = CAST(s.document_json AS nvarchar(max))
    FROM cfg.study s
    WHERE s.id = @study_row_id;
    IF @doc IS NULL OR ISJSON(@doc) <> 1
        SET @doc = N'{}';

    SET @overlay = portal.fn_json_guardrail_slice(
        COALESCE(JSON_QUERY(@doc, '$.actionConfig'), N'{}')
    );
    SET @inherited = portal.fn_study_guardrails_inherited(@study_row_id);

    SELECT TOP (1) @site_name = name
    FROM cfg.site
    WHERE status = 'published'
    ORDER BY CASE WHEN name = N'default' THEN 0 ELSE 1 END, id DESC;

    SELECT
        @study_row_id AS study_row_id,
        @name AS study_name,
        @site_name AS site_name,
        JSON_VALUE(@doc, '$.pipelineProfile') AS pipeline_profile,
        JSON_VALUE(@doc, '$.pipelineProcedure') AS pipeline_procedure,
        N'study_action_config_overlay' AS schema_id,
        @inherited AS inherited_guardrails,
        @overlay AS study_guardrail_overlay,
        portal.fn_json_deep_merge(@inherited, @overlay) AS effective_guardrails;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_set_study_guardrails_editor
    @study_row_id bigint,
    @edited_effective nvarchar(max)
AS
BEGIN
    SET NOCOUNT ON;

    IF @study_row_id IS NULL OR @study_row_id <= 0
        THROW 50001, N'study_row_id is required.', 1;
    IF NOT EXISTS (SELECT 1 FROM cfg.study WHERE id = @study_row_id)
        THROW 50010, N'cfg.study not found.', 1;
    IF @edited_effective IS NULL OR ISJSON(@edited_effective) <> 1
        OR LEFT(LTRIM(@edited_effective), 1) <> N'{'
        THROW 50021, N'edited_effective must be a JSON object (full working document).', 1;

    DECLARE @doc nvarchar(max) = (
        SELECT CAST(document_json AS nvarchar(max)) FROM cfg.study WHERE id = @study_row_id
    );
    IF @doc IS NULL OR ISJSON(@doc) <> 1
        SET @doc = N'{}';

    DECLARE @existing nvarchar(max) = COALESCE(JSON_QUERY(@doc, '$.actionConfig'), N'{}');
    DECLARE @inherited nvarchar(max) = portal.fn_study_guardrails_inherited(@study_row_id);
    DECLARE @edited nvarchar(max) = portal.fn_json_guardrail_slice(@edited_effective);
    DECLARE @diff nvarchar(max) = portal.fn_json_sparse_diff(@inherited, @edited);
    DECLARE @new nvarchar(max) = @existing;
    DECLARE @key nvarchar(400);
    DECLARE @val nvarchar(max);
    DECLARE @type int;
    DECLARE @path nvarchar(500);

    SET @new = JSON_MODIFY(@new, '$.alignment_qc', NULL);
    SET @new = JSON_MODIFY(@new, '$.extraction_qc', NULL);

    DECLARE c CURSOR LOCAL FAST_FORWARD FOR
        SELECT [key], [value], [type] FROM OPENJSON(@diff);
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

    SET @doc = JSON_MODIFY(@doc, '$.actionConfig', JSON_QUERY(@new));

    UPDATE cfg.study
    SET document_json = CAST(@doc AS json),
        content_hash = CONVERT(nvarchar(128), HASHBYTES('SHA2_256', @doc), 2),
        updated_at_utc = SYSUTCDATETIME()
    WHERE id = @study_row_id;

    EXEC portal.sp_get_study_guardrails_editor @study_row_id = @study_row_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_create_and_start_instance
    @workflow_version_id bigint,
    @context_json nvarchar(max) = NULL,
    @scope_id int = NULL,
    @study_row_id bigint = NULL,
    @domain_program_id bigint = NULL,
    @pipeline_profile_id bigint = NULL,
    @site_id bigint = NULL,
    @storage_profile_id bigint = NULL,
    @assay_procedure_id bigint = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF @scope_id IS NOT NULL
    BEGIN
        DECLARE @Access TABLE (IsAllowed bit, ContractID int, ReasonCode nvarchar(64));
        INSERT INTO @Access (IsAllowed, ContractID, ReasonCode)
        EXEC Contract.spContractValidateScopeAccess @ScopeID = @scope_id;

        DECLARE @allowed bit = (SELECT TOP (1) IsAllowed FROM @Access);
        DECLARE @contract_id int = (SELECT TOP (1) ContractID FROM @Access);

        IF ISNULL(@allowed, 0) = 0
            THROW 50200, N'NO_ACTIVE_CONTRACT_FOR_SCOPE', 1;

        DECLARE @pack varchar(32) = portal.fn_infer_process_pack_from_context(@context_json);
        IF NOT EXISTS (
            SELECT 1 FROM portal.fn_contract_entitled_modalities(@scope_id)
            WHERE modality = @pack
        )
            THROW 50201, N'PROCESS_PACK_NOT_ENTITLED', 1;

        DECLARE @def_id bigint;
        SELECT @def_id = workflow_def_id FROM wf.workflow_version WHERE id = @workflow_version_id;
        IF @def_id IS NULL
            THROW 50001, N'workflow_version_id not found.', 1;

        DECLARE @cwe_enabled bit;
        DECLARE @max_runs int;
        DECLARE @period_type varchar(8);
        SELECT
            @cwe_enabled = e.Enabled,
            @max_runs = e.MaxRunsPerPeriod,
            @period_type = e.PeriodType
        FROM Contract.ContractWorkflowEntitlements e
        WHERE e.ContractID = @contract_id AND e.WorkflowDefID = @def_id;

        IF @cwe_enabled = 0
            THROW 50202, N'WORKFLOW_NOT_ENTITLED', 1;

        IF @cwe_enabled = 1 AND @max_runs IS NOT NULL AND @period_type IS NOT NULL
        BEGIN
            DECLARE @period_start datetime2(3);
            DECLARE @now datetime2(3) = SYSUTCDATETIME();
            IF @period_type = 'DAY'
                SET @period_start = DATEFROMPARTS(YEAR(@now), MONTH(@now), DAY(@now));
            ELSE IF @period_type = 'WEEK'
                SET @period_start = DATEADD(DAY, 1 - DATEPART(WEEKDAY, CAST(@now AS DATE)), CAST(CAST(@now AS DATE) AS DATETIME2(3)));
            ELSE IF @period_type = 'MONTH'
                SET @period_start = DATEFROMPARTS(YEAR(@now), MONTH(@now), 1);

            DECLARE @runs int = 0;
            SELECT @runs = ISNULL(w.RunsExecuted, 0)
            FROM Contract.WorkflowUsageCounters w
            WHERE w.ContractID = @contract_id
              AND w.ScopeID = @scope_id
              AND w.WorkflowDefID = @def_id
              AND w.PeriodType = @period_type
              AND w.PeriodStartUtc = @period_start;

            IF @runs >= @max_runs
                THROW 50203, N'WORKFLOW_QUOTA_EXCEEDED', 1;
        END
    END

    DECLARE @instance_id bigint;
    DECLARE @ctx json = TRY_CAST(@context_json AS json);

    CREATE TABLE #created (id bigint);
    INSERT INTO #created (id)
    EXEC wf.wf_repo_create_workflow_instance
        @version_id = @workflow_version_id,
        @context_json = @ctx;

    SELECT TOP 1 @instance_id = id FROM #created;

    EXEC wf.sp_start_workflow_instance @workflow_instance_id = @instance_id;

    IF @study_row_id IS NOT NULL
    BEGIN
        EXEC portal.sp_link_study_instance
            @study_row_id = @study_row_id,
            @workflow_instance_id = @instance_id,
            @domain_program_id = @domain_program_id,
            @pipeline_profile_id = @pipeline_profile_id,
            @site_id = @site_id,
            @storage_profile_id = @storage_profile_id,
            @assay_procedure_id = @assay_procedure_id;
    END

    EXEC wf.wf_repo_get_workflow_instance @instance_id = @instance_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_workflow_instance_header
    @workflow_instance_id bigint
AS
BEGIN
    SET NOCOUNT ON;

    IF @workflow_instance_id IS NULL OR @workflow_instance_id <= 0
        THROW 50001, N'workflow_instance_id is required.', 1;

    SELECT
        i.id AS workflow_instance_id,
        i.status,
        i.workflow_version_id,
        d.id AS workflow_def_id,
        d.name AS workflow_name,
        wf.fn_instance_kind(d.name) AS instance_kind,
        v.version_major,
        v.version_minor,
        i.started_at_utc,
        i.completed_at_utc,
        l.study_row_id,
        st.name AS study_name,
        l.pipeline_profile_id,
        pp.name AS pipeline_profile,
        l.assay_procedure_id,
        ap.name AS assay_procedure,
        JSON_VALUE(CAST(i.context_json AS nvarchar(max)), '$.pipelineProfile') AS context_pipeline_profile,
        JSON_VALUE(CAST(i.context_json AS nvarchar(max)), '$.pipelineProcedure') AS context_pipeline_procedure,
        JSON_VALUE(CAST(i.context_json AS nvarchar(max)), '$.projectPath') AS project_path,
        JSON_VALUE(CAST(i.context_json AS nvarchar(max)), '$.primaryAnalyte') AS primary_analyte,
        (
            SELECT COUNT(*)
            FROM OPENJSON(CAST(i.context_json AS nvarchar(max)), '$.samples')
        ) AS sample_count,
        ISNULL(agg.failed_count, 0) AS failed_count,
        ISNULL(agg.running_count, 0) AS running_count,
        ISNULL(agg.queued_count, 0) AS queued_count,
        ISNULL(agg.succeeded_count, 0) AS succeeded_count,
        ISNULL(agg.task_count, 0) AS task_count
    FROM wf.workflow_instance i
    INNER JOIN wf.workflow_version v ON v.id = i.workflow_version_id
    INNER JOIN wf.workflow_def d ON d.id = v.workflow_def_id
    LEFT JOIN cfg.study_instance_link l ON l.workflow_instance_id = i.id
    LEFT JOIN cfg.study st ON st.id = l.study_row_id
    LEFT JOIN cfg.pipeline_profile pp ON pp.id = l.pipeline_profile_id
    LEFT JOIN cfg.assay_procedure ap ON ap.id = l.assay_procedure_id
    LEFT JOIN (
        SELECT
            ne.workflow_instance_id,
            SUM(CASE WHEN ne.status = N'FAILED' THEN 1 ELSE 0 END) AS failed_count,
            SUM(CASE WHEN ne.status = N'RUNNING' THEN 1 ELSE 0 END) AS running_count,
            SUM(CASE WHEN ne.status IN (N'READY', N'PENDING') THEN 1 ELSE 0 END) AS queued_count,
            SUM(CASE WHEN ne.status = N'SUCCEEDED' THEN 1 ELSE 0 END) AS succeeded_count,
            COUNT(*) AS task_count
        FROM wf.node_execution ne
        WHERE ne.workflow_instance_id = @workflow_instance_id
        GROUP BY ne.workflow_instance_id
    ) agg ON agg.workflow_instance_id = i.id
    WHERE i.id = @workflow_instance_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_instance_config
    @workflow_instance_id bigint
AS
BEGIN
    SET NOCOUNT ON;

    IF @workflow_instance_id IS NULL OR @workflow_instance_id <= 0
        THROW 50001, N'workflow_instance_id is required.', 1;

    DECLARE @ctx nvarchar(max);
    DECLARE @scope_key nvarchar(64);
    DECLARE @scope_cfg nvarchar(max);
    DECLARE @resolved nvarchar(max);

    SELECT
        @ctx = CAST(i.context_json AS nvarchar(max)),
        @scope_key = es.set_key,
        @scope_cfg = CAST(es.config_json AS nvarchar(max))
    FROM wf.workflow_instance i
    LEFT JOIN wf.execution_scope es ON es.id = i.execution_scope_id
    WHERE i.id = @workflow_instance_id;

    IF @ctx IS NULL AND NOT EXISTS (SELECT 1 FROM wf.workflow_instance WHERE id = @workflow_instance_id)
        THROW 50010, N'workflow_instance not found.', 1;

    SELECT @resolved = CONCAT(
        N'{',
        STRING_AGG(
            CONCAT(
                N'"',
                STRING_ESCAPE(sv.var_name, 'json'),
                N'":',
                CAST(sv.value_json AS nvarchar(max))
            ),
            N','
        ),
        N'}'
    )
    FROM wf.scope_variable sv
    WHERE sv.workflow_instance_id = @workflow_instance_id
      AND sv.var_name LIKE N'resolvedConfig__%';

    SELECT
        @workflow_instance_id AS workflow_instance_id,
        @scope_key AS execution_scope_key,
        CAST(portal.fn_redact_json_credentials(@ctx) AS nvarchar(max)) AS context_json_redacted,
        CAST(portal.fn_redact_json_credentials(@scope_cfg) AS nvarchar(max)) AS execution_scope_config_redacted,
        CAST(COALESCE(@resolved, N'{}') AS nvarchar(max)) AS resolved_config_json;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_instance_sample_progress
    @workflow_instance_id bigint
AS
BEGIN
    SET NOCOUNT ON;

    IF @workflow_instance_id IS NULL OR @workflow_instance_id <= 0
        THROW 50001, N'workflow_instance_id is required.', 1;

    SELECT
        ne.id AS node_execution_id,
        COALESCE(
            JSON_VALUE(CAST(ne.input_json AS nvarchar(max)), '$.sampleId'),
            JSON_VALUE(CAST(ne.input_json AS nvarchar(max)), '$.sample_id')
        ) AS sample_id,
        COALESCE(st.stage_key, N'other') AS stage_key,
        COALESCE(st.stage_seq, 999) AS stage_seq,
        wa.action_name,
        wn.node_key,
        ne.status,
        ne.result_code,
        ne.engine_error_code,
        ne.engine_error_message,
        ne.attempt_no,
        ne.stop_requested,
        ne.started_at_utc,
        ne.ended_at_utc AS completed_at_utc
    FROM wf.node_execution ne
    INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
    LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
    OUTER APPLY wf.fn_pipeline_stage_for_action(wa.action_name) st
    WHERE ne.workflow_instance_id = @workflow_instance_id
      AND COALESCE(
            JSON_VALUE(CAST(ne.input_json AS nvarchar(max)), '$.sampleId'),
            JSON_VALUE(CAST(ne.input_json AS nvarchar(max)), '$.sample_id')
          ) IS NOT NULL
    ORDER BY sample_id, COALESCE(st.stage_seq, 999), ne.id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_fail_node
    @node_execution_id bigint,
    @error_message nvarchar(1024) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @node_execution_id IS NULL OR @node_execution_id <= 0
        THROW 50001, N'node_execution_id is required.', 1;

    DECLARE @status varchar(32);
    DECLARE @instance_id bigint;

    BEGIN TRAN;

    SELECT
        @status = ne.status,
        @instance_id = ne.workflow_instance_id
    FROM wf.node_execution ne WITH (UPDLOCK, ROWLOCK)
    WHERE ne.id = @node_execution_id;

    IF @instance_id IS NULL
        THROW 50010, N'node_execution not found.', 1;
    IF @status NOT IN (N'READY', N'PENDING')
        THROW 50021, N'Only READY or PENDING tasks can be operator-failed. Use Stop for in-flight.', 1;

    DELETE FROM wf.task_lease WHERE node_execution_id = @node_execution_id;

    UPDATE wf.node_execution
    SET status = N'FAILED',
        result_code = 4098,
        engine_error_code = 4098,
        engine_error_message = COALESCE(NULLIF(LTRIM(RTRIM(@error_message)), N''), N'OPERATOR_FAILED'),
        ended_at_utc = SYSUTCDATETIME(),
        stop_requested = 0
    WHERE id = @node_execution_id;

    COMMIT;

    SELECT
        ne.id AS node_execution_id,
        ne.status,
        ne.engine_error_code,
        i.status AS instance_status
    FROM wf.node_execution ne
    INNER JOIN wf.workflow_instance i ON i.id = ne.workflow_instance_id
    WHERE ne.id = @node_execution_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_stop_node
    @node_execution_id bigint,
    @error_message nvarchar(1024) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @node_execution_id IS NULL OR @node_execution_id <= 0
        THROW 50001, N'node_execution_id is required.', 1;

    DECLARE @status varchar(32);
    DECLARE @can_stop bit;

    SELECT
        @status = ne.status,
        @can_stop = CAST(ISNULL(wa.can_stop, 1) AS bit)
    FROM wf.node_execution ne
    INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
    LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
    WHERE ne.id = @node_execution_id;

    IF @status IS NULL
        THROW 50010, N'node_execution not found.', 1;
    IF @status <> N'RUNNING'
        THROW 50021, N'Only RUNNING tasks can be stopped.', 1;
    IF ISNULL(@can_stop, 1) = 0
        THROW 50022, N'This action cannot be stopped (catalog can_stop=false).', 1;

    UPDATE wf.node_execution
    SET stop_requested = 1,
        engine_error_code = COALESCE(engine_error_code, 4099),
        engine_error_message = COALESCE(
            NULLIF(LTRIM(RTRIM(@error_message)), N''),
            N'STOP_REQUESTED'
        )
    WHERE id = @node_execution_id;

    SELECT
        ne.id AS node_execution_id,
        ne.status,
        ne.stop_requested,
        N'STOP' AS command
    FROM wf.node_execution ne
    WHERE ne.id = @node_execution_id;
END
GO

-- Drain READY/PENDING and mark the instance CANCELLED. In-flight success is
-- recorded, but wf_engine_activate / sequence/foreach continue refuse new work
-- unless workflow_instance.status is still RUNNING.
CREATE OR ALTER PROCEDURE portal.sp_cancel_instance
    @workflow_instance_id bigint,
    @error_message nvarchar(1024) = NULL,
    @stop_inflight bit = 0
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @workflow_instance_id IS NULL OR @workflow_instance_id <= 0
        THROW 50001, N'workflow_instance_id is required.', 1;

    DECLARE @status varchar(32);
    DECLARE @reason nvarchar(1024) = COALESCE(
        NULLIF(LTRIM(RTRIM(@error_message)), N''),
        N'OPERATOR_CANCELLED'
    );

    BEGIN TRAN;

    SELECT @status = status
    FROM wf.workflow_instance WITH (UPDLOCK, ROWLOCK)
    WHERE id = @workflow_instance_id;

    IF @status IS NULL
        THROW 50010, N'workflow_instance not found.', 1;
    IF @status = N'COMPLETED'
        THROW 50021, N'Cannot cancel a COMPLETED instance.', 1;
    IF @status = N'CANCELLED'
    BEGIN
        COMMIT;
        SELECT @workflow_instance_id AS workflow_instance_id, @status AS status, 0 AS queued_cancelled;
        RETURN;
    END

    DELETE tl
    FROM wf.task_lease tl
    INNER JOIN wf.node_execution ne ON ne.id = tl.node_execution_id
    WHERE ne.workflow_instance_id = @workflow_instance_id
      AND ne.status IN (N'READY', N'PENDING');

    UPDATE wf.node_execution
    SET status = N'CANCELLED',
        result_code = 4097,
        engine_error_code = 4097,
        engine_error_message = @reason,
        ended_at_utc = SYSUTCDATETIME(),
        stop_requested = 0
    WHERE workflow_instance_id = @workflow_instance_id
      AND status IN (N'READY', N'PENDING');

    DECLARE @queued int = @@ROWCOUNT;

    IF ISNULL(@stop_inflight, 0) = 1
    BEGIN
        UPDATE ne
        SET stop_requested = 1,
            engine_error_code = COALESCE(ne.engine_error_code, 4099),
            engine_error_message = COALESCE(ne.engine_error_message, @reason)
        FROM wf.node_execution ne
        INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
        LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
        WHERE ne.workflow_instance_id = @workflow_instance_id
          AND ne.status = N'RUNNING'
          AND ISNULL(wa.can_stop, 1) = 1;
    END

    UPDATE wf.workflow_instance
    SET status = N'CANCELLED',
        completed_at_utc = SYSUTCDATETIME()
    WHERE id = @workflow_instance_id;

    EXEC wf.wf_repo_upsert_instance_extension
        @instance_id = @workflow_instance_id,
        @extension_key = N'portal.operator_cancel',
        @data_json = NULL;

    COMMIT;

    SELECT
        @workflow_instance_id AS workflow_instance_id,
        N'CANCELLED' AS status,
        @queued AS queued_cancelled;
END
GO

-- Same drain as cancel, instance FAILED (4098). Engine continue/activate still
-- require status = RUNNING, so in-flight success cannot enqueue later stages.
CREATE OR ALTER PROCEDURE portal.sp_fail_instance
    @workflow_instance_id bigint,
    @error_message nvarchar(1024) = NULL,
    @stop_inflight bit = 0
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @workflow_instance_id IS NULL OR @workflow_instance_id <= 0
        THROW 50001, N'workflow_instance_id is required.', 1;

    DECLARE @status varchar(32);
    DECLARE @reason nvarchar(1024) = COALESCE(
        NULLIF(LTRIM(RTRIM(@error_message)), N''),
        N'OPERATOR_FAILED'
    );

    BEGIN TRAN;

    SELECT @status = status
    FROM wf.workflow_instance WITH (UPDLOCK, ROWLOCK)
    WHERE id = @workflow_instance_id;

    IF @status IS NULL
        THROW 50010, N'workflow_instance not found.', 1;
    IF @status = N'COMPLETED'
        THROW 50021, N'Cannot fail a COMPLETED instance.', 1;
    IF @status = N'FAILED'
    BEGIN
        COMMIT;
        SELECT @workflow_instance_id AS workflow_instance_id, @status AS status, 0 AS queued_failed;
        RETURN;
    END

    DELETE tl
    FROM wf.task_lease tl
    INNER JOIN wf.node_execution ne ON ne.id = tl.node_execution_id
    WHERE ne.workflow_instance_id = @workflow_instance_id
      AND ne.status IN (N'READY', N'PENDING');

    UPDATE wf.node_execution
    SET status = N'FAILED',
        result_code = 4098,
        engine_error_code = 4098,
        engine_error_message = @reason,
        ended_at_utc = SYSUTCDATETIME(),
        stop_requested = 0
    WHERE workflow_instance_id = @workflow_instance_id
      AND status IN (N'READY', N'PENDING');

    DECLARE @queued int = @@ROWCOUNT;

    IF ISNULL(@stop_inflight, 0) = 1
    BEGIN
        UPDATE ne
        SET stop_requested = 1,
            engine_error_code = COALESCE(ne.engine_error_code, 4099),
            engine_error_message = COALESCE(ne.engine_error_message, @reason)
        FROM wf.node_execution ne
        INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
        LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
        WHERE ne.workflow_instance_id = @workflow_instance_id
          AND ne.status = N'RUNNING'
          AND ISNULL(wa.can_stop, 1) = 1;
    END

    UPDATE wf.workflow_instance
    SET status = N'FAILED',
        completed_at_utc = SYSUTCDATETIME()
    WHERE id = @workflow_instance_id;

    EXEC wf.wf_repo_upsert_instance_extension
        @instance_id = @workflow_instance_id,
        @extension_key = N'portal.operator_fail',
        @data_json = NULL;

    COMMIT;

    SELECT
        @workflow_instance_id AS workflow_instance_id,
        N'FAILED' AS status,
        @queued AS queued_failed;
END
GO

/* Heartbeat honors per-task stop_requested as command=STOP (not fleet desired_state). */
CREATE OR ALTER PROCEDURE wf.sp_worker_heartbeat
    @node_execution_id BIGINT,
    @worker_id BIGINT,
    @worker_token NVARCHAR(4000),
    @extend_seconds INT = 300
AS
BEGIN
    SET NOCOUNT ON;

    EXEC wf.wf_worker_authenticate @worker_id = @worker_id, @worker_token = @worker_token;

    DECLARE @now DATETIME2(7) = SYSUTCDATETIME();
    DECLARE @desired_state VARCHAR(32) = N'ACTIVE';
    DECLARE @command VARCHAR(32) = N'NONE';
    DECLARE @stop_requested BIT = 0;

    UPDATE tl
    SET lease_expires_at_utc = DATEADD(SECOND, @extend_seconds, @now),
        heartbeat_at_utc = @now
    FROM wf.task_lease AS tl
    WHERE tl.node_execution_id = @node_execution_id AND tl.worker_id = @worker_id;

    DECLARE @rows INT = @@ROWCOUNT;

    SELECT @desired_state = COALESCE(w.desired_state, N'ACTIVE')
    FROM wf.worker AS w
    WHERE w.id = @worker_id;

    SELECT @stop_requested = ISNULL(ne.stop_requested, 0)
    FROM wf.node_execution AS ne
    WHERE ne.id = @node_execution_id;

    SET @command = CASE
        WHEN @stop_requested = 1 THEN N'STOP'
        WHEN @desired_state = N'DRAINING' THEN N'DRAIN'
        WHEN @desired_state = N'STOPPING' THEN N'STOP'
        ELSE N'NONE'
    END;

    SELECT @rows AS rows_updated, @desired_state AS desired_state, @command AS command;
END
GO
