/*
  Instance task monitor + operator retry (Azure SQL).

  Redeclares portal.sp_get_instance_tasks with engine_error_*, affinity, lease,
  and source URI columns. Adds:
    portal.sp_get_node_execution_detail
    portal.sp_retry_failed_node

  Deploy after portal_workflow_api.sql and wf_action_dispatch_affinity.sql.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

CREATE OR ALTER PROCEDURE portal.sp_get_instance_tasks
    @workflow_instance_id bigint
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        ne.id AS node_execution_id,
        ne.status,
        ne.result_code,
        ne.attempt_no,
        ne.engine_error_code,
        ne.engine_error_message,
        wn.node_key,
        wa.action_name,
        wa.capability,
        CAST(ISNULL(wa.can_stop, 1) AS bit) AS can_stop,
        CAST(ISNULL(wa.can_pause, 0) AS bit) AS can_pause,
        ne.affinity_key,
        ne.completed_by_worker_id,
        tl.worker_id AS lease_worker_id,
        tl.lease_expires_at_utc,
        COALESCE(
            JSON_VALUE(CAST(ne.input_json AS nvarchar(max)), '$.fastqStorage.uri'),
            JSON_VALUE(CAST(ne.input_json AS nvarchar(max)), '$.fastqSource.uri'),
            JSON_VALUE(CAST(ne.input_json AS nvarchar(max)), '$.sourceUri'),
            JSON_VALUE(CAST(ne.input_json AS nvarchar(max)), '$.uri'),
            JSON_VALUE(CAST(ne.input_json AS nvarchar(max)), '$.fastqStorage')
        ) AS source_uri,
        ne.input_json,
        ne.output_json,
        ne.started_at_utc,
        ne.ended_at_utc AS completed_at_utc
    FROM wf.node_execution ne
    INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
    LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
    LEFT JOIN wf.task_lease tl ON tl.node_execution_id = ne.id
    WHERE ne.workflow_instance_id = @workflow_instance_id
    ORDER BY ne.id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_node_execution_detail
    @node_execution_id bigint
AS
BEGIN
    SET NOCOUNT ON;

    IF @node_execution_id IS NULL OR @node_execution_id <= 0
        THROW 50001, N'node_execution_id is required.', 1;

    SELECT
        ne.id AS node_execution_id,
        ne.workflow_instance_id,
        i.status AS instance_status,
        ne.status,
        ne.result_code,
        ne.attempt_no,
        ne.engine_error_code,
        ne.engine_error_message,
        wn.node_key,
        wa.action_name,
        wa.capability,
        CAST(ISNULL(wa.can_stop, 1) AS bit) AS can_stop,
        CAST(ISNULL(wa.can_pause, 0) AS bit) AS can_pause,
        ne.affinity_key,
        ne.completed_by_worker_id,
        tl.worker_id AS lease_worker_id,
        tl.lease_expires_at_utc,
        COALESCE(
            JSON_VALUE(CAST(ne.input_json AS nvarchar(max)), '$.fastqStorage.uri'),
            JSON_VALUE(CAST(ne.input_json AS nvarchar(max)), '$.fastqSource.uri'),
            JSON_VALUE(CAST(ne.input_json AS nvarchar(max)), '$.sourceUri'),
            JSON_VALUE(CAST(ne.input_json AS nvarchar(max)), '$.uri'),
            JSON_VALUE(CAST(ne.input_json AS nvarchar(max)), '$.fastqStorage')
        ) AS source_uri,
        LEFT(CAST(ne.output_json AS nvarchar(max)), 4000) AS output_json_excerpt,
        ne.input_json,
        ne.output_json,
        ne.started_at_utc,
        ne.ended_at_utc AS completed_at_utc
    FROM wf.node_execution ne
    INNER JOIN wf.workflow_instance i ON i.id = ne.workflow_instance_id
    INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
    LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
    LEFT JOIN wf.task_lease tl ON tl.node_execution_id = ne.id
    WHERE ne.id = @node_execution_id;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_retry_failed_node
    @node_execution_id bigint
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @node_execution_id IS NULL OR @node_execution_id <= 0
        THROW 50001, N'node_execution_id is required.', 1;

    DECLARE @status varchar(32);
    DECLARE @instance_id bigint;
    DECLARE @instance_status varchar(32);

    BEGIN TRAN;

    SELECT
        @status = ne.status,
        @instance_id = ne.workflow_instance_id
    FROM wf.node_execution ne WITH (UPDLOCK, ROWLOCK)
    WHERE ne.id = @node_execution_id;

    IF @instance_id IS NULL
        THROW 50010, N'node_execution not found.', 1;

    IF @status <> N'FAILED'
        THROW 50021, N'Only FAILED tasks can be retried (set READY).', 1;

    DELETE FROM wf.task_lease WHERE node_execution_id = @node_execution_id;

    UPDATE wf.node_execution
    SET status = N'READY',
        attempt_no = ISNULL(attempt_no, 1) + 1,
        started_at_utc = NULL,
        ended_at_utc = NULL,
        result_code = NULL,
        engine_error_code = NULL,
        engine_error_message = NULL
    WHERE id = @node_execution_id;

    SELECT @instance_status = status
    FROM wf.workflow_instance WITH (UPDLOCK, ROWLOCK)
    WHERE id = @instance_id;

    IF @instance_status = N'FAILED'
    BEGIN
        UPDATE wf.workflow_instance
        SET status = N'RUNNING',
            completed_at_utc = NULL
        WHERE id = @instance_id;
    END

    COMMIT;

    SELECT
        ne.id AS node_execution_id,
        ne.status,
        ne.attempt_no,
        i.status AS instance_status
    FROM wf.node_execution ne
    INNER JOIN wf.workflow_instance i ON i.id = ne.workflow_instance_id
    WHERE ne.id = @node_execution_id;
END
GO
