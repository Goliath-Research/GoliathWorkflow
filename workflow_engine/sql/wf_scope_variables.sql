/*
  MethylPipeline wf schema - scoped variables (additive migration).
  Run against MethylPipeline after base wf schema is deployed.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

/* ---- workflow_node: named variables for control flow ---- */
IF COL_LENGTH('wf.workflow_node', 'condition_var') IS NULL
BEGIN
    ALTER TABLE wf.workflow_node ADD condition_var NVARCHAR(128) NULL;
END
GO

IF COL_LENGTH('wf.workflow_node', 'switch_var') IS NULL
BEGIN
    ALTER TABLE wf.workflow_node ADD switch_var NVARCHAR(128) NULL;
END
GO

/* ---- Definition: default variables when a scope opens ---- */
IF OBJECT_ID(N'wf.node_scope_default', N'U') IS NULL
BEGIN
    CREATE TABLE wf.node_scope_default (
        id                  BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        workflow_node_id    BIGINT NOT NULL,
        var_name            NVARCHAR(128) NOT NULL,
        default_expr        NVARCHAR(1024) NOT NULL,
        CONSTRAINT FK_nsd_node FOREIGN KEY (workflow_node_id) REFERENCES wf.workflow_node(id) ON DELETE CASCADE,
        CONSTRAINT UQ_nsd_node_var UNIQUE (workflow_node_id, var_name)
    );
    CREATE INDEX IX_nsd_node ON wf.node_scope_default(workflow_node_id);
END
GO

/* ---- Definition: ACTION output -> scope variable bindings ---- */
IF OBJECT_ID(N'wf.variable_output_binding', N'U') IS NULL
BEGIN
    CREATE TABLE wf.variable_output_binding (
        id                  BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        workflow_node_id    BIGINT NOT NULL,
        var_name            NVARCHAR(128) NOT NULL,
        source_kind         VARCHAR(32) NOT NULL,
        source_json_path    NVARCHAR(1024) NULL,
        CONSTRAINT FK_vob_node FOREIGN KEY (workflow_node_id) REFERENCES wf.workflow_node(id) ON DELETE CASCADE,
        CONSTRAINT CK_vob_source CHECK (source_kind IN (N'result_code', N'output_path')),
        CONSTRAINT UQ_vob_node_var UNIQUE (workflow_node_id, var_name)
    );
    CREATE INDEX IX_vob_node ON wf.variable_output_binding(workflow_node_id);
END
GO

/* ---- Runtime: variables per scope (scope_node_execution_id = 0 => instance root) ---- */
IF OBJECT_ID(N'wf.scope_variable', N'U') IS NULL
BEGIN
    CREATE TABLE wf.scope_variable (
        workflow_instance_id        BIGINT NOT NULL,
        scope_node_execution_id     BIGINT NOT NULL,
        var_name                    NVARCHAR(128) NOT NULL,
        value_json                  NVARCHAR(MAX) NOT NULL,
        updated_at_utc              DATETIME2(7) NOT NULL CONSTRAINT DF_sv_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_scope_variable PRIMARY KEY (workflow_instance_id, scope_node_execution_id, var_name),
        CONSTRAINT FK_sv_instance FOREIGN KEY (workflow_instance_id) REFERENCES wf.workflow_instance(id) ON DELETE CASCADE
    );
    CREATE INDEX IX_sv_instance_scope ON wf.scope_variable(workflow_instance_id, scope_node_execution_id);
END
GO
