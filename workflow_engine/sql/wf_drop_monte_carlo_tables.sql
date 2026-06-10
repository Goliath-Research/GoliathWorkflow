/*
  MethylPipeline wf schema - remove deprecated Monte Carlo domain tables.

  Monte Carlo orchestration is an optional domain extension: planners populate
  context_json.iterations[] and ValidationPipeline uses FOREACH + templates.

  Optional audit: wf.instance_extension (wf_instance_extension.sql).
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'wf.monte_carlo_run', N'U') IS NOT NULL
BEGIN
    DROP TABLE wf.monte_carlo_run;
    PRINT N'Dropped wf.monte_carlo_run.';
END
GO

IF OBJECT_ID(N'wf.monte_carlo_plan', N'U') IS NOT NULL
BEGIN
    DROP TABLE wf.monte_carlo_plan;
    PRINT N'Dropped wf.monte_carlo_plan.';
END
GO
