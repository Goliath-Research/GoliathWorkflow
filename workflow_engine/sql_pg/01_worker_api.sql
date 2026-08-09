/*
  MethylPipeline wf schema - PostgreSQL worker API (contract result shapes).
  Prerequisites: 00_schema.sql, 03_engine_core.sql (for wf_engine_on_action_complete).
*/

/*
  MethylPipeline wf schema - PostgreSQL worker API (contract result shapes).
  Prerequisites: 00_schema.sql, 03_engine_core.sql (for wf_engine_on_action_complete).
*/

CREATE OR REPLACE FUNCTION wf.wf_json_fragment_from_string(p_s text)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
  RETURN '"' || replace(replace(replace(coalesce(p_s, ''), '\', '\\'), '"', '\"'), E'\n', '\n') || '"';
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_worker_authenticate(
  IN p_worker_id bigint,
  IN p_worker_token text
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_tok text := nullif(btrim(p_worker_token), '');
  v_hash bytea;
BEGIN
  IF p_worker_id IS NULL THEN
    RAISE EXCEPTION 'worker_id is required' USING ERRCODE = '50002';
  END IF;
  IF v_tok IS NULL THEN
    RAISE EXCEPTION 'worker_token is required' USING ERRCODE = '50002';
  END IF;

  v_hash := wf.wf_sha256_text(v_tok);

  IF NOT EXISTS (
    SELECT 1
    FROM wf.worker_token wt
    INNER JOIN wf.worker w ON w.id = wt.worker_id
    INNER JOIN wf.cluster c ON c.id = w.cluster_id
    WHERE wt.worker_id = p_worker_id
      AND wt.token_hash = v_hash
      AND wt.status = 'ACTIVE'
      AND (wt.expires_at_utc IS NULL OR wt.expires_at_utc > (now() AT TIME ZONE 'utc'))
      AND w.status = 'REGISTERED'
      AND c.status = 'ACTIVE'
  ) THEN
    RAISE EXCEPTION 'Invalid or unauthorized worker credentials' USING ERRCODE = '50003';
  END IF;

  UPDATE wf.worker
  SET last_seen_at_utc = (now() AT TIME ZONE 'utc')
  WHERE id = p_worker_id;
END;
$$;

CREATE OR REPLACE FUNCTION wf.wf_worker_is_omnibus(p_capabilities jsonb)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
  -- Only explicit ["*"] is omnibus. NULL / [] mean "no capabilities"
  -- (native jsonb; never treat empty as wildcard).
  SELECT
    p_capabilities IS NOT NULL
    AND p_capabilities <> '[]'::jsonb
    AND p_capabilities @> '["*"]'::jsonb;
$$;

CREATE OR REPLACE FUNCTION wf.wf_worker_capability_allowed(
  p_worker_capabilities jsonb,
  p_task_capability text
)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT
    p_task_capability IS NULL
    OR wf.wf_worker_is_omnibus(p_worker_capabilities)
    OR EXISTS (
      SELECT 1
      FROM jsonb_array_elements_text(coalesce(p_worker_capabilities, '[]'::jsonb)) AS elem(value)
      WHERE elem.value = p_task_capability
    );
$$;

-- Return shape includes desired_state/command (worker fleet control).
DROP FUNCTION IF EXISTS wf.sp_worker_request_task(bigint, text, text, int);

CREATE OR REPLACE FUNCTION wf.sp_worker_request_task(
  p_worker_id bigint,
  p_worker_token text,
  p_capability text DEFAULT NULL,
  p_max_lease_seconds int DEFAULT 300
)
RETURNS TABLE (
  node_execution_id bigint,
  workflow_instance_id bigint,
  node_key text,
  action_name text,
  capability text,
  attempt_no int,
  input_json jsonb,
  iteration_no int,
  desired_state text,
  command text
)
LANGUAGE plpgsql
AS $$
#variable_conflict use_column
DECLARE
  v_now timestamptz := (now() AT TIME ZONE 'utc');
  v_lease_end timestamptz := v_now + make_interval(secs => p_max_lease_seconds);
  v_picked bigint;
  v_worker_capabilities jsonb;
  v_is_omnibus boolean;
  v_reclaim_cutoff timestamptz := v_now - make_interval(secs => 60);
  v_desired_state text := 'ACTIVE';
  v_command text := 'NONE';
BEGIN
  CALL wf.wf_worker_authenticate(p_worker_id, p_worker_token);

  -- Auto-unstick crashed workers: expired/missing leases → READY (quiet: discard rows).
  IF EXISTS (
    SELECT 1
    FROM wf.node_execution AS ne
    LEFT JOIN wf.task_lease AS l ON l.node_execution_id = ne.id
    WHERE ne.status = 'RUNNING'
      AND (
            l.node_execution_id IS NULL
         OR l.lease_expires_at_utc <= v_reclaim_cutoff
      )
  ) THEN
    PERFORM * FROM wf.sp_reclaim_expired_leases(NULL::bigint, 60, true);
  END IF;

  SELECT w.capabilities, coalesce(w.desired_state, 'ACTIVE')
  INTO v_worker_capabilities, v_desired_state
  FROM wf.worker w
  WHERE w.id = p_worker_id;

  v_command := CASE v_desired_state
    WHEN 'DRAINING' THEN 'DRAIN'
    WHEN 'STOPPING' THEN 'STOP'
    ELSE 'NONE'
  END;

  -- Drain/stop: echo control, do not claim new work.
  IF v_desired_state IN ('DRAINING', 'STOPPING') THEN
    RETURN QUERY SELECT
      NULL::bigint, NULL::bigint, NULL::text, NULL::text, NULL::text,
      NULL::int, NULL::jsonb, NULL::int, v_desired_state, v_command;
    RETURN;
  END IF;

  v_is_omnibus := wf.wf_worker_is_omnibus(v_worker_capabilities);

  IF p_capability IS NOT NULL
     AND NOT v_is_omnibus
     AND NOT wf.wf_worker_capability_allowed(v_worker_capabilities, p_capability) THEN
    RETURN QUERY SELECT
      NULL::bigint, NULL::bigint, NULL::text, NULL::text, NULL::text,
      NULL::int, NULL::jsonb, NULL::int, v_desired_state, v_command;
    RETURN;
  END IF;

  WITH cte AS (
    SELECT ne.id
    FROM wf.node_execution ne
    INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
    INNER JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
    INNER JOIN wf.workflow_instance wi ON wi.id = ne.workflow_instance_id
    WHERE ne.status = 'READY'
      AND wn.node_type = 'ACTION'
      AND wi.status = 'RUNNING'
      AND (ne.available_at_utc IS NULL OR ne.available_at_utc <= v_now)
      AND wf.wf_worker_capability_allowed(v_worker_capabilities, wa.capability)
      AND (
        p_capability IS NULL
        OR wa.capability = p_capability
        OR wa.capability IS NULL
      )
    ORDER BY ne.available_at_utc ASC NULLS FIRST, ne.id ASC
    LIMIT 1
    FOR UPDATE OF ne SKIP LOCKED
  )
  UPDATE wf.node_execution ne
  SET status = 'RUNNING',
      started_at_utc = v_now
  FROM cte
  WHERE ne.id = cte.id
  RETURNING ne.id INTO v_picked;

  IF v_picked IS NULL THEN
    RETURN QUERY SELECT
      NULL::bigint, NULL::bigint, NULL::text, NULL::text, NULL::text,
      NULL::int, NULL::jsonb, NULL::int, v_desired_state, v_command;
    RETURN;
  END IF;

  INSERT INTO wf.task_lease (node_execution_id, worker_id, lease_expires_at_utc, heartbeat_at_utc)
  VALUES (v_picked, p_worker_id, v_lease_end, v_now)
  ON CONFLICT (node_execution_id) DO UPDATE
  SET worker_id = EXCLUDED.worker_id,
      lease_expires_at_utc = EXCLUDED.lease_expires_at_utc,
      heartbeat_at_utc = EXCLUDED.heartbeat_at_utc;

  RETURN QUERY
  SELECT
    ne.id,
    ne.workflow_instance_id,
    wn.node_key,
    wa.action_name,
    wa.capability,
    ne.attempt_no,
    ne.input_json,
    ne.iteration_no,
    v_desired_state,
    v_command
  FROM wf.node_execution ne
  INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
  INNER JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
  WHERE ne.id = v_picked;
END;
$$;

CREATE OR REPLACE FUNCTION wf.sp_worker_submit_result(
  p_node_execution_id bigint,
  p_worker_id bigint,
  p_worker_token text,
  p_result_code int,
  p_output_json jsonb DEFAULT NULL
)
RETURNS TABLE (accepted boolean, instance_status text, next_ready_count int)
LANGUAGE plpgsql
AS $$
#variable_conflict use_column
DECLARE
  v_lease_worker bigint;
  v_cur_status text;
  v_instance_status text;
  v_next_ready int;
  v_accepted boolean := false;
BEGIN
  CALL wf.wf_worker_authenticate(p_worker_id, p_worker_token);

  SELECT tl.worker_id INTO v_lease_worker
  FROM wf.task_lease tl
  WHERE tl.node_execution_id = p_node_execution_id
  FOR UPDATE;

  IF v_lease_worker IS NULL OR v_lease_worker <> p_worker_id THEN
    RETURN QUERY SELECT false, NULL::text, 0;
    RETURN;
  END IF;

  SELECT ne.status INTO v_cur_status
  FROM wf.node_execution ne
  WHERE ne.id = p_node_execution_id
  FOR UPDATE;

  IF v_cur_status <> 'RUNNING' THEN
    RETURN QUERY SELECT false, NULL::text, 0;
    RETURN;
  END IF;

  CALL wf.wf_engine_on_action_complete(p_node_execution_id, p_result_code, p_output_json);
  v_accepted := true;

  SELECT wi.status INTO v_instance_status
  FROM wf.workflow_instance wi
  WHERE wi.id = (SELECT ne.workflow_instance_id FROM wf.node_execution ne WHERE ne.id = p_node_execution_id);

  SELECT count(*)::int INTO v_next_ready
  FROM wf.node_execution ne
  WHERE ne.workflow_instance_id = (SELECT ne2.workflow_instance_id FROM wf.node_execution ne2 WHERE ne2.id = p_node_execution_id)
    AND ne.status = 'READY';

  RETURN QUERY SELECT v_accepted, v_instance_status, v_next_ready;
END;
$$;

DROP FUNCTION IF EXISTS wf.sp_worker_heartbeat(bigint, bigint, text, int);

CREATE OR REPLACE FUNCTION wf.sp_worker_heartbeat(
  p_node_execution_id bigint,
  p_worker_id bigint,
  p_worker_token text,
  p_extend_seconds int DEFAULT 300
)
RETURNS TABLE (rows_updated int, desired_state text, command text)
LANGUAGE plpgsql
AS $$
DECLARE
  v_now timestamptz := (now() AT TIME ZONE 'utc');
  v_rows int;
  v_desired_state text := 'ACTIVE';
  v_command text := 'NONE';
BEGIN
  CALL wf.wf_worker_authenticate(p_worker_id, p_worker_token);

  UPDATE wf.task_lease tl
  SET lease_expires_at_utc = v_now + make_interval(secs => p_extend_seconds),
      heartbeat_at_utc = v_now
  WHERE tl.node_execution_id = p_node_execution_id
    AND tl.worker_id = p_worker_id;

  GET DIAGNOSTICS v_rows = ROW_COUNT;

  SELECT coalesce(w.desired_state, 'ACTIVE')
  INTO v_desired_state
  FROM wf.worker w
  WHERE w.id = p_worker_id;

  v_command := CASE v_desired_state
    WHEN 'DRAINING' THEN 'DRAIN'
    WHEN 'STOPPING' THEN 'STOP'
    ELSE 'NONE'
  END;

  RETURN QUERY SELECT v_rows, v_desired_state, v_command;
END;
$$;

CREATE OR REPLACE PROCEDURE wf.sp_worker_fail_task(
  IN p_node_execution_id bigint,
  IN p_worker_id bigint,
  IN p_worker_token text,
  IN p_error_code int,
  IN p_error_message text DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_now timestamptz := (now() AT TIME ZONE 'utc');
BEGIN
  CALL wf.wf_worker_authenticate(p_worker_id, p_worker_token);

  UPDATE wf.node_execution
  SET status = 'FAILED',
      result_code = p_error_code,
      engine_error_code = p_error_code,
      engine_error_message = p_error_message,
      ended_at_utc = v_now
  WHERE id = p_node_execution_id;

  UPDATE wf.workflow_instance wi
  SET status = 'FAILED', completed_at_utc = v_now
  FROM wf.node_execution ne
  WHERE ne.id = p_node_execution_id AND wi.id = ne.workflow_instance_id;

  DELETE FROM wf.task_lease WHERE node_execution_id = p_node_execution_id;
END;
$$;

CREATE OR REPLACE PROCEDURE wf.sp_start_workflow_instance(
  IN p_workflow_instance_id bigint
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_vid bigint;
  v_root bigint;
BEGIN
  SELECT workflow_version_id INTO v_vid
  FROM wf.workflow_instance WHERE id = p_workflow_instance_id;

  SELECT root_node_id INTO v_root
  FROM wf.workflow_version WHERE id = v_vid;

  IF v_root IS NULL THEN
    RAISE EXCEPTION 'Workflow version has no root_node_id' USING ERRCODE = '50001';
  END IF;

  UPDATE wf.workflow_instance
  SET status = 'RUNNING',
      started_at_utc = (now() AT TIME ZONE 'utc')
  WHERE id = p_workflow_instance_id;

  CALL wf.wf_init_instance_scope_from_context(p_workflow_instance_id);

  CALL wf.wf_resolve_collection_bindings(p_workflow_instance_id);

  CALL wf.wf_engine_activate(
    p_workflow_instance_id,
    v_root,
    NULL,
    0,
    NULL,
    NULL
  );
END;
$$;
