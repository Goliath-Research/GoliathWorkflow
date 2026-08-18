/*
  Instance task monitor + operator retry (PostgreSQL).
  Twin of sql_mssql/portal_ops_recovery_api.sql.
*/

DROP FUNCTION IF EXISTS portal.sp_get_instance_tasks(bigint);

CREATE OR REPLACE FUNCTION portal.sp_get_instance_tasks(p_workflow_instance_id bigint)
RETURNS TABLE (
  node_execution_id bigint,
  status text,
  result_code int,
  attempt_no int,
  engine_error_code int,
  engine_error_message text,
  node_key text,
  action_name text,
  capability text,
  can_stop boolean,
  can_pause boolean,
  affinity_key text,
  completed_by_worker_id bigint,
  lease_worker_id bigint,
  lease_expires_at_utc timestamptz,
  source_uri text,
  input_json jsonb,
  output_json jsonb,
  started_at_utc timestamptz,
  completed_at_utc timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    ne.id,
    ne.status,
    ne.result_code,
    ne.attempt_no,
    ne.engine_error_code,
    ne.engine_error_message,
    wn.node_key,
    wa.action_name,
    wa.capability,
    COALESCE(wa.can_stop, true),
    COALESCE(wa.can_pause, false),
    ne.affinity_key,
    ne.completed_by_worker_id,
    tl.worker_id,
    tl.lease_expires_at_utc,
    COALESCE(
      ne.input_json #>> '{fastqStorage,uri}',
      ne.input_json #>> '{fastqSource,uri}',
      ne.input_json->>'sourceUri',
      ne.input_json->>'uri',
      ne.input_json->>'fastqStorage'
    ),
    ne.input_json,
    ne.output_json,
    ne.started_at_utc,
    ne.ended_at_utc
  FROM wf.node_execution ne
  INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
  LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
  LEFT JOIN wf.task_lease tl ON tl.node_execution_id = ne.id
  WHERE ne.workflow_instance_id = p_workflow_instance_id
  ORDER BY ne.id;
$$;

DROP FUNCTION IF EXISTS portal.sp_get_node_execution_detail(bigint);

CREATE OR REPLACE FUNCTION portal.sp_get_node_execution_detail(p_node_execution_id bigint)
RETURNS TABLE (
  node_execution_id bigint,
  workflow_instance_id bigint,
  instance_status text,
  status text,
  result_code int,
  attempt_no int,
  engine_error_code int,
  engine_error_message text,
  node_key text,
  action_name text,
  capability text,
  can_stop boolean,
  can_pause boolean,
  affinity_key text,
  completed_by_worker_id bigint,
  lease_worker_id bigint,
  lease_expires_at_utc timestamptz,
  source_uri text,
  output_json_excerpt text,
  input_json jsonb,
  output_json jsonb,
  started_at_utc timestamptz,
  completed_at_utc timestamptz
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
  IF p_node_execution_id IS NULL OR p_node_execution_id <= 0 THEN
    RAISE EXCEPTION 'node_execution_id is required';
  END IF;

  RETURN QUERY
  SELECT
    ne.id,
    ne.workflow_instance_id,
    i.status,
    ne.status,
    ne.result_code,
    ne.attempt_no,
    ne.engine_error_code,
    ne.engine_error_message,
    wn.node_key,
    wa.action_name,
    wa.capability,
    COALESCE(wa.can_stop, true),
    COALESCE(wa.can_pause, false),
    ne.affinity_key,
    ne.completed_by_worker_id,
    tl.worker_id,
    tl.lease_expires_at_utc,
    COALESCE(
      ne.input_json #>> '{fastqStorage,uri}',
      ne.input_json #>> '{fastqSource,uri}',
      ne.input_json->>'sourceUri',
      ne.input_json->>'uri',
      ne.input_json->>'fastqStorage'
    ),
    left(ne.output_json::text, 4000),
    ne.input_json,
    ne.output_json,
    ne.started_at_utc,
    ne.ended_at_utc
  FROM wf.node_execution ne
  INNER JOIN wf.workflow_instance i ON i.id = ne.workflow_instance_id
  INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
  LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
  LEFT JOIN wf.task_lease tl ON tl.node_execution_id = ne.id
  WHERE ne.id = p_node_execution_id;
END;
$$;

DROP FUNCTION IF EXISTS portal.sp_retry_failed_node(bigint);

CREATE OR REPLACE FUNCTION portal.sp_retry_failed_node(p_node_execution_id bigint)
RETURNS TABLE (
  node_execution_id bigint,
  status text,
  attempt_no int,
  instance_status text
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_status text;
  v_instance_id bigint;
  v_instance_status text;
BEGIN
  IF p_node_execution_id IS NULL OR p_node_execution_id <= 0 THEN
    RAISE EXCEPTION 'node_execution_id is required';
  END IF;

  SELECT ne.status, ne.workflow_instance_id
    INTO v_status, v_instance_id
  FROM wf.node_execution ne
  WHERE ne.id = p_node_execution_id
  FOR UPDATE;

  IF v_instance_id IS NULL THEN
    RAISE EXCEPTION 'node_execution not found';
  END IF;

  IF v_status <> 'FAILED' THEN
    RAISE EXCEPTION 'Only FAILED tasks can be retried (set READY)';
  END IF;

  DELETE FROM wf.task_lease WHERE node_execution_id = p_node_execution_id;

  UPDATE wf.node_execution
  SET status = 'READY',
      attempt_no = COALESCE(attempt_no, 1) + 1,
      started_at_utc = NULL,
      ended_at_utc = NULL,
      result_code = NULL,
      engine_error_code = NULL,
      engine_error_message = NULL
  WHERE id = p_node_execution_id;

  SELECT i.status INTO v_instance_status
  FROM wf.workflow_instance i
  WHERE i.id = v_instance_id
  FOR UPDATE;

  IF v_instance_status = 'FAILED' THEN
    UPDATE wf.workflow_instance
    SET status = 'RUNNING',
        completed_at_utc = NULL
    WHERE id = v_instance_id;
  END IF;

  RETURN QUERY
  SELECT ne.id, ne.status, ne.attempt_no, i.status
  FROM wf.node_execution ne
  INNER JOIN wf.workflow_instance i ON i.id = ne.workflow_instance_id
  WHERE ne.id = p_node_execution_id;
END;
$$;
