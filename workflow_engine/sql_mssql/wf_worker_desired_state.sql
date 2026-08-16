/*
  Additive: wf.worker.desired_state + claim/heartbeat control ACK + portal SP.
*/
SET NOCOUNT ON;
GO

IF COL_LENGTH('wf.worker', 'desired_state') IS NULL
BEGIN
    ALTER TABLE wf.worker ADD desired_state varchar(32) NOT NULL
        CONSTRAINT DF_worker_desired_state DEFAULT ('ACTIVE');
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_worker_desired_state' AND parent_object_id = OBJECT_ID(N'wf.worker')
)
BEGIN
    ALTER TABLE wf.worker WITH CHECK
    ADD CONSTRAINT CK_worker_desired_state
    CHECK (desired_state IN ('ACTIVE', 'DRAINING', 'STOPPING'));
END
GO

CREATE OR ALTER PROCEDURE portal.sp_set_worker_desired_state
    @worker_id BIGINT = NULL,
    @desired_state VARCHAR(32),
    @cluster_id BIGINT = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @state VARCHAR(32) = UPPER(LTRIM(RTRIM(@desired_state)));
    IF @state NOT IN ('ACTIVE', 'DRAINING', 'STOPPING')
        THROW 50201, N'desired_state must be ACTIVE, DRAINING, or STOPPING', 1;

    IF @worker_id IS NOT NULL
    BEGIN
        UPDATE wf.worker
        SET desired_state = @state,
            updated_at_utc = SYSUTCDATETIME()
        WHERE id = @worker_id
          AND (@cluster_id IS NULL OR cluster_id = @cluster_id);

        SELECT id AS worker_id, desired_state, @@ROWCOUNT AS rows_updated
        FROM wf.worker
        WHERE id = @worker_id;
        RETURN;
    END

    IF @cluster_id IS NULL
        THROW 50202, N'worker_id or cluster_id is required', 1;

    UPDATE wf.worker
    SET desired_state = @state,
        updated_at_utc = SYSUTCDATETIME()
    WHERE cluster_id = @cluster_id;

    SELECT id AS worker_id, desired_state, @@ROWCOUNT AS rows_updated
    FROM wf.worker
    WHERE cluster_id = @cluster_id
    ORDER BY id;
END
GO

CREATE OR ALTER PROCEDURE wf.sp_worker_heartbeat
    @node_execution_id BIGINT,
    @worker_id BIGINT,
    @worker_token NVARCHAR(4000),
    @extend_seconds INT = 300
AS
BEGIN
    SET NOCOUNT ON;

    EXEC wf.wf_worker_authenticate @worker_id = @worker_id, @worker_token = @worker_token;

    DECLARE @now DATETIME2(7) = SYSUTCDATETIME();
    DECLARE @desired_state VARCHAR(32) = N'ACTIVE';
    DECLARE @command VARCHAR(32) = N'NONE';

    UPDATE tl
    SET lease_expires_at_utc = DATEADD(SECOND, @extend_seconds, @now),
        heartbeat_at_utc = @now
    FROM wf.task_lease AS tl
    WHERE tl.node_execution_id = @node_execution_id AND tl.worker_id = @worker_id;

    DECLARE @rows INT = @@ROWCOUNT;

    SELECT @desired_state = COALESCE(w.desired_state, N'ACTIVE')
    FROM wf.worker AS w
    WHERE w.id = @worker_id;

    SET @command = CASE @desired_state
        WHEN N'DRAINING' THEN N'DRAIN'
        WHEN N'STOPPING' THEN N'STOP'
        ELSE N'NONE'
    END;

    SELECT @rows AS rows_updated, @desired_state AS desired_state, @command AS command;
END
GO

-- NOTE: Soft affinity ORDER BY / completed_by_worker_id are applied by
-- wf_action_dispatch_affinity.sql (deployed after this file), which replaces
-- this procedure. Keep the FIFO body below for intermediate deploy steps.
CREATE OR ALTER PROCEDURE wf.sp_worker_request_task
    @worker_id BIGINT,
    @worker_token NVARCHAR(4000),
    @capability NVARCHAR(128) NULL,
    @max_lease_seconds INT = 300
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    EXEC wf.wf_worker_authenticate @worker_id = @worker_id, @worker_token = @worker_token;

    DECLARE @now DATETIME2(7) = SYSUTCDATETIME();
    DECLARE @lease_end DATETIME2(7) = DATEADD(SECOND, @max_lease_seconds, @now);
    DECLARE @worker_capabilities json;
    DECLARE @is_omnibus BIT;
    DECLARE @reclaim_cutoff DATETIME2(7) = DATEADD(SECOND, -60, @now);
    DECLARE @desired_state VARCHAR(32) = N'ACTIVE';
    DECLARE @command VARCHAR(32) = N'NONE';

    IF EXISTS (
        SELECT 1
        FROM wf.node_execution AS ne
        LEFT JOIN wf.task_lease AS l ON l.node_execution_id = ne.id
        WHERE ne.status = N'RUNNING'
          AND (
                l.node_execution_id IS NULL
             OR l.lease_expires_at_utc <= @reclaim_cutoff
          )
    )
    BEGIN
        EXEC wf.sp_reclaim_expired_leases @grace_seconds = 60, @quiet = 1;
    END

    SELECT
        @worker_capabilities = w.capabilities,
        @desired_state = COALESCE(w.desired_state, N'ACTIVE')
    FROM wf.worker AS w
    WHERE w.id = @worker_id;

    SET @command = CASE @desired_state
        WHEN N'DRAINING' THEN N'DRAIN'
        WHEN N'STOPPING' THEN N'STOP'
        ELSE N'NONE'
    END;

    IF @desired_state IN (N'DRAINING', N'STOPPING')
    BEGIN
        SELECT
            CAST(NULL AS BIGINT) AS node_execution_id,
            CAST(NULL AS BIGINT) AS workflow_instance_id,
            CAST(NULL AS NVARCHAR(256)) AS node_key,
            CAST(NULL AS NVARCHAR(256)) AS action_name,
            CAST(NULL AS NVARCHAR(128)) AS capability,
            CAST(NULL AS INT) AS attempt_no,
            CAST(NULL AS json) AS input_json,
            CAST(NULL AS INT) AS iteration_no,
            @desired_state AS desired_state,
            @command AS command;
        RETURN;
    END

    -- Catalog dispatch: exclusive_worker action already leased → no further claims.
    IF EXISTS (
        SELECT 1
        FROM wf.task_lease AS tl
        INNER JOIN wf.node_execution AS ne ON ne.id = tl.node_execution_id
        INNER JOIN wf.workflow_node AS wn ON wn.id = ne.workflow_node_id
        INNER JOIN wf.workflow_action AS wa ON wa.id = wn.workflow_action_id
        WHERE tl.worker_id = @worker_id
          AND tl.lease_expires_at_utc > @now
          AND ISNULL(wa.exclusive_worker, 0) = 1
    )
    BEGIN
        SELECT
            CAST(NULL AS BIGINT) AS node_execution_id,
            CAST(NULL AS BIGINT) AS workflow_instance_id,
            CAST(NULL AS NVARCHAR(256)) AS node_key,
            CAST(NULL AS NVARCHAR(256)) AS action_name,
            CAST(NULL AS NVARCHAR(128)) AS capability,
            CAST(NULL AS INT) AS attempt_no,
            CAST(NULL AS json) AS input_json,
            CAST(NULL AS INT) AS iteration_no,
            @desired_state AS desired_state,
            @command AS command;
        RETURN;
    END

    SET @is_omnibus = wf.wf_worker_is_omnibus(@worker_capabilities);

    IF @capability IS NOT NULL
       AND @is_omnibus = 0
       AND wf.wf_worker_capability_allowed(@worker_capabilities, @capability) = 0
    BEGIN
        SELECT
            CAST(NULL AS BIGINT) AS node_execution_id,
            CAST(NULL AS BIGINT) AS workflow_instance_id,
            CAST(NULL AS NVARCHAR(256)) AS node_key,
            CAST(NULL AS NVARCHAR(256)) AS action_name,
            CAST(NULL AS NVARCHAR(128)) AS capability,
            CAST(NULL AS INT) AS attempt_no,
            CAST(NULL AS json) AS input_json,
            CAST(NULL AS INT) AS iteration_no,
            @desired_state AS desired_state,
            @command AS command;
        RETURN;
    END

    BEGIN TRANSACTION;

    DECLARE @picked_ids TABLE (id BIGINT);

    ;WITH cte AS (
        SELECT TOP (1) ne.id
        FROM wf.node_execution AS ne WITH (ROWLOCK, READPAST, UPDLOCK)
        INNER JOIN wf.workflow_node AS wn ON wn.id = ne.workflow_node_id
        INNER JOIN wf.workflow_action AS wa ON wa.id = wn.workflow_action_id
        INNER JOIN wf.workflow_instance AS wi ON wi.id = ne.workflow_instance_id
        WHERE ne.status = N'READY'
          AND ne.input_json IS NOT NULL
          AND wn.node_type = N'ACTION'
          AND wi.status = N'RUNNING'
          AND (ne.available_at_utc IS NULL OR ne.available_at_utc <= @now)
          AND wf.wf_worker_capability_allowed(@worker_capabilities, wa.capability) = 1
          AND (
              @capability IS NULL
              OR wa.capability = @capability
              OR wa.capability IS NULL
          )
          -- exclusive_worker candidate requires an idle worker (no live leases).
          AND (
              ISNULL(wa.exclusive_worker, 0) = 0
              OR NOT EXISTS (
                  SELECT 1
                  FROM wf.task_lease AS tl_idle
                  WHERE tl_idle.worker_id = @worker_id
                    AND tl_idle.lease_expires_at_utc > @now
              )
          )
          -- max_per_worker: cap concurrent leases of this action on the worker.
          AND (
              wa.max_per_worker IS NULL
              OR (
                  SELECT COUNT(*)
                  FROM wf.task_lease AS tl_cap
                  INNER JOIN wf.node_execution AS ne_cap ON ne_cap.id = tl_cap.node_execution_id
                  INNER JOIN wf.workflow_node AS wn_cap ON wn_cap.id = ne_cap.workflow_node_id
                  WHERE tl_cap.worker_id = @worker_id
                    AND tl_cap.lease_expires_at_utc > @now
                    AND wn_cap.workflow_action_id = wa.id
              ) < wa.max_per_worker
          )
        ORDER BY ne.available_at_utc ASC, ne.id ASC
    )
    UPDATE ne
    SET status = N'RUNNING',
        started_at_utc = @now
    OUTPUT inserted.id INTO @picked_ids(id)
    FROM wf.node_execution AS ne
    INNER JOIN cte ON cte.id = ne.id;

    DECLARE @picked BIGINT;
    SELECT @picked = id FROM @picked_ids;

    IF @picked IS NULL
    BEGIN
        ROLLBACK TRANSACTION;
        SELECT
            CAST(NULL AS BIGINT) AS node_execution_id,
            CAST(NULL AS BIGINT) AS workflow_instance_id,
            CAST(NULL AS NVARCHAR(256)) AS node_key,
            CAST(NULL AS NVARCHAR(256)) AS action_name,
            CAST(NULL AS NVARCHAR(128)) AS capability,
            CAST(NULL AS INT) AS attempt_no,
            CAST(NULL AS json) AS input_json,
            CAST(NULL AS INT) AS iteration_no,
            @desired_state AS desired_state,
            @command AS command;
        RETURN;
    END

    ;MERGE wf.task_lease AS t
    USING (SELECT @picked AS node_execution_id) AS s ON (t.node_execution_id = s.node_execution_id)
    WHEN MATCHED THEN
        UPDATE SET worker_id = @worker_id, lease_expires_at_utc = @lease_end, heartbeat_at_utc = @now
    WHEN NOT MATCHED THEN
        INSERT (node_execution_id, worker_id, lease_expires_at_utc, heartbeat_at_utc)
        VALUES (@picked, @worker_id, @lease_end, @now);

    COMMIT TRANSACTION;

    SELECT
        ne.id AS node_execution_id,
        ne.workflow_instance_id,
        wn.node_key,
        wa.action_name,
        wa.capability,
        ne.attempt_no,
        ne.input_json,
        ne.iteration_no,
        @desired_state AS desired_state,
        @command AS command
    FROM wf.node_execution AS ne
    INNER JOIN wf.workflow_node AS wn ON wn.id = ne.workflow_node_id
    INNER JOIN wf.workflow_action AS wa ON wa.id = wn.workflow_action_id
    WHERE ne.id = @picked;
END
GO
