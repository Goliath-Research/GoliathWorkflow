/*
  cfg hyperparameter search ledger + portal API (Azure SQL).

  The portal UI owns the notion of a "hyperparameter search": a grid of trials,
  each of which becomes one wf.workflow_instance bound to a process-agnostic
  wf.execution_scope. These cfg tables give the UI a typed, queryable record of
  the search, its grid, and the trial -> instance mapping. wf stays agnostic.

  EpiPortal calls the portal.sp_* procedures directly (never the REST gateway).
  Grid/overlay JSON conforms to the exported Pydantic schemas
  (schemas/config/hyperparam_*.schema.json).

  Prerequisites:
  - cfg_schema.sql, cfg_registry_tables.sql (cfg.study)
  - wf_execution_scope.sql (wf.execution_scope), wf workflow_instance
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF SCHEMA_ID(N'portal') IS NULL
    EXEC(N'CREATE SCHEMA portal');
GO

IF OBJECT_ID(N'cfg.hyperparameter_search_run', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.hyperparameter_search_run (
        id                  BIGINT IDENTITY(1,1) NOT NULL,
        study_row_id        BIGINT NULL,
        display_name        NVARCHAR(256) NULL,
        base_context_hash   NVARCHAR(128) NULL,
        grid_json           json NOT NULL CONSTRAINT DF_hsr_grid DEFAULT (N'{}'),
        objective_json      json NOT NULL CONSTRAINT DF_hsr_obj DEFAULT (N'{}'),
        status              NVARCHAR(32) NOT NULL CONSTRAINT DF_hsr_status DEFAULT (N'created'),
        created_by          NVARCHAR(256) NULL,
        created_at_utc      DATETIME2(7) NOT NULL CONSTRAINT DF_hsr_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc      DATETIME2(7) NOT NULL CONSTRAINT DF_hsr_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_hyperparameter_search_run PRIMARY KEY (id),
        CONSTRAINT FK_hsr_study FOREIGN KEY (study_row_id) REFERENCES cfg.study(id),
        CONSTRAINT CK_hsr_status CHECK (status IN (
            N'created', N'running', N'completed', N'failed', N'cancelled'
        ))
    );
    CREATE INDEX IX_hsr_study ON cfg.hyperparameter_search_run(study_row_id);
END
GO

IF OBJECT_ID(N'cfg.hyperparameter_trial', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.hyperparameter_trial (
        id                      BIGINT IDENTITY(1,1) NOT NULL,
        search_id               BIGINT NOT NULL,
        trial_index             INT NOT NULL,
        overrides_json          json NOT NULL CONSTRAINT DF_ht_overrides DEFAULT (N'{}'),
        workflow_instance_id    BIGINT NULL,
        execution_scope_key     NVARCHAR(64) NULL,
        status                  NVARCHAR(32) NOT NULL CONSTRAINT DF_ht_status DEFAULT (N'pending'),
        objective               FLOAT NULL,
        feasible                BIT NULL,
        result_json             json NULL,
        created_at_utc          DATETIME2(7) NOT NULL CONSTRAINT DF_ht_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc          DATETIME2(7) NOT NULL CONSTRAINT DF_ht_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_hyperparameter_trial PRIMARY KEY (id),
        CONSTRAINT FK_ht_search FOREIGN KEY (search_id)
            REFERENCES cfg.hyperparameter_search_run(id) ON DELETE CASCADE,
        CONSTRAINT FK_ht_instance FOREIGN KEY (workflow_instance_id)
            REFERENCES wf.workflow_instance(id),
        CONSTRAINT UQ_ht_search_index UNIQUE (search_id, trial_index)
    );
    CREATE INDEX IX_ht_search ON cfg.hyperparameter_trial(search_id);
    CREATE INDEX IX_ht_instance ON cfg.hyperparameter_trial(workflow_instance_id);
END
GO

/*
  Create a search run and return its id. Instance creation happens in the portal
  middle-tier (Python) because finalization is an in-process step; trials are then
  recorded via portal.sp_add_hyperparam_trial.
*/
CREATE OR ALTER PROCEDURE portal.sp_start_hyperparam_grid
    @study_row_id BIGINT = NULL,
    @display_name NVARCHAR(256) = NULL,
    @grid_json json = NULL,
    @objective_json json = NULL,
    @base_context_hash NVARCHAR(128) = NULL,
    @created_by NVARCHAR(256) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO cfg.hyperparameter_search_run (
        study_row_id, display_name, base_context_hash, grid_json, objective_json, status, created_by
    ) VALUES (
        @study_row_id,
        NULLIF(LTRIM(RTRIM(@display_name)), N''),
        @base_context_hash,
        COALESCE(@grid_json, N'{}'),
        COALESCE(@objective_json, N'{}'),
        N'running',
        @created_by
    );

    SELECT CAST(SCOPE_IDENTITY() AS BIGINT) AS search_id;
END;
GO

CREATE OR ALTER PROCEDURE portal.sp_add_hyperparam_trial
    @search_id BIGINT,
    @trial_index INT,
    @overrides_json json = NULL,
    @workflow_instance_id BIGINT = NULL,
    @execution_scope_key NVARCHAR(64) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF EXISTS (
        SELECT 1 FROM cfg.hyperparameter_trial
        WHERE search_id = @search_id AND trial_index = @trial_index
    )
        UPDATE cfg.hyperparameter_trial
        SET overrides_json = COALESCE(@overrides_json, N'{}'),
            workflow_instance_id = @workflow_instance_id,
            execution_scope_key = @execution_scope_key,
            status = N'started',
            updated_at_utc = SYSUTCDATETIME()
        WHERE search_id = @search_id AND trial_index = @trial_index;
    ELSE
        INSERT INTO cfg.hyperparameter_trial (
            search_id, trial_index, overrides_json, workflow_instance_id, execution_scope_key, status
        ) VALUES (
            @search_id,
            @trial_index,
            COALESCE(@overrides_json, N'{}'),
            @workflow_instance_id,
            @execution_scope_key,
            N'started'
        );
END;
GO

CREATE OR ALTER PROCEDURE portal.sp_score_hyperparam_trial
    @search_id BIGINT,
    @trial_index INT,
    @objective FLOAT = NULL,
    @feasible BIT = NULL,
    @result_json json = NULL
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE cfg.hyperparameter_trial
    SET objective = @objective,
        feasible = @feasible,
        result_json = @result_json,
        status = N'scored',
        updated_at_utc = SYSUTCDATETIME()
    WHERE search_id = @search_id AND trial_index = @trial_index;
END;
GO

CREATE OR ALTER PROCEDURE portal.sp_set_hyperparam_search_status
    @search_id BIGINT,
    @status NVARCHAR(32)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE cfg.hyperparameter_search_run
    SET status = @status,
        updated_at_utc = SYSUTCDATETIME()
    WHERE id = @search_id;
END;
GO

/* Apply dotted trial overrides onto an existing nested actionConfig.
   Same semantics as workflow_engine.ops.hyperparam_grid.apply_overlay:
   key "validation.stability_dmp_freq" sets actionConfig.validation.stability_dmp_freq;
   JSON null deletes that leaf. Does not replace sibling guardrails. */
CREATE OR ALTER FUNCTION portal.fn_apply_dotted_action_config(
    @base nvarchar(max),
    @overrides nvarchar(max)
)
RETURNS nvarchar(max)
AS
BEGIN
    DECLARE @cur nvarchar(max) = @base;
    IF @cur IS NULL OR ISJSON(@cur) <> 1 OR LEFT(LTRIM(@cur), 1) <> N'{'
        SET @cur = N'{}';
    IF @overrides IS NULL OR ISJSON(@overrides) <> 1 OR LEFT(LTRIM(@overrides), 1) <> N'{'
        RETURN @cur;

    DECLARE @okey nvarchar(400);
    DECLARE @oval nvarchar(max);
    DECLARE @otype int;
    DECLARE @rest nvarchar(400);
    DECLARE @path nvarchar(1000);
    DECLARE @part nvarchar(128);
    DECLARE @dot int;

    DECLARE c CURSOR LOCAL FAST_FORWARD FOR
        SELECT [key], [value], [type] FROM OPENJSON(@overrides);

    OPEN c;
    FETCH NEXT FROM c INTO @okey, @oval, @otype;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @rest = @okey;
        SET @path = N'$';

        WHILE LEN(@rest) > 0
        BEGIN
            SET @dot = CHARINDEX(N'.', @rest);
            IF @dot = 0
            BEGIN
                SET @part = @rest;
                SET @rest = N'';
            END
            ELSE
            BEGIN
                SET @part = LEFT(@rest, @dot - 1);
                SET @rest = SUBSTRING(@rest, @dot + 1, 400);
            END

            IF @part IS NULL OR @part = N''
                CONTINUE;

            SET @path = @path + N'.' + QUOTENAME(@part, N'"');

            IF LEN(@rest) > 0 AND JSON_QUERY(@cur, @path) IS NULL
                SET @cur = JSON_MODIFY(@cur, @path, JSON_QUERY(N'{}'));
        END

        IF @path = N'$'
        BEGIN
            FETCH NEXT FROM c INTO @okey, @oval, @otype;
            CONTINUE;
        END

        IF @otype = 0
            SET @cur = JSON_MODIFY(@cur, @path, NULL);
        ELSE IF @otype = 1
            SET @cur = JSON_MODIFY(@cur, @path, @oval);
        ELSE IF @otype IN (2, 3)
        BEGIN
            /* JSON_MODIFY(float) emits scientific notation; stash a marker then
               splice the original number/bool token so 0.75 stays 0.75. */
            SET @cur = JSON_MODIFY(@cur, @path, N'__mp_json_token__');
            SET @cur = REPLACE(@cur, N'"__mp_json_token__"', @oval);
        END
        ELSE IF @otype IN (4, 5)
            SET @cur = JSON_MODIFY(
                @cur,
                @path,
                JSON_QUERY(@overrides, CONCAT(N'$.', QUOTENAME(@okey, N'"')))
            );

        FETCH NEXT FROM c INTO @okey, @oval, @otype;
    END

    CLOSE c;
    DEALLOCATE c;
    RETURN @cur;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_promote_hyperparam_winner
    @search_id BIGINT,
    @trial_index INT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @study_row_id BIGINT;
    DECLARE @overrides nvarchar(max);
    DECLARE @existing nvarchar(max);
    DECLARE @merged nvarchar(max);

    SELECT @study_row_id = r.study_row_id
    FROM cfg.hyperparameter_search_run r
    WHERE r.id = @search_id;

    IF @study_row_id IS NULL
        THROW 50010, N'search_id not found or has no study_row_id (cannot write a published profile).', 1;

    SELECT @overrides = CAST(t.overrides_json AS nvarchar(max))
    FROM cfg.hyperparameter_trial t
    WHERE t.search_id = @search_id AND t.trial_index = @trial_index;

    IF @overrides IS NULL
        THROW 50010, N'trial not found.', 1;
    IF ISJSON(@overrides) <> 1 OR LEFT(LTRIM(@overrides), 1) <> N'{'
        THROW 50021, N'trial overrides_json must be a JSON object.', 1;

    SELECT @existing = CAST(
        COALESCE(JSON_QUERY(CAST(document_json AS nvarchar(max)), '$.actionConfig'), N'{}')
        AS nvarchar(max)
    )
    FROM cfg.study
    WHERE id = @study_row_id;

    SET @merged = portal.fn_apply_dotted_action_config(@existing, @overrides);

    EXEC portal.sp_set_study_action_config_overlay
        @study_row_id = @study_row_id,
        @action_config_overlay = @merged;

    UPDATE cfg.hyperparameter_trial
    SET result_json = CAST(
            JSON_MODIFY(
                COALESCE(CAST(result_json AS nvarchar(max)), N'{}'),
                '$.promoted',
                CAST(1 AS bit)
            ) AS json
        ),
        updated_at_utc = SYSUTCDATETIME()
    WHERE search_id = @search_id AND trial_index = @trial_index;

    SELECT
        @search_id AS search_id,
        @trial_index AS trial_index,
        @study_row_id AS study_row_id,
        CAST(@merged AS nvarchar(max)) AS action_config_overlay;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_hyperparam_search
    @search_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        r.id AS search_id,
        r.status AS search_status,
        t.trial_index,
        t.overrides_json,
        t.workflow_instance_id,
        t.execution_scope_key,
        i.status AS instance_status,
        t.status AS trial_status,
        t.objective,
        t.feasible
    FROM cfg.hyperparameter_search_run AS r
    LEFT JOIN cfg.hyperparameter_trial AS t ON t.search_id = r.id
    LEFT JOIN wf.workflow_instance AS i ON i.id = t.workflow_instance_id
    WHERE r.id = @search_id
    ORDER BY t.trial_index;
END;
GO
