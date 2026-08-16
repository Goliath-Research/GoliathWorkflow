-- Auto-extracted by scripts/extract_legacy_schema.py from MethylPipeline.sql
-- Idempotent incremental deploy (IF OBJECT_ID / CREATE OR ALTER).
-- Do not edit by hand unless also updating the twin under sql_pg/.

IF SCHEMA_ID(N'RBAC') IS NULL EXEC(N'CREATE SCHEMA [RBAC]');
GO

IF OBJECT_ID(N'RBAC.Users', N'U') IS NULL
BEGIN
CREATE TABLE RBAC.Users (
  ID int IDENTITY,
  FullName varchar(200) NOT NULL,
  email varchar(50) NOT NULL,
  Active int NOT NULL DEFAULT (1),
  username AS (left([email],charindex('@',[email])-(1))),
  PRIMARY KEY CLUSTERED (ID)
)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UQ_RBAC_Users_Email' AND object_id IS NOT NULL)
BEGIN
  CREATE UNIQUE INDEX UQ_RBAC_Users_Email
  ON RBAC.Users (email)
END
GO

IF OBJECT_ID(N'RBAC.Roles', N'U') IS NULL
BEGIN
CREATE TABLE RBAC.Roles (
  ID int IDENTITY,
  Name varchar(200) NOT NULL,
  BypassScope bit NOT NULL CONSTRAINT DF_Roles_BypassScope DEFAULT (0),
  PRIMARY KEY CLUSTERED (ID),
  UNIQUE (Name)
)
END
GO

IF OBJECT_ID(N'RBAC.BypassScopeApprovals', N'U') IS NULL
BEGIN
CREATE TABLE RBAC.BypassScopeApprovals (
  ApprovalID bigint IDENTITY,
  UserID int NOT NULL,
  RoleID int NOT NULL,
  RequestedByUserID int NOT NULL,
  ApprovedByUserID int NULL,
  Status varchar(16) NOT NULL CONSTRAINT DF_BypassScopeApprovals_Status DEFAULT ('PENDING'),
  Reason varchar(500) NOT NULL,
  TicketRef varchar(128) NULL,
  CreatedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_BypassScopeApprovals_CreatedAtUtc DEFAULT (sysutcdatetime()),
  ApprovedAtUtc datetime2(3) NULL,
  ExpiresAtUtc datetime2(3) NULL,
  CONSTRAINT PK_RBAC_BypassScopeApprovals PRIMARY KEY CLUSTERED (ApprovalID),
  CONSTRAINT CK_BypassScopeApprovals_Status CHECK ([Status]='REVOKED' OR [Status]='REJECTED' OR [Status]='APPROVED' OR [Status]='PENDING')
)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_BypassScopeApprovals_UserRoleStatus' AND object_id IS NOT NULL)
BEGIN
  CREATE INDEX IX_BypassScopeApprovals_UserRoleStatus
  ON RBAC.BypassScopeApprovals (UserID, RoleID, Status, ExpiresAtUtc)
END
GO

IF OBJECT_ID(N'FK_BypassScopeApprovals_ApprovedByUserID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_BypassScopeApprovals_ApprovedByUserID'
)
BEGIN
  ALTER TABLE RBAC.BypassScopeApprovals
  ADD CONSTRAINT FK_BypassScopeApprovals_ApprovedByUserID FOREIGN KEY (ApprovedByUserID) REFERENCES RBAC.Users (ID)
END
GO

IF OBJECT_ID(N'FK_BypassScopeApprovals_RequestedByUserID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_BypassScopeApprovals_RequestedByUserID'
)
BEGIN
  ALTER TABLE RBAC.BypassScopeApprovals
  ADD CONSTRAINT FK_BypassScopeApprovals_RequestedByUserID FOREIGN KEY (RequestedByUserID) REFERENCES RBAC.Users (ID)
END
GO

IF OBJECT_ID(N'FK_BypassScopeApprovals_RoleID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_BypassScopeApprovals_RoleID'
)
BEGIN
  ALTER TABLE RBAC.BypassScopeApprovals
  ADD CONSTRAINT FK_BypassScopeApprovals_RoleID FOREIGN KEY (RoleID) REFERENCES RBAC.Roles (ID)
END
GO

IF OBJECT_ID(N'FK_BypassScopeApprovals_UserID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_BypassScopeApprovals_UserID'
)
BEGIN
  ALTER TABLE RBAC.BypassScopeApprovals
  ADD CONSTRAINT FK_BypassScopeApprovals_UserID FOREIGN KEY (UserID) REFERENCES RBAC.Users (ID)
END
GO

IF OBJECT_ID(N'RBAC.Permissions', N'U') IS NULL
BEGIN
CREATE TABLE RBAC.Permissions (
  ID int IDENTITY,
  Name varchar(200) NOT NULL,
  ObjID int NOT NULL,
  OperationID int NOT NULL,
  PRIMARY KEY CLUSTERED (ID),
  CONSTRAINT UQ_Permissions_Object_Operation UNIQUE (ObjID, OperationID)
)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Permissions_Object' AND object_id IS NOT NULL)
BEGIN
  CREATE INDEX IX_Permissions_Object
  ON RBAC.Permissions (ObjID)
END
GO

IF OBJECT_ID(N'FK_Permissions_Operations', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_Permissions_Operations'
)
BEGIN
  ALTER TABLE RBAC.Permissions
  ADD CONSTRAINT FK_Permissions_Operations FOREIGN KEY (OperationID) REFERENCES Meta.Operations (ID)
END
GO

IF OBJECT_ID(N'RBAC.Role_Permissions', N'U') IS NULL
BEGIN
CREATE TABLE RBAC.Role_Permissions (
  RoleID int NOT NULL,
  PermissionID int NOT NULL,
  CONSTRAINT PK_Role_Permissions PRIMARY KEY CLUSTERED (RoleID, PermissionID)
)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_RolePerm_Perm' AND object_id IS NOT NULL)
BEGIN
  CREATE INDEX IX_RolePerm_Perm
  ON RBAC.Role_Permissions (PermissionID)
END
GO

IF OBJECT_ID(N'FK_Role_Permissions_Permissions', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_Role_Permissions_Permissions'
)
BEGIN
  ALTER TABLE RBAC.Role_Permissions
  ADD CONSTRAINT FK_Role_Permissions_Permissions FOREIGN KEY (PermissionID) REFERENCES RBAC.Permissions (ID) ON DELETE CASCADE ON UPDATE CASCADE
END
GO

IF OBJECT_ID(N'FK_Role_Permissions_Roles', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_Role_Permissions_Roles'
)
BEGIN
  ALTER TABLE RBAC.Role_Permissions
  ADD CONSTRAINT FK_Role_Permissions_Roles FOREIGN KEY (RoleID) REFERENCES RBAC.Roles (ID) ON DELETE CASCADE ON UPDATE CASCADE
END
GO

IF OBJECT_ID(N'RBAC.IdentityProviders', N'U') IS NULL
BEGIN
CREATE TABLE RBAC.IdentityProviders (
  ProviderID int IDENTITY,
  Name varchar(128) NOT NULL,
  ProviderType varchar(32) NOT NULL,
  Issuer nvarchar(512) NOT NULL,
  AllowedDomainPattern varchar(255) NULL,
  Active bit NOT NULL CONSTRAINT DF_RBAC_IdentityProviders_Active DEFAULT (1),
  CreatedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_RBAC_IdentityProviders_CreatedAtUtc DEFAULT (sysutcdatetime()),
  CONSTRAINT PK_RBAC_IdentityProviders PRIMARY KEY CLUSTERED (ProviderID),
  CONSTRAINT UQ_RBAC_IdentityProviders_Issuer UNIQUE (Issuer),
  CONSTRAINT CK_RBAC_IdentityProviders_ProviderType CHECK ([ProviderType]='OIDC_CUSTOM' OR [ProviderType]='ENTRA' OR [ProviderType]='GOOGLE')
)
END
GO

IF OBJECT_ID(N'RBAC.ExternalIdentities', N'U') IS NULL
BEGIN
CREATE TABLE RBAC.ExternalIdentities (
  ID int IDENTITY,
  UserID int NOT NULL,
  ProviderID int NOT NULL,
  Subject nvarchar(512) NOT NULL,
  EmailSnapshot varchar(255) NULL,
  Active bit NOT NULL CONSTRAINT DF_RBAC_ExternalIdentities_Active DEFAULT (1),
  CreatedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_RBAC_ExternalIdentities_CreatedAtUtc DEFAULT (sysutcdatetime()),
  LastLoginAtUtc datetime2(3) NULL,
  CONSTRAINT PK_RBAC_ExternalIdentities PRIMARY KEY CLUSTERED (ID),
  CONSTRAINT UQ_RBAC_ExternalIdentities_Provider_Subject UNIQUE (ProviderID, Subject)
)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_RBAC_ExternalIdentities_UserID' AND object_id IS NOT NULL)
BEGIN
  CREATE INDEX IX_RBAC_ExternalIdentities_UserID
  ON RBAC.ExternalIdentities (UserID, Active)
END
GO

IF OBJECT_ID(N'FK_RBAC_ExternalIdentities_ProviderID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_RBAC_ExternalIdentities_ProviderID'
)
BEGIN
  ALTER TABLE RBAC.ExternalIdentities
  ADD CONSTRAINT FK_RBAC_ExternalIdentities_ProviderID FOREIGN KEY (ProviderID) REFERENCES RBAC.IdentityProviders (ProviderID)
END
GO

IF OBJECT_ID(N'FK_RBAC_ExternalIdentities_UserID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_RBAC_ExternalIdentities_UserID'
)
BEGIN
  ALTER TABLE RBAC.ExternalIdentities
  ADD CONSTRAINT FK_RBAC_ExternalIdentities_UserID FOREIGN KEY (UserID) REFERENCES RBAC.Users (ID)
END
GO

IF OBJECT_ID(N'RBAC.Groups', N'U') IS NULL
BEGIN
CREATE TABLE RBAC.Groups (
  ID int IDENTITY,
  Name varchar(200) NOT NULL,
  PRIMARY KEY CLUSTERED (ID),
  UNIQUE (Name)
)
END
GO

IF OBJECT_ID(N'RBAC.Group_Users', N'U') IS NULL
BEGIN
CREATE TABLE RBAC.Group_Users (
  GroupID int NOT NULL,
  UserID int NOT NULL,
  AddedAt datetime2(3) NOT NULL DEFAULT (sysutcdatetime()),
  CONSTRAINT PK_GroupMembers PRIMARY KEY CLUSTERED (GroupID, UserID)
)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_GroupMembers_User' AND object_id IS NOT NULL)
BEGIN
  CREATE INDEX IX_GroupMembers_User
  ON RBAC.Group_Users (UserID)
END
GO

IF OBJECT_ID(N'FK_GroupMembers_Groups', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_GroupMembers_Groups'
)
BEGIN
  ALTER TABLE RBAC.Group_Users
  ADD CONSTRAINT FK_GroupMembers_Groups FOREIGN KEY (GroupID) REFERENCES RBAC.Groups (ID) ON DELETE CASCADE ON UPDATE CASCADE
END
GO

IF OBJECT_ID(N'FK_GroupMembers_Users', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_GroupMembers_Users'
)
BEGIN
  ALTER TABLE RBAC.Group_Users
  ADD CONSTRAINT FK_GroupMembers_Users FOREIGN KEY (UserID) REFERENCES RBAC.Users (ID) ON DELETE CASCADE ON UPDATE CASCADE
END
GO

IF OBJECT_ID(N'RBAC.Group_Roles', N'U') IS NULL
BEGIN
CREATE TABLE RBAC.Group_Roles (
  GroupID int NOT NULL,
  RoleID int NOT NULL,
  CONSTRAINT PK_Group_Roles PRIMARY KEY CLUSTERED (GroupID, RoleID)
)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Group_Roles_Role' AND object_id IS NOT NULL)
BEGIN
  CREATE INDEX IX_Group_Roles_Role
  ON RBAC.Group_Roles (RoleID)
END
GO

IF OBJECT_ID(N'FK_Group_Roles_Groups', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_Group_Roles_Groups'
)
BEGIN
  ALTER TABLE RBAC.Group_Roles
  ADD CONSTRAINT FK_Group_Roles_Groups FOREIGN KEY (GroupID) REFERENCES RBAC.Groups (ID) ON DELETE CASCADE ON UPDATE CASCADE
END
GO

IF OBJECT_ID(N'FK_Group_Roles_Roles', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_Group_Roles_Roles'
)
BEGIN
  ALTER TABLE RBAC.Group_Roles
  ADD CONSTRAINT FK_Group_Roles_Roles FOREIGN KEY (RoleID) REFERENCES RBAC.Roles (ID) ON DELETE CASCADE ON UPDATE CASCADE
END
GO

IF OBJECT_ID(N'RBAC.Scopes', N'U') IS NULL
BEGIN
CREATE TABLE RBAC.Scopes (
  ScopeID int IDENTITY,
  ScopeType varchar(32) NOT NULL,
  Name varchar(200) NOT NULL,
  InstitutionID int NULL,
  LabID int NULL,
  OwnerUserID int NULL,
  Active bit NOT NULL CONSTRAINT DF_RBAC_Scopes_Active DEFAULT (1),
  CreatedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_RBAC_Scopes_CreatedAtUtc DEFAULT (sysutcdatetime()),
  CONSTRAINT PK_RBAC_Scopes PRIMARY KEY CLUSTERED (ScopeID),
  CONSTRAINT CK_RBAC_Scopes_EntityByType CHECK ([ScopeType]='INSTITUTION' AND [InstitutionID] IS NOT NULL AND [LabID] IS NULL AND [OwnerUserID] IS NULL OR [ScopeType]='LAB' AND [LabID] IS NOT NULL AND [InstitutionID] IS NULL AND [OwnerUserID] IS NULL OR [ScopeType]='INDEPENDENT_USER' AND [OwnerUserID] IS NOT NULL AND [InstitutionID] IS NULL AND [LabID] IS NULL),
  CONSTRAINT CK_RBAC_Scopes_ScopeType CHECK ([ScopeType]='INDEPENDENT_USER' OR [ScopeType]='LAB' OR [ScopeType]='INSTITUTION')
)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_RBAC_Scopes_InstitutionID' AND object_id IS NOT NULL)
BEGIN
  CREATE INDEX IX_RBAC_Scopes_InstitutionID
  ON RBAC.Scopes (InstitutionID)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_RBAC_Scopes_LabID' AND object_id IS NOT NULL)
BEGIN
  CREATE INDEX IX_RBAC_Scopes_LabID
  ON RBAC.Scopes (LabID)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_RBAC_Scopes_OwnerUserID' AND object_id IS NOT NULL)
BEGIN
  CREATE INDEX IX_RBAC_Scopes_OwnerUserID
  ON RBAC.Scopes (OwnerUserID)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_RBAC_Scopes_IndependentUser' AND object_id IS NOT NULL)
BEGIN
  CREATE UNIQUE INDEX UX_RBAC_Scopes_IndependentUser
  ON RBAC.Scopes (OwnerUserID)
  WHERE ([ScopeType]='INDEPENDENT_USER')
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_RBAC_Scopes_Institution' AND object_id IS NOT NULL)
BEGIN
  CREATE UNIQUE INDEX UX_RBAC_Scopes_Institution
  ON RBAC.Scopes (InstitutionID)
  WHERE ([ScopeType]='INSTITUTION')
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_RBAC_Scopes_Lab' AND object_id IS NOT NULL)
BEGIN
  CREATE UNIQUE INDEX UX_RBAC_Scopes_Lab
  ON RBAC.Scopes (LabID)
  WHERE ([ScopeType]='LAB')
END
GO

IF OBJECT_ID(N'FK_RBAC_Scopes_InstitutionID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_RBAC_Scopes_InstitutionID'
)
BEGIN
  ALTER TABLE RBAC.Scopes
  ADD CONSTRAINT FK_RBAC_Scopes_InstitutionID FOREIGN KEY (InstitutionID) REFERENCES portal.Institutions (ID)
END
GO

IF OBJECT_ID(N'FK_RBAC_Scopes_LabID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_RBAC_Scopes_LabID'
)
BEGIN
  ALTER TABLE RBAC.Scopes
  ADD CONSTRAINT FK_RBAC_Scopes_LabID FOREIGN KEY (LabID) REFERENCES portal.Labs (ID)
END
GO

IF OBJECT_ID(N'FK_RBAC_Scopes_OwnerUserID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_RBAC_Scopes_OwnerUserID'
)
BEGIN
  ALTER TABLE RBAC.Scopes
  ADD CONSTRAINT FK_RBAC_Scopes_OwnerUserID FOREIGN KEY (OwnerUserID) REFERENCES RBAC.Users (ID)
END
GO

IF OBJECT_ID(N'RBAC.UserRoleGrants', N'U') IS NULL
BEGIN
CREATE TABLE RBAC.UserRoleGrants (
  ID int IDENTITY,
  UserID int NOT NULL,
  RoleID int NOT NULL,
  GrantType varchar(16) NOT NULL,
  ScopeID int NULL,
  Active bit NOT NULL CONSTRAINT DF_UserRoleGrants_Active DEFAULT (1),
  GrantedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_UserRoleGrants_GrantedAtUtc DEFAULT (sysutcdatetime()),
  RevokedAtUtc datetime2(3) NULL,
  ApprovalID bigint NULL,
  CONSTRAINT PK_RBAC_UserRoleGrants PRIMARY KEY CLUSTERED (ID),
  CONSTRAINT CK_UserRoleGrants_GrantType CHECK ([GrantType]='SCOPED' OR [GrantType]='GLOBAL'),
  CONSTRAINT CK_UserRoleGrants_ScopeByGrantType CHECK ([GrantType]='GLOBAL' AND [ScopeID] IS NULL OR [GrantType]='SCOPED' AND [ScopeID] IS NOT NULL)
)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_UserRoleGrants_Scope_Active' AND object_id IS NOT NULL)
BEGIN
  CREATE INDEX IX_UserRoleGrants_Scope_Active
  ON RBAC.UserRoleGrants (ScopeID, Active)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_UserRoleGrants_User_Active' AND object_id IS NOT NULL)
BEGIN
  CREATE INDEX IX_UserRoleGrants_User_Active
  ON RBAC.UserRoleGrants (UserID, Active)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_UserRoleGrants_ActiveGrant' AND object_id IS NOT NULL)
BEGIN
  CREATE UNIQUE INDEX UX_UserRoleGrants_ActiveGrant
  ON RBAC.UserRoleGrants (UserID, RoleID, GrantType, ScopeID)
  WHERE ([Active]=(1))
END
GO

IF OBJECT_ID(N'FK_UserRoleGrants_ApprovalID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_UserRoleGrants_ApprovalID'
)
BEGIN
  ALTER TABLE RBAC.UserRoleGrants
  ADD CONSTRAINT FK_UserRoleGrants_ApprovalID FOREIGN KEY (ApprovalID) REFERENCES RBAC.BypassScopeApprovals (ApprovalID)
END
GO

IF OBJECT_ID(N'FK_UserRoleGrants_RoleID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_UserRoleGrants_RoleID'
)
BEGIN
  ALTER TABLE RBAC.UserRoleGrants
  ADD CONSTRAINT FK_UserRoleGrants_RoleID FOREIGN KEY (RoleID) REFERENCES RBAC.Roles (ID)
END
GO

IF OBJECT_ID(N'FK_UserRoleGrants_ScopeID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_UserRoleGrants_ScopeID'
)
BEGIN
  ALTER TABLE RBAC.UserRoleGrants
  ADD CONSTRAINT FK_UserRoleGrants_ScopeID FOREIGN KEY (ScopeID) REFERENCES RBAC.Scopes (ScopeID)
END
GO

IF OBJECT_ID(N'FK_UserRoleGrants_UserID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_UserRoleGrants_UserID'
)
BEGIN
  ALTER TABLE RBAC.UserRoleGrants
  ADD CONSTRAINT FK_UserRoleGrants_UserID FOREIGN KEY (UserID) REFERENCES RBAC.Users (ID)
END
GO

IF OBJECT_ID(N'RBAC.Sessions', N'U') IS NULL
BEGIN
CREATE TABLE RBAC.Sessions (
  ID int IDENTITY,
  Name varchar(200) NULL,
  UserID int NOT NULL,
  Created datetime2(3) NOT NULL DEFAULT (sysutcdatetime()),
  ActiveScopeID int NULL,
  AuthProviderID int NULL,
  AuthSubjectSnapshot nvarchar(512) NULL,
  AuthenticatedAtUtc datetime2(3) NULL,
  PRIMARY KEY CLUSTERED (ID),
  CONSTRAINT CK_Sessions_AuthBinding CHECK ([AuthProviderID] IS NULL AND [AuthSubjectSnapshot] IS NULL OR [AuthProviderID] IS NOT NULL AND [AuthSubjectSnapshot] IS NOT NULL)
)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Sessions_ActiveScopeID' AND object_id IS NOT NULL)
BEGIN
  CREATE INDEX IX_Sessions_ActiveScopeID
  ON RBAC.Sessions (ActiveScopeID)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Sessions_AuthProviderID' AND object_id IS NOT NULL)
BEGIN
  CREATE INDEX IX_Sessions_AuthProviderID
  ON RBAC.Sessions (AuthProviderID)
END
GO

IF OBJECT_ID(N'FK_Sessions_ActiveScopeID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_Sessions_ActiveScopeID'
)
BEGIN
  ALTER TABLE RBAC.Sessions
  ADD CONSTRAINT FK_Sessions_ActiveScopeID FOREIGN KEY (ActiveScopeID) REFERENCES RBAC.Scopes (ScopeID)
END
GO

IF OBJECT_ID(N'FK_Sessions_AuthProviderID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_Sessions_AuthProviderID'
)
BEGIN
  ALTER TABLE RBAC.Sessions
  ADD CONSTRAINT FK_Sessions_AuthProviderID FOREIGN KEY (AuthProviderID) REFERENCES RBAC.IdentityProviders (ProviderID)
END
GO

IF OBJECT_ID(N'FK_Sessions_Users', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_Sessions_Users'
)
BEGIN
  ALTER TABLE RBAC.Sessions
  ADD CONSTRAINT FK_Sessions_Users FOREIGN KEY (UserID) REFERENCES RBAC.Users (ID) ON DELETE CASCADE ON UPDATE CASCADE
END
GO

IF OBJECT_ID(N'RBAC.Session_Roles', N'U') IS NULL
BEGIN
CREATE TABLE RBAC.Session_Roles (
  SessionID int NOT NULL,
  RoleID int NOT NULL,
  CONSTRAINT PK_Session_Roles PRIMARY KEY CLUSTERED (SessionID, RoleID)
)
END
GO

IF OBJECT_ID(N'FK_Session_Roles_Roles', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_Session_Roles_Roles'
)
BEGIN
  ALTER TABLE RBAC.Session_Roles
  ADD CONSTRAINT FK_Session_Roles_Roles FOREIGN KEY (RoleID) REFERENCES RBAC.Roles (ID) ON DELETE CASCADE ON UPDATE CASCADE
END
GO

IF OBJECT_ID(N'FK_Session_Roles_Sessions', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_Session_Roles_Sessions'
)
BEGIN
  ALTER TABLE RBAC.Session_Roles
  ADD CONSTRAINT FK_Session_Roles_Sessions FOREIGN KEY (SessionID) REFERENCES RBAC.Sessions (ID) ON DELETE CASCADE ON UPDATE CASCADE
END
GO

IF OBJECT_ID(N'RBAC.ScopeIdentityProviders', N'U') IS NULL
BEGIN
CREATE TABLE RBAC.ScopeIdentityProviders (
  ScopeID int NOT NULL,
  ProviderID int NOT NULL,
  Active bit NOT NULL CONSTRAINT DF_RBAC_ScopeIdentityProviders_Active DEFAULT (1),
  CreatedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_RBAC_ScopeIdentityProviders_CreatedAtUtc DEFAULT (sysutcdatetime()),
  CONSTRAINT PK_RBAC_ScopeIdentityProviders PRIMARY KEY CLUSTERED (ScopeID, ProviderID)
)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_RBAC_ScopeIdentityProviders_ProviderID' AND object_id IS NOT NULL)
BEGIN
  CREATE INDEX IX_RBAC_ScopeIdentityProviders_ProviderID
  ON RBAC.ScopeIdentityProviders (ProviderID, Active)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_RBAC_ScopeIdentityProviders_ActiveScope' AND object_id IS NOT NULL)
BEGIN
  CREATE UNIQUE INDEX UX_RBAC_ScopeIdentityProviders_ActiveScope
  ON RBAC.ScopeIdentityProviders (ScopeID)
  WHERE ([Active]=(1))
END
GO

IF OBJECT_ID(N'FK_RBAC_ScopeIdentityProviders_ProviderID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_RBAC_ScopeIdentityProviders_ProviderID'
)
BEGIN
  ALTER TABLE RBAC.ScopeIdentityProviders
  ADD CONSTRAINT FK_RBAC_ScopeIdentityProviders_ProviderID FOREIGN KEY (ProviderID) REFERENCES RBAC.IdentityProviders (ProviderID)
END
GO

IF OBJECT_ID(N'FK_RBAC_ScopeIdentityProviders_ScopeID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_RBAC_ScopeIdentityProviders_ScopeID'
)
BEGIN
  ALTER TABLE RBAC.ScopeIdentityProviders
  ADD CONSTRAINT FK_RBAC_ScopeIdentityProviders_ScopeID FOREIGN KEY (ScopeID) REFERENCES RBAC.Scopes (ScopeID)
END
GO

