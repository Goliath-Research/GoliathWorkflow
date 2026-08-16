-- Auto-extracted by scripts/extract_legacy_schema.py from MethylPipeline.sql
-- Idempotent incremental deploy (IF OBJECT_ID / CREATE OR ALTER).
-- Do not edit by hand unless also updating the twin under sql_pg/.

/* 
	Author	Inty Saez 
	Date 	04/13/2026
	Subject	Get UserId by User's email  
*/

CREATE OR ALTER PROCEDURE RBAC.spGetUserIdByEmail
    @Email  NVARCHAR(100),
    @UserId INT = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT @UserId = u.ID
    FROM   RBAC.Users u
    WHERE  u.email = @Email
      AND  u.Active = 1;
    -- Returns NULL in @UserId if no active user found.
END;
GO

/*
	Author	Inty Saez 
	Date 	04/13/2026
	Subject Get User's Role 
*/


CREATE OR ALTER PROCEDURE RBAC.spGetUserRoles
    @UserId INT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT DISTINCT
        @UserId     AS UserId,
        r.Name      AS Role,
        r.ID        AS RoleId
    FROM   RBAC.Group_Users  gu
    JOIN   RBAC.Group_Roles  gr  ON gr.GroupID = gu.GroupID
    JOIN   RBAC.Roles        r   ON r.ID       = gr.RoleID
    WHERE  gu.UserID = @UserId
    ORDER BY r.Name;
END;
GO

CREATE OR ALTER TRIGGER RBAC.trg_UserRoleGrants_EnforceBypassScopeApproval
ON RBAC.UserRoleGrants
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    IF EXISTS
    (
        SELECT 1
        FROM inserted i
        INNER JOIN [RBAC].[Roles] r ON r.[ID] = i.[RoleID]
        WHERE i.[Active] = 1
          AND r.[BypassScope] = 1
          AND i.[GrantType] <> 'GLOBAL'
    )
    BEGIN
        THROW 50150, 'BypassScope roles require GLOBAL grant type.', 1;
    END

    IF EXISTS
    (
        SELECT 1
        FROM inserted i
        INNER JOIN [RBAC].[Roles] r ON r.[ID] = i.[RoleID]
        LEFT JOIN [RBAC].[BypassScopeApprovals] a
            ON a.[ApprovalID] = i.[ApprovalID]
           AND a.[UserID] = i.[UserID]
           AND a.[RoleID] = i.[RoleID]
           AND a.[Status] = 'APPROVED'
           AND (a.[ExpiresAtUtc] IS NULL OR a.[ExpiresAtUtc] >= SYSUTCDATETIME())
        WHERE i.[Active] = 1
          AND r.[BypassScope] = 1
          AND a.[ApprovalID] IS NULL
    )
    BEGIN
        THROW 50151, 'BypassScope role grant requires a valid approved approval record.', 1;
    END
END
GO

/*
Revokes a direct role assignment from a session.
Returns:
  - Result set 1: revocation summary
  - Result set 2: standardized status envelope
*/
CREATE OR ALTER PROCEDURE RBAC.usp_session_revoke_role
    @SessionID INT,
    @RoleID INT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @StartedTran BIT = 0;
    DECLARE @DeletedRows INT = 0;

    BEGIN TRY
        IF @@TRANCOUNT = 0
        BEGIN
            BEGIN TRANSACTION;
            SET @StartedTran = 1;
        END

        IF @SessionID IS NULL OR @SessionID <= 0
        BEGIN
            SELECT 50001 AS StatusCode, N'ValidationError: @SessionID must be > 0.' AS StatusMessage,
                   NULL AS SqlErrorNumber, NULL AS SqlErrorState, NULL AS SqlErrorSeverity,
                   OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID) AS ProcedureName,
                   SYSUTCDATETIME() AS UtcTimestamp;
            RETURN 50001;
        END

        IF @RoleID IS NULL OR @RoleID <= 0
        BEGIN
            SELECT 50001 AS StatusCode, N'ValidationError: @RoleID must be > 0.' AS StatusMessage,
                   NULL AS SqlErrorNumber, NULL AS SqlErrorState, NULL AS SqlErrorSeverity,
                   OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID) AS ProcedureName,
                   SYSUTCDATETIME() AS UtcTimestamp;
            RETURN 50001;
        END

        DELETE FROM [RBAC].[Session_Roles]
        WHERE [SessionID] = @SessionID
          AND [RoleID] = @RoleID;

        SET @DeletedRows = @@ROWCOUNT;

        SELECT
            @SessionID AS SessionID,
            @RoleID AS RoleID,
            @DeletedRows AS RowsAffected;

        IF @StartedTran = 1
        BEGIN
            COMMIT TRANSACTION;
        END

        SELECT
            0 AS StatusCode,
            N'OK' AS StatusMessage,
            NULL AS SqlErrorNumber,
            NULL AS SqlErrorState,
            NULL AS SqlErrorSeverity,
            OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID) AS ProcedureName,
            SYSUTCDATETIME() AS UtcTimestamp;
        RETURN 0;
    END TRY
    BEGIN CATCH
        IF @StartedTran = 1 AND @@TRANCOUNT > 0
        BEGIN
            ROLLBACK TRANSACTION;
        END

        SELECT
            ERROR_NUMBER() AS StatusCode,
            ERROR_MESSAGE() AS StatusMessage,
            ERROR_NUMBER() AS SqlErrorNumber,
            ERROR_STATE() AS SqlErrorState,
            ERROR_SEVERITY() AS SqlErrorSeverity,
            COALESCE(ERROR_PROCEDURE(), OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID)) AS ProcedureName,
            SYSUTCDATETIME() AS UtcTimestamp;
        RETURN ERROR_NUMBER();
    END CATCH
END;
GO

/*
Checks if a session is authorized for an object/operation pair.
Returns:
  - Result set 1: authorization decision
  - Result set 2: standardized status envelope
*/
CREATE OR ALTER PROCEDURE RBAC.usp_session_is_authorized
    @SessionID INT,
    @ObjID INT,
    @OperationID INT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRY
        IF @SessionID IS NULL OR @SessionID <= 0
        BEGIN
            SELECT 50001 AS StatusCode, N'ValidationError: @SessionID must be > 0.' AS StatusMessage,
                   NULL AS SqlErrorNumber, NULL AS SqlErrorState, NULL AS SqlErrorSeverity,
                   OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID) AS ProcedureName,
                   SYSUTCDATETIME() AS UtcTimestamp;
            RETURN 50001;
        END

        IF @ObjID IS NULL OR @ObjID <= 0
        BEGIN
            SELECT 50001 AS StatusCode, N'ValidationError: @ObjID must be > 0.' AS StatusMessage,
                   NULL AS SqlErrorNumber, NULL AS SqlErrorState, NULL AS SqlErrorSeverity,
                   OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID) AS ProcedureName,
                   SYSUTCDATETIME() AS UtcTimestamp;
            RETURN 50001;
        END

        IF @OperationID IS NULL OR @OperationID <= 0
        BEGIN
            SELECT 50001 AS StatusCode, N'ValidationError: @OperationID must be > 0.' AS StatusMessage,
                   NULL AS SqlErrorNumber, NULL AS SqlErrorState, NULL AS SqlErrorSeverity,
                   OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID) AS ProcedureName,
                   SYSUTCDATETIME() AS UtcTimestamp;
            RETURN 50001;
        END

        IF NOT EXISTS (SELECT 1 FROM [RBAC].[Sessions] WHERE [ID] = @SessionID)
        BEGIN
            SELECT 50010 AS StatusCode, N'BusinessRule: Session not found.' AS StatusMessage,
                   NULL AS SqlErrorNumber, NULL AS SqlErrorState, NULL AS SqlErrorSeverity,
                   OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID) AS ProcedureName,
                   SYSUTCDATETIME() AS UtcTimestamp;
            RETURN 50010;
        END

        IF NOT EXISTS (SELECT 1 FROM [dbo].[Objs] WHERE [ID] = @ObjID)
        BEGIN
            SELECT 50010 AS StatusCode, N'BusinessRule: Object not found.' AS StatusMessage,
                   NULL AS SqlErrorNumber, NULL AS SqlErrorState, NULL AS SqlErrorSeverity,
                   OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID) AS ProcedureName,
                   SYSUTCDATETIME() AS UtcTimestamp;
            RETURN 50010;
        END

        IF NOT EXISTS (SELECT 1 FROM [Meta].[Operations] WHERE [ID] = @OperationID)
        BEGIN
            SELECT 50010 AS StatusCode, N'BusinessRule: Operation not found.' AS StatusMessage,
                   NULL AS SqlErrorNumber, NULL AS SqlErrorState, NULL AS SqlErrorSeverity,
                   OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID) AS ProcedureName,
                   SYSUTCDATETIME() AS UtcTimestamp;
            RETURN 50010;
        END

        ;WITH SessionUser AS
        (
            SELECT s.[ID] AS SessionID, s.[UserID]
            FROM [RBAC].[Sessions] s
            WHERE s.[ID] = @SessionID
        ),
        EffectiveRoles AS
        (
            SELECT sr.[RoleID]
            FROM [RBAC].[Session_Roles] sr
            WHERE sr.[SessionID] = @SessionID

            UNION

            SELECT gr.[RoleID]
            FROM SessionUser su
            INNER JOIN [RBAC].[Group_Users] gu ON gu.[UserID] = su.[UserID]
            INNER JOIN [RBAC].[Group_Roles] gr ON gr.[GroupID] = gu.[GroupID]
        ),
        PermissionMatch AS
        (
            SELECT 1 AS MatchFound
            FROM EffectiveRoles er
            INNER JOIN [RBAC].[Role_Permissions] rp ON rp.[RoleID] = er.[RoleID]
            INNER JOIN [RBAC].[Permissions] p ON p.[ID] = rp.[PermissionID]
            WHERE p.[ObjID] = @ObjID
              AND p.[OperationID] = @OperationID
        )
        SELECT
            @SessionID AS SessionID,
            @ObjID AS ObjID,
            @OperationID AS OperationID,
            CAST(CASE WHEN EXISTS (SELECT 1 FROM PermissionMatch) THEN 1 ELSE 0 END AS BIT) AS IsAuthorized;

        SELECT
            0 AS StatusCode,
            N'OK' AS StatusMessage,
            NULL AS SqlErrorNumber,
            NULL AS SqlErrorState,
            NULL AS SqlErrorSeverity,
            OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID) AS ProcedureName,
            SYSUTCDATETIME() AS UtcTimestamp;
        RETURN 0;
    END TRY
    BEGIN CATCH
        SELECT
            ERROR_NUMBER() AS StatusCode,
            ERROR_MESSAGE() AS StatusMessage,
            ERROR_NUMBER() AS SqlErrorNumber,
            ERROR_STATE() AS SqlErrorState,
            ERROR_SEVERITY() AS SqlErrorSeverity,
            COALESCE(ERROR_PROCEDURE(), OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID)) AS ProcedureName,
            SYSUTCDATETIME() AS UtcTimestamp;
        RETURN ERROR_NUMBER();
    END CATCH
END;
GO

CREATE OR ALTER PROCEDURE RBAC.usp_session_get_effective_roles_v2
    @SessionID INT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @SessionID IS NULL OR @SessionID <= 0
        THROW 50001, 'ValidationError: @SessionID must be > 0.', 1;

    IF NOT EXISTS (SELECT 1 FROM [RBAC].[Sessions] WHERE [ID] = @SessionID)
        THROW 50010, 'BusinessRule: Session not found.', 1;

    ;WITH SessionUser AS
    (
        SELECT s.[ID] AS SessionID, s.[UserID], s.[ActiveScopeID]
        FROM [RBAC].[Sessions] s
        WHERE s.[ID] = @SessionID
    ),
    CandidateRoles AS
    (
        SELECT
            urg.[RoleID],
            CAST(CASE WHEN urg.[GrantType] = 'GLOBAL' THEN N'GlobalGrant' ELSE N'ScopedGrant' END AS NVARCHAR(32)) AS RoleSource,
            CAST(CASE WHEN urg.[GrantType] = 'GLOBAL' THEN 400 ELSE 350 END AS INT) AS SourcePriority
        FROM SessionUser su
        INNER JOIN [RBAC].[UserRoleGrants] urg
            ON urg.[UserID] = su.[UserID]
           AND urg.[Active] = 1
           AND
           (
               urg.[GrantType] = 'GLOBAL'
               OR (urg.[GrantType] = 'SCOPED' AND urg.[ScopeID] = su.[ActiveScopeID])
           )

        UNION ALL

        SELECT
            sr.[RoleID],
            CAST(N'DirectSessionRole' AS NVARCHAR(32)) AS RoleSource,
            CAST(200 AS INT) AS SourcePriority
        FROM [RBAC].[Session_Roles] sr
        WHERE sr.[SessionID] = @SessionID

        UNION ALL

        SELECT
            gr.[RoleID],
            CAST(N'GroupInheritedRole' AS NVARCHAR(32)) AS RoleSource,
            CAST(100 AS INT) AS SourcePriority
        FROM SessionUser su
        INNER JOIN [RBAC].[Group_Users] gu ON gu.[UserID] = su.[UserID]
        INNER JOIN [RBAC].[Group_Roles] gr ON gr.[GroupID] = gu.[GroupID]
    ),
    RankedRoles AS
    (
        SELECT
            cr.[RoleID],
            cr.[RoleSource],
            cr.[SourcePriority],
            ROW_NUMBER() OVER (PARTITION BY cr.[RoleID] ORDER BY cr.[SourcePriority] DESC) AS rn
        FROM CandidateRoles cr
    )
    SELECT
        rr.[RoleID],
        r.[Name] AS RoleName,
        r.[BypassScope],
        rr.[RoleSource] AS EffectiveRoleSource,
        rr.[SourcePriority] AS EffectiveRolePriority
    FROM RankedRoles rr
    INNER JOIN [RBAC].[Roles] r ON r.[ID] = rr.[RoleID]
    WHERE rr.rn = 1
    ORDER BY rr.[SourcePriority] DESC, r.[BypassScope] DESC, r.[Name];
END
GO

/*
Returns effective permissions for a session from:
  - direct session roles
  - inherited roles from user group memberships
Returns:
  - Result set 1: permissions
  - Result set 2: standardized status envelope
*/
CREATE OR ALTER PROCEDURE RBAC.usp_session_get_effective_permissions
    @SessionID INT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRY
        IF @SessionID IS NULL OR @SessionID <= 0
        BEGIN
            SELECT 50001 AS StatusCode, N'ValidationError: @SessionID must be > 0.' AS StatusMessage,
                   NULL AS SqlErrorNumber, NULL AS SqlErrorState, NULL AS SqlErrorSeverity,
                   OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID) AS ProcedureName,
                   SYSUTCDATETIME() AS UtcTimestamp;
            RETURN 50001;
        END

        IF NOT EXISTS (SELECT 1 FROM [RBAC].[Sessions] WHERE [ID] = @SessionID)
        BEGIN
            SELECT 50010 AS StatusCode, N'BusinessRule: Session not found.' AS StatusMessage,
                   NULL AS SqlErrorNumber, NULL AS SqlErrorState, NULL AS SqlErrorSeverity,
                   OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID) AS ProcedureName,
                   SYSUTCDATETIME() AS UtcTimestamp;
            RETURN 50010;
        END

        ;WITH SessionUser AS
        (
            SELECT s.[ID] AS SessionID, s.[UserID]
            FROM [RBAC].[Sessions] s
            WHERE s.[ID] = @SessionID
        ),
        EffectiveRoles AS
        (
            SELECT sr.[RoleID], CAST(N'DirectSessionRole' AS NVARCHAR(50)) AS RoleSource
            FROM [RBAC].[Session_Roles] sr
            WHERE sr.[SessionID] = @SessionID

            UNION

            SELECT gr.[RoleID], CAST(N'GroupInheritedRole' AS NVARCHAR(50)) AS RoleSource
            FROM SessionUser su
            INNER JOIN [RBAC].[Group_Users] gu ON gu.[UserID] = su.[UserID]
            INNER JOIN [RBAC].[Group_Roles] gr ON gr.[GroupID] = gu.[GroupID]
        )
        SELECT DISTINCT
            er.[RoleID],
            r.[Name] AS RoleName,
            rp.[PermissionID],
            p.[Name] AS PermissionName,
            p.[ObjID],
            p.[OperationID],
            er.[RoleSource]
        FROM EffectiveRoles er
        INNER JOIN [RBAC].[Roles] r ON r.[ID] = er.[RoleID]
        INNER JOIN [RBAC].[Role_Permissions] rp ON rp.[RoleID] = er.[RoleID]
        INNER JOIN [RBAC].[Permissions] p ON p.[ID] = rp.[PermissionID]
        ORDER BY er.[RoleSource], er.[RoleID], rp.[PermissionID];

        SELECT
            0 AS StatusCode,
            N'OK' AS StatusMessage,
            NULL AS SqlErrorNumber,
            NULL AS SqlErrorState,
            NULL AS SqlErrorSeverity,
            OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID) AS ProcedureName,
            SYSUTCDATETIME() AS UtcTimestamp;
        RETURN 0;
    END TRY
    BEGIN CATCH
        SELECT
            ERROR_NUMBER() AS StatusCode,
            ERROR_MESSAGE() AS StatusMessage,
            ERROR_NUMBER() AS SqlErrorNumber,
            ERROR_STATE() AS SqlErrorState,
            ERROR_SEVERITY() AS SqlErrorSeverity,
            COALESCE(ERROR_PROCEDURE(), OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID)) AS ProcedureName,
            SYSUTCDATETIME() AS UtcTimestamp;
        RETURN ERROR_NUMBER();
    END CATCH
END;
GO

/*
Assigns a role directly to a session.
Returns:
  - Result set 1: assignment details
  - Result set 2: standardized status envelope
*/
CREATE OR ALTER PROCEDURE RBAC.usp_session_assign_role
    @SessionID INT,
    @RoleID INT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @StartedTran BIT = 0;

    BEGIN TRY
        IF @@TRANCOUNT = 0
        BEGIN
            BEGIN TRANSACTION;
            SET @StartedTran = 1;
        END

        IF @SessionID IS NULL OR @SessionID <= 0
        BEGIN
            SELECT 50001 AS StatusCode, N'ValidationError: @SessionID must be > 0.' AS StatusMessage,
                   NULL AS SqlErrorNumber, NULL AS SqlErrorState, NULL AS SqlErrorSeverity,
                   OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID) AS ProcedureName,
                   SYSUTCDATETIME() AS UtcTimestamp;
            RETURN 50001;
        END

        IF @RoleID IS NULL OR @RoleID <= 0
        BEGIN
            SELECT 50001 AS StatusCode, N'ValidationError: @RoleID must be > 0.' AS StatusMessage,
                   NULL AS SqlErrorNumber, NULL AS SqlErrorState, NULL AS SqlErrorSeverity,
                   OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID) AS ProcedureName,
                   SYSUTCDATETIME() AS UtcTimestamp;
            RETURN 50001;
        END

        IF NOT EXISTS (SELECT 1 FROM [RBAC].[Sessions] WHERE [ID] = @SessionID)
        BEGIN
            SELECT 50010 AS StatusCode, N'BusinessRule: Session not found.' AS StatusMessage,
                   NULL AS SqlErrorNumber, NULL AS SqlErrorState, NULL AS SqlErrorSeverity,
                   OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID) AS ProcedureName,
                   SYSUTCDATETIME() AS UtcTimestamp;
            RETURN 50010;
        END

        IF NOT EXISTS (SELECT 1 FROM [RBAC].[Roles] WHERE [ID] = @RoleID)
        BEGIN
            SELECT 50010 AS StatusCode, N'BusinessRule: Role not found.' AS StatusMessage,
                   NULL AS SqlErrorNumber, NULL AS SqlErrorState, NULL AS SqlErrorSeverity,
                   OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID) AS ProcedureName,
                   SYSUTCDATETIME() AS UtcTimestamp;
            RETURN 50010;
        END

        IF NOT EXISTS
        (
            SELECT 1
            FROM [RBAC].[Session_Roles]
            WHERE [SessionID] = @SessionID
              AND [RoleID] = @RoleID
        )
        BEGIN
            INSERT INTO [RBAC].[Session_Roles]
            (
                [SessionID],
                [RoleID]
            )
            VALUES
            (
                @SessionID,
                @RoleID
            );
        END

        SELECT
            sr.[SessionID],
            sr.[RoleID]
        FROM [RBAC].[Session_Roles] sr
        WHERE sr.[SessionID] = @SessionID
          AND sr.[RoleID] = @RoleID;

        IF @StartedTran = 1
        BEGIN
            COMMIT TRANSACTION;
        END

        SELECT
            0 AS StatusCode,
            N'OK' AS StatusMessage,
            NULL AS SqlErrorNumber,
            NULL AS SqlErrorState,
            NULL AS SqlErrorSeverity,
            OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID) AS ProcedureName,
            SYSUTCDATETIME() AS UtcTimestamp;
        RETURN 0;
    END TRY
    BEGIN CATCH
        IF @StartedTran = 1 AND @@TRANCOUNT > 0
        BEGIN
            ROLLBACK TRANSACTION;
        END

        SELECT
            ERROR_NUMBER() AS StatusCode,
            ERROR_MESSAGE() AS StatusMessage,
            ERROR_NUMBER() AS SqlErrorNumber,
            ERROR_STATE() AS SqlErrorState,
            ERROR_SEVERITY() AS SqlErrorSeverity,
            COALESCE(ERROR_PROCEDURE(), OBJECT_SCHEMA_NAME(@@PROCID) + N'.' + OBJECT_NAME(@@PROCID)) AS ProcedureName,
            SYSUTCDATETIME() AS UtcTimestamp;
        RETURN ERROR_NUMBER();
    END CATCH
END;
GO

CREATE OR ALTER PROCEDURE RBAC.spResolveUserByScopeIdentity
    @ScopeID INT,
    @Issuer NVARCHAR(512),
    @Subject NVARCHAR(512),
    @UserID INT OUTPUT,
    @ProviderID INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    SET @UserID = NULL;
    SET @ProviderID = NULL;

    IF @ScopeID IS NULL OR @ScopeID <= 0
       OR @Issuer IS NULL OR LTRIM(RTRIM(@Issuer)) = N'' 
       OR @Subject IS NULL OR LTRIM(RTRIM(@Subject)) = N''
    BEGIN
        THROW 50001, 'ValidationError: ScopeID, Issuer and Subject are required.', 1;
    END

    SELECT TOP (1)
        @ProviderID = ip.[ProviderID]
    FROM [RBAC].[ScopeIdentityProviders] sip
    INNER JOIN [RBAC].[IdentityProviders] ip
        ON ip.[ProviderID] = sip.[ProviderID]
    WHERE sip.[ScopeID] = @ScopeID
      AND sip.[Active] = 1
      AND ip.[Active] = 1
      AND ip.[Issuer] = @Issuer;

    IF @ProviderID IS NULL
    BEGIN
        THROW 50020, 'BusinessRule: Scope is not configured for the provided issuer.', 1;
    END

    SELECT TOP (1)
        @UserID = ei.[UserID]
    FROM [RBAC].[ExternalIdentities] ei
    INNER JOIN [RBAC].[Users] u
        ON u.[ID] = ei.[UserID]
    WHERE ei.[ProviderID] = @ProviderID
      AND ei.[Subject] = @Subject
      AND ei.[Active] = 1
      AND u.[Active] = 1;

    IF @UserID IS NOT NULL
    BEGIN
        UPDATE [RBAC].[ExternalIdentities]
        SET [LastLoginAtUtc] = SYSUTCDATETIME()
        WHERE [ProviderID] = @ProviderID
          AND [Subject] = @Subject
          AND [UserID] = @UserID;
    END

    SELECT @ProviderID AS [ProviderID], @UserID AS [UserID];
END
GO

/*
	Author	Inty Saez
	Date 	05/06/2026
	Subject	Get User Nav Tree (RBAC)
*/

CREATE OR ALTER PROCEDURE RBAC.spGetUserNavTree
    @UserId INT,
    @RoleId INT,
    @ScopeID INT = NULL
AS
BEGIN
    SET NOCOUNT ON;

    ;WITH UserAuthorizedNodes AS
    (
        SELECT
            rn.NodeId,
            n.NodePath
        FROM portal.Role2Node rn
        JOIN portal.NavTree n ON n.ID = rn.NodeId
        JOIN portal.viewUserAllRoles u ON u.RoleId = rn.RoleId AND u.UserId = @UserId
        WHERE 
            rn.RoleId = @RoleId
            AND (@ScopeID IS NULL OR rn.ScopeId = @ScopeID)
    ),
    VisibleTree AS
    (
        SELECT
            n.ID,
            n.ParentID,
            n.Caption,
            n.Seq,
            n.InfoID,
            n.SortPath
        FROM portal.NavTree n
        WHERE EXISTS
        (
            SELECT 1
            FROM UserAuthorizedNodes uan
            WHERE uan.NodeId = n.ID OR uan.NodePath LIKE n.NodePath + '/%'
        )
    )
    SELECT
        CAST(v.ID AS SMALLINT)       AS ID,
        CAST(v.ParentID AS SMALLINT) AS ParentID,
        v.Caption,
        v.Seq,
        v.InfoID
    FROM VisibleTree v
    ORDER BY v.SortPath, v.ID;
END;
GO

