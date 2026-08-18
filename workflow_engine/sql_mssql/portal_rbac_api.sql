/*
  Portal RBAC admin façade (Azure SQL).

  EpiPortal Admin screens call portal.sp_* only — not RBAC.* write procs.
  Session/nav at login still uses RBAC.spGetUserNavTree / usp_session_*.

  Prerequisites: rbac_schema.sql, onboarding_schema.sql, portal.Role2Node.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

CREATE OR ALTER PROCEDURE portal.sp_list_users
    @include_inactive bit = 0
AS
BEGIN
    SET NOCOUNT ON;
    SELECT u.ID AS user_id, u.FullName, u.email, u.Active
    FROM RBAC.Users u
    WHERE @include_inactive = 1 OR u.Active = 1
    ORDER BY u.FullName, u.email;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_user
    @user_id int
AS
BEGIN
    SET NOCOUNT ON;
    SELECT u.ID AS user_id, u.FullName, u.email, u.Active
    FROM RBAC.Users u
    WHERE u.ID = @user_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_upsert_user
    @email varchar(50),
    @full_name varchar(200),
    @active int = 1,
    @user_id int = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @normalized varchar(50) = LOWER(LTRIM(RTRIM(@email)));

    IF @normalized IS NULL OR @normalized = ''
        THROW 50001, N'email is required.', 1;
    IF @full_name IS NULL OR LTRIM(RTRIM(@full_name)) = ''
        THROW 50001, N'full_name is required.', 1;

    SELECT @user_id = u.ID FROM RBAC.Users u WHERE u.email = @normalized;

    IF @user_id IS NULL
    BEGIN
        INSERT INTO RBAC.Users (FullName, email, Active)
        VALUES (@full_name, @normalized, ISNULL(@active, 1));
        SET @user_id = SCOPE_IDENTITY();
    END
    ELSE
        UPDATE RBAC.Users
        SET FullName = @full_name, Active = ISNULL(@active, Active)
        WHERE ID = @user_id;

    SELECT @user_id AS user_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_user_identities
    @user_id int
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        ei.ID AS identity_id,
        ei.ProviderID AS provider_id,
        p.Name AS provider_name,
        ei.Subject,
        ei.EmailSnapshot,
        ei.Active,
        ei.LastLoginAtUtc
    FROM RBAC.ExternalIdentities ei
    INNER JOIN RBAC.IdentityProviders p ON p.ProviderID = ei.ProviderID
    WHERE ei.UserID = @user_id
    ORDER BY ei.ID;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_roles
AS
BEGIN
    SET NOCOUNT ON;
    SELECT r.ID AS role_id, r.Name, r.BypassScope
    FROM RBAC.Roles r
    ORDER BY r.Name;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_permissions
    @role_id int = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        p.ID AS permission_id,
        p.Name,
        p.ObjID,
        p.OperationID,
        rp.RoleID
    FROM RBAC.Permissions p
    LEFT JOIN RBAC.Role_Permissions rp
      ON rp.PermissionID = p.ID AND (@role_id IS NULL OR rp.RoleID = @role_id)
    WHERE @role_id IS NULL OR rp.RoleID = @role_id
    ORDER BY p.Name;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_scopes
    @include_inactive bit = 0
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        s.ScopeID AS scope_id,
        s.ScopeType,
        s.Name,
        s.InstitutionID,
        s.LabID,
        s.OwnerUserID,
        s.Active
    FROM RBAC.Scopes s
    WHERE @include_inactive = 1 OR s.Active = 1
    ORDER BY s.Name;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_scope
    @scope_id int
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        s.ScopeID AS scope_id,
        s.ScopeType,
        s.Name,
        s.InstitutionID,
        s.LabID,
        s.OwnerUserID,
        s.Active
    FROM RBAC.Scopes s
    WHERE s.ScopeID = @scope_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_grant_user_role
    @user_id int,
    @role_id int,
    @grant_type varchar(16),
    @scope_id int = NULL,
    @approval_id bigint = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @bypass bit;
    SELECT @bypass = BypassScope FROM RBAC.Roles WHERE ID = @role_id;
    IF @bypass IS NULL
        THROW 50010, N'role_id not found.', 1;

    SET @grant_type = UPPER(LTRIM(RTRIM(@grant_type)));
    IF @grant_type NOT IN (N'SCOPED', N'GLOBAL')
        THROW 50001, N'grant_type must be SCOPED or GLOBAL.', 1;

    IF @bypass = 1 AND @grant_type <> N'GLOBAL'
        THROW 50150, N'BypassScope roles require GLOBAL grant type.', 1;

    IF @bypass = 1
    BEGIN
        IF @approval_id IS NULL
            THROW 50151, N'BypassScope GLOBAL grants require approval_id.', 1;
        IF NOT EXISTS (
            SELECT 1 FROM RBAC.BypassScopeApprovals a
            WHERE a.ApprovalID = @approval_id
              AND a.UserID = @user_id
              AND a.RoleID = @role_id
              AND a.Status = N'APPROVED'
        )
            THROW 50152, N'approval_id is not an APPROVED BypassScope approval for this user and role.', 1;
    END

    IF @grant_type = N'GLOBAL' SET @scope_id = NULL;
    IF @grant_type = N'SCOPED' AND (@scope_id IS NULL OR @scope_id <= 0)
        THROW 50001, N'scope_id is required for SCOPED grants.', 1;

    IF EXISTS (
        SELECT 1 FROM RBAC.UserRoleGrants
        WHERE UserID = @user_id AND RoleID = @role_id AND GrantType = @grant_type
          AND ((ScopeID IS NULL AND @scope_id IS NULL) OR ScopeID = @scope_id)
          AND Active = 1
    )
    BEGIN
        SELECT CAST(0 AS bit) AS inserted;
        RETURN;
    END

    INSERT INTO RBAC.UserRoleGrants (UserID, RoleID, GrantType, ScopeID, Active, ApprovalID)
    VALUES (@user_id, @role_id, @grant_type, @scope_id, 1, @approval_id);

    SELECT CAST(1 AS bit) AS inserted, SCOPE_IDENTITY() AS grant_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_user_role_grants
    @user_id int
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        g.ID AS grant_id,
        g.UserID AS user_id,
        g.RoleID AS role_id,
        r.Name AS role_name,
        g.GrantType,
        g.ScopeID AS scope_id,
        s.Name AS scope_name,
        g.Active,
        g.GrantedAtUtc,
        g.RevokedAtUtc,
        g.ApprovalID
    FROM RBAC.UserRoleGrants g
    INNER JOIN RBAC.Roles r ON r.ID = g.RoleID
    LEFT JOIN RBAC.Scopes s ON s.ScopeID = g.ScopeID
    WHERE g.UserID = @user_id
    ORDER BY g.Active DESC, r.Name;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_revoke_user_role
    @user_id int,
    @role_id int,
    @grant_type varchar(16),
    @scope_id int = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET @grant_type = UPPER(LTRIM(RTRIM(@grant_type)));

    UPDATE RBAC.UserRoleGrants
    SET Active = 0, RevokedAtUtc = SYSUTCDATETIME()
    WHERE UserID = @user_id AND RoleID = @role_id AND GrantType = @grant_type
      AND Active = 1
      AND ((ScopeID IS NULL AND @scope_id IS NULL) OR ScopeID = @scope_id);

    SELECT @@ROWCOUNT AS rows_updated;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_user_groups
AS
BEGIN
    SET NOCOUNT ON;
    SELECT g.ID AS group_id, g.Name
    FROM RBAC.Groups g
    ORDER BY g.Name;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_set_user_group_members
    @group_id int,
    @user_ids nvarchar(max)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    BEGIN TRAN;

    DELETE FROM RBAC.Group_Users WHERE GroupID = @group_id;

    INSERT INTO RBAC.Group_Users (GroupID, UserID)
    SELECT DISTINCT @group_id, CAST(j.[value] AS int)
    FROM OPENJSON(@user_ids) j
    WHERE TRY_CAST(j.[value] AS int) IS NOT NULL;

    COMMIT;
    SELECT @@ROWCOUNT AS members;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_set_user_group_roles
    @group_id int,
    @role_ids nvarchar(max)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    BEGIN TRAN;

    DELETE FROM RBAC.Group_Roles WHERE GroupID = @group_id;

    INSERT INTO RBAC.Group_Roles (GroupID, RoleID)
    SELECT DISTINCT @group_id, CAST(j.[value] AS int)
    FROM OPENJSON(@role_ids) j
    WHERE TRY_CAST(j.[value] AS int) IS NOT NULL;

    COMMIT;
    SELECT @@ROWCOUNT AS roles;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_user_sessions
    @user_id int
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        s.ID AS session_id,
        s.Name,
        s.UserID,
        s.Created,
        s.ActiveScopeID,
        s.AuthProviderID,
        s.AuthenticatedAtUtc
    FROM RBAC.Sessions s
    WHERE s.UserID = @user_id
    ORDER BY s.Created DESC;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_role_nav_nodes
    @role_id int,
    @scope_id int = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT rn.ScopeId, rn.RoleId, rn.NodeId, n.Caption, n.ParentID
    FROM portal.Role2Node rn
    INNER JOIN portal.NavTree n ON n.ID = rn.NodeId
    WHERE rn.RoleId = @role_id
      AND (@scope_id IS NULL OR rn.ScopeId = @scope_id)
    ORDER BY n.Caption;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_grant_role_nav_node
    @role_id int,
    @node_id int,
    @scope_id int
AS
BEGIN
    SET NOCOUNT ON;
    IF NOT EXISTS (
        SELECT 1 FROM portal.Role2Node
        WHERE RoleId = @role_id AND NodeId = @node_id AND ScopeId = @scope_id
    )
        INSERT INTO portal.Role2Node (RoleId, NodeId, ScopeId)
        VALUES (@role_id, @node_id, @scope_id);
    SELECT CAST(1 AS bit) AS ok;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_deny_role_nav_node
    @role_id int,
    @node_id int,
    @scope_id int
AS
BEGIN
    SET NOCOUNT ON;
    DELETE FROM portal.Role2Node
    WHERE RoleId = @role_id AND NodeId = @node_id AND ScopeId = @scope_id;
    SELECT @@ROWCOUNT AS rows_deleted;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_create_invitation_batch
    @scope_id int,
    @created_by_user_id int
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO Onboarding.InvitationBatches (ScopeID, CreatedByUserID, Status)
    VALUES (@scope_id, @created_by_user_id, N'OPEN');
    SELECT SCOPE_IDENTITY() AS batch_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_create_invitation
    @scope_id int,
    @email varchar(255),
    @expected_provider_id int,
    @expires_at_utc datetime2(3),
    @batch_id bigint = NULL,
    @default_role_id int = NULL,
    @grant_type varchar(16) = N'SCOPED',
    @expected_domain varchar(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET @grant_type = UPPER(ISNULL(@grant_type, N'SCOPED'));
    INSERT INTO Onboarding.Invitations (
        BatchID, ScopeID, Email, ExpectedProviderID, ExpectedDomain,
        DefaultRoleID, GrantType, ExpiresAtUtc, Status
    )
    VALUES (
        @batch_id, @scope_id, LOWER(LTRIM(RTRIM(@email))), @expected_provider_id,
        @expected_domain, @default_role_id, @grant_type, @expires_at_utc, N'PENDING'
    );
    SELECT SCOPE_IDENTITY() AS invitation_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_invitations
    @scope_id int = NULL,
    @status varchar(16) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        i.InvitationID,
        i.BatchID,
        i.ScopeID,
        i.Email,
        i.DefaultRoleID,
        i.GrantType,
        i.Status,
        i.ExpiresAtUtc,
        i.AcceptedByUserID,
        i.AcceptedAtUtc,
        i.CreatedAtUtc
    FROM Onboarding.Invitations i
    WHERE (@scope_id IS NULL OR i.ScopeID = @scope_id)
      AND (@status IS NULL OR i.Status = @status)
    ORDER BY i.CreatedAtUtc DESC;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_revoke_invitation
    @invitation_id bigint
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE Onboarding.Invitations
    SET Status = N'REVOKED'
    WHERE InvitationID = @invitation_id AND Status = N'PENDING';
    SELECT @@ROWCOUNT AS rows_updated;
END
GO
