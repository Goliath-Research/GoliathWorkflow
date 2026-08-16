-- Auto-extracted by scripts/extract_legacy_schema.py from MethylPipeline.sql
-- Idempotent incremental deploy (IF OBJECT_ID / CREATE OR ALTER).
-- Do not edit by hand unless also updating the twin under sql_pg/.

IF SCHEMA_ID(N'Contract') IS NULL EXEC(N'CREATE SCHEMA [Contract]');
GO

IF OBJECT_ID(N'Contract.Contracts', N'U') IS NULL
BEGIN
CREATE TABLE Contract.Contracts (
  ContractID int IDENTITY,
  CustomerID int NOT NULL,
  Name varchar(200) NOT NULL,
  Status varchar(24) NOT NULL CONSTRAINT DF_Contracts_Status DEFAULT ('DRAFT'),
  StartDateUtc datetime2(3) NOT NULL,
  EndDateUtc datetime2(3) NULL,
  PlanCode varchar(64) NULL,
  BillingCycle varchar(16) NULL,
  AutoRenew bit NOT NULL CONSTRAINT DF_Contracts_AutoRenew DEFAULT (0),
  TermsVersion varchar(32) NULL,
  CreatedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_Contracts_CreatedAtUtc DEFAULT (sysutcdatetime()),
  UpdatedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_Contracts_UpdatedAtUtc DEFAULT (sysutcdatetime()),
  CONSTRAINT PK_Contract_Contracts PRIMARY KEY CLUSTERED (ContractID),
  CONSTRAINT UQ_Contract_Contracts_CustomerRef UNIQUE (CustomerID),
  CONSTRAINT CK_Contracts_DateRange CHECK ([EndDateUtc] IS NULL OR [EndDateUtc]>=[StartDateUtc]),
  CONSTRAINT CK_Contracts_Status CHECK ([Status]='TERMINATED' OR [Status]='EXPIRED' OR [Status]='SUSPENDED' OR [Status]='ACTIVE' OR [Status]='DRAFT')
)
END
GO

IF OBJECT_ID(N'FK_Contracts_Customers_ID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_Contracts_Customers_ID'
)
BEGIN
  ALTER TABLE Contract.Contracts
  ADD CONSTRAINT FK_Contracts_Customers_ID FOREIGN KEY (CustomerID) REFERENCES portal.Customers (ID) ON DELETE CASCADE ON UPDATE CASCADE
END
GO

IF OBJECT_ID(N'Contract.WorkflowUsageCounters', N'U') IS NULL
BEGIN
CREATE TABLE Contract.WorkflowUsageCounters (
  ContractID int NOT NULL,
  ScopeID int NOT NULL,
  WorkflowDefID bigint NOT NULL,
  PeriodType varchar(8) NOT NULL,
  PeriodStartUtc datetime2(3) NOT NULL,
  RunsExecuted int NOT NULL CONSTRAINT DF_WUC_RunsExecuted DEFAULT (0),
  UpdatedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_WUC_UpdatedAtUtc DEFAULT (sysutcdatetime()),
  CONSTRAINT PK_Contract_WorkflowUsageCounters PRIMARY KEY CLUSTERED (ContractID, ScopeID, WorkflowDefID, PeriodType, PeriodStartUtc),
  CONSTRAINT CK_WUC_PeriodType CHECK ([PeriodType]='MONTH' OR [PeriodType]='WEEK' OR [PeriodType]='DAY')
)
END
GO

IF OBJECT_ID(N'FK_WUC_ContractID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_WUC_ContractID'
)
BEGIN
  ALTER TABLE Contract.WorkflowUsageCounters
  ADD CONSTRAINT FK_WUC_ContractID FOREIGN KEY (ContractID) REFERENCES Contract.Contracts (ContractID)
END
GO

IF OBJECT_ID(N'FK_WUC_ScopeID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_WUC_ScopeID'
)
BEGIN
  ALTER TABLE Contract.WorkflowUsageCounters
  ADD CONSTRAINT FK_WUC_ScopeID FOREIGN KEY (ScopeID) REFERENCES RBAC.Scopes (ScopeID)
END
GO

IF OBJECT_ID(N'FK_WUC_WorkflowDefID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_WUC_WorkflowDefID'
)
BEGIN
  ALTER TABLE Contract.WorkflowUsageCounters
  ADD CONSTRAINT FK_WUC_WorkflowDefID FOREIGN KEY (WorkflowDefID) REFERENCES wf.workflow_def (id)
END
GO

IF OBJECT_ID(N'Contract.ContractWorkflowEntitlements', N'U') IS NULL
BEGIN
CREATE TABLE Contract.ContractWorkflowEntitlements (
  ContractID int NOT NULL,
  WorkflowDefID bigint NOT NULL,
  Enabled bit NOT NULL CONSTRAINT DF_CWE_Enabled DEFAULT (1),
  MaxRunsPerPeriod int NULL,
  PeriodType varchar(8) NULL,
  MaxConcurrentRuns int NULL,
  DataRetentionDays int NULL,
  SlaTier varchar(32) NULL,
  SupportTier varchar(32) NULL,
  CreatedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_CWE_CreatedAtUtc DEFAULT (sysutcdatetime()),
  CONSTRAINT PK_Contract_WorkflowEntitlements PRIMARY KEY CLUSTERED (ContractID, WorkflowDefID),
  CONSTRAINT CK_CWE_PeriodType CHECK ([PeriodType] IS NULL OR ([PeriodType]='MONTH' OR [PeriodType]='WEEK' OR [PeriodType]='DAY'))
)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_CWE_Enabled' AND object_id IS NOT NULL)
BEGIN
  CREATE INDEX IX_CWE_Enabled
  ON Contract.ContractWorkflowEntitlements (Enabled, WorkflowDefID)
END
GO

IF OBJECT_ID(N'FK_CWE_ContractID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_CWE_ContractID'
)
BEGIN
  ALTER TABLE Contract.ContractWorkflowEntitlements
  ADD CONSTRAINT FK_CWE_ContractID FOREIGN KEY (ContractID) REFERENCES Contract.Contracts (ContractID)
END
GO

IF OBJECT_ID(N'FK_CWE_WorkflowDefID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_CWE_WorkflowDefID'
)
BEGIN
  ALTER TABLE Contract.ContractWorkflowEntitlements
  ADD CONSTRAINT FK_CWE_WorkflowDefID FOREIGN KEY (WorkflowDefID) REFERENCES wf.workflow_def (id)
END
GO

IF OBJECT_ID(N'Contract.ContractScopes', N'U') IS NULL
BEGIN
CREATE TABLE Contract.ContractScopes (
  ContractID int NOT NULL,
  ScopeID int NOT NULL,
  Status varchar(24) NOT NULL CONSTRAINT DF_ContractScopes_Status DEFAULT ('ACTIVE'),
  ActivatedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_ContractScopes_ActivatedAtUtc DEFAULT (sysutcdatetime()),
  EffectiveFromUtc datetime2(3) NOT NULL CONSTRAINT DF_ContractScopes_EffectiveFromUtc DEFAULT (sysutcdatetime()),
  EffectiveToUtc datetime2(3) NULL,
  CONSTRAINT PK_Contract_ContractScopes PRIMARY KEY CLUSTERED (ContractID, ScopeID),
  CONSTRAINT CK_ContractScopes_EffectiveRange CHECK ([EffectiveToUtc] IS NULL OR [EffectiveToUtc]>=[EffectiveFromUtc]),
  CONSTRAINT CK_ContractScopes_Status CHECK ([Status]='TERMINATED' OR [Status]='EXPIRED' OR [Status]='SUSPENDED' OR [Status]='ACTIVE')
)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ContractScopes_Status' AND object_id IS NOT NULL)
BEGIN
  CREATE INDEX IX_ContractScopes_Status
  ON Contract.ContractScopes (Status, ScopeID, EffectiveFromUtc, EffectiveToUtc)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_ContractScopes_ActiveScope' AND object_id IS NOT NULL)
BEGIN
  CREATE UNIQUE INDEX UX_ContractScopes_ActiveScope
  ON Contract.ContractScopes (ScopeID)
  WHERE ([Status]='ACTIVE')
END
GO

IF OBJECT_ID(N'FK_ContractScopes_ContractID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_ContractScopes_ContractID'
)
BEGIN
  ALTER TABLE Contract.ContractScopes
  ADD CONSTRAINT FK_ContractScopes_ContractID FOREIGN KEY (ContractID) REFERENCES Contract.Contracts (ContractID)
END
GO

IF OBJECT_ID(N'FK_ContractScopes_ScopeID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_ContractScopes_ScopeID'
)
BEGIN
  ALTER TABLE Contract.ContractScopes
  ADD CONSTRAINT FK_ContractScopes_ScopeID FOREIGN KEY (ScopeID) REFERENCES RBAC.Scopes (ScopeID)
END
GO

IF OBJECT_ID(N'Contract.ContractRolePolicies', N'U') IS NULL
BEGIN
CREATE TABLE Contract.ContractRolePolicies (
  ContractID int NOT NULL,
  RoleID int NOT NULL,
  GrantTypeAllowed varchar(16) NOT NULL CONSTRAINT DF_CRP_GrantTypeAllowed DEFAULT ('SCOPED'),
  MaxUsersForRole int NULL,
  RequiresApproval bit NOT NULL CONSTRAINT DF_CRP_RequiresApproval DEFAULT (0),
  CreatedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_CRP_CreatedAtUtc DEFAULT (sysutcdatetime()),
  CONSTRAINT PK_Contract_RolePolicies PRIMARY KEY CLUSTERED (ContractID, RoleID),
  CONSTRAINT CK_CRP_GrantTypeAllowed CHECK ([GrantTypeAllowed]='BOTH' OR [GrantTypeAllowed]='SCOPED' OR [GrantTypeAllowed]='GLOBAL')
)
END
GO

IF OBJECT_ID(N'FK_CRP_ContractID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_CRP_ContractID'
)
BEGIN
  ALTER TABLE Contract.ContractRolePolicies
  ADD CONSTRAINT FK_CRP_ContractID FOREIGN KEY (ContractID) REFERENCES Contract.Contracts (ContractID)
END
GO

IF OBJECT_ID(N'FK_CRP_RoleID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_CRP_RoleID'
)
BEGIN
  ALTER TABLE Contract.ContractRolePolicies
  ADD CONSTRAINT FK_CRP_RoleID FOREIGN KEY (RoleID) REFERENCES RBAC.Roles (ID)
END
GO

IF OBJECT_ID(N'Contract.ContractLimits', N'U') IS NULL
BEGIN
CREATE TABLE Contract.ContractLimits (
  ContractLimitID bigint IDENTITY,
  ContractID int NOT NULL,
  ScopeID int NULL,
  MaxActiveUsers int NULL,
  MaxStorageGB decimal(18, 2) NULL,
  MaxRunsPerMonth int NULL,
  CreatedAtUtc datetime2(3) NOT NULL CONSTRAINT DF_ContractLimits_CreatedAtUtc DEFAULT (sysutcdatetime()),
  CONSTRAINT PK_Contract_ContractLimits PRIMARY KEY CLUSTERED (ContractLimitID)
)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_ContractLimits_GlobalPerContract' AND object_id IS NOT NULL)
BEGIN
  CREATE UNIQUE INDEX UX_ContractLimits_GlobalPerContract
  ON Contract.ContractLimits (ContractID)
  WHERE ([ScopeID] IS NULL)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_ContractLimits_PerScope' AND object_id IS NOT NULL)
BEGIN
  CREATE UNIQUE INDEX UX_ContractLimits_PerScope
  ON Contract.ContractLimits (ContractID, ScopeID)
  WHERE ([ScopeID] IS NOT NULL)
END
GO

IF OBJECT_ID(N'FK_ContractLimits_ContractID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_ContractLimits_ContractID'
)
BEGIN
  ALTER TABLE Contract.ContractLimits
  ADD CONSTRAINT FK_ContractLimits_ContractID FOREIGN KEY (ContractID) REFERENCES Contract.Contracts (ContractID)
END
GO

