-- Auto-extracted by scripts/extract_legacy_schema.py from MethylPipeline.sql
-- Idempotent incremental deploy (IF OBJECT_ID / CREATE OR ALTER).
-- Do not edit by hand unless also updating the twin under sql_pg/.

IF SCHEMA_ID(N'Onboarding') IS NULL EXEC(N'CREATE SCHEMA [Onboarding]');
GO

IF OBJECT_ID(N'Onboarding.InvitationBatches', N'U') IS NULL
BEGIN
CREATE TABLE Onboarding.InvitationBatches (
  BatchID bigint IDENTITY,
  ScopeID int NOT NULL,
  CreatedByUserID int NOT NULL,
  Status varchar(16) NOT NULL CONSTRAINT DF_InvitationBatches_Status DEFAULT ('OPEN'),
  CreatedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_InvitationBatches_CreatedAtUtc DEFAULT (sysutcdatetime()),
  CONSTRAINT PK_Onboarding_InvitationBatches PRIMARY KEY CLUSTERED (BatchID),
  CONSTRAINT CK_InvitationBatches_Status CHECK ([Status]='CANCELLED' OR [Status]='CLOSED' OR [Status]='OPEN')
)
END
GO

IF OBJECT_ID(N'FK_InvitationBatches_CreatedByUserID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_InvitationBatches_CreatedByUserID'
)
BEGIN
  ALTER TABLE Onboarding.InvitationBatches
  ADD CONSTRAINT FK_InvitationBatches_CreatedByUserID FOREIGN KEY (CreatedByUserID) REFERENCES RBAC.Users (ID)
END
GO

IF OBJECT_ID(N'FK_InvitationBatches_ScopeID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_InvitationBatches_ScopeID'
)
BEGIN
  ALTER TABLE Onboarding.InvitationBatches
  ADD CONSTRAINT FK_InvitationBatches_ScopeID FOREIGN KEY (ScopeID) REFERENCES RBAC.Scopes (ScopeID)
END
GO

IF OBJECT_ID(N'Onboarding.Invitations', N'U') IS NULL
BEGIN
CREATE TABLE Onboarding.Invitations (
  InvitationID bigint IDENTITY,
  BatchID bigint NULL,
  ScopeID int NOT NULL,
  Email varchar(255) NOT NULL,
  ExpectedProviderID int NOT NULL,
  ExpectedDomain varchar(255) NULL,
  DefaultRoleID int NULL,
  GrantType varchar(16) NOT NULL CONSTRAINT DF_Invitations_GrantType DEFAULT ('SCOPED'),
  ExpiresAtUtc datetime2(3) NOT NULL,
  Status varchar(16) NOT NULL CONSTRAINT DF_Invitations_Status DEFAULT ('PENDING'),
  AcceptedByUserID int NULL,
  AcceptedAtUtc datetime2(3) NULL,
  CreatedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_Invitations_CreatedAtUtc DEFAULT (sysutcdatetime()),
  CONSTRAINT PK_Onboarding_Invitations PRIMARY KEY CLUSTERED (InvitationID),
  CONSTRAINT CK_Invitations_GrantType CHECK ([GrantType]='SCOPED' OR [GrantType]='GLOBAL'),
  CONSTRAINT CK_Invitations_Status CHECK ([Status]='REVOKED' OR [Status]='CANCELLED' OR [Status]='EXPIRED' OR [Status]='ACCEPTED' OR [Status]='PENDING')
)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Invitations_Email' AND object_id IS NOT NULL)
BEGIN
  CREATE INDEX IX_Invitations_Email
  ON Onboarding.Invitations (Email, Status)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_Invitations_Scope_Status' AND object_id IS NOT NULL)
BEGIN
  CREATE INDEX IX_Invitations_Scope_Status
  ON Onboarding.Invitations (ScopeID, Status, ExpiresAtUtc)
END
GO

IF OBJECT_ID(N'FK_Invitations_AcceptedByUserID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_Invitations_AcceptedByUserID'
)
BEGIN
  ALTER TABLE Onboarding.Invitations
  ADD CONSTRAINT FK_Invitations_AcceptedByUserID FOREIGN KEY (AcceptedByUserID) REFERENCES RBAC.Users (ID)
END
GO

IF OBJECT_ID(N'FK_Invitations_BatchID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_Invitations_BatchID'
)
BEGIN
  ALTER TABLE Onboarding.Invitations
  ADD CONSTRAINT FK_Invitations_BatchID FOREIGN KEY (BatchID) REFERENCES Onboarding.InvitationBatches (BatchID)
END
GO

IF OBJECT_ID(N'FK_Invitations_DefaultRoleID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_Invitations_DefaultRoleID'
)
BEGIN
  ALTER TABLE Onboarding.Invitations
  ADD CONSTRAINT FK_Invitations_DefaultRoleID FOREIGN KEY (DefaultRoleID) REFERENCES RBAC.Roles (ID)
END
GO

IF OBJECT_ID(N'FK_Invitations_ExpectedProviderID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_Invitations_ExpectedProviderID'
)
BEGIN
  ALTER TABLE Onboarding.Invitations
  ADD CONSTRAINT FK_Invitations_ExpectedProviderID FOREIGN KEY (ExpectedProviderID) REFERENCES RBAC.IdentityProviders (ProviderID)
END
GO

IF OBJECT_ID(N'FK_Invitations_ScopeID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_Invitations_ScopeID'
)
BEGIN
  ALTER TABLE Onboarding.Invitations
  ADD CONSTRAINT FK_Invitations_ScopeID FOREIGN KEY (ScopeID) REFERENCES RBAC.Scopes (ScopeID)
END
GO

IF OBJECT_ID(N'Onboarding.AuditLog', N'U') IS NULL
BEGIN
CREATE TABLE Onboarding.AuditLog (
  AuditID bigint IDENTITY,
  ScopeID int NULL,
  InvitationID bigint NULL,
  ActorUserID int NULL,
  EventType varchar(64) NOT NULL,
  EventDataJson json NULL,
  CreatedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_OnboardingAudit_CreatedAtUtc DEFAULT (sysutcdatetime()),
  CONSTRAINT PK_Onboarding_AuditLog PRIMARY KEY CLUSTERED (AuditID)
)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_OnboardingAudit_Scope_Time' AND object_id IS NOT NULL)
BEGIN
  CREATE INDEX IX_OnboardingAudit_Scope_Time
  ON Onboarding.AuditLog (ScopeID, CreatedAtUtc)
END
GO

IF OBJECT_ID(N'FK_OnboardingAudit_ActorUserID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_OnboardingAudit_ActorUserID'
)
BEGIN
  ALTER TABLE Onboarding.AuditLog
  ADD CONSTRAINT FK_OnboardingAudit_ActorUserID FOREIGN KEY (ActorUserID) REFERENCES RBAC.Users (ID)
END
GO

IF OBJECT_ID(N'FK_OnboardingAudit_InvitationID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_OnboardingAudit_InvitationID'
)
BEGIN
  ALTER TABLE Onboarding.AuditLog
  ADD CONSTRAINT FK_OnboardingAudit_InvitationID FOREIGN KEY (InvitationID) REFERENCES Onboarding.Invitations (InvitationID)
END
GO

IF OBJECT_ID(N'FK_OnboardingAudit_ScopeID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_OnboardingAudit_ScopeID'
)
BEGIN
  ALTER TABLE Onboarding.AuditLog
  ADD CONSTRAINT FK_OnboardingAudit_ScopeID FOREIGN KEY (ScopeID) REFERENCES RBAC.Scopes (ScopeID)
END
GO

IF OBJECT_ID(N'Onboarding.ApprovalQueue', N'U') IS NULL
BEGIN
CREATE TABLE Onboarding.ApprovalQueue (
  ApprovalID bigint IDENTITY,
  InvitationID bigint NOT NULL,
  RequestedRoleID int NOT NULL,
  RequestedGrantType varchar(16) NOT NULL,
  Status varchar(16) NOT NULL CONSTRAINT DF_ApprovalQueue_Status DEFAULT ('PENDING'),
  ReviewedByUserID int NULL,
  ReviewedAtUtc datetime2(3) NULL,
  ReviewComment varchar(500) NULL,
  CreatedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_ApprovalQueue_CreatedAtUtc DEFAULT (sysutcdatetime()),
  CONSTRAINT PK_Onboarding_ApprovalQueue PRIMARY KEY CLUSTERED (ApprovalID),
  CONSTRAINT CK_ApprovalQueue_GrantType CHECK ([RequestedGrantType]='SCOPED' OR [RequestedGrantType]='GLOBAL'),
  CONSTRAINT CK_ApprovalQueue_Status CHECK ([Status]='CANCELLED' OR [Status]='REJECTED' OR [Status]='APPROVED' OR [Status]='PENDING')
)
END
GO

IF OBJECT_ID(N'FK_ApprovalQueue_InvitationID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_ApprovalQueue_InvitationID'
)
BEGIN
  ALTER TABLE Onboarding.ApprovalQueue
  ADD CONSTRAINT FK_ApprovalQueue_InvitationID FOREIGN KEY (InvitationID) REFERENCES Onboarding.Invitations (InvitationID)
END
GO

IF OBJECT_ID(N'FK_ApprovalQueue_RequestedRoleID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_ApprovalQueue_RequestedRoleID'
)
BEGIN
  ALTER TABLE Onboarding.ApprovalQueue
  ADD CONSTRAINT FK_ApprovalQueue_RequestedRoleID FOREIGN KEY (RequestedRoleID) REFERENCES RBAC.Roles (ID)
END
GO

IF OBJECT_ID(N'FK_ApprovalQueue_ReviewedByUserID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_ApprovalQueue_ReviewedByUserID'
)
BEGIN
  ALTER TABLE Onboarding.ApprovalQueue
  ADD CONSTRAINT FK_ApprovalQueue_ReviewedByUserID FOREIGN KEY (ReviewedByUserID) REFERENCES RBAC.Users (ID)
END
GO

