-- Capability-authoritative worker claim + enroll hygiene (NVIDIA GH200 fleet).
-- Contracts stay native JSON (MSSQL json / PG jsonb), not NVARCHAR string bags.
-- Empty capabilities [] must NOT be treated as omnibus. Enroll requires a
-- non-empty capabilities payload from the worker (methyl-worker enroll probes).
-- Claim result includes desired_state/command (see wf_worker_desired_state.sql).

SET NOCOUNT ON;
GO

-- Parameter type change NVARCHAR→json: recreate (CREATE OR ALTER cannot retarget types).
-- Drop dependents first (request_task references these functions).
IF OBJECT_ID(N'wf.sp_worker_request_task', N'P') IS NOT NULL
    DROP PROCEDURE wf.sp_worker_request_task;
IF OBJECT_ID(N'wf.wf_worker_capability_allowed', N'FN') IS NOT NULL
    DROP FUNCTION wf.wf_worker_capability_allowed;
IF OBJECT_ID(N'wf.wf_worker_is_omnibus', N'FN') IS NOT NULL
    DROP FUNCTION wf.wf_worker_is_omnibus;
GO

CREATE FUNCTION wf.wf_worker_is_omnibus(@capabilities json)
RETURNS BIT
AS
BEGIN
    -- Only explicit ["*"] is omnibus. NULL / [] mean "no capabilities".
    IF @capabilities IS NULL
        RETURN 0;
    IF NOT EXISTS (SELECT 1 FROM OPENJSON(@capabilities))
        RETURN 0;
    IF EXISTS (
        SELECT 1
        FROM OPENJSON(@capabilities) WITH (value NVARCHAR(128) '$') AS caps
        WHERE caps.value = N'*'
    )
        RETURN 1;
    RETURN 0;
END;
GO

CREATE FUNCTION wf.wf_worker_capability_allowed(
    @worker_capabilities json,
    @task_capability NVARCHAR(128)
)
RETURNS BIT
AS
BEGIN
    IF @task_capability IS NULL
        RETURN 1;
    IF wf.wf_worker_is_omnibus(@worker_capabilities) = 1
        RETURN 1;
    IF EXISTS (
        SELECT 1
        FROM OPENJSON(@worker_capabilities) WITH (value NVARCHAR(128) '$') AS caps
        WHERE caps.value = @task_capability
    )
        RETURN 1;
    RETURN 0;
END;
GO

-- Full body lives in wf_worker_desired_state.sql (desired_state ACK). Re-apply that script
-- after this file if both are deployed, or deploy wf_worker_desired_state.sql last.
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
