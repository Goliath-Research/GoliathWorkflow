/*
  DEPRECATED — Monte Carlo domain tables removed from the workflow engine core.

  Use instead:
  - wf_scope_readpath.sql          scope read helpers (wf_get_scope_variable_json/int)
  - wf_instance_extension.sql      optional generic extension persistence
  - wf_drop_monte_carlo_tables.sql drop legacy wf.monte_carlo_* tables
  - wf_validation_pipeline_seed.sql ValidationPipeline (FOREACH over context_json.iterations[])

  Validation planners populate context_json before sp_start_workflow_instance.
  See contract/validation_planner_capabilities.md
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

PRINT N'DEPRECATED: wf_monte_carlo_support.sql is a no-op. Deploy wf_scope_readpath.sql and wf_instance_extension.sql instead.';
GO
