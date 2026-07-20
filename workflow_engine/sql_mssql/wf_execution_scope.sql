/*
  MethylPipeline wf schema - execution scope registry and action result ledger (Azure SQL).

  An "execution scope" is the workflow engine's process-agnostic identity for one
  fully-resolved configuration combination (a hash of the baked resolvedConfig__*
  slices). It carries no domain meaning: higher layers (cfg) attach the notion of a
  "hyperparameter" trial to a scope. The word "hyperparameter" deliberately does not
  appear in wf.

  Prerequisites:
  - base wf schema (workflow_instance)

  Standalone apply: the instance-extension objects below are inlined (same as
  wf_instance_extension.sql) so wf_apply_execution_scope can persist
  methyl.execution.scope without a prior script run.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

/* --- migration: rename legacy hyperparameter_set objects to execution_scope --- */

IF OBJECT_ID(N'wf.hyperparameter_set', N'U') IS NOT NULL
   AND OBJECT_ID(N'wf.execution_scope', N'U') IS NULL
BEGIN
    IF OBJECT_ID(N'wf.hyperparameter_set_action_entry', N'U') IS NOT NULL
        EXEC sp_rename N'wf.hyperparameter_set_action_entry', N'execution_scope_action_entry';
    IF COL_LENGTH('wf.execution_scope_action_entry', 'hyperparameter_set_id') IS NOT NULL
        EXEC sp_rename N'wf.execution_scope_action_entry.hyperparameter_set_id', N'execution_scope_id', N'COLUMN';
    IF COL_LENGTH('wf.workflow_instance', 'hyperparameter_set_id') IS NOT NULL
        EXEC sp_rename N'wf.workflow_instance.hyperparameter_set_id', N'execution_scope_id', N'COLUMN';
    EXEC sp_rename N'wf.hyperparameter_set', N'execution_scope';

    /* legacy procedures/functions are superseded by the execution_scope names below */
    IF OBJECT_ID(N'wf.wf_apply_hyperparameter_set', N'P') IS NOT NULL
        DROP PROCEDURE wf.wf_apply_hyperparameter_set;
    IF OBJECT_ID(N'wf.wf_repo_upsert_hyperparameter_set', N'P') IS NOT NULL
        DROP PROCEDURE wf.wf_repo_upsert_hyperparameter_set;
    IF OBJECT_ID(N'wf.wf_repo_upsert_hyperparameter_action_entry', N'P') IS NOT NULL
        DROP PROCEDURE wf.wf_repo_upsert_hyperparameter_action_entry;
    IF OBJECT_ID(N'wf.wf_repo_get_hyperparameter_set', N'IF') IS NOT NULL
        DROP FUNCTION wf.wf_repo_get_hyperparameter_set;
    IF OBJECT_ID(N'wf.wf_repo_list_hyperparameter_action_entries', N'IF') IS NOT NULL
        DROP FUNCTION wf.wf_repo_list_hyperparameter_action_entries;
END
GO

/* --- instance extension (keep in sync with wf_instance_extension.sql) --- */

IF OBJECT_ID(N'wf.instance_extension', N'U') IS NULL
BEGIN
    CREATE TABLE wf.instance_extension (
        workflow_instance_id    BIGINT NOT NULL,
        extension_key           NVARCHAR(128) NOT NULL,
        data_json               json NULL,
        created_at_utc          DATETIME2(7) NOT NULL CONSTRAINT DF_ie_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc          DATETIME2(7) NOT NULL CONSTRAINT DF_ie_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_instance_extension PRIMARY KEY (workflow_instance_id, extension_key),
        CONSTRAINT FK_ie_instance FOREIGN KEY (workflow_instance_id)
            REFERENCES wf.workflow_instance(id) ON DELETE CASCADE
    );
    CREATE INDEX IX_ie_instance ON wf.instance_extension(workflow_instance_id);
END
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_upsert_instance_extension
    @instance_id BIGINT,
    @extension_key NVARCHAR(128),
    @data_json json = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF @extension_key IS NULL OR LTRIM(RTRIM(@extension_key)) = N''
        RETURN;

    IF EXISTS (
        SELECT 1 FROM wf.instance_extension
        WHERE workflow_instance_id = @instance_id AND extension_key = @extension_key
    )
        UPDATE wf.instance_extension
        SET data_json = @data_json, updated_at_utc = SYSUTCDATETIME()
        WHERE workflow_instance_id = @instance_id AND extension_key = @extension_key;
    ELSE
        INSERT INTO wf.instance_extension (workflow_instance_id, extension_key, data_json)
        VALUES (@instance_id, @extension_key, @data_json);
END;
GO

/* --- execution scope registry and ledger --- */

IF OBJECT_ID(N'wf.execution_scope', N'U') IS NULL
BEGIN
    CREATE TABLE wf.execution_scope (
        id              BIGINT IDENTITY(1,1) NOT NULL,
        set_key         NVARCHAR(64) NOT NULL,
        display_name    NVARCHAR(256) NULL,
        config_json     json NOT NULL CONSTRAINT DF_es_config DEFAULT (N'{}'),
        created_at_utc  DATETIME2(7) NOT NULL CONSTRAINT DF_es_created DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_execution_scope PRIMARY KEY (id),
        CONSTRAINT UQ_es_set_key UNIQUE (set_key)
    );
    CREATE INDEX IX_es_set_key ON wf.execution_scope(set_key);
END
GO

IF COL_LENGTH('wf.workflow_instance', 'execution_scope_id') IS NULL
BEGIN
    ALTER TABLE wf.workflow_instance
        ADD execution_scope_id BIGINT NULL
            CONSTRAINT FK_wi_execution_scope
            REFERENCES wf.execution_scope(id);
    CREATE INDEX IX_wi_execution_scope ON wf.workflow_instance(execution_scope_id);
END
GO

IF OBJECT_ID(N'wf.execution_scope_action_entry', N'U') IS NULL
BEGIN
    CREATE TABLE wf.execution_scope_action_entry (
        id                      BIGINT IDENTITY(1,1) NOT NULL,
        execution_scope_id      BIGINT NOT NULL,
        workflow_instance_id    BIGINT NOT NULL,
        action_name             NVARCHAR(128) NOT NULL,
        run_key                 NVARCHAR(128) NOT NULL CONSTRAINT DF_esae_run_key DEFAULT (N'default'),
        content_key             NVARCHAR(128) NOT NULL,
        recorded_at_utc         DATETIME2(7) NOT NULL CONSTRAINT DF_esae_recorded DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_execution_scope_action_entry PRIMARY KEY (id),
        CONSTRAINT FK_esae_scope FOREIGN KEY (execution_scope_id)
            REFERENCES wf.execution_scope(id) ON DELETE CASCADE,
        CONSTRAINT FK_esae_instance FOREIGN KEY (workflow_instance_id)
            REFERENCES wf.workflow_instance(id) ON DELETE CASCADE,
        CONSTRAINT UQ_esae_scope_action_run UNIQUE (execution_scope_id, action_name, run_key)
    );
    CREATE INDEX IX_esae_instance ON wf.execution_scope_action_entry(workflow_instance_id);
    CREATE INDEX IX_esae_scope ON wf.execution_scope_action_entry(execution_scope_id);
END
GO

/*
  Upsert helper is a PROCEDURE (not a scalar FUNCTION): SQL Server forbids
  INSERT/UPDATE against base tables inside user-defined functions (Msg 443).
  The scope id is returned via the @set_id OUTPUT parameter.
*/
CREATE OR ALTER PROCEDURE wf.wf_repo_upsert_execution_scope
    @set_key NVARCHAR(64),
    @display_name NVARCHAR(256) = NULL,
    @config_json json = NULL,
    @set_id BIGINT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @cfg json = COALESCE(@config_json, N'{}');
    SET @set_id = NULL;

    IF @set_key IS NULL OR LTRIM(RTRIM(@set_key)) = N''
        RETURN;

    SELECT @set_id = es.id
    FROM wf.execution_scope AS es WITH (UPDLOCK, HOLDLOCK)
    WHERE es.set_key = @set_key;

    IF @set_id IS NULL
    BEGIN
        INSERT INTO wf.execution_scope (set_key, display_name, config_json)
        VALUES (@set_key, NULLIF(LTRIM(RTRIM(@display_name)), N''), @cfg);
        SET @set_id = SCOPE_IDENTITY();
    END
    ELSE
    BEGIN
        UPDATE wf.execution_scope
        SET display_name = COALESCE(NULLIF(LTRIM(RTRIM(@display_name)), N''), display_name),
            config_json = @cfg
        WHERE id = @set_id;
    END
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_apply_execution_scope
    @workflow_instance_id BIGINT,
    @set_key NVARCHAR(64),
    @display_name NVARCHAR(256) = NULL,
    @config_json json = NULL,
    @persist_extension BIT = 1
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @set_id BIGINT;
    DECLARE @cfg json = COALESCE(@config_json, N'{}');

    IF @set_key IS NULL OR LTRIM(RTRIM(@set_key)) = N''
        RETURN;

    EXEC wf.wf_repo_upsert_execution_scope
        @set_key = @set_key,
        @display_name = @display_name,
        @config_json = @cfg,
        @set_id = @set_id OUTPUT;

    UPDATE wf.workflow_instance
    SET execution_scope_id = @set_id
    WHERE id = @workflow_instance_id;

    IF @persist_extension = 1
    BEGIN
        DECLARE @ext json = (
            SELECT @set_key AS executionScopeId,
                   @display_name AS executionScopeName,
                   JSON_QUERY(@cfg) AS config
            FOR JSON PATH, WITHOUT_ARRAY_WRAPPER
        );
        EXEC wf.wf_repo_upsert_instance_extension
            @instance_id = @workflow_instance_id,
            @extension_key = N'methyl.execution.scope',
            @data_json = @ext;
    END
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_upsert_execution_scope_action_entry
    @set_key NVARCHAR(64),
    @workflow_instance_id BIGINT,
    @action_name NVARCHAR(128),
    @run_key NVARCHAR(128) = N'default',
    @content_key NVARCHAR(128)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @set_id BIGINT;

    IF @set_key IS NULL OR LTRIM(RTRIM(@set_key)) = N''
       OR @action_name IS NULL OR LTRIM(RTRIM(@action_name)) = N''
       OR @content_key IS NULL OR LTRIM(RTRIM(@content_key)) = N''
        RETURN;

    /* Resolve the scope id; only create (never clobber config_json) when missing. */
    SELECT @set_id = es.id
    FROM wf.execution_scope AS es
    WHERE es.set_key = @set_key;

    IF @set_id IS NULL
        EXEC wf.wf_repo_upsert_execution_scope
            @set_key = @set_key,
            @display_name = NULL,
            @config_json = N'{}',
            @set_id = @set_id OUTPUT;

    IF EXISTS (
        SELECT 1
        FROM wf.execution_scope_action_entry
        WHERE execution_scope_id = @set_id
          AND action_name = @action_name
          AND run_key = COALESCE(NULLIF(LTRIM(RTRIM(@run_key)), N''), N'default')
    )
        UPDATE wf.execution_scope_action_entry
        SET content_key = @content_key,
            workflow_instance_id = @workflow_instance_id,
            recorded_at_utc = SYSUTCDATETIME()
        WHERE execution_scope_id = @set_id
          AND action_name = @action_name
          AND run_key = COALESCE(NULLIF(LTRIM(RTRIM(@run_key)), N''), N'default');
    ELSE
        INSERT INTO wf.execution_scope_action_entry (
            execution_scope_id,
            workflow_instance_id,
            action_name,
            run_key,
            content_key
        ) VALUES (
            @set_id,
            @workflow_instance_id,
            @action_name,
            COALESCE(NULLIF(LTRIM(RTRIM(@run_key)), N''), N'default'),
            @content_key
        );
END;
GO

CREATE OR ALTER FUNCTION wf.wf_repo_get_execution_scope
(
    @set_key NVARCHAR(64)
)
RETURNS TABLE
AS
RETURN
(
    SELECT es.id, es.set_key, es.display_name, es.config_json, es.created_at_utc
    FROM wf.execution_scope AS es
    WHERE es.set_key = @set_key
);
GO

CREATE OR ALTER FUNCTION wf.wf_repo_list_execution_scope_action_entries
(
    @set_key NVARCHAR(64)
)
RETURNS TABLE
AS
RETURN
(
    SELECT e.action_name, e.run_key, e.content_key, e.workflow_instance_id, e.recorded_at_utc
    FROM wf.execution_scope_action_entry AS e
    INNER JOIN wf.execution_scope AS es ON es.id = e.execution_scope_id
    WHERE es.set_key = @set_key
);
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_get_action_submit_context
    @node_execution_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        ne.workflow_instance_id,
        COALESCE(
            JSON_VALUE(wi.context_json, '$.executionScopeId'),
            JSON_VALUE(wi.context_json, '$.hyperparamSetId'),
            es.set_key
        ) AS execution_scope_key,
        wa.action_name,
        ne.input_json
    FROM wf.node_execution AS ne
    INNER JOIN wf.workflow_instance AS wi ON wi.id = ne.workflow_instance_id
    LEFT JOIN wf.execution_scope AS es ON es.id = wi.execution_scope_id
    INNER JOIN wf.workflow_node AS wn ON wn.id = ne.workflow_node_id
    LEFT JOIN wf.workflow_action AS wa ON wa.id = wn.workflow_action_id
    WHERE ne.id = @node_execution_id;
END;
GO
