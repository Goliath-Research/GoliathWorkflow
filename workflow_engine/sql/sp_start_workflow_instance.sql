USE MethylPipeline
GO

ALTER PROCEDURE dbo.sp_start_workflow_instance
    @workflow_instance_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @vid BIGINT;
    DECLARE @root BIGINT;

    SELECT @vid = workflow_version_id FROM dbo.workflow_instance WHERE id = @workflow_instance_id;
    SELECT @root = root_node_id FROM dbo.workflow_version WHERE id = @vid;

    IF @root IS NULL
        THROW 50001, N'Workflow version has no root_node_id.', 1;

    UPDATE dbo.workflow_instance
    SET 
      status = N'RUNNING', 
      started_at_utc = SYSUTCDATETIME()
    WHERE id = @workflow_instance_id;

    EXEC dbo.wf_engine_activate
        @workflow_instance_id = @workflow_instance_id,
        @workflow_node_id = @root,
        @parent_node_execution_id = NULL,
        @iteration_no = 0,
        @sequence_index = NULL,
        @parallel_index = NULL;
END;
GO