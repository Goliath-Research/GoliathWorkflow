/*
  Reclaim RUNNING node_executions whose task_lease has expired (or is missing).

  Workers only claim READY rows. A crash/restart leaves RUNNING + stale lease
  stranded forever unless this procedure (or manual SQL) runs.

  Safe for long Align jobs while heartbeats renew the lease. Do not call with
  @grace_seconds that is shorter than normal heartbeat jitter without cause.

  Portal UI / ops: EXEC portal.sp_reclaim_expired_leases
    @workflow_instance_id = 59,   -- optional
    @grace_seconds = 60;
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

CREATE OR ALTER PROCEDURE wf.sp_reclaim_expired_leases
    @workflow_instance_id BIGINT = NULL,
    @grace_seconds INT = 60
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @grace_seconds < 0 SET @grace_seconds = 0;

    DECLARE @cutoff DATETIME2(7) = DATEADD(SECOND, -@grace_seconds, SYSUTCDATETIME());
    DECLARE @reclaimed TABLE (
        node_execution_id BIGINT NOT NULL,
        workflow_instance_id BIGINT NOT NULL,
        previous_worker_id BIGINT NULL,
        lease_expired_at_utc DATETIME2(7) NULL
    );

    BEGIN TRANSACTION;

    ;WITH expired AS (
        SELECT ne.id AS node_execution_id,
               ne.workflow_instance_id,
               l.worker_id AS previous_worker_id,
               l.lease_expires_at_utc
        FROM wf.node_execution AS ne
        LEFT JOIN wf.task_lease AS l ON l.node_execution_id = ne.id
        WHERE ne.status = N'RUNNING'
          AND (
                l.node_execution_id IS NULL
             OR l.lease_expires_at_utc <= @cutoff
          )
          AND (@workflow_instance_id IS NULL OR ne.workflow_instance_id = @workflow_instance_id)
    )
    UPDATE ne
    SET status = N'READY',
        result_code = NULL,
        engine_error_code = NULL,
        engine_error_message = N'reclaimed: lease expired or missing',
        output_json = NULL,
        started_at_utc = NULL,
        ended_at_utc = NULL,
        attempt_no = ISNULL(ne.attempt_no, 0) + 1,
        available_at_utc = SYSUTCDATETIME()
    OUTPUT inserted.id, inserted.workflow_instance_id, e.previous_worker_id, e.lease_expires_at_utc
    INTO @reclaimed (node_execution_id, workflow_instance_id, previous_worker_id, lease_expired_at_utc)
    FROM wf.node_execution AS ne
    INNER JOIN expired AS e ON e.node_execution_id = ne.id
    WHERE ne.status = N'RUNNING';

    DELETE l
    FROM wf.task_lease AS l
    INNER JOIN @reclaimed AS r ON r.node_execution_id = l.node_execution_id;

    COMMIT TRANSACTION;

    SELECT node_execution_id,
           workflow_instance_id,
           previous_worker_id,
           lease_expired_at_utc,
           SYSUTCDATETIME() AS reclaimed_at_utc
    FROM @reclaimed
    ORDER BY node_execution_id;
END;
GO

CREATE OR ALTER PROCEDURE portal.sp_reclaim_expired_leases
    @workflow_instance_id BIGINT = NULL,
    @grace_seconds INT = 60
AS
BEGIN
    SET NOCOUNT ON;
    EXEC wf.sp_reclaim_expired_leases
        @workflow_instance_id = @workflow_instance_id,
        @grace_seconds = @grace_seconds;
END;
GO
