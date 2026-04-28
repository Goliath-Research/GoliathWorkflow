/*
  Workflow Engine - Additional indexes and optional constraint hygiene.
  Run after workflow_definition.sql and workflow_runtime.sql.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

-- Prevent duplicate parent-child edges (same link twice).
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'UQ_we_parent_child' AND object_id = OBJECT_ID(N'dbo.workflow_edge')
)
CREATE UNIQUE INDEX UQ_we_parent_child ON dbo.workflow_edge(parent_node_id, child_node_id);
GO

-- Scheduler / worker polling: runnable ACTION tasks for a capability.
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'IX_ne_ready_worker_poll' AND object_id = OBJECT_ID(N'dbo.node_execution')
)
CREATE INDEX IX_ne_ready_worker_poll ON dbo.node_execution(status, available_at_utc)
    INCLUDE (workflow_instance_id, workflow_node_id)
    WHERE status IN (N'READY', N'RUNNING');
GO

-- Prior-output lookup by instance + logical node key (via workflow_node join in queries).
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'IX_ne_instance_status_ended' AND object_id = OBJECT_ID(N'dbo.node_execution')
)
CREATE INDEX IX_ne_instance_status_ended ON dbo.node_execution(workflow_instance_id, status, ended_at_utc DESC)
    INCLUDE (workflow_node_id, result_code, output_json);
GO
