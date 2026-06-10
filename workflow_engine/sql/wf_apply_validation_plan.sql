/*
  Apply ValidationPipeline planner output to a workflow instance.

  Merges planner context_json into workflow_instance.context_json and optionally
  persists the full plan under wf.instance_extension (methylvalidation.plan).

  The planner itself runs in Python (validation.plan-iterations worker capability);
  this procedure is the database bridge for portal/middle-tier after planning.

  Prerequisites:
  - wf_instance_extension.sql
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'wf.workflow_instance', N'U') IS NULL
BEGIN
    RAISERROR(N'Prerequisite missing: base wf schema not deployed.', 16, 1);
    RETURN;
END
GO

CREATE OR ALTER PROCEDURE wf.wf_apply_validation_plan
    @workflow_instance_id BIGINT,
    @context_json json,
    @persist_extension BIT = 1
AS
BEGIN
    SET NOCOUNT ON;

    IF @context_json IS NULL
        RETURN;

    UPDATE wf.workflow_instance
    SET context_json = @context_json
    WHERE id = @workflow_instance_id;

    IF @persist_extension = 1
       AND JSON_VALUE(@context_json, '$.validationPlan') IS NOT NULL
    BEGIN
        EXEC wf.wf_repo_upsert_instance_extension
            @instance_id = @workflow_instance_id,
            @extension_key = N'methylvalidation.plan',
            @data_json = JSON_QUERY(@context_json, '$.validationPlan');
    END
END;
GO
