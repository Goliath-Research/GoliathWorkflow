/*
  Fix workflow_edge uniqueness for IF/FOREACH branches.

  UQ_we_parent_child_order (parent_node_id, child_order) rejects valid graphs where
  an IF node has both THEN and ELSE edges at child_order=0. The engine selects
  branches by branch_kind, not child_order alone.

  Keep UQ_we_parent_child (parent_node_id, child_node_id); drop the order-only index.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_we_parent_child_order'
      AND object_id = OBJECT_ID(N'wf.workflow_edge')
)
    DROP INDEX UQ_we_parent_child_order ON wf.workflow_edge;
GO

PRINT N'wf.workflow_edge: dropped UQ_we_parent_child_order (IF THEN/ELSE compatible).';
GO
