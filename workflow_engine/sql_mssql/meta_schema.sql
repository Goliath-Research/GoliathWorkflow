-- Auto-extracted by scripts/extract_legacy_schema.py from MethylPipeline.sql
-- Idempotent incremental deploy (IF OBJECT_ID / CREATE OR ALTER).
-- Do not edit by hand unless also updating the twin under sql_pg/.

IF SCHEMA_ID(N'Meta') IS NULL EXEC(N'CREATE SCHEMA [Meta]');
GO

IF OBJECT_ID(N'Meta.LinkTypes', N'U') IS NULL
BEGIN
CREATE TABLE Meta.LinkTypes (
  ID tinyint IDENTITY,
  Name varchar(32) NOT NULL,
  CONSTRAINT PK_LinkKind_ID PRIMARY KEY CLUSTERED (ID)
)
END
GO

IF OBJECT_ID(N'Meta.Event', N'U') IS NULL
BEGIN
CREATE TABLE Meta.Event (
  ID tinyint IDENTITY,
  Name varchar(32) NOT NULL,
  PRIMARY KEY CLUSTERED (ID)
)
END
GO

IF OBJECT_ID(N'Meta.Classes', N'U') IS NULL
BEGIN
CREATE TABLE Meta.Classes (
  ID int IDENTITY,
  Name varchar(128) NOT NULL,
  TableName varchar(64) NULL,
  ParentID int NULL,
  HasHistory bit NULL,
  CONSTRAINT PK_Classes PRIMARY KEY CLUSTERED (ID)
)
END
GO

IF OBJECT_ID(N'Meta.Operations', N'U') IS NULL
BEGIN
CREATE TABLE Meta.Operations (
  ID int IDENTITY,
  Name varchar(100) NOT NULL,
  ClassID int NOT NULL,
  PRIMARY KEY CLUSTERED (ID),
  CONSTRAINT UQ_Operations_Class_Name UNIQUE (ClassID, Name)
)
END
GO

IF OBJECT_ID(N'Meta.Objs', N'U') IS NULL
BEGIN
CREATE TABLE Meta.Objs (
  ID int IDENTITY,
  ClassID int NOT NULL,
  PRIMARY KEY CLUSTERED (ID)
)
END
GO

IF OBJECT_ID(N'FK_Objs_Classes_ID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_Objs_Classes_ID'
)
BEGIN
  ALTER TABLE Meta.Objs
  ADD CONSTRAINT FK_Objs_Classes_ID FOREIGN KEY (ClassID) REFERENCES Meta.Classes (ID) ON DELETE CASCADE ON UPDATE CASCADE
END
GO

IF OBJECT_ID(N'Meta.Links', N'U') IS NULL
BEGIN
CREATE TABLE Meta.Links (
  ID int IDENTITY,
  Name varchar(64) NOT NULL,
  ClassID1 int NOT NULL,
  ClassID2 int NOT NULL,
  LinkTypeID tinyint NOT NULL,
  MinIdx2 int NULL,
  MaxIdx2 int NULL,
  Indexed bit NULL DEFAULT (0),
  Owns bit NULL,
  CONSTRAINT PK_Link_ID PRIMARY KEY CLUSTERED (ID),
  CONSTRAINT CK_Link_Cardinality CHECK ([MinIdx2] IS NULL OR [MaxIdx2] IS NULL OR [MinIdx2]<=[MaxIdx2])
)
END
GO

IF OBJECT_ID(N'Meta.Collections', N'U') IS NULL
BEGIN
CREATE TABLE Meta.Collections (
  ID int IDENTITY,
  Name varchar(200) NOT NULL,
  Type char(1) NOT NULL,
  ItemClassID int NULL,
  ValueType char(1) NOT NULL,
  PRIMARY KEY CLUSTERED (ID),
  CHECK ([ValueType]='O' OR [ValueType]='N' OR [ValueType]='S'),
  CHECK ([Type]='T' OR [Type]='L' OR [Type]='S')
)
END
GO

IF OBJECT_ID(N'FK_Collection_ItemClass', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_Collection_ItemClass'
)
BEGIN
  ALTER TABLE Meta.Collections
  ADD CONSTRAINT FK_Collection_ItemClass FOREIGN KEY (ItemClassID) REFERENCES Meta.Classes (ID)
END
GO

IF OBJECT_ID(N'Meta.CollectionItem', N'U') IS NULL
BEGIN
CREATE TABLE Meta.CollectionItem (
  ID int IDENTITY,
  CollectionID int NOT NULL,
  ParentID int NULL,
  Idx int NULL,
  ValueString varchar(64) NULL,
  ValueNumber decimal(38, 10) NULL,
  ValueObjectID int NULL,
  PRIMARY KEY CLUSTERED (ID),
  CONSTRAINT CHK_Values_OnlyOne CHECK ([ValueString] IS NOT NULL AND [ValueNumber] IS NULL AND [ValueObjectID] IS NULL OR [ValueString] IS NULL AND [ValueNumber] IS NOT NULL AND [ValueObjectID] IS NULL OR [ValueString] IS NULL AND [ValueNumber] IS NULL AND [ValueObjectID] IS NOT NULL)
)
END
GO

IF OBJECT_ID(N'FK_CollectionItem_Collection', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_CollectionItem_Collection'
)
BEGIN
  ALTER TABLE Meta.CollectionItem
  ADD CONSTRAINT FK_CollectionItem_Collection FOREIGN KEY (CollectionID) REFERENCES Meta.Collections (ID)
END
GO

IF OBJECT_ID(N'FK_CollectionItem_Objs_ID', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_CollectionItem_Objs_ID'
)
BEGIN
  ALTER TABLE Meta.CollectionItem
  ADD CONSTRAINT FK_CollectionItem_Objs_ID FOREIGN KEY (ValueObjectID) REFERENCES Meta.Objs (ID) ON DELETE CASCADE ON UPDATE CASCADE
END
GO

IF OBJECT_ID(N'FK_CollectionItem_Parent', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_CollectionItem_Parent'
)
BEGIN
  ALTER TABLE Meta.CollectionItem
  ADD CONSTRAINT FK_CollectionItem_Parent FOREIGN KEY (ParentID) REFERENCES Meta.CollectionItem (ID)
END
GO

IF OBJECT_ID(N'Meta.CollectionItemValue', N'U') IS NULL
BEGIN
CREATE TABLE Meta.CollectionItemValue (
  CollectionItemID int NOT NULL,
  Name varchar(64) NOT NULL,
  ValueType char(1) NOT NULL,
  ValueString varchar(400) NULL,
  ValueNumber decimal(38, 10) NULL,
  ValueDate datetime2 NULL,
  ValueBit bit NULL,
  CONSTRAINT PK_CollectionItemValue PRIMARY KEY CLUSTERED (CollectionItemID, Name),
  CONSTRAINT CHK_CollectionItemValue_OnlyOneValue CHECK ([ValueString] IS NOT NULL AND [ValueNumber] IS NULL AND [ValueDate] IS NULL AND [ValueBit] IS NULL OR [ValueString] IS NULL AND [ValueNumber] IS NOT NULL AND [ValueDate] IS NULL AND [ValueBit] IS NULL OR [ValueString] IS NULL AND [ValueNumber] IS NULL AND [ValueDate] IS NOT NULL AND [ValueBit] IS NULL OR [ValueString] IS NULL AND [ValueNumber] IS NULL AND [ValueDate] IS NULL AND [ValueBit] IS NOT NULL),
  CONSTRAINT CHK_CollectionItemValue_ValueType CHECK ([ValueType]='B' OR [ValueType]='D' OR [ValueType]='N' OR [ValueType]='S')
)
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_CollectionItemValue_Name' AND object_id IS NOT NULL)
BEGIN
  CREATE INDEX IX_CollectionItemValue_Name
  ON Meta.CollectionItemValue (Name)
END
GO

IF OBJECT_ID(N'FK_CollectionItemValue_CollectionItem', N'F') IS NULL AND NOT EXISTS (
  SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_CollectionItemValue_CollectionItem'
)
BEGIN
  ALTER TABLE Meta.CollectionItemValue
  ADD CONSTRAINT FK_CollectionItemValue_CollectionItem FOREIGN KEY (CollectionItemID) REFERENCES Meta.CollectionItem (ID) ON DELETE CASCADE
END
GO

