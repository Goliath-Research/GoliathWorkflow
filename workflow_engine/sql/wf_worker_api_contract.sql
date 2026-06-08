/*
  Contract alignment: sp_worker_submit_result returns single-row result set
  (accepted, instance_status, next_ready_count) per db_objects.yaml.
  Deploy after base MethylPipeline.sql worker API.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

CREATE OR ALTER PROCEDURE wf.sp_worker_submit_result
    @node_execution_id BIGINT,
    @worker_id BIGINT,
    @worker_token NVARCHAR(4000),
    @result_code INT,
    @output_json NVARCHAR(MAX) NULL,
    @accepted BIT = NULL OUTPUT,
    @instance_status VARCHAR(32) = NULL OUTPUT,
    @next_ready_count INT = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    SET @accepted = 0;
    SET @next_ready_count = 0;
    SET @instance_status = NULL;

    EXEC wf.wf_worker_authenticate @worker_id = @worker_id, @worker_token = @worker_token;

    BEGIN TRANSACTION;

    DECLARE @lease_worker BIGINT;
    SELECT @lease_worker = worker_id FROM wf.task_lease WITH (UPDLOCK, HOLDLOCK) WHERE node_execution_id = @node_execution_id;

    IF @lease_worker IS NULL OR @lease_worker <> @worker_id
    BEGIN
        ROLLBACK TRANSACTION;
        SELECT CAST(0 AS BIT) AS accepted, CAST(NULL AS VARCHAR(32)) AS instance_status, 0 AS next_ready_count;
        RETURN;
    END

    DECLARE @cur_status VARCHAR(32);
    SELECT @cur_status = status FROM wf.node_execution WITH (UPDLOCK, HOLDLOCK) WHERE id = @node_execution_id;

    IF @cur_status <> N'RUNNING'
    BEGIN
        ROLLBACK TRANSACTION;
        SELECT CAST(0 AS BIT) AS accepted, CAST(NULL AS VARCHAR(32)) AS instance_status, 0 AS next_ready_count;
        RETURN;
    END

    EXEC wf.wf_engine_on_action_complete
        @action_execution_id = @node_execution_id,
        @result_code = @result_code,
        @output_json = @output_json;

    SET @accepted = 1;

    SELECT @instance_status = status FROM wf.workflow_instance WHERE id = (SELECT workflow_instance_id FROM wf.node_execution WHERE id = @node_execution_id);

    SELECT @next_ready_count = COUNT(*)
    FROM wf.node_execution
    WHERE workflow_instance_id = (SELECT workflow_instance_id FROM wf.node_execution WHERE id = @node_execution_id)
      AND status = N'READY';

    COMMIT TRANSACTION;

    SELECT @accepted AS accepted, @instance_status AS instance_status, @next_ready_count AS next_ready_count;
END;
GO
