/*
  MethylPipeline wf schema - hyperparameter set registry and action result ledger (Azure SQL).

  Prerequisites: base wf schema (workflow_instance)
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'wf.hyperparameter_set', N'U') IS NULL
BEGIN
    CREATE TABLE wf.hyperparameter_set (
        id              BIGINT IDENTITY(1,1) NOT NULL,
        set_key         NVARCHAR(64) NOT NULL,
        display_name    NVARCHAR(256) NULL,
        config_json     json NOT NULL CONSTRAINT DF_hps_config DEFAULT (N'{}'),
        created_at_utc  DATETIME2(7) NOT NULL CONSTRAINT DF_hps_created DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_hyperparameter_set PRIMARY KEY (id),
        CONSTRAINT UQ_hps_set_key UNIQUE (set_key)
    );
    CREATE INDEX IX_hps_set_key ON wf.hyperparameter_set(set_key);
END
GO

IF COL_LENGTH('wf.workflow_instance', 'hyperparameter_set_id') IS NULL
BEGIN
    ALTER TABLE wf.workflow_instance
        ADD hyperparameter_set_id BIGINT NULL
            CONSTRAINT FK_wi_hyperparameter_set
            REFERENCES wf.hyperparameter_set(id);
    CREATE INDEX IX_wi_hyperparameter_set ON wf.workflow_instance(hyperparameter_set_id);
END
GO

IF OBJECT_ID(N'wf.hyperparameter_set_action_entry', N'U') IS NULL
BEGIN
    CREATE TABLE wf.hyperparameter_set_action_entry (
        id                      BIGINT IDENTITY(1,1) NOT NULL,
        hyperparameter_set_id   BIGINT NOT NULL,
        workflow_instance_id    BIGINT NOT NULL,
        action_name             NVARCHAR(128) NOT NULL,
        run_key                 NVARCHAR(128) NOT NULL CONSTRAINT DF_hpse_run_key DEFAULT (N'default'),
        content_key             NVARCHAR(128) NOT NULL,
        recorded_at_utc         DATETIME2(7) NOT NULL CONSTRAINT DF_hpse_recorded DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_hyperparameter_set_action_entry PRIMARY KEY (id),
        CONSTRAINT FK_hpse_set FOREIGN KEY (hyperparameter_set_id)
            REFERENCES wf.hyperparameter_set(id) ON DELETE CASCADE,
        CONSTRAINT FK_hpse_instance FOREIGN KEY (workflow_instance_id)
            REFERENCES wf.workflow_instance(id) ON DELETE CASCADE,
        CONSTRAINT UQ_hpse_set_action_run UNIQUE (hyperparameter_set_id, action_name, run_key)
    );
    CREATE INDEX IX_hpse_instance ON wf.hyperparameter_set_action_entry(workflow_instance_id);
    CREATE INDEX IX_hpse_set ON wf.hyperparameter_set_action_entry(hyperparameter_set_id);
END
GO

CREATE OR ALTER FUNCTION wf.wf_repo_upsert_hyperparameter_set
(
    @set_key NVARCHAR(64),
    @display_name NVARCHAR(256) = NULL,
    @config_json json = NULL
)
RETURNS BIGINT
AS
BEGIN
    DECLARE @id BIGINT;
    DECLARE @cfg json = COALESCE(@config_json, N'{}');

    IF @set_key IS NULL OR LTRIM(RTRIM(@set_key)) = N''
        RETURN NULL;

    SELECT @id = hs.id
    FROM wf.hyperparameter_set AS hs WITH (UPDLOCK, HOLDLOCK)
    WHERE hs.set_key = @set_key;

    IF @id IS NULL
    BEGIN
        INSERT INTO wf.hyperparameter_set (set_key, display_name, config_json)
        VALUES (@set_key, NULLIF(LTRIM(RTRIM(@display_name)), N''), @cfg);
        SET @id = SCOPE_IDENTITY();
    END
    ELSE
    BEGIN
        UPDATE wf.hyperparameter_set
        SET display_name = COALESCE(NULLIF(LTRIM(RTRIM(@display_name)), N''), display_name),
            config_json = @cfg
        WHERE id = @id;
    END

    RETURN @id;
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_apply_hyperparameter_set
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

    SET @set_id = wf.wf_repo_upsert_hyperparameter_set(@set_key, @display_name, @cfg);

    UPDATE wf.workflow_instance
    SET hyperparameter_set_id = @set_id
    WHERE id = @workflow_instance_id;

    IF @persist_extension = 1
    BEGIN
        DECLARE @ext json = (
            SELECT @set_key AS hyperparamSetId,
                   @display_name AS hyperparamSetName,
                   JSON_QUERY(@cfg) AS config
            FOR JSON PATH, WITHOUT_ARRAY_WRAPPER
        );
        EXEC wf.wf_repo_upsert_instance_extension
            @instance_id = @workflow_instance_id,
            @extension_key = N'methyl.hyperparameter.set',
            @data_json = @ext;
    END
END;
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_upsert_hyperparameter_action_entry
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

    SET @set_id = wf.wf_repo_upsert_hyperparameter_set(@set_key, NULL, N'{}');

    IF EXISTS (
        SELECT 1
        FROM wf.hyperparameter_set_action_entry
        WHERE hyperparameter_set_id = @set_id
          AND action_name = @action_name
          AND run_key = COALESCE(NULLIF(LTRIM(RTRIM(@run_key)), N''), N'default')
    )
        UPDATE wf.hyperparameter_set_action_entry
        SET content_key = @content_key,
            workflow_instance_id = @workflow_instance_id,
            recorded_at_utc = SYSUTCDATETIME()
        WHERE hyperparameter_set_id = @set_id
          AND action_name = @action_name
          AND run_key = COALESCE(NULLIF(LTRIM(RTRIM(@run_key)), N''), N'default');
    ELSE
        INSERT INTO wf.hyperparameter_set_action_entry (
            hyperparameter_set_id,
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

CREATE OR ALTER FUNCTION wf.wf_repo_get_hyperparameter_set
(
    @set_key NVARCHAR(64)
)
RETURNS TABLE
AS
RETURN
(
    SELECT hs.id, hs.set_key, hs.display_name, hs.config_json, hs.created_at_utc
    FROM wf.hyperparameter_set AS hs
    WHERE hs.set_key = @set_key
);
GO

CREATE OR ALTER FUNCTION wf.wf_repo_list_hyperparameter_action_entries
(
    @set_key NVARCHAR(64)
)
RETURNS TABLE
AS
RETURN
(
    SELECT e.action_name, e.run_key, e.content_key, e.workflow_instance_id, e.recorded_at_utc
    FROM wf.hyperparameter_set_action_entry AS e
    INNER JOIN wf.hyperparameter_set AS hs ON hs.id = e.hyperparameter_set_id
    WHERE hs.set_key = @set_key
);
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_get_action_submit_context
    @node_execution_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        ne.workflow_instance_id,
        COALESCE(JSON_VALUE(wi.context_json, '$.hyperparamSetId'), hs.set_key) AS hyperparam_set_key,
        wa.action_name,
        ne.input_json
    FROM wf.node_execution AS ne
    INNER JOIN wf.workflow_instance AS wi ON wi.id = ne.workflow_instance_id
    LEFT JOIN wf.hyperparameter_set AS hs ON hs.id = wi.hyperparameter_set_id
    INNER JOIN wf.workflow_node AS wn ON wn.id = ne.workflow_node_id
    LEFT JOIN wf.workflow_action AS wa ON wa.id = wn.workflow_action_id
    WHERE ne.id = @node_execution_id;
END;
GO
