/*
  MethylPipeline wf schema - PostgreSQL engine runtime (SQL-only activation path).
  Prerequisites: 00_schema.sql
*/

CREATE OR REPLACE FUNCTION wf.wf_try_task_result_code(
  p_workflow_instance_id bigint,
  p_node_key text
)
RETURNS int
LANGUAGE plpgsql
STABLE
AS $$
DECLARE v_r int;
BEGIN
  SELECT ne.result_code INTO v_r
  FROM wf.node_execution ne
  INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
  WHERE ne.workflow_instance_id = p_workflow_instance_id
    AND wn.node_key = p_node_key
    AND ne.status = 'SUCCEEDED'
  ORDER BY ne.ended_at_utc DESC NULLS LAST, ne.id DESC
  LIMIT 1;
  RETURN v_r;
END;
$$;

CREATE OR REPLACE FUNCTION wf.wf_get_scope_variable_json(
  p_workflow_instance_id bigint,
  p_start_scope_node_execution_id bigint,
  p_var_name text
)
RETURNS text
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_cur bigint := coalesce(p_start_scope_node_execution_id, 0);
  v_v text;
  v_parent bigint;
BEGIN
  LOOP
    SELECT sv.value_json::text INTO v_v
    FROM wf.scope_variable sv
    WHERE sv.workflow_instance_id = p_workflow_instance_id
      AND sv.scope_node_execution_id = v_cur
      AND sv.var_name = p_var_name;
    IF v_v IS NOT NULL THEN
      RETURN v_v;
    END IF;
    EXIT WHEN v_cur = 0;
    SELECT ne.parent_node_execution_id INTO v_parent
    FROM wf.node_execution ne WHERE ne.id = v_cur;
    v_cur := coalesce(v_parent, 0);
  END LOOP;
  RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION wf.wf_get_scope_variable_int(
  p_workflow_instance_id bigint,
  p_start_scope_node_execution_id bigint,
  p_var_name text
)
RETURNS int
LANGUAGE plpgsql
STABLE
AS $$
DECLARE v_json text;
BEGIN
  v_json := wf.wf_get_scope_variable_json(p_workflow_instance_id, p_start_scope_node_execution_id, p_var_name);
  IF v_json IS NULL OR btrim(v_json) = '' THEN
    RETURN NULL;
  END IF;
  BEGIN
    RETURN v_json::int;
  EXCEPTION WHEN others THEN
    RETURN NULL;
  END;
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_set_scope_variable(
  IN p_workflow_instance_id bigint,
  IN p_scope_node_execution_id bigint,
  IN p_var_name text,
  IN p_value_json text
)
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO wf.scope_variable (workflow_instance_id, scope_node_execution_id, var_name, value_json, updated_at_utc)
  VALUES (p_workflow_instance_id, p_scope_node_execution_id, p_var_name, coalesce(p_value_json::jsonb, 'null'::jsonb), (now() AT TIME ZONE 'utc'))
  ON CONFLICT (workflow_instance_id, scope_node_execution_id, var_name)
  DO UPDATE SET value_json = EXCLUDED.value_json, updated_at_utc = EXCLUDED.updated_at_utc;
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_init_instance_scope_from_context(
  IN p_workflow_instance_id bigint
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_ctx jsonb;
  v_key text;
  v_val jsonb;
BEGIN
  SELECT wi.context_json INTO v_ctx FROM wf.workflow_instance wi WHERE wi.id = p_workflow_instance_id;
  DELETE FROM wf.scope_variable
  WHERE workflow_instance_id = p_workflow_instance_id AND scope_node_execution_id = 0;
  IF v_ctx IS NULL OR v_ctx = '{}'::jsonb THEN
    RETURN;
  END IF;
  FOR v_key, v_val IN SELECT * FROM jsonb_each(v_ctx)
  LOOP
    CALL wf.wf_set_scope_variable(p_workflow_instance_id, 0, v_key, v_val::text);
  END LOOP;
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_seed_execution_context(
  IN p_node_execution_id bigint,
  IN p_workflow_instance_id bigint,
  IN p_workflow_node_id bigint,
  IN p_parent_node_execution_id bigint,
  IN p_iteration_no int,
  IN p_sequence_index int,
  IN p_parallel_index int
)
LANGUAGE plpgsql
AS $$
BEGIN
  DELETE FROM wf.execution_context WHERE node_execution_id = p_node_execution_id;
  INSERT INTO wf.execution_context (node_execution_id, context_key, context_value_json)
  VALUES (p_node_execution_id, 'ctx.iterationNo', to_jsonb(p_iteration_no)::text);
  IF p_sequence_index IS NOT NULL THEN
    INSERT INTO wf.execution_context (node_execution_id, context_key, context_value_json)
    VALUES (p_node_execution_id, 'ctx.sequenceIndex', to_jsonb(p_sequence_index)::text);
  END IF;
  IF p_parallel_index IS NOT NULL THEN
    INSERT INTO wf.execution_context (node_execution_id, context_key, context_value_json)
    VALUES (p_node_execution_id, 'ctx.parallelIndex', to_jsonb(p_parallel_index)::text);
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION wf.wf_build_input_json_for_action(
  p_node_execution_id bigint,
  p_workflow_instance_id bigint,
  p_workflow_node_id bigint,
  OUT p_final_json jsonb,
  OUT p_failed boolean,
  OUT p_fail_code int,
  OUT p_fail_msg text
)
LANGUAGE plpgsql
AS $$
BEGIN
  p_failed := false;
  p_fail_code := 0;
  p_fail_msg := NULL;
  SELECT coalesce(wit.template_json, '{}'::jsonb) INTO p_final_json
  FROM wf.workflow_input_template wit
  WHERE wit.workflow_node_id = p_workflow_node_id;
  IF p_final_json IS NULL THEN
    p_final_json := '{}'::jsonb;
  END IF;
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_engine_on_composite_complete(
  IN p_node_execution_id bigint
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_parent bigint;
  v_inst bigint;
BEGIN
  SELECT ne.parent_node_execution_id, ne.workflow_instance_id
  INTO v_parent, v_inst
  FROM wf.node_execution ne WHERE ne.id = p_node_execution_id;

  IF v_parent IS NULL THEN
    UPDATE wf.workflow_instance
    SET status = 'COMPLETED', completed_at_utc = (now() AT TIME ZONE 'utc')
    WHERE id = v_inst AND status = 'RUNNING';
    RETURN;
  END IF;
  CALL wf.wf_engine_continue_parent(v_parent);
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_sequence_continue(IN p_sequence_execution_id bigint)
LANGUAGE plpgsql
AS $$
DECLARE
  v_inst bigint;
  v_seq_node bigint;
  v_last_child_ne bigint;
  v_last_status text;
  v_last_child_wn bigint;
  v_next_order int;
  v_next_child bigint;
  v_iter int;
BEGIN
  SELECT ne.workflow_instance_id, ne.workflow_node_id INTO v_inst, v_seq_node
  FROM wf.node_execution ne WHERE ne.id = p_sequence_execution_id;

  SELECT ne.id, ne.workflow_node_id, ne.status
  INTO v_last_child_ne, v_last_child_wn, v_last_status
  FROM wf.node_execution ne
  WHERE ne.parent_node_execution_id = p_sequence_execution_id
    AND ne.status IN ('SUCCEEDED','FAILED','SKIPPED')
  ORDER BY ne.ended_at_utc DESC NULLS LAST, ne.id DESC
  LIMIT 1;

  IF v_last_status = 'FAILED' THEN
    UPDATE wf.node_execution SET status = 'FAILED', ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = p_sequence_execution_id;
    UPDATE wf.workflow_instance SET status = 'FAILED', completed_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_inst;
    RETURN;
  END IF;

  SELECT e.child_order + 1 INTO v_next_order
  FROM wf.workflow_edge e
  WHERE e.parent_node_id = v_seq_node AND e.child_node_id = v_last_child_wn;

  SELECT e.child_node_id INTO v_next_child
  FROM wf.workflow_edge e
  WHERE e.parent_node_id = v_seq_node AND e.child_order = v_next_order
  LIMIT 1;

  IF v_next_child IS NULL THEN
    UPDATE wf.node_execution SET status = 'SUCCEEDED', ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = p_sequence_execution_id;
    CALL wf.wf_engine_on_composite_complete(p_sequence_execution_id);
    RETURN;
  END IF;

  SELECT ne.iteration_no INTO v_iter FROM wf.node_execution ne WHERE ne.id = p_sequence_execution_id;
  CALL wf.wf_engine_activate(v_inst, v_next_child, p_sequence_execution_id, v_iter, v_next_order, NULL);
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_parallel_continue(IN p_parallel_execution_id bigint)
LANGUAGE plpgsql
AS $$
DECLARE
  v_inst bigint;
  v_pnode bigint;
  v_total int;
  v_finished int;
BEGIN
  SELECT ne.workflow_instance_id, ne.workflow_node_id INTO v_inst, v_pnode
  FROM wf.node_execution ne WHERE ne.id = p_parallel_execution_id;

  SELECT count(*) INTO v_total FROM wf.workflow_edge e WHERE e.parent_node_id = v_pnode;
  SELECT count(*) INTO v_finished
  FROM wf.node_execution ne
  WHERE ne.parent_node_execution_id = p_parallel_execution_id
    AND ne.status IN ('SUCCEEDED','FAILED','SKIPPED','CANCELLED');

  IF v_finished < v_total THEN RETURN; END IF;

  IF EXISTS (
    SELECT 1 FROM wf.node_execution ne
    WHERE ne.parent_node_execution_id = p_parallel_execution_id AND ne.status = 'FAILED'
  ) THEN
    UPDATE wf.node_execution SET status = 'FAILED', ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = p_parallel_execution_id;
    UPDATE wf.workflow_instance SET status = 'FAILED', completed_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_inst;
    RETURN;
  END IF;

  UPDATE wf.node_execution SET status = 'SUCCEEDED', ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = p_parallel_execution_id;
  CALL wf.wf_engine_on_composite_complete(p_parallel_execution_id);
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_repeat_continue(IN p_repeat_execution_id bigint)
LANGUAGE plpgsql
AS $$
DECLARE
  v_inst bigint;
  v_ctl bigint;
  v_ls bigint;
  v_cur int;
  v_max int;
  v_body bigint;
BEGIN
  SELECT ne.workflow_instance_id, ne.workflow_node_id INTO v_inst, v_ctl
  FROM wf.node_execution ne WHERE ne.id = p_repeat_execution_id;

  SELECT ls.id, ls.current_iteration, ls.repeat_target_count
  INTO v_ls, v_cur, v_max
  FROM wf.loop_state ls
  WHERE ls.scope_node_execution_id = p_repeat_execution_id
  LIMIT 1;

  IF v_ls IS NULL THEN
    UPDATE wf.node_execution SET status = 'FAILED', engine_error_code = 10007, ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = p_repeat_execution_id;
    UPDATE wf.workflow_instance SET status = 'FAILED', completed_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_inst;
    RETURN;
  END IF;

  v_cur := v_cur + 1;
  UPDATE wf.loop_state SET current_iteration = v_cur WHERE id = v_ls;

  IF v_cur >= v_max THEN
    UPDATE wf.node_execution SET status = 'SUCCEEDED', ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = p_repeat_execution_id;
    CALL wf.wf_engine_on_composite_complete(p_repeat_execution_id);
    RETURN;
  END IF;

  SELECT e.child_node_id INTO v_body
  FROM wf.workflow_edge e
  WHERE e.parent_node_id = v_ctl AND e.branch_kind = 'BODY'
  ORDER BY e.child_order ASC LIMIT 1;

  CALL wf.wf_engine_activate(v_inst, v_body, p_repeat_execution_id, v_cur + 1, NULL, NULL);
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_while_continue(IN p_while_execution_id bigint)
LANGUAGE plpgsql
AS $$
DECLARE
  v_inst bigint;
  v_ctl bigint;
  v_body bigint;
  v_cond int;
  v_cref text;
BEGIN
  SELECT ne.workflow_instance_id, ne.workflow_node_id INTO v_inst, v_ctl
  FROM wf.node_execution ne WHERE ne.id = p_while_execution_id;

  SELECT wn.condition_ref_node_key INTO v_cref FROM wf.workflow_node wn WHERE wn.id = v_ctl;
  v_cond := wf.wf_try_task_result_code(v_inst, v_cref);

  IF v_cond IS NULL OR v_cond = 0 THEN
    UPDATE wf.node_execution SET status = 'SUCCEEDED', ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = p_while_execution_id;
    CALL wf.wf_engine_on_composite_complete(p_while_execution_id);
    RETURN;
  END IF;

  SELECT e.child_node_id INTO v_body
  FROM wf.workflow_edge e
  WHERE e.parent_node_id = v_ctl AND e.branch_kind = 'BODY'
  ORDER BY e.child_order ASC LIMIT 1;

  CALL wf.wf_engine_activate(v_inst, v_body, p_while_execution_id, 1, NULL, NULL);
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_engine_continue_parent(IN p_parent_node_execution_id bigint)
LANGUAGE plpgsql
AS $$
DECLARE v_ptype text;
BEGIN
  SELECT wn.node_type INTO v_ptype
  FROM wf.node_execution ne
  INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
  WHERE ne.id = p_parent_node_execution_id;

  IF v_ptype = 'SEQUENCE' THEN
    CALL wf.wf_sequence_continue(p_parent_node_execution_id);
  ELSIF v_ptype = 'PARALLEL' THEN
    CALL wf.wf_parallel_continue(p_parent_node_execution_id);
  ELSIF v_ptype IN ('IF','SWITCH') THEN
    UPDATE wf.node_execution SET status = 'SUCCEEDED', ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = p_parent_node_execution_id;
    CALL wf.wf_engine_on_composite_complete(p_parent_node_execution_id);
  ELSIF v_ptype = 'REPEAT' THEN
    CALL wf.wf_repeat_continue(p_parent_node_execution_id);
  ELSIF v_ptype = 'WHILE' THEN
    CALL wf.wf_while_continue(p_parent_node_execution_id);
  END IF;
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_engine_on_action_complete(
  IN p_action_execution_id bigint,
  IN p_result_code int,
  IN p_output_json jsonb
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_inst bigint;
  v_parent bigint;
  v_ptype text;
BEGIN
  SELECT ne.workflow_instance_id, ne.parent_node_execution_id
  INTO v_inst, v_parent
  FROM wf.node_execution ne WHERE ne.id = p_action_execution_id;

  IF p_result_code < 0 THEN
    UPDATE wf.node_execution
    SET status = 'FAILED', result_code = p_result_code, output_json = p_output_json,
        ended_at_utc = (now() AT TIME ZONE 'utc'), engine_error_code = p_result_code
    WHERE id = p_action_execution_id;
    DELETE FROM wf.task_lease WHERE node_execution_id = p_action_execution_id;
    UPDATE wf.workflow_instance SET status = 'FAILED', completed_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_inst;
    RETURN;
  END IF;

  UPDATE wf.node_execution
  SET status = 'SUCCEEDED', result_code = p_result_code, output_json = p_output_json,
      ended_at_utc = (now() AT TIME ZONE 'utc')
  WHERE id = p_action_execution_id;
  DELETE FROM wf.task_lease WHERE node_execution_id = p_action_execution_id;

  IF v_parent IS NULL THEN
    UPDATE wf.workflow_instance SET status = 'COMPLETED', completed_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_inst;
    RETURN;
  END IF;

  SELECT wn.node_type INTO v_ptype
  FROM wf.node_execution ne INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
  WHERE ne.id = v_parent;

  IF v_ptype = 'SEQUENCE' THEN
    CALL wf.wf_sequence_continue(v_parent);
  ELSIF v_ptype = 'PARALLEL' THEN
    CALL wf.wf_parallel_continue(v_parent);
  ELSIF v_ptype IN ('IF','SWITCH') THEN
    UPDATE wf.node_execution SET status = 'SUCCEEDED', ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_parent;
    CALL wf.wf_engine_on_composite_complete(v_parent);
  ELSIF v_ptype = 'REPEAT' THEN
    CALL wf.wf_repeat_continue(v_parent);
  ELSIF v_ptype = 'WHILE' THEN
    CALL wf.wf_while_continue(v_parent);
  END IF;
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_engine_activate(
  IN p_workflow_instance_id bigint,
  IN p_workflow_node_id bigint,
  IN p_parent_node_execution_id bigint,
  IN p_iteration_no int DEFAULT 0,
  IN p_sequence_index int DEFAULT NULL,
  IN p_parallel_index int DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_node_type text;
  v_node_key text;
  v_ne_id bigint;
  v_pex bigint;
  v_fj jsonb;
  v_failed boolean;
  v_fc int;
  v_fm text;
  v_child bigint;
  v_ord int;
  v_pidx int := 0;
  v_cond int;
  v_pick text;
  v_rcount int;
  v_body bigint;
  v_wcond int;
  rec record;
BEGIN
  SELECT wn.node_type, wn.node_key INTO v_node_type, v_node_key
  FROM wf.workflow_node wn WHERE wn.id = p_workflow_node_id;
  IF v_node_type IS NULL THEN RETURN; END IF;

  IF v_node_type = 'ACTION' THEN
    INSERT INTO wf.node_execution (
      workflow_instance_id, workflow_node_id, status, attempt_no,
      parent_node_execution_id, iteration_no, available_at_utc
    ) VALUES (
      p_workflow_instance_id, p_workflow_node_id, 'READY', 1,
      p_parent_node_execution_id, p_iteration_no, (now() AT TIME ZONE 'utc')
    ) RETURNING id INTO v_ne_id;

    CALL wf.wf_seed_execution_context(
      v_ne_id, p_workflow_instance_id, p_workflow_node_id,
      p_parent_node_execution_id, p_iteration_no, p_sequence_index, p_parallel_index
    );

    SELECT * INTO v_fj, v_failed, v_fc, v_fm
    FROM wf.wf_build_input_json_for_action(v_ne_id, p_workflow_instance_id, p_workflow_node_id);

    IF v_failed THEN
      UPDATE wf.node_execution SET status = 'FAILED', engine_error_code = v_fc, engine_error_message = v_fm,
        ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_ne_id;
      UPDATE wf.workflow_instance SET status = 'FAILED', completed_at_utc = (now() AT TIME ZONE 'utc')
      WHERE id = p_workflow_instance_id;
      RETURN;
    END IF;
    UPDATE wf.node_execution SET input_json = v_fj WHERE id = v_ne_id;
    RETURN;
  END IF;

  INSERT INTO wf.node_execution (
    workflow_instance_id, workflow_node_id, status, attempt_no,
    parent_node_execution_id, iteration_no, started_at_utc, available_at_utc
  ) VALUES (
    p_workflow_instance_id, p_workflow_node_id, 'RUNNING', 1,
    p_parent_node_execution_id, p_iteration_no, (now() AT TIME ZONE 'utc'), (now() AT TIME ZONE 'utc')
  ) RETURNING id INTO v_pex;

  IF v_node_type = 'SEQUENCE' THEN
    SELECT e.child_node_id, e.child_order INTO v_child, v_ord
    FROM wf.workflow_edge e WHERE e.parent_node_id = p_workflow_node_id
    ORDER BY e.child_order ASC LIMIT 1;
    IF v_child IS NULL THEN
      UPDATE wf.node_execution SET status = 'SUCCEEDED', ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_pex;
      CALL wf.wf_engine_on_composite_complete(v_pex);
      RETURN;
    END IF;
    CALL wf.wf_engine_activate(p_workflow_instance_id, v_child, v_pex, p_iteration_no, v_ord, NULL);
    RETURN;
  END IF;

  IF v_node_type = 'PARALLEL' THEN
    FOR rec IN SELECT e.child_node_id FROM wf.workflow_edge e WHERE e.parent_node_id = p_workflow_node_id ORDER BY e.child_order
    LOOP
      CALL wf.wf_engine_activate(p_workflow_instance_id, rec.child_node_id, v_pex, p_iteration_no, NULL, v_pidx);
      v_pidx := v_pidx + 1;
    END LOOP;
    RETURN;
  END IF;

  IF v_node_type = 'IF' THEN
    SELECT wn.condition_ref_node_key INTO v_node_key FROM wf.workflow_node wn WHERE wn.id = p_workflow_node_id;
    v_cond := wf.wf_try_task_result_code(p_workflow_instance_id, v_node_key);
    v_pick := CASE WHEN v_cond IS NOT NULL AND v_cond <> 0 THEN 'THEN' ELSE 'ELSE' END;
    SELECT e.child_node_id INTO v_child FROM wf.workflow_edge e
    WHERE e.parent_node_id = p_workflow_node_id AND e.branch_kind = v_pick
    ORDER BY e.child_order ASC LIMIT 1;
    IF v_child IS NULL THEN
      UPDATE wf.node_execution SET status = 'FAILED', engine_error_code = 10003, ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_pex;
      UPDATE wf.workflow_instance SET status = 'FAILED', completed_at_utc = (now() AT TIME ZONE 'utc') WHERE id = p_workflow_instance_id;
      RETURN;
    END IF;
    CALL wf.wf_engine_activate(p_workflow_instance_id, v_child, v_pex, p_iteration_no, NULL, NULL);
    RETURN;
  END IF;

  IF v_node_type = 'SWITCH' THEN
    SELECT wn.switch_ref_node_key INTO v_node_key FROM wf.workflow_node wn WHERE wn.id = p_workflow_node_id;
    v_cond := wf.wf_try_task_result_code(p_workflow_instance_id, v_node_key);
    SELECT e.child_node_id INTO v_child FROM wf.workflow_edge e
    WHERE e.parent_node_id = p_workflow_node_id AND e.branch_kind = 'CASE' AND e.switch_case_value = v_cond
    ORDER BY e.child_order ASC LIMIT 1;
    IF v_child IS NULL THEN
      SELECT e.child_node_id INTO v_child FROM wf.workflow_edge e
      WHERE e.parent_node_id = p_workflow_node_id AND e.branch_kind = 'DEFAULT'
      ORDER BY e.child_order ASC LIMIT 1;
    END IF;
    IF v_child IS NULL THEN
      UPDATE wf.node_execution SET status = 'FAILED', engine_error_code = 10004, ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_pex;
      UPDATE wf.workflow_instance SET status = 'FAILED', completed_at_utc = (now() AT TIME ZONE 'utc') WHERE id = p_workflow_instance_id;
      RETURN;
    END IF;
    CALL wf.wf_engine_activate(p_workflow_instance_id, v_child, v_pex, p_iteration_no, NULL, NULL);
    RETURN;
  END IF;

  IF v_node_type = 'REPEAT' THEN
    SELECT wn.repeat_count INTO v_rcount FROM wf.workflow_node wn WHERE wn.id = p_workflow_node_id;
    IF v_rcount IS NULL OR v_rcount < 1 THEN v_rcount := 1; END IF;
    INSERT INTO wf.loop_state (workflow_instance_id, control_node_id, scope_node_execution_id, current_iteration, repeat_target_count)
    VALUES (p_workflow_instance_id, p_workflow_node_id, v_pex, 0, v_rcount);
    SELECT e.child_node_id INTO v_body FROM wf.workflow_edge e
    WHERE e.parent_node_id = p_workflow_node_id AND e.branch_kind = 'BODY' ORDER BY e.child_order ASC LIMIT 1;
    IF v_body IS NULL THEN
      UPDATE wf.node_execution SET status = 'FAILED', engine_error_code = 10005, ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_pex;
      UPDATE wf.workflow_instance SET status = 'FAILED', completed_at_utc = (now() AT TIME ZONE 'utc') WHERE id = p_workflow_instance_id;
      RETURN;
    END IF;
    CALL wf.wf_engine_activate(p_workflow_instance_id, v_body, v_pex, 1, NULL, NULL);
    RETURN;
  END IF;

  IF v_node_type = 'WHILE' THEN
    SELECT e.child_node_id INTO v_body FROM wf.workflow_edge e
    WHERE e.parent_node_id = p_workflow_node_id AND e.branch_kind = 'BODY' ORDER BY e.child_order ASC LIMIT 1;
    IF v_body IS NULL THEN
      UPDATE wf.node_execution SET status = 'FAILED', engine_error_code = 10006, ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_pex;
      UPDATE wf.workflow_instance SET status = 'FAILED', completed_at_utc = (now() AT TIME ZONE 'utc') WHERE id = p_workflow_instance_id;
      RETURN;
    END IF;
    SELECT wn.condition_ref_node_key INTO v_node_key FROM wf.workflow_node wn WHERE wn.id = p_workflow_node_id;
    v_wcond := wf.wf_try_task_result_code(p_workflow_instance_id, v_node_key);
    IF v_wcond IS NULL OR v_wcond = 0 THEN
      UPDATE wf.node_execution SET status = 'SUCCEEDED', ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_pex;
      CALL wf.wf_engine_on_composite_complete(v_pex);
      RETURN;
    END IF;
    CALL wf.wf_engine_activate(p_workflow_instance_id, v_body, v_pex, 1, NULL, NULL);
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION wf.wf_try_task_output_json(
  p_workflow_instance_id bigint,
  p_node_key text,
  p_json_path text DEFAULT NULL
)
RETURNS text
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_out text;
  v_jv text;
BEGIN
  SELECT ne.output_json::text INTO v_out
  FROM wf.node_execution ne
  INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
  WHERE ne.workflow_instance_id = p_workflow_instance_id
    AND wn.node_key = p_node_key
    AND ne.status = 'SUCCEEDED'
  ORDER BY ne.ended_at_utc DESC NULLS LAST, ne.id DESC
  LIMIT 1;
  IF v_out IS NULL THEN RETURN NULL; END IF;
  IF p_json_path IS NULL OR btrim(p_json_path) = '' THEN RETURN v_out; END IF;
  BEGIN
    v_jv := JSON_VALUE(v_out::json, p_json_path);
    IF v_jv IS NOT NULL THEN RETURN v_jv; END IF;
  EXCEPTION WHEN others THEN NULL;
  END;
  RETURN wf.wf_json_fragment_from_string(v_out);
END;
$$;

-- Stub for contract parity; full resolver in wf_sql_runtime_parity port
CREATE OR REPLACE PROCEDURE wf.wf_resolve_token(
  IN p_token text,
  IN p_node_execution_id bigint,
  IN p_workflow_instance_id bigint,
  OUT p_out_fragment text,
  OUT p_failed boolean,
  OUT p_fail_code int,
  OUT p_fail_msg text
)
LANGUAGE plpgsql
AS $$
BEGIN
  p_failed := false;
  p_fail_code := 0;
  p_fail_msg := NULL;
  p_out_fragment := wf.wf_json_fragment_from_string(p_token);
END;
$$;
