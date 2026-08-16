-- Auto-extracted by scripts/extract_legacy_schema.py from MethylPipeline.sql
-- Idempotent incremental deploy (IF OBJECT_ID / CREATE OR ALTER).
-- Do not edit by hand unless also updating the twin under sql_pg/.

CREATE OR ALTER PROCEDURE Onboarding.spAcceptInvitation
    @InvitationID BIGINT,
    @Issuer NVARCHAR(512),
    @Subject NVARCHAR(512),
    @Email VARCHAR(255),
    @FullName VARCHAR(200),
    @UserID INT OUTPUT,
    @UtcNow DATETIME2(3) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @UtcNow IS NULL SET @UtcNow = SYSUTCDATETIME();

    -- Validate required inputs before opening the transaction.
    IF @InvitationID IS NULL OR @InvitationID <= 0
       OR @Issuer IS NULL OR LTRIM(RTRIM(@Issuer)) = N''
       OR @Subject IS NULL OR LTRIM(RTRIM(@Subject)) = N''
       OR @Email IS NULL OR LTRIM(RTRIM(@Email)) = ''
       OR @FullName IS NULL OR LTRIM(RTRIM(@FullName)) = ''
    BEGIN
        THROW 50001, 'ValidationError: InvitationID, Issuer, Subject, Email and FullName are required.', 1;
    END

    DECLARE @NormalizedEmail VARCHAR(255) = LOWER(LTRIM(RTRIM(@Email)));
    DECLARE @NormalizedInvitationEmail VARCHAR(255);
    DECLARE @ScopeID INT;
    DECLARE @ExpectedProviderID INT;
    DECLARE @ExpectedDomain VARCHAR(255);
    DECLARE @DefaultRoleID INT;
    DECLARE @GrantType VARCHAR(16);
    DECLARE @InvitationStatus VARCHAR(16);
    DECLARE @ExpiresAtUtc DATETIME2(3);
    DECLARE @ContractID INT = NULL;
    DECLARE @RoleAllowed BIT = 1;
    DECLARE @RoleRequiresApproval BIT = 0;
    DECLARE @RoleReason NVARCHAR(64) = N'OK';
    DECLARE @GrantedRoleID INT = NULL;
    DECLARE @GrantedScopeID INT = NULL;

    SET @UserID = NULL;

    BEGIN TRY
        BEGIN TRANSACTION;

        SELECT
            @ScopeID = i.[ScopeID],
            @NormalizedInvitationEmail = LOWER(LTRIM(RTRIM(i.[Email]))),
            @ExpectedProviderID = i.[ExpectedProviderID],
            @ExpectedDomain = i.[ExpectedDomain],
            @DefaultRoleID = i.[DefaultRoleID],
            @GrantType = i.[GrantType],
            @InvitationStatus = i.[Status],
            @ExpiresAtUtc = i.[ExpiresAtUtc]
        FROM [Onboarding].[Invitations] i WITH (UPDLOCK, HOLDLOCK)
        WHERE i.[InvitationID] = @InvitationID;

        -- Validate invitation existence.
        IF @ScopeID IS NULL
            THROW 50010, 'BusinessRule: Invitation not found.', 1;

        -- Validate invitation lifecycle state.
        IF @InvitationStatus <> 'PENDING'
            THROW 50011, 'BusinessRule: Invitation is not pending.', 1;

        -- Validate invitation expiration and mark stale pending rows as expired.
        IF @ExpiresAtUtc < @UtcNow
        BEGIN
            UPDATE [Onboarding].[Invitations]
            SET [Status] = 'EXPIRED'
            WHERE [InvitationID] = @InvitationID
              AND [Status] = 'PENDING';

            THROW 50012, 'BusinessRule: Invitation has expired.', 1;
        END

        -- Validate that authenticated email matches invited email.
        IF @NormalizedInvitationEmail <> @NormalizedEmail
            THROW 50013, 'BusinessRule: Invitation email does not match authenticated email.', 1;

        -- Validate issuer/provider consistency for the invitation.
        IF NOT EXISTS
        (
            SELECT 1
            FROM [RBAC].[IdentityProviders] ip
            WHERE ip.[ProviderID] = @ExpectedProviderID
              AND ip.[Active] = 1
              AND ip.[Issuer] = @Issuer
        )
            THROW 50014, 'BusinessRule: Invitation provider does not match authenticated issuer.', 1;

        -- Validate that the scope is currently linked to the expected provider.
        IF NOT EXISTS
        (
            SELECT 1
            FROM [RBAC].[ScopeIdentityProviders] sip
            WHERE sip.[ScopeID] = @ScopeID
              AND sip.[ProviderID] = @ExpectedProviderID
              AND sip.[Active] = 1
        )
            THROW 50015, 'BusinessRule: Scope is not active for invitation provider.', 1;

        -- Validate optional email domain policy from the invitation.
        IF @ExpectedDomain IS NOT NULL
           AND RIGHT(@NormalizedEmail, LEN(@ExpectedDomain) + 1) <> '@' + LOWER(@ExpectedDomain)
            THROW 50016, 'BusinessRule: Authenticated email is outside expected domain.', 1;

        DECLARE @ScopeAccess TABLE (IsAllowed BIT, ContractID INT, ReasonCode NVARCHAR(64));
        INSERT INTO @ScopeAccess
        EXEC [Contract].[spContractValidateScopeAccess]
            @ScopeID = @ScopeID,
            @UtcNow = @UtcNow;

        SELECT TOP (1)
            @ContractID = sa.[ContractID]
        FROM @ScopeAccess sa
        WHERE sa.[IsAllowed] = 1;

        -- Validate active contract coverage for the invited scope.
        IF @ContractID IS NULL
            THROW 50017, 'BusinessRule: Scope has no active contract for invitation acceptance.', 1;

        SELECT
            @UserID = u.[ID]
        FROM [RBAC].[Users] u WITH (UPDLOCK, HOLDLOCK)
        WHERE u.[email] = @NormalizedEmail;

        IF @UserID IS NULL
        BEGIN
            INSERT INTO [RBAC].[Users] ([FullName], [email], [Active])
            VALUES (@FullName, @NormalizedEmail, 1);
            SET @UserID = SCOPE_IDENTITY();
        END
        ELSE
        BEGIN
            UPDATE [RBAC].[Users]
            SET [FullName] = @FullName,
                [Active] = 1
            WHERE [ID] = @UserID
              AND ([FullName] <> @FullName OR [Active] <> 1);
        END

        DECLARE @ExistingIdentityUserID INT = NULL;
        SELECT
            @ExistingIdentityUserID = ei.[UserID]
        FROM [RBAC].[ExternalIdentities] ei WITH (UPDLOCK, HOLDLOCK)
        WHERE ei.[ProviderID] = @ExpectedProviderID
          AND ei.[Subject] = @Subject;

        -- Validate that external identity is not already bound to another user.
        IF @ExistingIdentityUserID IS NOT NULL AND @ExistingIdentityUserID <> @UserID
            THROW 50018, 'BusinessRule: External identity is already bound to a different user.', 1;

        IF @ExistingIdentityUserID IS NULL
        BEGIN
            INSERT INTO [RBAC].[ExternalIdentities]
            (
                [UserID],
                [ProviderID],
                [Subject],
                [EmailSnapshot],
                [Active],
                [LastLoginAtUtc]
            )
            VALUES
            (
                @UserID,
                @ExpectedProviderID,
                @Subject,
                @NormalizedEmail,
                1,
                @UtcNow
            );
        END
        ELSE
        BEGIN
            UPDATE [RBAC].[ExternalIdentities]
            SET [UserID] = @UserID,
                [EmailSnapshot] = @NormalizedEmail,
                [Active] = 1,
                [LastLoginAtUtc] = @UtcNow
            WHERE [ProviderID] = @ExpectedProviderID
              AND [Subject] = @Subject;
        END

        IF @DefaultRoleID IS NOT NULL
        BEGIN
            DECLARE @RoleValidation TABLE (IsAllowed BIT, ContractID INT, ReasonCode NVARCHAR(64), RequiresApproval BIT);
            INSERT INTO @RoleValidation
            EXEC [Contract].[spContractValidateRoleGrant]
                @ScopeID = @ScopeID,
                @RoleID = @DefaultRoleID,
                @GrantType = @GrantType,
                @UtcNow = @UtcNow;

            SELECT TOP (1)
                @RoleAllowed = rv.[IsAllowed],
                @RoleRequiresApproval = rv.[RequiresApproval],
                @RoleReason = rv.[ReasonCode]
            FROM @RoleValidation rv;

            -- Validate role/grant entitlement against contract policies.
            IF ISNULL(@RoleAllowed, 0) = 0
                THROW 50019, 'BusinessRule: Invitation role/grant is not allowed by contract.', 1;

            -- Validate whether policy requires an additional approval workflow.
            IF ISNULL(@RoleRequiresApproval, 0) = 1
                THROW 50020, 'BusinessRule: Invitation role grant requires manual approval.', 1;

            IF @GrantType = 'SCOPED'
                SET @GrantedScopeID = @ScopeID;
            ELSE
                SET @GrantedScopeID = NULL;

            IF NOT EXISTS
            (
                SELECT 1
                FROM [RBAC].[UserRoleGrants] urg
                WHERE urg.[UserID] = @UserID
                  AND urg.[RoleID] = @DefaultRoleID
                  AND urg.[GrantType] = @GrantType
                  AND
                  (
                      (urg.[ScopeID] = @GrantedScopeID)
                      OR (urg.[ScopeID] IS NULL AND @GrantedScopeID IS NULL)
                  )
                  AND urg.[Active] = 1
            )
            BEGIN
                INSERT INTO [RBAC].[UserRoleGrants]
                (
                    [UserID],
                    [RoleID],
                    [GrantType],
                    [ScopeID],
                    [Active]
                )
                VALUES
                (
                    @UserID,
                    @DefaultRoleID,
                    @GrantType,
                    @GrantedScopeID,
                    1
                );
            END

            SET @GrantedRoleID = @DefaultRoleID;
        END

        UPDATE [Onboarding].[Invitations]
        SET [Status] = 'ACCEPTED',
            [AcceptedByUserID] = @UserID,
            [AcceptedAtUtc] = @UtcNow
        WHERE [InvitationID] = @InvitationID;

        INSERT INTO [Onboarding].[AuditLog]
        (
            [ScopeID],
            [InvitationID],
            [ActorUserID],
            [EventType],
            [EventDataJson]
        )
        VALUES
        (
            @ScopeID,
            @InvitationID,
            @UserID,
            'INVITATION_ACCEPTED',
            (
                SELECT
                    @ContractID AS ContractID,
                    @ExpectedProviderID AS ProviderID,
                    @GrantedRoleID AS GrantedRoleID,
                    @GrantType AS GrantType,
                    @RoleReason AS RolePolicyReasonCode
                FOR JSON PATH, WITHOUT_ARRAY_WRAPPER
            )
        );

        COMMIT TRANSACTION;

        SELECT
            @InvitationID AS InvitationID,
            @UserID AS UserID,
            @ScopeID AS ScopeID,
            @ExpectedProviderID AS ProviderID,
            @ContractID AS ContractID,
            @GrantedRoleID AS GrantedRoleID,
            @GrantType AS GrantType,
            CAST(CASE WHEN @GrantedRoleID IS NULL THEN 0 ELSE 1 END AS BIT) AS RoleGrantApplied;

        RETURN 0;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END
GO

