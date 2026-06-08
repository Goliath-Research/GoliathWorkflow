/*
  MethylPipeline wf schema - PostgreSQL repository API (middle-tier persistence).
  Dialect-neutral wrappers for WfEngine.Repository.
  Prerequisites: 00_schema.sql
*/

CREATE OR REPLACE PROCEDURE wf.wf_repo_set_instance_status(
  IN p_instance_id bigint,
  IN p_status text
)
LANGUAGE plpgsql
AS $$
BEGIN
  IF p_status IN ('COMPLETED','FAILED','CANCELLED') THEN
    UPDATE wf.workflow_instance
    SET status = p_status, completed_at_utc = coalesce(completed_at_utc, (now() AT TIME ZONE 'utc'))
    WHERE id = p_instance_id;
  ELSIF p_status = 'RUNNING' THEN
    UPDATE wf.workflow_instance
    SET status = p_status, started_at_utc = coalesce(started_at_utc, (now() AT TIME ZONE 'utc'))
    WHERE id = p_instance_id;
  ELSE
    UPDATE wf.workflow_instance SET status = p_status WHERE id = p_instance_id;
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION wf.wf_repo_create_workflow_instance(
  p_version_id bigint,
  p_context_json jsonb DEFAULT NULL
)
RETURNS TABLE (id bigint)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  INSERT INTO wf.workflow_instance (workflow_version_id, status, context_json)
  VALUES (p_version_id, 'CREATED', p_context_json)
  RETURNING wf.workflow_instance.id;
END;
$$;

CREATE OR REPLACE FUNCTION wf.wf_repo_insert_node_execution(
  p_workflow_instance_id bigint,
  p_workflow_node_id bigint,
  p_status text,
  p_attempt_no int,
  p_parent_node_execution_id bigint,
  p_iteration_no int,
  p_input_json jsonb,
  p_set_available_now boolean,
  p_set_started_now boolean
)
RETURNS TABLE (id bigint)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  INSERT INTO wf.node_execution (
    workflow_instance_id, workflow_node_id, status, attempt_no,
    parent_node_execution_id, iteration_no, input_json, available_at_utc, started_at_utc
  ) VALUES (
    p_workflow_instance_id, p_workflow_node_id, p_status, p_attempt_no,
    p_parent_node_execution_id, p_iteration_no, p_input_json,
    CASE WHEN p_set_available_now THEN (now() AT TIME ZONE 'utc') ELSE NULL END,
    CASE WHEN p_set_started_now THEN (now() AT TIME ZONE 'utc') ELSE NULL END
  )
  RETURNING wf.node_execution.id;
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_repo_update_node_execution_status(
  IN p_execution_id bigint,
  IN p_status text,
  IN p_output_json jsonb,
  IN p_has_result_code boolean,
  IN p_result_code int,
  IN p_engine_error_code int,
  IN p_engine_error_message text
)
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE wf.node_execution
  SET status = p_status,
      output_json = p_output_json,
      ended_at_utc = (now() AT TIME ZONE 'utc'),
      result_code = CASE WHEN p_has_result_code THEN p_result_code ELSE result_code END,
      engine_error_code = CASE WHEN p_engine_error_code <> 0 THEN p_engine_error_code ELSE engine_error_code END,
      engine_error_message = CASE WHEN p_engine_error_code <> 0 THEN p_engine_error_message ELSE engine_error_message END
  WHERE id = p_execution_id;
END;
$$;

CREATE OR REPLACE FUNCTION wf.wf_repo_insert_loop_state(
  p_workflow_instance_id bigint,
  p_control_node_id bigint,
  p_scope_node_execution_id bigint,
  p_current_iteration int,
  p_repeat_target_count int
)
RETURNS TABLE (id bigint)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  INSERT INTO wf.loop_state (
    workflow_instance_id, control_node_id, scope_node_execution_id,
    current_iteration, repeat_target_count
  ) VALUES (
    p_workflow_instance_id, p_control_node_id, p_scope_node_execution_id,
    p_current_iteration, p_repeat_target_count
  )
  RETURNING wf.loop_state.id;
END;
$$;

CREATE OR REPLACE FUNCTION wf.wf_repo_get_running_instances(p_max_count int)
RETURNS TABLE (id bigint)
LANGUAGE sql
STABLE
AS $$
  SELECT wi.id FROM wf.workflow_instance wi
  WHERE wi.status = 'RUNNING'
  ORDER BY wi.id
  LIMIT p_max_count;
$$;

CREATE OR REPLACE FUNCTION wf.wf_repo_try_latest_task_result_code(
  p_instance_id bigint,
  p_node_key text
)
RETURNS TABLE (found boolean, result_code int)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE v_rc int;
BEGIN
  SELECT ne.result_code INTO v_rc
  FROM wf.node_execution ne
  INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
  WHERE ne.workflow_instance_id = p_instance_id
    AND wn.node_key = p_node_key
    AND ne.status = 'SUCCEEDED'
  ORDER BY ne.ended_at_utc DESC NULLS LAST, ne.id DESC
  LIMIT 1;
  IF v_rc IS NULL THEN
    RETURN QUERY SELECT false, NULL::int;
  ELSE
    RETURN QUERY SELECT true, v_rc;
  END IF;
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_repo_upsert_monte_carlo_plan(
  IN p_instance_id bigint,
  IN p_base_project_path text,
  IN p_layout text,
  IN p_seed int,
  IN p_feature_iterations int,
  IN p_quality_iterations int,
  IN p_config_json jsonb
)
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO wf.monte_carlo_plan (
    workflow_instance_id, base_project_path, layout_name, seed,
    feature_iterations, quality_iterations, config_json
  ) VALUES (
    p_instance_id, p_base_project_path, p_layout, p_seed,
    p_feature_iterations, p_quality_iterations, p_config_json
  )
  ON CONFLICT (workflow_instance_id) DO UPDATE SET
    base_project_path = EXCLUDED.base_project_path,
    layout_name = EXCLUDED.layout_name,
    seed = EXCLUDED.seed,
    feature_iterations = EXCLUDED.feature_iterations,
    quality_iterations = EXCLUDED.quality_iterations,
    config_json = EXCLUDED.config_json,
    updated_at_utc = (now() AT TIME ZONE 'utc');
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_repo_upsert_monte_carlo_run(
  IN p_instance_id bigint,
  IN p_run_id text,
  IN p_iteration_no int,
  IN p_phase text,
  IN p_task_config_json jsonb
)
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO wf.monte_carlo_run (
    workflow_instance_id, run_id, iteration_no, phase_name, task_config_json
  ) VALUES (
    p_instance_id, p_run_id, p_iteration_no, p_phase, p_task_config_json
  )
  ON CONFLICT (workflow_instance_id, run_id) DO UPDATE SET
    iteration_no = EXCLUDED.iteration_no,
    phase_name = EXCLUDED.phase_name,
    task_config_json = EXCLUDED.task_config_json,
    updated_at_utc = (now() AT TIME ZONE 'utc');
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_repo_set_scope_variable(
  IN p_instance_id bigint,
  IN p_scope_exec_id bigint,
  IN p_var_name text,
  IN p_value_json text
)
LANGUAGE plpgsql
AS $$
BEGIN
  CALL wf.wf_set_scope_variable(p_instance_id, p_scope_exec_id, p_var_name, p_value_json);
END;
$$;
