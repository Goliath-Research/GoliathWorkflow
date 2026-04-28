/*
  Workflow Engine - Definition Layer (SQL Server)
  Tables: workflow definitions, versions, nodes, edges, actions, input templates/bindings.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.workflow_input_binding', N'U') IS NOT NULL DROP TABLE dbo.workflow_input_binding;
IF OBJECT_ID(N'dbo.workflow_input_template', N'U') IS NOT NULL DROP TABLE dbo.workflow_input_template;
IF OBJECT_ID(N'dbo.workflow_edge', N'U') IS NOT NULL DROP TABLE dbo.workflow_edge;

IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_wfv_root' AND parent_object_id = OBJECT_ID(N'dbo.workflow_version'))
    ALTER TABLE dbo.workflow_version DROP CONSTRAINT FK_wfv_root;

IF OBJECT_ID(N'dbo.workflow_node', N'U') IS NOT NULL DROP TABLE dbo.workflow_node;
IF OBJECT_ID(N'dbo.workflow_action', N'U') IS NOT NULL DROP TABLE dbo.workflow_action;
IF OBJECT_ID(N'dbo.workflow_version', N'U') IS NOT NULL DROP TABLE dbo.workflow_version;
IF OBJECT_ID(N'dbo.workflow_def', N'U') IS NOT NULL DROP TABLE dbo.workflow_def;
GO

CREATE TABLE dbo.workflow_def (
    id              BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    name            NVARCHAR(256) NOT NULL,
    description     NVARCHAR(MAX) NULL,
    created_at_utc  DATETIME2(7) NOT NULL CONSTRAINT DF_workflow_def_created DEFAULT (SYSUTCDATETIME())
);
GO

CREATE TABLE dbo.workflow_version (
    id                  BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    workflow_def_id     BIGINT NOT NULL,
    version_major       INT NOT NULL CONSTRAINT DF_wfv_major DEFAULT (1),
    version_minor       INT NOT NULL CONSTRAINT DF_wfv_minor DEFAULT (0),
    is_active           BIT NOT NULL CONSTRAINT DF_wfv_active DEFAULT (1),
    root_node_id        BIGINT NULL,
    CONSTRAINT FK_wfv_def FOREIGN KEY (workflow_def_id) REFERENCES dbo.workflow_def(id),
    CONSTRAINT UQ_wfv_def_version UNIQUE (workflow_def_id, version_major, version_minor)
);
GO

CREATE TABLE dbo.workflow_action (
    id                  BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    action_name         NVARCHAR(256) NOT NULL,
    capability          NVARCHAR(128) NULL,
    payload_schema_ref  NVARCHAR(512) NULL,
    CONSTRAINT UQ_workflow_action_name UNIQUE (action_name)
);
GO

CREATE TABLE dbo.workflow_node (
    id                  BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    workflow_version_id BIGINT NOT NULL,
    node_type           VARCHAR(32) NOT NULL,
    node_key            NVARCHAR(128) NOT NULL,
    workflow_action_id  BIGINT NULL,
    repeat_count        INT NULL,
    condition_ref_node_key NVARCHAR(128) NULL,
    switch_ref_node_key    NVARCHAR(128) NULL,
    CONSTRAINT FK_wn_version FOREIGN KEY (workflow_version_id) REFERENCES dbo.workflow_version(id) ON DELETE CASCADE,
    CONSTRAINT FK_wn_action FOREIGN KEY (workflow_action_id) REFERENCES dbo.workflow_action(id),
    CONSTRAINT CK_wn_node_type CHECK (node_type IN (
        N'ACTION', N'SEQUENCE', N'PARALLEL', N'IF', N'SWITCH', N'REPEAT', N'WHILE'
    )),
    CONSTRAINT UQ_wn_version_key UNIQUE (workflow_version_id, node_key)
);
GO

CREATE INDEX IX_workflow_node_version ON dbo.workflow_node(workflow_version_id);
GO

CREATE TABLE dbo.workflow_edge (
    id                  BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    parent_node_id      BIGINT NOT NULL,
    child_node_id       BIGINT NOT NULL,
    child_order         INT NOT NULL CONSTRAINT DF_we_child_order DEFAULT (0),
    branch_kind         VARCHAR(32) NULL,
    condition_expr      NVARCHAR(MAX) NULL,
    switch_case_value   INT NULL,
    is_default          BIT NOT NULL CONSTRAINT DF_we_default DEFAULT (0),
    CONSTRAINT FK_we_parent FOREIGN KEY (parent_node_id) REFERENCES dbo.workflow_node(id) ON DELETE CASCADE,
    CONSTRAINT FK_we_child FOREIGN KEY (child_node_id) REFERENCES dbo.workflow_node(id) ON DELETE CASCADE,
    CONSTRAINT CK_we_no_self_loop CHECK (parent_node_id <> child_node_id),
    CONSTRAINT CK_we_branch_kind CHECK (branch_kind IS NULL OR branch_kind IN (
        N'SEQUENCE', N'PARALLEL', N'THEN', N'ELSE', N'CASE', N'DEFAULT', N'BODY'
    ))
);
GO

CREATE UNIQUE INDEX UQ_we_parent_child_order ON dbo.workflow_edge(parent_node_id, child_order);
CREATE INDEX IX_we_parent ON dbo.workflow_edge(parent_node_id);
CREATE INDEX IX_we_child ON dbo.workflow_edge(child_node_id);
GO

ALTER TABLE dbo.workflow_version WITH NOCHECK
ADD CONSTRAINT FK_wfv_root FOREIGN KEY (root_node_id) REFERENCES dbo.workflow_node(id);
GO

CREATE TABLE dbo.workflow_input_template (
    workflow_node_id    BIGINT NOT NULL PRIMARY KEY,
    template_json       NVARCHAR(MAX) NOT NULL CONSTRAINT DF_wit_template DEFAULT (N'{}'),
    CONSTRAINT FK_wit_node FOREIGN KEY (workflow_node_id) REFERENCES dbo.workflow_node(id) ON DELETE CASCADE
);
GO

CREATE TABLE dbo.workflow_input_binding (
    id                  BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    workflow_node_id    BIGINT NOT NULL,
    target_json_path    NVARCHAR(1024) NOT NULL,
    source_expr         NVARCHAR(1024) NOT NULL,
    is_required         BIT NOT NULL CONSTRAINT DF_wib_required DEFAULT (0),
    CONSTRAINT FK_wib_node FOREIGN KEY (workflow_node_id) REFERENCES dbo.workflow_node(id) ON DELETE CASCADE
);
GO

CREATE INDEX IX_wib_node ON dbo.workflow_input_binding(workflow_node_id);
GO
