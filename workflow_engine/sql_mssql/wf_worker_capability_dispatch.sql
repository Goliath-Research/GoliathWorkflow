-- Capability-authoritative worker claim + enroll hygiene (NVIDIA GH200 fleet).
-- Empty capabilities [] must NOT be treated as omnibus (that let half-enrolled
-- workers claim Align and fail-fast the study). Enroll requires a non-empty
-- capabilities_json from the worker (methyl-worker enroll probes by default).

SET NOCOUNT ON;
GO

CREATE OR ALTER FUNCTION wf.wf_worker_is_omnibus(@capabilities NVARCHAR(MAX))
RETURNS BIT
AS
BEGIN
    -- Only explicit ["*"] is omnibus. NULL / '' / [] mean "no capabilities".
    IF @capabilities IS NULL OR LTRIM(RTRIM(@capabilities)) = N'' OR @capabilities = N'[]'
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

CREATE OR ALTER FUNCTION wf.wf_worker_capability_allowed(
    @worker_capabilities NVARCHAR(MAX),
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
    DECLARE @worker_capabilities NVARCHAR(MAX);
    DECLARE @is_omnibus BIT;
    DECLARE @reclaim_cutoff DATETIME2(7) = DATEADD(SECOND, -60, @now);

    -- Auto-unstick crashed workers: expired/missing leases → READY (quiet: no result set).
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

    SELECT @worker_capabilities = CONVERT(NVARCHAR(MAX), w.capabilities)
    FROM wf.worker AS w
    WHERE w.id = @worker_id;

    SET @is_omnibus = wf.wf_worker_is_omnibus(@worker_capabilities);

    IF @capability IS NOT NULL
       AND @is_omnibus = 0
       AND wf.wf_worker_capability_allowed(@worker_capabilities, @capability) = 0
    BEGIN
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
        ne.iteration_no
    FROM wf.node_execution AS ne
    INNER JOIN wf.workflow_node AS wn ON wn.id = ne.workflow_node_id
    INNER JOIN wf.workflow_action AS wa ON wa.id = wn.workflow_action_id
    WHERE ne.id = @picked;
END;
GO
