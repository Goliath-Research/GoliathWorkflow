/*
  Contract process-pack entitlements + portal.sp_* admin façade (Azure SQL).

  Commercial grain is regulatory.primary_modality:
    methylation | rnaseq | proteomics
  Contract.ContractWorkflowEntitlements remain derived graph quotas.

  Also:
    - optional @scope_id on operator catalogs (NULL = unfiltered, CI/dev)
    - portal.sp_create_and_start_instance pack + contract checks

  Deploy after cfg_analyte_catalog.sql / cfg_assay_procedure_links.sql
  and portal_workflow_api.sql.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'Contract.ContractProcessPackEntitlements', N'U') IS NULL
BEGIN
    CREATE TABLE Contract.ContractProcessPackEntitlements (
        ContractID int NOT NULL,
        Modality varchar(32) NOT NULL,
        Enabled bit NOT NULL CONSTRAINT DF_CPPE_Enabled DEFAULT (1),
        EffectiveFromUtc datetime2(3) NOT NULL CONSTRAINT DF_CPPE_From DEFAULT (sysutcdatetime()),
        EffectiveToUtc datetime2(3) NULL,
        CreatedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_CPPE_Created DEFAULT (sysutcdatetime()),
        CONSTRAINT PK_Contract_ProcessPackEntitlements PRIMARY KEY CLUSTERED (ContractID, Modality),
        CONSTRAINT CK_CPPE_Modality CHECK (
            [Modality] IN (N'methylation', N'rnaseq', N'proteomics')
        ),
        CONSTRAINT CK_CPPE_Range CHECK (
            [EffectiveToUtc] IS NULL OR [EffectiveToUtc] >= [EffectiveFromUtc]
        )
    );
END
GO

IF OBJECT_ID(N'FK_CPPE_ContractID', N'F') IS NULL AND NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_CPPE_ContractID'
)
BEGIN
    ALTER TABLE Contract.ContractProcessPackEntitlements
    ADD CONSTRAINT FK_CPPE_ContractID
        FOREIGN KEY (ContractID) REFERENCES Contract.Contracts (ContractID);
END
GO

CREATE OR ALTER FUNCTION portal.fn_infer_process_pack(
    @name nvarchar(256),
    @document_json nvarchar(max)
)
RETURNS varchar(32)
AS
BEGIN
    DECLARE @mod varchar(32) = LOWER(LTRIM(RTRIM(JSON_VALUE(@document_json, '$.regulatory.primary_modality'))));
    IF @mod IN (N'methylation', N'rnaseq', N'proteomics') RETURN @mod;

    SET @mod = LOWER(LTRIM(RTRIM(JSON_VALUE(@document_json, '$.catalog.family'))));
    IF @mod IN (N'methylation', N'rnaseq', N'proteomics') RETURN @mod;

    DECLARE @n nvarchar(256) = LOWER(ISNULL(@name, N''));
    IF @n LIKE N'%rnaseq%' OR @n LIKE N'rna[_-]%' OR @n LIKE N'%rna.seq%' RETURN N'rnaseq';
    IF @n LIKE N'%proteom%' RETURN N'proteomics';
    RETURN N'methylation';
END
GO

CREATE OR ALTER FUNCTION portal.fn_infer_process_pack_from_context(@context_json nvarchar(max))
RETURNS varchar(32)
AS
BEGIN
    DECLARE @mod varchar(32) = LOWER(LTRIM(RTRIM(JSON_VALUE(@context_json, '$.regulatory.primary_modality'))));
    IF @mod IN (N'methylation', N'rnaseq', N'proteomics') RETURN @mod;

    DECLARE @profile nvarchar(256) = JSON_VALUE(@context_json, '$.pipelineProfile');
    DECLARE @procedure nvarchar(256) = JSON_VALUE(@context_json, '$.pipelineProcedure');
    DECLARE @from_name varchar(32) = portal.fn_infer_process_pack(
        COALESCE(@profile, @procedure),
        NULL
    );
    RETURN @from_name;
END
GO

CREATE OR ALTER FUNCTION portal.fn_contract_entitled_modalities(@scope_id int)
RETURNS TABLE
AS
RETURN
(
    SELECT DISTINCT e.Modality AS modality
    FROM Contract.ContractProcessPackEntitlements e
    INNER JOIN Contract.ContractScopes cs ON cs.ContractID = e.ContractID
    INNER JOIN Contract.Contracts c ON c.ContractID = cs.ContractID
    WHERE @scope_id IS NOT NULL
      AND cs.ScopeID = @scope_id
      AND cs.Status = N'ACTIVE'
      AND c.Status = N'ACTIVE'
      AND e.Enabled = 1
      AND cs.EffectiveFromUtc <= SYSUTCDATETIME()
      AND (cs.EffectiveToUtc IS NULL OR cs.EffectiveToUtc >= SYSUTCDATETIME())
      AND c.StartDateUtc <= SYSUTCDATETIME()
      AND (c.EndDateUtc IS NULL OR c.EndDateUtc >= SYSUTCDATETIME())
      AND e.EffectiveFromUtc <= SYSUTCDATETIME()
      AND (e.EffectiveToUtc IS NULL OR e.EffectiveToUtc >= SYSUTCDATETIME())
);
GO

CREATE OR ALTER PROCEDURE portal.sp_contract_entitled_modalities
    @scope_id int
AS
BEGIN
    SET NOCOUNT ON;
    SELECT modality FROM portal.fn_contract_entitled_modalities(@scope_id) ORDER BY modality;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_contracts
    @include_inactive bit = 0
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        c.ContractID AS contract_id,
        c.CustomerID AS customer_id,
        cu.Name AS customer_name,
        c.Name,
        c.Status,
        c.StartDateUtc,
        c.EndDateUtc,
        c.PlanCode,
        c.BillingCycle,
        c.AutoRenew,
        c.TermsVersion,
        c.CreatedAtUtc,
        c.UpdatedAtUtc
    FROM Contract.Contracts c
    INNER JOIN portal.Customers cu ON cu.ID = c.CustomerID
    WHERE @include_inactive = 1
       OR c.Status IN (N'DRAFT', N'ACTIVE')
    ORDER BY c.Name;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_contract
    @contract_id int
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        c.ContractID AS contract_id,
        c.CustomerID AS customer_id,
        cu.Name AS customer_name,
        c.Name,
        c.Status,
        c.StartDateUtc,
        c.EndDateUtc,
        c.PlanCode,
        c.BillingCycle,
        c.AutoRenew,
        c.TermsVersion,
        c.CreatedAtUtc,
        c.UpdatedAtUtc
    FROM Contract.Contracts c
    INNER JOIN portal.Customers cu ON cu.ID = c.CustomerID
    WHERE c.ContractID = @contract_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_upsert_contract
    @customer_id int,
    @name varchar(200),
    @status varchar(24) = N'DRAFT',
    @start_date_utc datetime2(3) = NULL,
    @end_date_utc datetime2(3) = NULL,
    @plan_code varchar(64) = NULL,
    @billing_cycle varchar(16) = NULL,
    @auto_renew bit = 0,
    @terms_version varchar(32) = NULL,
    @contract_id int = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    IF @customer_id IS NULL OR @customer_id <= 0
        THROW 50001, N'customer_id is required.', 1;
    IF @name IS NULL OR LTRIM(RTRIM(@name)) = N''
        THROW 50001, N'name is required.', 1;

    SET @status = UPPER(LTRIM(RTRIM(ISNULL(@status, N'DRAFT'))));
    IF @status NOT IN (N'DRAFT', N'ACTIVE', N'SUSPENDED', N'EXPIRED', N'TERMINATED')
        THROW 50001, N'Invalid contract status.', 1;

    IF @start_date_utc IS NULL SET @start_date_utc = SYSUTCDATETIME();

    SELECT @contract_id = c.ContractID
    FROM Contract.Contracts c
    WHERE c.CustomerID = @customer_id;

    IF @contract_id IS NULL
    BEGIN
        INSERT INTO Contract.Contracts (
            CustomerID, Name, Status, StartDateUtc, EndDateUtc,
            PlanCode, BillingCycle, AutoRenew, TermsVersion
        )
        VALUES (
            @customer_id, @name, @status, @start_date_utc, @end_date_utc,
            @plan_code, @billing_cycle, ISNULL(@auto_renew, 0), @terms_version
        );
        SET @contract_id = SCOPE_IDENTITY();
    END
    ELSE
        UPDATE Contract.Contracts
        SET Name = @name,
            Status = @status,
            StartDateUtc = @start_date_utc,
            EndDateUtc = @end_date_utc,
            PlanCode = @plan_code,
            BillingCycle = @billing_cycle,
            AutoRenew = ISNULL(@auto_renew, AutoRenew),
            TermsVersion = @terms_version,
            UpdatedAtUtc = SYSUTCDATETIME()
        WHERE ContractID = @contract_id;

    SELECT @contract_id AS contract_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_contract_process_packs
    @contract_id int
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        e.ContractID AS contract_id,
        e.Modality AS modality,
        e.Enabled,
        e.EffectiveFromUtc,
        e.EffectiveToUtc
    FROM Contract.ContractProcessPackEntitlements e
    WHERE e.ContractID = @contract_id
    ORDER BY e.Modality;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_set_contract_process_packs
    @contract_id int,
    @modalities nvarchar(max)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF NOT EXISTS (SELECT 1 FROM Contract.Contracts WHERE ContractID = @contract_id)
        THROW 50010, N'contract_id not found.', 1;

    BEGIN TRAN;

    DELETE FROM Contract.ContractProcessPackEntitlements WHERE ContractID = @contract_id;

    INSERT INTO Contract.ContractProcessPackEntitlements (ContractID, Modality, Enabled)
    SELECT DISTINCT @contract_id, LOWER(LTRIM(RTRIM(CAST(j.[value] AS varchar(32))))), 1
    FROM OPENJSON(@modalities) j
    WHERE LOWER(LTRIM(RTRIM(CAST(j.[value] AS varchar(32))))) IN (N'methylation', N'rnaseq', N'proteomics');

    COMMIT;
    SELECT @@ROWCOUNT AS packs;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_contract_scopes
    @contract_id int
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        cs.ContractID AS contract_id,
        cs.ScopeID AS scope_id,
        s.Name AS scope_name,
        s.ScopeType,
        cs.Status,
        cs.ActivatedAtUtc,
        cs.EffectiveFromUtc,
        cs.EffectiveToUtc
    FROM Contract.ContractScopes cs
    INNER JOIN RBAC.Scopes s ON s.ScopeID = cs.ScopeID
    WHERE cs.ContractID = @contract_id
    ORDER BY s.Name;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_contract_limits
    @contract_id int
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        l.ContractLimitID,
        l.ContractID AS contract_id,
        l.ScopeID AS scope_id,
        l.MaxActiveUsers,
        l.MaxStorageGB,
        l.MaxRunsPerMonth,
        l.CreatedAtUtc
    FROM Contract.ContractLimits l
    WHERE l.ContractID = @contract_id
    ORDER BY l.ScopeID;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_contract_role_policies
    @contract_id int
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        p.ContractID AS contract_id,
        p.RoleID AS role_id,
        r.Name AS role_name,
        p.GrantTypeAllowed,
        p.MaxUsersForRole,
        p.RequiresApproval,
        p.CreatedAtUtc
    FROM Contract.ContractRolePolicies p
    INNER JOIN RBAC.Roles r ON r.ID = p.RoleID
    WHERE p.ContractID = @contract_id
    ORDER BY r.Name;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_set_contract_scopes
    @contract_id int,
    @scopes_json nvarchar(max)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF NOT EXISTS (SELECT 1 FROM Contract.Contracts WHERE ContractID = @contract_id)
        THROW 50010, N'contract_id not found.', 1;
    IF @scopes_json IS NULL OR ISJSON(@scopes_json) <> 1
        THROW 50021, N'scopes_json must be a JSON array.', 1;

    BEGIN TRAN;
    DELETE FROM Contract.ContractScopes WHERE ContractID = @contract_id;

    INSERT INTO Contract.ContractScopes (ContractID, ScopeID, Status, EffectiveFromUtc, EffectiveToUtc)
    SELECT
        @contract_id,
        TRY_CAST(JSON_VALUE(j.[value], '$.scope_id') AS int),
        COALESCE(NULLIF(JSON_VALUE(j.[value], '$.status'), N''), N'ACTIVE'),
        COALESCE(TRY_CAST(JSON_VALUE(j.[value], '$.effective_from_utc') AS datetime2(3)), SYSUTCDATETIME()),
        TRY_CAST(JSON_VALUE(j.[value], '$.effective_to_utc') AS datetime2(3))
    FROM OPENJSON(@scopes_json) j
    WHERE TRY_CAST(JSON_VALUE(j.[value], '$.scope_id') AS int) IS NOT NULL;

    COMMIT;
    EXEC portal.sp_list_contract_scopes @contract_id = @contract_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_set_contract_limits
    @contract_id int,
    @limits_json nvarchar(max)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF NOT EXISTS (SELECT 1 FROM Contract.Contracts WHERE ContractID = @contract_id)
        THROW 50010, N'contract_id not found.', 1;
    IF @limits_json IS NULL OR ISJSON(@limits_json) <> 1
        THROW 50021, N'limits_json must be a JSON array.', 1;

    BEGIN TRAN;
    DELETE FROM Contract.ContractLimits WHERE ContractID = @contract_id;

    INSERT INTO Contract.ContractLimits (ContractID, ScopeID, MaxActiveUsers, MaxStorageGB, MaxRunsPerMonth)
    SELECT
        @contract_id,
        TRY_CAST(JSON_VALUE(j.[value], '$.scope_id') AS int),
        TRY_CAST(JSON_VALUE(j.[value], '$.max_active_users') AS int),
        TRY_CAST(JSON_VALUE(j.[value], '$.max_storage_gb') AS decimal(18, 2)),
        TRY_CAST(JSON_VALUE(j.[value], '$.max_runs_per_month') AS int)
    FROM OPENJSON(@limits_json) j;

    COMMIT;
    EXEC portal.sp_list_contract_limits @contract_id = @contract_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_set_contract_role_policies
    @contract_id int,
    @policies_json nvarchar(max)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF NOT EXISTS (SELECT 1 FROM Contract.Contracts WHERE ContractID = @contract_id)
        THROW 50010, N'contract_id not found.', 1;
    IF @policies_json IS NULL OR ISJSON(@policies_json) <> 1
        THROW 50021, N'policies_json must be a JSON array.', 1;

    BEGIN TRAN;
    DELETE FROM Contract.ContractRolePolicies WHERE ContractID = @contract_id;

    INSERT INTO Contract.ContractRolePolicies (
        ContractID, RoleID, GrantTypeAllowed, MaxUsersForRole, RequiresApproval
    )
    SELECT
        @contract_id,
        TRY_CAST(JSON_VALUE(j.[value], '$.role_id') AS int),
        COALESCE(NULLIF(JSON_VALUE(j.[value], '$.grant_type_allowed'), N''), N'SCOPED'),
        TRY_CAST(JSON_VALUE(j.[value], '$.max_users_for_role') AS int),
        CASE WHEN JSON_VALUE(j.[value], '$.requires_approval') IN (N'true', N'1') THEN 1 ELSE 0 END
    FROM OPENJSON(@policies_json) j
    WHERE TRY_CAST(JSON_VALUE(j.[value], '$.role_id') AS int) IS NOT NULL;

    COMMIT;
    EXEC portal.sp_list_contract_role_policies @contract_id = @contract_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_contract_usage
    @contract_id int
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        w.ContractID AS contract_id,
        w.ScopeID AS scope_id,
        w.WorkflowDefID AS workflow_def_id,
        wd.name AS workflow_name,
        w.PeriodType,
        w.PeriodStartUtc,
        w.RunsExecuted,
        w.UpdatedAtUtc
    FROM Contract.WorkflowUsageCounters w
    LEFT JOIN wf.workflow_def wd ON wd.id = w.WorkflowDefID
    WHERE w.ContractID = @contract_id
    ORDER BY w.PeriodStartUtc DESC;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_pipeline_profile_catalog
    @include_advanced bit = 0,
    @scope_id int = NULL
AS
BEGIN
    SET NOCOUNT ON;
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
      AND (
            @scope_id IS NULL
         OR portal.fn_infer_process_pack(p.name, CAST(p.document_json AS nvarchar(max))) IN (
                SELECT modality FROM portal.fn_contract_entitled_modalities(@scope_id)
            )
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

CREATE OR ALTER PROCEDURE portal.sp_list_assay_procedure_catalog
    @analyte nvarchar(64) = NULL,
    @include_advanced bit = 0,
    @scope_id int = NULL
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
      AND (
            @scope_id IS NULL
         OR portal.fn_infer_process_pack(p.name, CAST(p.document_json AS nvarchar(max))) IN (
                SELECT modality FROM portal.fn_contract_entitled_modalities(@scope_id)
            )
          )
    ORDER BY p.name, p.version;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_analyte_catalog
    @include_advanced bit = 0,
    @scope_id int = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        a.id,
        a.name,
        a.version,
        a.status,
        JSON_VALUE(a.document_json, '$.catalog.title') AS title,
        JSON_VALUE(a.document_json, '$.catalog.summary') AS summary,
        JSON_VALUE(a.document_json, '$.catalog.visibility') AS visibility,
        JSON_VALUE(a.document_json, '$.catalog.lifecycle') AS lifecycle,
        JSON_VALUE(a.document_json, '$.catalog.family') AS family,
        JSON_VALUE(a.document_json, '$.catalog.replacedBy') AS replaced_by,
        CAST(JSON_QUERY(a.document_json, '$.aliases') AS json) AS aliases
    FROM cfg.analyte a
    WHERE a.status = 'published'
      AND JSON_VALUE(a.document_json, '$.catalog.lifecycle') = N'active'
      AND (
            JSON_VALUE(a.document_json, '$.catalog.visibility') = N'operator'
         OR (@include_advanced = 1
             AND JSON_VALUE(a.document_json, '$.catalog.visibility') = N'advanced')
          )
      AND (
            @scope_id IS NULL
         OR portal.fn_infer_process_pack(a.name, CAST(a.document_json AS nvarchar(max))) IN (
                SELECT modality FROM portal.fn_contract_entitled_modalities(@scope_id)
            )
          )
    ORDER BY a.name, a.version;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_workflow_definitions
    @source_filter varchar(32) = NULL,
    @scope_id int = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT wd.id AS workflow_def_id,
           wd.name,
           COALESCE(wd.source, 'system') AS source,
           wv.id AS workflow_version_id,
           wv.version_major,
           wv.version_minor
    FROM wf.workflow_def wd
    OUTER APPLY (
        SELECT TOP 1 id, version_major, version_minor
        FROM wf.workflow_version
        WHERE workflow_def_id = wd.id AND is_active = 1
        ORDER BY version_major DESC, version_minor DESC
    ) wv
    WHERE (@source_filter IS NULL OR COALESCE(wd.source, 'system') = @source_filter)
      AND (
            @scope_id IS NULL
         OR portal.fn_infer_process_pack(wd.name, NULL) IN (
                SELECT modality FROM portal.fn_contract_entitled_modalities(@scope_id)
            )
          )
    ORDER BY wd.name;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_create_and_start_instance
    @workflow_version_id bigint,
    @context_json nvarchar(max) = NULL,
    @scope_id int = NULL
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

    EXEC wf.wf_repo_get_workflow_instance @instance_id = @instance_id;
END
GO
