-- Auto-extracted by scripts/extract_legacy_schema.py from MethylPipeline.sql
-- Idempotent incremental deploy (IF OBJECT_ID / CREATE OR ALTER).
-- Do not edit by hand unless also updating the twin under sql_pg/.

CREATE OR ALTER PROCEDURE Contract.spContractValidateScopeAccess
    @ScopeID INT,
    @UtcNow DATETIME2(3) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    IF @UtcNow IS NULL SET @UtcNow = SYSUTCDATETIME();

    IF @ScopeID IS NULL OR @ScopeID <= 0
    BEGIN
        SELECT CAST(0 AS BIT) AS IsAllowed, NULL AS ContractID, N'INVALID_SCOPE' AS ReasonCode;
        RETURN 50001;
    END

    ;WITH ScopeContract AS
    (
        SELECT TOP (1)
            c.ContractID
        FROM Contract.ContractScopes cs
        INNER JOIN Contract.Contracts c ON c.ContractID = cs.ContractID
        WHERE cs.ScopeID = @ScopeID
          AND cs.Status = 'ACTIVE'
          AND cs.EffectiveFromUtc <= @UtcNow
          AND (cs.EffectiveToUtc IS NULL OR cs.EffectiveToUtc >= @UtcNow)
          AND c.Status = 'ACTIVE'
          AND c.StartDateUtc <= @UtcNow
          AND (c.EndDateUtc IS NULL OR c.EndDateUtc >= @UtcNow)
        ORDER BY cs.EffectiveFromUtc DESC, c.ContractID DESC
    )
    SELECT
        CAST(CASE WHEN EXISTS (SELECT 1 FROM ScopeContract) THEN 1 ELSE 0 END AS BIT) AS IsAllowed,
        (SELECT TOP (1) ContractID FROM ScopeContract) AS ContractID,
        CASE WHEN EXISTS (SELECT 1 FROM ScopeContract) THEN N'OK' ELSE N'NO_ACTIVE_CONTRACT_FOR_SCOPE' END AS ReasonCode;

    RETURN 0;
END
GO

CREATE OR ALTER PROCEDURE Contract.spContractValidateWorkflowExecution
    @ScopeID INT,
    @WorkflowDefID BIGINT,
    @UtcNow DATETIME2(3) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    IF @UtcNow IS NULL SET @UtcNow = SYSUTCDATETIME();

    DECLARE @Access TABLE (IsAllowed BIT, ContractID INT, ReasonCode NVARCHAR(64));
    INSERT INTO @Access
    EXEC Contract.spContractValidateScopeAccess @ScopeID = @ScopeID, @UtcNow = @UtcNow;

    DECLARE @ScopeAllowed BIT = (SELECT TOP (1) IsAllowed FROM @Access);
    DECLARE @ContractID INT = (SELECT TOP (1) ContractID FROM @Access);

    IF ISNULL(@ScopeAllowed, 0) = 0
    BEGIN
        SELECT CAST(0 AS BIT) AS IsAllowed, @ContractID AS ContractID, N'NO_ACTIVE_CONTRACT_FOR_SCOPE' AS ReasonCode;
        RETURN 50020;
    END

    DECLARE @Enabled BIT = 0;
    DECLARE @MaxRuns INT = NULL;
    DECLARE @PeriodType VARCHAR(8) = NULL;
    DECLARE @RunsExecuted INT = 0;
    DECLARE @PeriodStartUtc DATETIME2(3) = NULL;

    SELECT
        @Enabled = e.Enabled,
        @MaxRuns = e.MaxRunsPerPeriod,
        @PeriodType = e.PeriodType
    FROM Contract.ContractWorkflowEntitlements e
    WHERE e.ContractID = @ContractID
      AND e.WorkflowDefID = @WorkflowDefID;

    IF @Enabled IS NULL OR @Enabled = 0
    BEGIN
        SELECT CAST(0 AS BIT) AS IsAllowed, @ContractID AS ContractID, N'WORKFLOW_NOT_ENTITLED' AS ReasonCode;
        RETURN 50021;
    END

    IF @MaxRuns IS NOT NULL AND @PeriodType IS NOT NULL
    BEGIN
        IF @PeriodType = 'DAY'
            SET @PeriodStartUtc = DATEFROMPARTS(YEAR(@UtcNow), MONTH(@UtcNow), DAY(@UtcNow));
        ELSE IF @PeriodType = 'WEEK'
            SET @PeriodStartUtc = DATEADD(DAY, 1 - DATEPART(WEEKDAY, CAST(@UtcNow AS DATE)), CAST(CAST(@UtcNow AS DATE) AS DATETIME2(3)));
        ELSE IF @PeriodType = 'MONTH'
            SET @PeriodStartUtc = DATEFROMPARTS(YEAR(@UtcNow), MONTH(@UtcNow), 1);

        SELECT @RunsExecuted = ISNULL(w.RunsExecuted, 0)
        FROM Contract.WorkflowUsageCounters w
        WHERE w.ContractID = @ContractID
          AND w.ScopeID = @ScopeID
          AND w.WorkflowDefID = @WorkflowDefID
          AND w.PeriodType = @PeriodType
          AND w.PeriodStartUtc = @PeriodStartUtc;

        IF @RunsExecuted >= @MaxRuns
        BEGIN
            SELECT
                CAST(0 AS BIT) AS IsAllowed,
                @ContractID AS ContractID,
                N'WORKFLOW_QUOTA_EXCEEDED' AS ReasonCode,
                @RunsExecuted AS RunsExecuted,
                @MaxRuns AS MaxRunsPerPeriod,
                @PeriodType AS PeriodType;
            RETURN 50022;
        END
    END

    SELECT
        CAST(1 AS BIT) AS IsAllowed,
        @ContractID AS ContractID,
        N'OK' AS ReasonCode,
        ISNULL(@RunsExecuted, 0) AS RunsExecuted,
        @MaxRuns AS MaxRunsPerPeriod,
        @PeriodType AS PeriodType;

    RETURN 0;
END
GO

CREATE OR ALTER PROCEDURE Contract.spContractConsumeWorkflowQuota
    @ScopeID INT,
    @WorkflowDefID BIGINT,
    @ConsumeRuns INT = 1,
    @UtcNow DATETIME2(3) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @UtcNow IS NULL SET @UtcNow = SYSUTCDATETIME();

    IF @ScopeID IS NULL OR @ScopeID <= 0
       OR @WorkflowDefID IS NULL OR @WorkflowDefID <= 0
       OR @ConsumeRuns IS NULL OR @ConsumeRuns <= 0
    BEGIN
        RAISERROR('ValidationError: ScopeID, WorkflowDefID and ConsumeRuns (>0) are required.', 16, 1);
        RETURN;
    END

    DECLARE @ContractID INT = NULL;
    DECLARE @Enabled BIT = 0;
    DECLARE @MaxRuns INT = NULL;
    DECLARE @PeriodType VARCHAR(8) = NULL;
    DECLARE @PeriodStartUtc DATETIME2(3) = NULL;
    DECLARE @RunsExecuted INT = 0;
    DECLARE @NewRunsExecuted INT = 0;

    BEGIN TRY
        BEGIN TRANSACTION;

        SELECT TOP (1)
            @ContractID = c.ContractID
        FROM Contract.ContractScopes cs
        INNER JOIN Contract.Contracts c
            ON c.ContractID = cs.ContractID
        WHERE cs.ScopeID = @ScopeID
          AND cs.Status = 'ACTIVE'
          AND cs.EffectiveFromUtc <= @UtcNow
          AND (cs.EffectiveToUtc IS NULL OR cs.EffectiveToUtc >= @UtcNow)
          AND c.Status = 'ACTIVE'
          AND c.StartDateUtc <= @UtcNow
          AND (c.EndDateUtc IS NULL OR c.EndDateUtc >= @UtcNow)
        ORDER BY cs.EffectiveFromUtc DESC, c.ContractID DESC;

        IF @ContractID IS NULL
        BEGIN
            RAISERROR('BusinessRule: Scope has no active contract.', 16, 1);
            RETURN;
        END

        SELECT
            @Enabled = e.Enabled,
            @MaxRuns = e.MaxRunsPerPeriod,
            @PeriodType = e.PeriodType
        FROM Contract.ContractWorkflowEntitlements e
        WHERE e.ContractID = @ContractID
          AND e.WorkflowDefID = @WorkflowDefID;

        IF @Enabled IS NULL OR @Enabled = 0
        BEGIN
            RAISERROR('BusinessRule: Workflow is not entitled for the active contract.', 16, 1);
            RETURN;
        END

        -- No periodic limit configured: allow execution without counter mutation.
        IF @MaxRuns IS NULL OR @PeriodType IS NULL
        BEGIN
            SELECT
                CAST(1 AS BIT) AS IsAllowed,
                @ContractID AS ContractID,
                N'OK_UNLIMITED' AS ReasonCode,
                CAST(NULL AS INT) AS RunsExecuted,
                CAST(NULL AS INT) AS MaxRunsPerPeriod,
                CAST(NULL AS VARCHAR(8)) AS PeriodType,
                CAST(NULL AS DATETIME2(3)) AS PeriodStartUtc;
            COMMIT TRANSACTION;
            RETURN 0;
        END

        IF @PeriodType = 'DAY'
            SET @PeriodStartUtc = DATEFROMPARTS(YEAR(@UtcNow), MONTH(@UtcNow), DAY(@UtcNow));
        ELSE IF @PeriodType = 'WEEK'
            SET @PeriodStartUtc = DATEADD(DAY, 1 - DATEPART(WEEKDAY, CAST(@UtcNow AS DATE)), CAST(CAST(@UtcNow AS DATE) AS DATETIME2(3)));
        ELSE IF @PeriodType = 'MONTH'
            SET @PeriodStartUtc = DATEFROMPARTS(YEAR(@UtcNow), MONTH(@UtcNow), 1);
        ELSE
        BEGIN
            RAISERROR('ValidationError: Unsupported PeriodType.', 16, 1);
            RETURN;
        END

        -- Lock counter row (or key-range) before evaluating and mutating to prevent race conditions.
        SELECT
            @RunsExecuted = w.RunsExecuted
        FROM Contract.WorkflowUsageCounters w WITH (UPDLOCK, HOLDLOCK)
        WHERE w.ContractID = @ContractID
          AND w.ScopeID = @ScopeID
          AND w.WorkflowDefID = @WorkflowDefID
          AND w.PeriodType = @PeriodType
          AND w.PeriodStartUtc = @PeriodStartUtc;

        IF @RunsExecuted IS NULL
        BEGIN
            INSERT INTO Contract.WorkflowUsageCounters
            (
                ContractID,
                ScopeID,
                WorkflowDefID,
                PeriodType,
                PeriodStartUtc,
                RunsExecuted,
                UpdatedAtUtc
            )
            VALUES
            (
                @ContractID,
                @ScopeID,
                @WorkflowDefID,
                @PeriodType,
                @PeriodStartUtc,
                0,
                @UtcNow
            );
            SET @RunsExecuted = 0;
        END

        SET @NewRunsExecuted = @RunsExecuted + @ConsumeRuns;

        IF @NewRunsExecuted > @MaxRuns
        BEGIN
            SELECT
                CAST(0 AS BIT) AS IsAllowed,
                @ContractID AS ContractID,
                N'WORKFLOW_QUOTA_EXCEEDED' AS ReasonCode,
                @RunsExecuted AS RunsExecuted,
                @MaxRuns AS MaxRunsPerPeriod,
                @PeriodType AS PeriodType,
                @PeriodStartUtc AS PeriodStartUtc;
            ROLLBACK TRANSACTION;
            RETURN 50022;
        END

        UPDATE Contract.WorkflowUsageCounters
        SET RunsExecuted = @NewRunsExecuted,
            UpdatedAtUtc = @UtcNow
        WHERE ContractID = @ContractID
          AND ScopeID = @ScopeID
          AND WorkflowDefID = @WorkflowDefID
          AND PeriodType = @PeriodType
          AND PeriodStartUtc = @PeriodStartUtc;

        SELECT
            CAST(1 AS BIT) AS IsAllowed,
            @ContractID AS ContractID,
            N'OK' AS ReasonCode,
            @NewRunsExecuted AS RunsExecuted,
            @MaxRuns AS MaxRunsPerPeriod,
            @PeriodType AS PeriodType,
            @PeriodStartUtc AS PeriodStartUtc;

        COMMIT TRANSACTION;
        RETURN 0;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        -- Re-raise the original error
        DECLARE @ErrorMessage NVARCHAR(4000), @ErrorSeverity INT, @ErrorState INT;
        SELECT 
            @ErrorMessage = ERROR_MESSAGE(),
            @ErrorSeverity = ERROR_SEVERITY(),
            @ErrorState = ERROR_STATE();
        RAISERROR (@ErrorMessage, @ErrorSeverity, @ErrorState);
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE Contract.spContractValidateRoleGrant
    @ScopeID INT,
    @RoleID INT,
    @GrantType VARCHAR(16),
    @UtcNow DATETIME2(3) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    IF @UtcNow IS NULL SET @UtcNow = SYSUTCDATETIME();

    IF @GrantType NOT IN ('GLOBAL','SCOPED')
    BEGIN
        SELECT CAST(0 AS BIT) AS IsAllowed, NULL AS ContractID, N'INVALID_GRANT_TYPE' AS ReasonCode, CAST(0 AS BIT) AS RequiresApproval;
        RETURN 50030;
    END

    DECLARE @Access TABLE (IsAllowed BIT, ContractID INT, ReasonCode NVARCHAR(64));
    INSERT INTO @Access
    EXEC Contract.spContractValidateScopeAccess @ScopeID = @ScopeID, @UtcNow = @UtcNow;

    DECLARE @ScopeAllowed BIT = (SELECT TOP (1) IsAllowed FROM @Access);
    DECLARE @ContractID INT = (SELECT TOP (1) ContractID FROM @Access);

    IF ISNULL(@ScopeAllowed, 0) = 0
    BEGIN
        SELECT CAST(0 AS BIT) AS IsAllowed, @ContractID AS ContractID, N'NO_ACTIVE_CONTRACT_FOR_SCOPE' AS ReasonCode, CAST(0 AS BIT) AS RequiresApproval;
        RETURN 50031;
    END

    DECLARE @Allowed VARCHAR(16) = NULL;
    DECLARE @RequiresApproval BIT = 0;

    SELECT
        @Allowed = p.GrantTypeAllowed,
        @RequiresApproval = p.RequiresApproval
    FROM Contract.ContractRolePolicies p
    WHERE p.ContractID = @ContractID
      AND p.RoleID = @RoleID;

    IF @Allowed IS NULL
    BEGIN
        SELECT CAST(0 AS BIT) AS IsAllowed, @ContractID AS ContractID, N'ROLE_NOT_ALLOWED_BY_CONTRACT' AS ReasonCode, CAST(0 AS BIT) AS RequiresApproval;
        RETURN 50032;
    END

    IF NOT
    (
        @Allowed = 'BOTH'
        OR (@Allowed = 'GLOBAL' AND @GrantType = 'GLOBAL')
        OR (@Allowed = 'SCOPED' AND @GrantType = 'SCOPED')
    )
    BEGIN
        SELECT CAST(0 AS BIT) AS IsAllowed, @ContractID AS ContractID, N'GRANT_TYPE_NOT_ALLOWED_BY_CONTRACT' AS ReasonCode, @RequiresApproval AS RequiresApproval;
        RETURN 50033;
    END

    SELECT CAST(1 AS BIT) AS IsAllowed, @ContractID AS ContractID, N'OK' AS ReasonCode, @RequiresApproval AS RequiresApproval;
    RETURN 0;
END
GO

