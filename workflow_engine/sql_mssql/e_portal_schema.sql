-- Auto-extracted by scripts/extract_legacy_schema.py from MethylPipeline.sql
-- Idempotent incremental deploy (IF OBJECT_ID / CREATE OR ALTER).
-- Do not edit by hand unless also updating the twin under sql_pg/.

IF SCHEMA_ID(N'e_portal') IS NULL EXEC(N'CREATE SCHEMA [e_portal]');
GO

IF OBJECT_ID(N'e_portal.AppRole2Node', N'U') IS NULL
BEGIN
  CREATE TABLE [e_portal].[AppRole2Node] (
    [AppRoleId] int NOT NULL,
    [NodeId] int NOT NULL,
    CONSTRAINT [PK_e_portal_AppRole2Node] PRIMARY KEY ([AppRoleId], [NodeId])
  );
END
GO

IF OBJECT_ID(N'e_portal.AppRole2Roles', N'U') IS NULL
BEGIN
  CREATE TABLE [e_portal].[AppRole2Roles] (
    [RoleId] int NOT NULL,
    [AppRoleId] tinyint NOT NULL,
    CONSTRAINT [PK_e_portal_AppRole2Roles] PRIMARY KEY ([AppRoleId], [RoleId])
  );
END
GO

IF OBJECT_ID(N'e_portal.AppRoles', N'U') IS NULL
BEGIN
  CREATE TABLE [e_portal].[AppRoles] (
    [Id] tinyint IDENTITY(1,1) NOT NULL,
    [AppRole] varchar(128) NOT NULL,
    CONSTRAINT [PK_e_portal_AppRoles] PRIMARY KEY ([Id])
  );
END
GO

IF OBJECT_ID(N'e_portal.DMDataSetDef', N'U') IS NULL
BEGIN
  CREATE TABLE [e_portal].[DMDataSetDef] (
    [DMDataSetDefId] int IDENTITY(1,1) NOT NULL,
    [DMKey] nvarchar(100) NOT NULL,
    [DataSetKey] nvarchar(100) NOT NULL,
    [SourceType] nvarchar(20) NOT NULL,
    [SourceName] nvarchar(500) NOT NULL,
    [SourceColumns] nvarchar(500) NULL,
    [SourceWhere] nvarchar(500) NULL,
    [SourceOrderBy] nvarchar(200) NULL,
    [Role] nvarchar(20) NOT NULL DEFAULT ('DETAIL'),
    [Seq] int NOT NULL DEFAULT ((0)),
    CONSTRAINT [PK_e_portal_DMDataSetDef] PRIMARY KEY ([DMDataSetDefId])
  );
END
GO

IF OBJECT_ID(N'e_portal.DMDef', N'U') IS NULL
BEGIN
  CREATE TABLE [e_portal].[DMDef] (
    [DMDefId] int IDENTITY(1,1) NOT NULL,
    [DMKey] nvarchar(100) NOT NULL,
    [Title] nvarchar(200) NULL,
    [IsActive] bit NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_e_portal_DMDef] PRIMARY KEY ([DMDefId])
  );
END
GO

IF OBJECT_ID(N'e_portal.DMParamDef', N'U') IS NULL
BEGIN
  CREATE TABLE [e_portal].[DMParamDef] (
    [DMParamDefId] int IDENTITY(1,1) NOT NULL,
    [DMKey] nvarchar(100) NOT NULL,
    [DataSetKey] nvarchar(100) NOT NULL,
    [ParamName] nvarchar(100) NOT NULL,
    [ParamSource] nvarchar(100) NULL,
    [DefaultValue] nvarchar(200) NULL,
    CONSTRAINT [PK_e_portal_DMParamDef] PRIMARY KEY ([DMParamDefId])
  );
END
GO

IF OBJECT_ID(N'e_portal.DMRelationDef', N'U') IS NULL
BEGIN
  CREATE TABLE [e_portal].[DMRelationDef] (
    [DMRelationDefId] int IDENTITY(1,1) NOT NULL,
    [DMKey] nvarchar(100) NOT NULL,
    [MasterDataSetKey] nvarchar(100) NOT NULL,
    [DetailDataSetKey] nvarchar(100) NOT NULL,
    [MasterField] nvarchar(100) NOT NULL,
    [DetailParam] nvarchar(100) NOT NULL,
    CONSTRAINT [PK_e_portal_DMRelationDef] PRIMARY KEY ([DMRelationDefId])
  );
END
GO

IF OBJECT_ID(N'e_portal.EPSessions', N'U') IS NULL
BEGIN
  CREATE TABLE [e_portal].[EPSessions] (
    [uniSessionId] varchar(50) NOT NULL,
    [sqlSessionId] int NOT NULL,
    [StartDate] datetime NULL DEFAULT (getdate()),
    [EndDate] datetime NULL,
    [UserId] bigint NULL,
    [ClientQty] int NULL DEFAULT ((0)),
    CONSTRAINT [PK_e_portal_EPSessions] PRIMARY KEY ([uniSessionId], [sqlSessionId])
  );
END
GO

IF OBJECT_ID(N'e_portal.FrameDef', N'U') IS NULL
BEGIN
  CREATE TABLE [e_portal].[FrameDef] (
    [FrameDefId] int IDENTITY(1,1) NOT NULL,
    [FrameKey] nvarchar(100) NOT NULL,
    [MasterStoredProc] nvarchar(200) NOT NULL,
    [Title] nvarchar(200) NULL,
    [IdField] nvarchar(100) NULL,
    [IsActive] bit NOT NULL DEFAULT ((1)),
    [FrameType] nvarchar(20) NOT NULL DEFAULT ('MASTER_DETAIL'),
    [DMKey] nvarchar(100) NULL,
    CONSTRAINT [PK_e_portal_FrameDef] PRIMARY KEY ([FrameDefId])
  );
END
GO

IF OBJECT_ID(N'e_portal.FrameDimensionDef', N'U') IS NULL
BEGIN
  CREATE TABLE [e_portal].[FrameDimensionDef] (
    [FrameDimensionDefId] int IDENTITY(1,1) NOT NULL,
    [FrameKey] nvarchar(100) NOT NULL,
    [Caption] nvarchar(100) NOT NULL,
    [StoredProc] nvarchar(200) NOT NULL,
    [ParamName] nvarchar(100) NOT NULL,
    [ParamSource] nvarchar(100) NOT NULL,
    [DimOrder] int NOT NULL DEFAULT ((0)),
    CONSTRAINT [PK_e_portal_FrameDimensionDef] PRIMARY KEY ([FrameDimensionDefId])
  );
END
GO

IF OBJECT_ID(N'e_portal.FrameFilterDef', N'U') IS NULL
BEGIN
  CREATE TABLE [e_portal].[FrameFilterDef] (
    [FrameFilterDefId] int IDENTITY(1,1) NOT NULL,
    [FrameKey] nvarchar(100) NOT NULL,
    [FieldName] nvarchar(100) NOT NULL,
    [Caption] nvarchar(100) NOT NULL,
    [FilterOrder] int NOT NULL DEFAULT ((0)),
    CONSTRAINT [PK_e_portal_FrameFilterDef] PRIMARY KEY ([FrameFilterDefId])
  );
END
GO

IF OBJECT_ID(N'e_portal.FramePanelDef', N'U') IS NULL
BEGIN
  CREATE TABLE [e_portal].[FramePanelDef] (
    [FramePanelDefId] int IDENTITY(1,1) NOT NULL,
    [FrameKey] nvarchar(100) NOT NULL,
    [PanelKey] nvarchar(100) NOT NULL,
    [Title] nvarchar(200) NULL,
    [PanelType] nvarchar(20) NOT NULL,
    [Region] nvarchar(20) NOT NULL,
    [DMKey] nvarchar(100) NULL,
    [DataSetKey] nvarchar(100) NULL,
    [RegionSize] int NULL DEFAULT ((50)),
    [Seq] int NOT NULL DEFAULT ((0)),
    CONSTRAINT [PK_e_portal_FramePanelDef] PRIMARY KEY ([FramePanelDefId])
  );
END
GO

IF OBJECT_ID(N'e_portal.NavTree', N'U') IS NULL
BEGIN
  CREATE TABLE [e_portal].[NavTree] (
    [ID] int IDENTITY(1,1) NOT NULL,
    [ParentID] int NULL,
    [Caption] varchar(50) NOT NULL,
    [Seq] smallint NOT NULL,
    [InfoID] int NULL,
    CONSTRAINT [PK_e_portal_NavTree] PRIMARY KEY ([ID])
  );
END
GO

IF OBJECT_ID(N'e_portal.NodeInfos', N'U') IS NULL
BEGIN
  CREATE TABLE [e_portal].[NodeInfos] (
    [Id] int IDENTITY(1,1) NOT NULL,
    [Name] varchar(128) NOT NULL,
    [Singleton] bit NOT NULL DEFAULT ((1)),
    [TypeId] tinyint NULL DEFAULT ((1)),
    [FrameKey] nvarchar(100) NULL,
    CONSTRAINT [PK_e_portal_NodeInfos] PRIMARY KEY ([Id])
  );
END
GO

IF OBJECT_ID(N'e_portal.Roles', N'U') IS NULL
BEGIN
  CREATE TABLE [e_portal].[Roles] (
    [RoleId] int IDENTITY(1,1) NOT NULL,
    [Name] varchar(128) NOT NULL,
    CONSTRAINT [PK_e_portal_Roles] PRIMARY KEY ([RoleId])
  );
END
GO

IF OBJECT_ID(N'e_portal.SyUsers', N'U') IS NULL
BEGIN
  CREATE TABLE [e_portal].[SyUsers] (
    [UserId] bigint IDENTITY(1,1) NOT NULL,
    [FullName] varchar(100) NOT NULL,
    [Email] varchar(50) NOT NULL,
    [Active] int NOT NULL DEFAULT ((1)),
    [username] varchar(50) NULL,
    CONSTRAINT [PK_e_portal_SyUsers] PRIMARY KEY ([UserId])
  );
END
GO

IF OBJECT_ID(N'e_portal.UserRoles', N'U') IS NULL
BEGIN
  CREATE TABLE [e_portal].[UserRoles] (
    [UserId] bigint NOT NULL,
    [RoleId] int NOT NULL,
    CONSTRAINT [PK_e_portal_UserRoles] PRIMARY KEY ([UserId], [RoleId])
  );
END
GO

