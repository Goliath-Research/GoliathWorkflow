/*
  Workflow Engine (wf schema) - delete workflow definition and optional runtime data.

  Deletes a workflow definition (all versions, nodes, edges, templates) so a seed
  script can be re-run. Optionally removes all workflow instances first.

  Usage:
    EXEC wf.sp_delete_workflow_def @workflow_name = N'PCaTwoGroupFlow';
    -- then re-run wf_pca_two_group_seed.sql

  Direct DELETE FROM wf.workflow_def fails because of FK constraints (versions,
  instances, edges, root_node_id cycle). Use this procedure instead.

  Prerequisites: base wf schema (MethylPipeline.sql).
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'wf.workflow_def', N'U') IS NULL
BEGIN
    RAISERROR(N'Prerequisite missing: deploy base wf schema first.', 16, 1);
    RETURN;
END
GO

CREATE OR ALTER PROCEDURE wf.sp_delete_workflow_def
    @workflow_def_id BIGINT = NULL,
    @workflow_name NVARCHAR(256) = NULL,
    @delete_instances BIT = 1,
    @force BIT = 0,
    @deleted_instance_count INT = NULL OUTPUT,
    @deleted_version_count INT = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    SET @deleted_instance_count = 0;
    SET @deleted_version_count = 0;

    IF @workflow_def_id IS NULL AND (@workflow_name IS NULL OR LTRIM(RTRIM(@workflow_name)) = N'')
        THROW 50010, N'Provide @workflow_def_id or @workflow_name.', 1;

    IF @workflow_def_id IS NULL
        SELECT @workflow_def_id = id
        FROM wf.workflow_def
        WHERE name = @workflow_name;

    IF @workflow_def_id IS NULL
    BEGIN
        DECLARE @msg NVARCHAR(512) = N'Workflow definition not found.';
        IF @workflow_name IS NOT NULL
            SET @msg = N'Workflow definition not found: ' + @workflow_name;
        THROW 50011, @msg, 1;
    END

    IF OBJECT_ID(N'Contract.ContractWorkflowEntitlements', N'U') IS NOT NULL
       AND EXISTS (
           SELECT 1
           FROM Contract.ContractWorkflowEntitlements
           WHERE WorkflowDefID = @workflow_def_id
       )
    BEGIN
        IF @force = 0
            THROW 50012, N'Contract.ContractWorkflowEntitlements references this workflow. Re-run with @force = 1 to remove entitlements.', 1;

        DELETE FROM Contract.ContractWorkflowEntitlements
        WHERE WorkflowDefID = @workflow_def_id;
    END

    IF OBJECT_ID(N'Contract.WorkflowUsageCounters', N'U') IS NOT NULL
       AND EXISTS (
           SELECT 1
           FROM Contract.WorkflowUsageCounters
           WHERE WorkflowDefID = @workflow_def_id
       )
    BEGIN
        IF @force = 0
            THROW 50013, N'Contract.WorkflowUsageCounters references this workflow. Re-run with @force = 1 to remove usage counters.', 1;

        DELETE FROM Contract.WorkflowUsageCounters
        WHERE WorkflowDefID = @workflow_def_id;
    END

    BEGIN TRANSACTION;

    DECLARE @version_ids TABLE (id BIGINT NOT NULL PRIMARY KEY);
    INSERT INTO @version_ids (id)
    SELECT id FROM wf.workflow_version WHERE workflow_def_id = @workflow_def_id;

    IF @delete_instances = 1
    BEGIN
        DECLARE @instance_ids TABLE (id BIGINT NOT NULL PRIMARY KEY);
        INSERT INTO @instance_ids (id)
        SELECT wi.id
        FROM wf.workflow_instance AS wi
        INNER JOIN @version_ids AS v ON v.id = wi.workflow_version_id;

        SET @deleted_instance_count = @@ROWCOUNT;

        IF @deleted_instance_count > 0
        BEGIN
            DELETE ls
            FROM wf.loop_state AS ls
            INNER JOIN @instance_ids AS i ON i.id = ls.workflow_instance_id;

            UPDATE ne
            SET parent_node_execution_id = NULL
            FROM wf.node_execution AS ne
            INNER JOIN @instance_ids AS i ON i.id = ne.workflow_instance_id;

            DELETE wi
            FROM wf.workflow_instance AS wi
            INNER JOIN @instance_ids AS i ON i.id = wi.id;
        END
    END
    ELSE IF EXISTS (
        SELECT 1
        FROM wf.workflow_instance AS wi
        INNER JOIN @version_ids AS v ON v.id = wi.workflow_version_id
    )
    BEGIN
        ROLLBACK TRANSACTION;
        THROW 50014, N'Workflow has instances. Set @delete_instances = 1 or delete instances manually.', 1;
    END

    UPDATE wv
    SET root_node_id = NULL
    FROM wf.workflow_version AS wv
    WHERE wv.workflow_def_id = @workflow_def_id;

    DELETE ls
    FROM wf.loop_state AS ls
    WHERE EXISTS (
        SELECT 1
        FROM wf.workflow_node AS wn
        INNER JOIN @version_ids AS v ON v.id = wn.workflow_version_id
        WHERE wn.id = ls.control_node_id
    );

    DELETE we
    FROM wf.workflow_edge AS we
    WHERE EXISTS (
        SELECT 1
        FROM wf.workflow_node AS wn
        INNER JOIN @version_ids AS v ON v.id = wn.workflow_version_id
        WHERE wn.id = we.parent_node_id OR wn.id = we.child_node_id
    );

    DELETE wv
    FROM wf.workflow_version AS wv
    WHERE wv.workflow_def_id = @workflow_def_id;

    SET @deleted_version_count = @@ROWCOUNT;

    DELETE FROM wf.workflow_def
    WHERE id = @workflow_def_id;

    COMMIT TRANSACTION;

    SELECT
        @workflow_def_id AS deleted_workflow_def_id,
        @deleted_instance_count AS deleted_instance_count,
        @deleted_version_count AS deleted_version_count;
END;
GO

PRINT N'wf.sp_delete_workflow_def deployed.';
GO
