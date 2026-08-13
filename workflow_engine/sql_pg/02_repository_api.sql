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
DECLARE
  v_ctx jsonb := COALESCE(p_context_json, '{}'::jsonb);
  v_set_key text;
  v_id bigint;
BEGIN
  /*
    ACTION templates bind ${var.executionScopeId}. Portal SQL starts often skip
    Python finalize_instance_context, so bake a scope key here when absent.
  */
  v_set_key := NULLIF(BTRIM(COALESCE(v_ctx->>'executionScopeId', v_ctx->>'hyperparamSetId')), '');
  IF v_set_key IS NULL THEN
    v_set_key := LEFT(encode(wf.wf_sha256_text(v_ctx::text), 'hex'), 32);
    v_ctx := v_ctx || jsonb_build_object(
      'executionScopeId', v_set_key,
      'hyperparamSetId', v_set_key
    );
  ELSE
    IF v_ctx->>'executionScopeId' IS NULL THEN
      v_ctx := v_ctx || jsonb_build_object('executionScopeId', v_set_key);
    END IF;
    IF v_ctx->>'hyperparamSetId' IS NULL THEN
      v_ctx := v_ctx || jsonb_build_object('hyperparamSetId', v_set_key);
    END IF;
  END IF;

  INSERT INTO wf.workflow_instance (workflow_version_id, status, context_json)
  VALUES (p_version_id, 'CREATED', v_ctx)
  RETURNING wf.workflow_instance.id INTO v_id;

  BEGIN
    CALL wf.wf_apply_execution_scope(v_id, v_set_key, NULL, NULL, true);
  EXCEPTION
    WHEN OTHERS THEN
      NULL; -- optional on partially deployed schemas
  END;

  id := v_id;
  RETURN NEXT;
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

CREATE OR REPLACE FUNCTION wf.wf_repo_get_workflow_instance(p_instance_id bigint)
RETURNS TABLE (
  id bigint,
  workflow_version_id bigint,
  status text
)
LANGUAGE sql
STABLE
AS $$
  SELECT wi.id, wi.workflow_version_id, wi.status
  FROM wf.workflow_instance wi
  WHERE wi.id = p_instance_id;
$$;

CREATE OR REPLACE FUNCTION wf.wf_repo_try_latest_task_result_code(
  p_instance_id bigint,
  p_node_key text
)
RETURNS TABLE (found boolean, result_code int)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_rc int;
  v_found boolean := false;
BEGIN
  SELECT ne.result_code INTO v_rc
  FROM wf.node_execution ne
  INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
  WHERE ne.workflow_instance_id = p_instance_id
    AND wn.node_key = p_node_key
    AND ne.status = 'SUCCEEDED'
  ORDER BY ne.ended_at_utc DESC NULLS LAST, ne.id DESC
  LIMIT 1;
  /* FOUND is set by PL/pgSQL after SELECT INTO: true if a row was returned,
     false if no row matched. This correctly distinguishes "row exists with
     NULL result_code" from "no matching row". */
  v_found := FOUND;
  RETURN QUERY SELECT v_found, v_rc;
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_repo_upsert_instance_extension(
  IN p_instance_id bigint,
  IN p_extension_key text,
  IN p_data_json jsonb
)
LANGUAGE plpgsql
AS $$
BEGIN
  IF p_extension_key IS NULL OR btrim(p_extension_key) = '' THEN
    RETURN;
  END IF;

  INSERT INTO wf.instance_extension (workflow_instance_id, extension_key, data_json)
  VALUES (p_instance_id, p_extension_key, p_data_json)
  ON CONFLICT (workflow_instance_id, extension_key) DO UPDATE SET
    data_json = EXCLUDED.data_json,
    updated_at_utc = (now() AT TIME ZONE 'utc');
END;
$$;

CREATE OR REPLACE FUNCTION wf.wf_repo_get_instance_extension(
  p_instance_id bigint,
  p_extension_key text
)
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
  SELECT ie.data_json
  FROM wf.instance_extension ie
  WHERE ie.workflow_instance_id = p_instance_id
    AND ie.extension_key = p_extension_key;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_repo_set_scope_variable(
  IN p_instance_id bigint,
  IN p_scope_exec_id bigint,
  IN p_var_name text,
  IN p_value_json jsonb
)
LANGUAGE plpgsql
AS $$
BEGIN
  CALL wf.wf_set_scope_variable(p_instance_id, p_scope_exec_id, p_var_name, p_value_json::text);
END;
$$;
