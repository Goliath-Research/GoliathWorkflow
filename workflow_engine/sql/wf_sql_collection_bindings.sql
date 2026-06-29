/*
  Generic collection bindings for Azure SQL (parity with sql_pg/wf_sql_collection_bindings.sql).

  Resolves JSON arrays into scope-0 before FOREACH activation. jsonFile bindings require
  the gateway planner to pre-populate scope (SQL Server cannot read arbitrary host paths).

  Prerequisites: wf_scope_readpath.sql, wf_sql_scope_writepath_parity.sql
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'wf.workflow_collection_binding', N'U') IS NULL
BEGIN
    CREATE TABLE wf.workflow_collection_binding (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        workflow_version_id BIGINT NOT NULL,
        bind_order INT NOT NULL CONSTRAINT DF_wcb_bind_order DEFAULT (0),
        scope_var NVARCHAR(256) NOT NULL,
        source_kind NVARCHAR(32) NOT NULL,
        path_var NVARCHAR(256) NULL,
        base_var NVARCHAR(256) NULL,
        json_path NVARCHAR(512) NULL,
        CONSTRAINT FK_wcb_version FOREIGN KEY (workflow_version_id)
            REFERENCES wf.workflow_version(id) ON DELETE CASCADE,
        CONSTRAINT UQ_wcb_version_scope UNIQUE (workflow_version_id, scope_var),
        CONSTRAINT CK_wcb_source_kind CHECK (source_kind IN (N'jsonFile', N'jsonPath'))
    );
    CREATE INDEX IX_wcb_version ON wf.workflow_collection_binding(workflow_version_id, bind_order);
END
GO

CREATE OR ALTER PROCEDURE wf.wf_resolve_collection_bindings
    @workflow_instance_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @version_id BIGINT;
    DECLARE @scope_var NVARCHAR(256);
    DECLARE @source_kind NVARCHAR(32);
    DECLARE @path_var NVARCHAR(256);
    DECLARE @base_var NVARCHAR(256);
    DECLARE @json_path NVARCHAR(512);
    DECLARE @existing NVARCHAR(MAX);
    DECLARE @base_json NVARCHAR(MAX);
    DECLARE @extracted NVARCHAR(MAX);
    DECLARE @path_expr NVARCHAR(512);

    SELECT @version_id = workflow_version_id
    FROM wf.workflow_instance
    WHERE id = @workflow_instance_id;

    IF @version_id IS NULL
        RETURN;

    DECLARE binding_cur CURSOR LOCAL FAST_FORWARD FOR
        SELECT scope_var, source_kind, path_var, base_var, json_path
        FROM wf.workflow_collection_binding
        WHERE workflow_version_id = @version_id
        ORDER BY bind_order ASC, id ASC;

    OPEN binding_cur;
    FETCH NEXT FROM binding_cur INTO @scope_var, @source_kind, @path_var, @base_var, @json_path;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @existing = wf.wf_get_scope_variable_json(@workflow_instance_id, 0, @scope_var);
        IF @existing IS NOT NULL AND LTRIM(RTRIM(@existing)) NOT IN (N'', N'null')
        BEGIN
            FETCH NEXT FROM binding_cur INTO @scope_var, @source_kind, @path_var, @base_var, @json_path;
            CONTINUE;
        END

        IF @source_kind = N'jsonPath'
        BEGIN
            SET @base_json = wf.wf_get_scope_variable_json(@workflow_instance_id, 0, @base_var);
            IF @base_json IS NULL OR LTRIM(RTRIM(@base_json)) IN (N'', N'null')
                THROW 50020, N'collection binding jsonPath missing base scope variable', 1;

            SET @path_expr = NULLIF(LTRIM(RTRIM(@json_path)), N'');

            /* Parity with PG wf_json_path_to_pg: NULL / '' / '$' / '$.' → entire base document. */
            IF @path_expr IS NULL OR @path_expr IN (N'$', N'$.')
                SET @extracted = @base_json;
            ELSE
            BEGIN
                IF LEFT(@path_expr, 2) <> N'$.'
                    SET @path_expr = N'$.' + LTRIM(REPLACE(@path_expr, N'$.', N''));
                SET @extracted = JSON_QUERY(@base_json, @path_expr);
            END

            IF @extracted IS NULL OR @extracted = N'null'
                THROW 50021, N'collection binding jsonPath produced null', 1;

            EXEC wf.wf_set_scope_variable
                @workflow_instance_id = @workflow_instance_id,
                @scope_node_execution_id = 0,
                @var_name = @scope_var,
                @value_json = CAST(@extracted AS json);
        END
        ELSE IF @source_kind = N'jsonFile'
        BEGIN
            /* Host file reads are not available on Azure SQL — rely on gateway-enriched context. */
            THROW 50022,
                N'collection binding jsonFile is not supported on Azure SQL; use gateway study start endpoints or pre-populate scope in context_json',
                1;
        END

        FETCH NEXT FROM binding_cur INTO @scope_var, @source_kind, @path_var, @base_var, @json_path;
    END

    CLOSE binding_cur;
    DEALLOCATE binding_cur;
END;
GO

PRINT N'wf_sql_collection_bindings.sql applied.';
GO
