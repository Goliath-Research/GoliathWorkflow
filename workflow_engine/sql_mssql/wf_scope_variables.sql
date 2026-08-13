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
        value_json                  json NOT NULL,
        updated_at_utc              DATETIME2(7) NOT NULL CONSTRAINT DF_sv_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_scope_variable PRIMARY KEY (workflow_instance_id, scope_node_execution_id, var_name),
        CONSTRAINT FK_sv_instance FOREIGN KEY (workflow_instance_id) REFERENCES wf.workflow_instance(id) ON DELETE CASCADE
    );
    CREATE INDEX IX_sv_instance_scope ON wf.scope_variable(workflow_instance_id, scope_node_execution_id);
END
GO

/*
  Azure json rejects RFC 8259 scalars. Box fragments so the column can be json;
  wf.wf_json_unbox restores the fragment for readers. Redefined in
  wf_json_column_alignment.sql (CREATE OR ALTER, safe to re-run).
*/
CREATE OR ALTER FUNCTION wf.wf_json_box(@frag nvarchar(max))
RETURNS json
AS
BEGIN
    IF @frag IS NULL
        RETURN CAST(N'{"$mp.v":null}' AS json);

    DECLARE @t nvarchar(max) = LTRIM(RTRIM(@frag));
    IF ISJSON(@t, OBJECT) = 1 OR ISJSON(@t, ARRAY) = 1
        RETURN CAST(@t AS json);

    IF ISJSON(@t, VALUE) = 1
        RETURN CAST(CONCAT(N'{"$mp.v":', @t, N'}') AS json);

    RETURN CAST(CONCAT(N'{"$mp.v":', wf.wf_json_fragment_from_string(@t), N'}') AS json);
END;
GO

CREATE OR ALTER FUNCTION wf.wf_json_unbox(@doc nvarchar(max))
RETURNS nvarchar(max)
AS
BEGIN
    IF @doc IS NULL
        RETURN NULL;

    IF ISJSON(@doc, OBJECT) <> 1
        RETURN @doc;

    DECLARE @val nvarchar(max);
    DECLARE @typ int;
    SELECT @val = [value], @typ = [type]
    FROM OPENJSON(@doc)
    WHERE [key] = N'$mp.v';

    IF @typ IS NULL
        RETURN @doc;
    IF @typ = 0
        RETURN N'null';
    IF @typ = 1
        RETURN wf.wf_json_fragment_from_string(@val);
    IF @typ = 2
        RETURN @val;
    IF @typ = 3
        RETURN LOWER(@val);
    IF @typ IN (4, 5)
        RETURN JSON_QUERY(@doc, N'$."$mp.v"');
    RETURN @val;
END;
GO
