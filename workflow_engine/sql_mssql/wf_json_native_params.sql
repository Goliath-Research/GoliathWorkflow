/*
  Native json parameters for engine + worker submit (replaces NVARCHAR JSON shims).

  Deploy before wf_worker_api_contract.sql on Azure SQL databases that still use
  @output_json NVARCHAR(MAX) from the base MethylPipeline bundle.

  Prerequisites: wf schema with json columns on workflow_instance / node_execution.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

CREATE OR ALTER PROCEDURE wf.wf_engine_on_action_complete
    @action_execution_id BIGINT,
    @result_code INT,
    @output_json json NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @inst BIGINT;
    DECLARE @wn BIGINT;
    DECLARE @parent BIGINT;

    SELECT @inst = workflow_instance_id, @wn = workflow_node_id, @parent = parent_node_execution_id
    FROM wf.node_execution WHERE id = @action_execution_id;

    IF @result_code < 0
    BEGIN
        UPDATE wf.node_execution
        SET status = N'FAILED',
            result_code = @result_code,
            output_json = @output_json,
            ended_at_utc = SYSUTCDATETIME(),
            engine_error_code = @result_code
        WHERE id = @action_execution_id;

        DELETE FROM wf.task_lease WHERE node_execution_id = @action_execution_id;

        UPDATE wf.workflow_instance
        SET status = N'FAILED', completed_at_utc = SYSUTCDATETIME()
        WHERE id = @inst;

        RETURN;
    END

    UPDATE wf.node_execution
    SET status = N'SUCCEEDED',
        result_code = @result_code,
        output_json = @output_json,
        ended_at_utc = SYSUTCDATETIME()
    WHERE id = @action_execution_id;

    DELETE FROM wf.task_lease WHERE node_execution_id = @action_execution_id;

    IF @parent IS NULL
    BEGIN
        UPDATE wf.workflow_instance SET status = N'COMPLETED', completed_at_utc = SYSUTCDATETIME() WHERE id = @inst;
        RETURN;
    END

    DECLARE @ptype VARCHAR(32);
    SELECT @ptype = wn.node_type
    FROM wf.node_execution AS ne
    INNER JOIN wf.workflow_node AS wn ON wn.id = ne.workflow_node_id
    WHERE ne.id = @parent;

    IF @ptype = N'SEQUENCE'
        EXEC wf.wf_sequence_continue @sequence_execution_id = @parent;

    ELSE IF @ptype = N'PARALLEL'
        EXEC wf.wf_parallel_continue @parallel_execution_id = @parent;

    ELSE IF @ptype IN (N'IF', N'SWITCH')
    BEGIN
        UPDATE wf.node_execution SET status = N'SUCCEEDED', ended_at_utc = SYSUTCDATETIME() WHERE id = @parent;
        EXEC wf.wf_engine_on_composite_complete @node_execution_id = @parent;
    END

    ELSE IF @ptype = N'REPEAT'
        EXEC wf.wf_repeat_continue @repeat_execution_id = @parent;

    ELSE IF @ptype = N'WHILE'
        EXEC wf.wf_while_continue @while_execution_id = @parent;

    /* FOREACH parents (direct ACTION body) dispatch through the router so this script
       can be re-applied without dropping FOREACH continuation. */
    ELSE IF @ptype = N'FOREACH'
        EXEC wf.wf_foreach_route_continue @foreach_execution_id = @parent;
END;
GO
