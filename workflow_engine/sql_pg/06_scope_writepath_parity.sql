/*
  PostgreSQL scope write-path parity with Delphi WfEngine.Scope.
  Deploy after 05_runtime_parity.sql.
*/

CREATE OR REPLACE FUNCTION wf.wf_scope_write_exec_id(
  p_action_execution_id bigint,
  p_parent_node_execution_id bigint
)
RETURNS bigint
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_parent_node_type text;
BEGIN
  IF p_parent_node_execution_id IS NULL THEN
    RETURN 0;
  END IF;
  SELECT wn.node_type INTO v_parent_node_type
  FROM wf.node_execution ne
  INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
  WHERE ne.id = p_parent_node_execution_id;
  IF v_parent_node_type = 'PARALLEL' THEN
    RETURN p_action_execution_id;
  END IF;
  RETURN p_parent_node_execution_id;
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_open_scope(
  IN p_workflow_instance_id bigint,
  IN p_from_scope_exec_id bigint,
  IN p_to_scope_exec_id bigint,
  IN p_workflow_node_id bigint
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_from bigint := coalesce(p_from_scope_exec_id, 0);
  v_to bigint := coalesce(p_to_scope_exec_id, 0);
  rec record;
  v_resolved text;
  v_failed boolean;
  v_fc int;
  v_fm text;
BEGIN
  IF v_from <> v_to THEN
    INSERT INTO wf.scope_variable (workflow_instance_id, scope_node_execution_id, var_name, value_json)
    SELECT sv.workflow_instance_id, v_to, sv.var_name, sv.value_json
    FROM wf.scope_variable sv
    WHERE sv.workflow_instance_id = p_workflow_instance_id
      AND sv.scope_node_execution_id = v_from
      AND NOT EXISTS (
        SELECT 1 FROM wf.scope_variable x
        WHERE x.workflow_instance_id = p_workflow_instance_id
          AND x.scope_node_execution_id = v_to
          AND x.var_name = sv.var_name
      );
  END IF;

  FOR rec IN
    SELECT nsd.var_name, nsd.default_expr
    FROM wf.node_scope_default nsd
    WHERE nsd.workflow_node_id = p_workflow_node_id
  LOOP
    CALL wf.wf_resolve_placeholders(
      rec.default_expr, v_to, p_workflow_instance_id,
      v_resolved, v_failed, v_fc, v_fm
    );
    IF NOT v_failed THEN
      CALL wf.wf_set_scope_variable(p_workflow_instance_id, v_to, rec.var_name, v_resolved);
    END IF;
  END LOOP;
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_apply_output_bindings(
  IN p_action_execution_id bigint,
  IN p_result_code int,
  IN p_output_json jsonb
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_inst bigint;
  v_wn bigint;
  v_parent bigint;
  v_scope_exec bigint;
  v_oj text;
  rec record;
  v_frag text;
  v_jp text;
BEGIN
  SELECT ne.workflow_instance_id, ne.workflow_node_id, ne.parent_node_execution_id
  INTO v_inst, v_wn, v_parent
  FROM wf.node_execution ne WHERE ne.id = p_action_execution_id;
  IF v_wn IS NULL THEN
    RETURN;
  END IF;

  v_oj := NULLIF(btrim(p_output_json::text), '');
  IF v_oj = 'null' THEN
    v_oj := NULL;
  END IF;

  v_scope_exec := wf.wf_scope_write_exec_id(p_action_execution_id, v_parent);

  FOR rec IN
    SELECT vob.var_name, vob.source_kind, vob.source_json_path
    FROM wf.variable_output_binding vob
    WHERE vob.workflow_node_id = v_wn
  LOOP
    IF rec.source_kind = 'result_code' THEN
      v_frag := coalesce(p_result_code, 0)::text;
    ELSIF rec.source_kind = 'output_path' THEN
      IF v_oj IS NULL THEN
        v_frag := 'null';
      ELSE
        v_jp := coalesce(btrim(rec.source_json_path), '');
        IF v_jp = '' THEN
          v_frag := v_oj;
        ELSE
          IF left(v_jp, 1) <> '$' THEN
            v_jp := '$.' || v_jp;
          END IF;
          BEGIN
            v_frag := jsonb_path_query_first(v_oj::jsonb, v_jp::jsonpath)::text;
          EXCEPTION WHEN others THEN
            v_frag := NULL;
          END;
          IF v_frag IS NULL THEN
            v_frag := 'null';
          END IF;
        END IF;
      END IF;
    ELSE
      v_frag := 'null';
    END IF;

    CALL wf.wf_set_scope_variable(v_inst, v_scope_exec, rec.var_name, v_frag);
  END LOOP;
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
    IF NOT EXISTS (
      SELECT 1 FROM wf.workflow_instance wi
      WHERE wi.id = v_inst AND wi.status = 'RUNNING'
    ) THEN
      RETURN;
    END IF;
    IF v_parent IS NOT NULL THEN
      CALL wf.wf_engine_continue_parent(v_parent);
    END IF;
    RETURN;
  END IF;

  UPDATE wf.node_execution
  SET status = 'SUCCEEDED', result_code = p_result_code, output_json = p_output_json,
      ended_at_utc = (now() AT TIME ZONE 'utc')
  WHERE id = p_action_execution_id;
  DELETE FROM wf.task_lease WHERE node_execution_id = p_action_execution_id;

  CALL wf.wf_apply_output_bindings(p_action_execution_id, p_result_code, p_output_json);

  IF NOT EXISTS (
    SELECT 1 FROM wf.workflow_instance wi
    WHERE wi.id = v_inst AND wi.status = 'RUNNING'
  ) THEN
    RETURN;
  END IF;

  IF v_parent IS NULL THEN
    UPDATE wf.workflow_instance SET status = 'COMPLETED', completed_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_inst AND status = 'RUNNING';
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
  -- FOREACH parents (direct ACTION body) dispatch through the router so re-running
  -- this parity script never drops FOREACH continuation.
  ELSIF v_ptype = 'FOREACH' THEN
    CALL wf.wf_foreach_route_continue(v_parent);
  END IF;
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
  v_cvar text;
  v_iter int;
BEGIN
  SELECT ne.workflow_instance_id, ne.workflow_node_id INTO v_inst, v_ctl
  FROM wf.node_execution ne WHERE ne.id = p_while_execution_id;

  SELECT wn.condition_var, wn.condition_ref_node_key INTO v_cvar, v_cref
  FROM wf.workflow_node wn WHERE wn.id = v_ctl;

  IF coalesce(btrim(v_cvar), '') <> '' THEN
    v_cond := wf.wf_get_scope_variable_int(v_inst, p_while_execution_id, v_cvar);
  END IF;
  IF v_cond IS NULL AND coalesce(btrim(v_cref), '') <> '' THEN
    v_cond := wf.wf_try_task_result_code(v_inst, v_cref);
  END IF;

  IF v_cond IS NULL OR v_cond = 0 THEN
    UPDATE wf.node_execution SET status = 'SUCCEEDED', ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = p_while_execution_id;
    CALL wf.wf_engine_on_composite_complete(p_while_execution_id);
    RETURN;
  END IF;

  SELECT coalesce(max(ne.iteration_no), 0) INTO v_iter
  FROM wf.node_execution ne
  WHERE ne.parent_node_execution_id = p_while_execution_id
    AND ne.workflow_node_id = (
      SELECT e.child_node_id FROM wf.workflow_edge e
      WHERE e.parent_node_id = v_ctl AND e.branch_kind = 'BODY'
      ORDER BY e.child_order ASC LIMIT 1
    );

  SELECT e.child_node_id INTO v_body
  FROM wf.workflow_edge e
  WHERE e.parent_node_id = v_ctl AND e.branch_kind = 'BODY'
  ORDER BY e.child_order ASC LIMIT 1;

  CALL wf.wf_engine_activate(v_inst, v_body, p_while_execution_id, v_iter + 1, NULL, NULL);
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
  v_cref text;
  v_cvar text;
  v_sref text;
  v_svar text;
  v_parent_ntype text;
  v_scope bigint;
  rec record;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM wf.workflow_instance wi
    WHERE wi.id = p_workflow_instance_id AND wi.status = 'RUNNING'
  ) THEN
    RETURN;
  END IF;

  SELECT wn.node_type INTO v_node_type
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

    IF p_parent_node_execution_id IS NOT NULL THEN
      SELECT wn.node_type INTO v_parent_ntype
      FROM wf.node_execution ne
      INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
      WHERE ne.id = p_parent_node_execution_id;
      IF v_parent_ntype = 'PARALLEL' THEN
        INSERT INTO wf.scope_variable (workflow_instance_id, scope_node_execution_id, var_name, value_json)
        SELECT sv.workflow_instance_id, v_ne_id, sv.var_name, sv.value_json
        FROM wf.scope_variable sv
        WHERE sv.workflow_instance_id = p_workflow_instance_id
          AND sv.scope_node_execution_id = p_parent_node_execution_id;
      END IF;
    END IF;

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

  v_scope := coalesce(p_parent_node_execution_id, 0);
  CALL wf.wf_open_scope(p_workflow_instance_id, v_scope, v_pex, p_workflow_node_id);

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
    SELECT wn.condition_ref_node_key, wn.condition_var INTO v_cref, v_cvar
    FROM wf.workflow_node wn WHERE wn.id = p_workflow_node_id;
    IF coalesce(btrim(v_cvar), '') <> '' THEN
      v_cond := wf.wf_get_scope_variable_int(p_workflow_instance_id, v_pex, v_cvar);
    END IF;
    IF v_cond IS NULL AND coalesce(btrim(v_cref), '') <> '' THEN
      v_cond := wf.wf_try_task_result_code(p_workflow_instance_id, v_cref);
    END IF;
    v_pick := CASE WHEN v_cond IS NOT NULL AND v_cond <> 0 THEN 'THEN' ELSE 'ELSE' END;
    SELECT e.child_node_id INTO v_child FROM wf.workflow_edge e
    WHERE e.parent_node_id = p_workflow_node_id AND e.branch_kind = v_pick
    ORDER BY e.child_order ASC LIMIT 1;
    IF v_child IS NULL THEN
      UPDATE wf.node_execution SET status = 'FAILED', engine_error_code = 10003,
        engine_error_message = 'Missing IF branch.', ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_pex;
      UPDATE wf.workflow_instance SET status = 'FAILED', completed_at_utc = (now() AT TIME ZONE 'utc') WHERE id = p_workflow_instance_id;
      RETURN;
    END IF;
    CALL wf.wf_engine_activate(p_workflow_instance_id, v_child, v_pex, p_iteration_no, NULL, NULL);
    RETURN;
  END IF;

  IF v_node_type = 'SWITCH' THEN
    SELECT wn.switch_ref_node_key, wn.switch_var INTO v_sref, v_svar
    FROM wf.workflow_node wn WHERE wn.id = p_workflow_node_id;
    IF coalesce(btrim(v_svar), '') <> '' THEN
      v_cond := wf.wf_get_scope_variable_int(p_workflow_instance_id, v_pex, v_svar);
    END IF;
    IF v_cond IS NULL AND coalesce(btrim(v_sref), '') <> '' THEN
      v_cond := wf.wf_try_task_result_code(p_workflow_instance_id, v_sref);
    END IF;
    SELECT e.child_node_id INTO v_child FROM wf.workflow_edge e
    WHERE e.parent_node_id = p_workflow_node_id AND e.branch_kind = 'CASE' AND e.switch_case_value = v_cond
    ORDER BY e.child_order ASC LIMIT 1;
    IF v_child IS NULL THEN
      SELECT e.child_node_id INTO v_child FROM wf.workflow_edge e
      WHERE e.parent_node_id = p_workflow_node_id AND e.branch_kind = 'DEFAULT'
      ORDER BY e.child_order ASC LIMIT 1;
    END IF;
    IF v_child IS NULL THEN
      UPDATE wf.node_execution SET status = 'FAILED', engine_error_code = 10004,
        engine_error_message = 'Missing SWITCH case.', ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_pex;
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
    SELECT wn.condition_ref_node_key, wn.condition_var INTO v_cref, v_cvar
    FROM wf.workflow_node wn WHERE wn.id = p_workflow_node_id;
    IF coalesce(btrim(v_cvar), '') <> '' THEN
      v_wcond := wf.wf_get_scope_variable_int(p_workflow_instance_id, v_pex, v_cvar);
    END IF;
    IF v_wcond IS NULL AND coalesce(btrim(v_cref), '') <> '' THEN
      v_wcond := wf.wf_try_task_result_code(p_workflow_instance_id, v_cref);
    END IF;
    IF v_wcond IS NULL OR v_wcond = 0 THEN
      UPDATE wf.node_execution SET status = 'SUCCEEDED', ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_pex;
      CALL wf.wf_engine_on_composite_complete(v_pex);
      RETURN;
    END IF;
    CALL wf.wf_engine_activate(p_workflow_instance_id, v_body, v_pex, 1, NULL, NULL);
  END IF;
END;
$$;
