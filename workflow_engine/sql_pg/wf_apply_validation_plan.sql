/*
  PostgreSQL: apply ValidationPipeline planner output to a workflow instance.
*/

CREATE OR REPLACE PROCEDURE wf.wf_apply_validation_plan(
  IN p_workflow_instance_id bigint,
  IN p_context_json jsonb,
  IN p_persist_extension boolean DEFAULT true
)
LANGUAGE plpgsql
AS $$
BEGIN
  IF p_context_json IS NULL THEN
    RETURN;
  END IF;

  UPDATE wf.workflow_instance
  SET context_json = p_context_json
  WHERE id = p_workflow_instance_id;

  IF p_persist_extension
     AND p_context_json ? 'validationPlan' THEN
    CALL wf.wf_repo_upsert_instance_extension(
      p_workflow_instance_id,
      'methylvalidation.plan',
      p_context_json -> 'validationPlan'
    );
  END IF;
END;
$$;
