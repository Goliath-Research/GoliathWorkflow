/*
  PostgreSQL FOREACH control-flow parity (port of sql/wf_sql_foreach_support.sql).

  Deploy after 06_scope_writepath_parity.sql and 07_scope_encoding_parity.sql.

  FOREACH CAAS (iteration-bundle short-circuit):
  Local engine probes ``{project_root}/.caas/foreach_bundle/{content_key}/``.
  Distributed gateway/workers may mirror hits into ``wf.foreach_bundle_entry``;
  ``wf_foreach_caas_try_skip_body`` then marks BODY SKIPPED without claiming leaf ACTIONs.
*/

CREATE TABLE IF NOT EXISTS wf.foreach_bundle_entry (
  workflow_instance_id bigint NOT NULL,
  foreach_node_key text NOT NULL,
  iteration_index int NOT NULL,
  content_key text NOT NULL,
  status text NOT NULL DEFAULT 'completed',
  committed_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  PRIMARY KEY (workflow_instance_id, foreach_node_key, iteration_index)
);

CREATE INDEX IF NOT EXISTS ix_foreach_bundle_entry_content
  ON wf.foreach_bundle_entry (content_key);

CREATE OR REPLACE FUNCTION wf.wf_foreach_bundle_is_hit(
  p_workflow_instance_id bigint,
  p_foreach_node_key text,
  p_iteration_index int
)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM wf.foreach_bundle_entry b
    WHERE b.workflow_instance_id = p_workflow_instance_id
      AND b.foreach_node_key = p_foreach_node_key
      AND b.iteration_index = p_iteration_index
      AND b.status = 'completed'
  );
$$;

CREATE OR REPLACE FUNCTION wf.wf_foreach_caas_try_skip_body(
  p_workflow_instance_id bigint,
  p_body_node_execution_id bigint,
  p_foreach_node_execution_id bigint,
  p_iteration_no int
)
RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
  v_parent_type text;
  v_foreach_key text;
  v_zbi int;
BEGIN
  IF p_foreach_node_execution_id IS NULL OR p_body_node_execution_id IS NULL THEN
    RETURN false;
  END IF;

  SELECT wn.node_type, wn.node_key
  INTO v_parent_type, v_foreach_key
  FROM wf.node_execution ne
  INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
  WHERE ne.id = p_foreach_node_execution_id;

  IF v_parent_type IS DISTINCT FROM 'FOREACH' THEN
    RETURN false;
  END IF;

  v_zbi := CASE WHEN p_iteration_no < 1 THEN 0 ELSE p_iteration_no - 1 END;

  IF NOT wf.wf_foreach_bundle_is_hit(p_workflow_instance_id, v_foreach_key, v_zbi) THEN
    RETURN false;
  END IF;

  UPDATE wf.node_execution
  SET status = 'SKIPPED',
      ended_at_utc = (now() AT TIME ZONE 'utc'),
      engine_error_message = 'foreach_caas_bundle_hit'
  WHERE id = p_body_node_execution_id
    AND status IN ('PENDING', 'READY', 'RUNNING');

  CALL wf.wf_engine_on_composite_complete(p_body_node_execution_id);
  RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION wf.wf_json_array_length(p_json text)
RETURNS int
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
  IF p_json IS NULL OR btrim(p_json) = '' THEN
    RETURN NULL;
  END IF;
  IF left(btrim(p_json), 1) <> '[' THEN
    RETURN NULL;
  END IF;
  RETURN jsonb_array_length(p_json::jsonb);
EXCEPTION WHEN others THEN
  RETURN NULL;
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_foreach_bind_iteration(
  IN p_workflow_instance_id bigint,
  IN p_scope_node_execution_id bigint,
  IN p_collection_scope_exec_id bigint,
  IN p_collection_var text,
  IN p_item_var text,
  IN p_index_var text,
  IN p_zero_based_index int
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_coll text;
  v_elem jsonb;
  v_key text;
  v_val jsonb;
BEGIN
  IF p_collection_var IS NULL OR btrim(p_collection_var) = '' THEN
    RETURN;
  END IF;

  v_coll := wf.wf_get_scope_variable_json(
    p_workflow_instance_id, p_collection_scope_exec_id, p_collection_var
  );
  IF v_coll IS NULL THEN
    RETURN;
  END IF;

  v_elem := v_coll::jsonb -> p_zero_based_index;
  IF v_elem IS NULL OR v_elem = 'null'::jsonb THEN
    v_elem := 'null'::jsonb;
  END IF;

  CALL wf.wf_set_scope_variable(
    p_workflow_instance_id, p_scope_node_execution_id,
    coalesce(nullif(btrim(p_item_var), ''), 'item'), v_elem::text
  );
  CALL wf.wf_set_scope_variable(
    p_workflow_instance_id, p_scope_node_execution_id,
    coalesce(nullif(btrim(p_index_var), ''), 'index'), p_zero_based_index::text
  );

  IF jsonb_typeof(v_elem) = 'object' THEN
    FOR v_key, v_val IN SELECT * FROM jsonb_each(v_elem)
    LOOP
      IF v_key IS NOT NULL
         AND v_key <> coalesce(nullif(btrim(p_item_var), ''), 'item')
         AND v_key <> coalesce(nullif(btrim(p_index_var), ''), 'index')
      THEN
        CALL wf.wf_set_scope_variable(
          p_workflow_instance_id, p_scope_node_execution_id, v_key, v_val::text
        );
      END IF;
    END LOOP;
  END IF;
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_try_bind_foreach_body(
  IN p_workflow_instance_id bigint,
  IN p_workflow_node_id bigint,
  IN p_parent_node_execution_id bigint,
  IN p_scope_node_execution_id bigint,
  IN p_iteration_no int
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_parent_node_id bigint;
  v_parent_type text;
  v_coll text;
  v_item text;
  v_idx text;
  v_zbi int;
BEGIN
  IF p_parent_node_execution_id IS NULL THEN
    RETURN;
  END IF;

  SELECT ne.workflow_node_id, wn.node_type
  INTO v_parent_node_id, v_parent_type
  FROM wf.node_execution ne
  INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
  WHERE ne.id = p_parent_node_execution_id;

  IF v_parent_type <> 'FOREACH' THEN
    RETURN;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM wf.workflow_edge e
    WHERE e.parent_node_id = v_parent_node_id
      AND e.child_node_id = p_workflow_node_id
      AND e.branch_kind = 'BODY'
  ) THEN
    RETURN;
  END IF;

  SELECT foreach_collection_var, foreach_item_var, foreach_index_var
  INTO v_coll, v_item, v_idx
  FROM wf.workflow_node WHERE id = v_parent_node_id;

  v_zbi := CASE WHEN p_iteration_no < 1 THEN 0 ELSE p_iteration_no - 1 END;

  CALL wf.wf_foreach_bind_iteration(
    p_workflow_instance_id,
    p_scope_node_execution_id,
    p_parent_node_execution_id,
    v_coll,
    v_item,
    v_idx,
    v_zbi
  );
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_foreach_continue(IN p_foreach_execution_id bigint)
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
  SELECT ne.workflow_instance_id, ne.workflow_node_id
  INTO v_inst, v_ctl
  FROM wf.node_execution ne WHERE ne.id = p_foreach_execution_id;

  SELECT ls.id, ls.current_iteration, ls.repeat_target_count
  INTO v_ls, v_cur, v_max
  FROM wf.loop_state ls
  WHERE ls.scope_node_execution_id = p_foreach_execution_id
  ORDER BY ls.id DESC
  LIMIT 1;

  IF v_ls IS NULL THEN
    UPDATE wf.node_execution SET status = 'FAILED', engine_error_code = 10009,
      ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = p_foreach_execution_id;
    UPDATE wf.workflow_instance SET status = 'FAILED', completed_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_inst;
    RETURN;
  END IF;

  v_cur := v_cur + 1;
  UPDATE wf.loop_state SET current_iteration = v_cur WHERE id = v_ls;

  IF v_cur >= v_max THEN
    UPDATE wf.node_execution SET status = 'SUCCEEDED', ended_at_utc = (now() AT TIME ZONE 'utc')
    WHERE id = p_foreach_execution_id;
    CALL wf.wf_engine_on_composite_complete(p_foreach_execution_id);
    RETURN;
  END IF;

  SELECT e.child_node_id INTO v_body FROM wf.workflow_edge e
  WHERE e.parent_node_id = v_ctl AND e.branch_kind = 'BODY'
  ORDER BY e.child_order ASC LIMIT 1;

  IF v_body IS NULL THEN
    UPDATE wf.node_execution SET status = 'FAILED', engine_error_code = 10010,
      ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = p_foreach_execution_id;
    UPDATE wf.workflow_instance SET status = 'FAILED', completed_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_inst;
    RETURN;
  END IF;

  CALL wf.wf_engine_activate(v_inst, v_body, p_foreach_execution_id, v_cur + 1, NULL, NULL);
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_foreach_parallel_continue(IN p_foreach_execution_id bigint)
LANGUAGE plpgsql
AS $$
DECLARE
  v_inst bigint;
  v_max int;
  v_finished int;
BEGIN
  SELECT ne.workflow_instance_id INTO v_inst
  FROM wf.node_execution ne WHERE ne.id = p_foreach_execution_id;

  SELECT ls.repeat_target_count INTO v_max
  FROM wf.loop_state ls
  WHERE ls.scope_node_execution_id = p_foreach_execution_id
  ORDER BY ls.id DESC LIMIT 1;

  IF v_max IS NULL THEN
    UPDATE wf.node_execution SET status = 'FAILED', engine_error_code = 10009,
      ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = p_foreach_execution_id;
    UPDATE wf.workflow_instance SET status = 'FAILED', completed_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_inst;
    RETURN;
  END IF;

  IF EXISTS (
    SELECT 1 FROM wf.node_execution
    WHERE parent_node_execution_id = p_foreach_execution_id AND status = 'FAILED'
  ) THEN
    UPDATE wf.node_execution SET status = 'FAILED', ended_at_utc = (now() AT TIME ZONE 'utc')
    WHERE id = p_foreach_execution_id;
    UPDATE wf.workflow_instance SET status = 'FAILED', completed_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_inst;
    RETURN;
  END IF;

  SELECT count(*) INTO v_finished
  FROM wf.node_execution
  WHERE parent_node_execution_id = p_foreach_execution_id
    AND status IN ('SUCCEEDED', 'FAILED', 'SKIPPED', 'CANCELLED');

  IF v_finished < v_max THEN
    RETURN;
  END IF;

  UPDATE wf.node_execution SET status = 'SUCCEEDED', ended_at_utc = (now() AT TIME ZONE 'utc')
  WHERE id = p_foreach_execution_id;
  CALL wf.wf_engine_on_composite_complete(p_foreach_execution_id);
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_engine_continue_parent(IN p_parent_node_execution_id bigint)
LANGUAGE plpgsql
AS $$
DECLARE v_ptype text; v_parallel boolean;
BEGIN
  SELECT wn.node_type, coalesce(wn.foreach_parallel, false)
  INTO v_ptype, v_parallel
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
  ELSIF v_ptype = 'FOREACH' THEN
    IF v_parallel THEN
      CALL wf.wf_foreach_parallel_continue(p_parent_node_execution_id);
    ELSE
      CALL wf.wf_foreach_continue(p_parent_node_execution_id);
    END IF;
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
  v_fparallel boolean;
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

  CALL wf.wf_apply_output_bindings(p_action_execution_id, p_result_code, p_output_json);

  IF v_parent IS NULL THEN
    UPDATE wf.workflow_instance SET status = 'COMPLETED', completed_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_inst;
    RETURN;
  END IF;

  SELECT wn.node_type, coalesce(wn.foreach_parallel, false)
  INTO v_ptype, v_fparallel
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
  ELSIF v_ptype = 'FOREACH' THEN
    IF v_fparallel THEN
      CALL wf.wf_foreach_parallel_continue(v_parent);
    ELSE
      CALL wf.wf_foreach_continue(v_parent);
    END IF;
  END IF;
END;
$$;

-- Extend wf_engine_activate with FOREACH activation and FOREACH/PARALLEL scope copy on ACTION.
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
  v_fcoll text;
  v_fpar boolean;
  v_coll_json text;
  v_flen int;
  v_fi int;
  rec record;
BEGIN
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
      IF v_parent_ntype IN ('PARALLEL', 'FOREACH') THEN
        INSERT INTO wf.scope_variable (workflow_instance_id, scope_node_execution_id, var_name, value_json)
        SELECT sv.workflow_instance_id, v_ne_id, sv.var_name, sv.value_json
        FROM wf.scope_variable sv
        WHERE sv.workflow_instance_id = p_workflow_instance_id
          AND sv.scope_node_execution_id = p_parent_node_execution_id;
      END IF;
      IF v_parent_ntype = 'FOREACH' THEN
        CALL wf.wf_try_bind_foreach_body(
          p_workflow_instance_id, p_workflow_node_id,
          p_parent_node_execution_id, v_ne_id, p_iteration_no
        );
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
  CALL wf.wf_try_bind_foreach_body(
    p_workflow_instance_id, p_workflow_node_id,
    p_parent_node_execution_id, v_pex, p_iteration_no
  );

  -- Iteration-bundle CAAS: skip BODY fan-out when a prior successful iteration is mirrored.
  IF wf.wf_foreach_caas_try_skip_body(
    p_workflow_instance_id, v_pex, p_parent_node_execution_id, p_iteration_no
  ) THEN
    RETURN;
  END IF;

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
    RETURN;
  END IF;

  IF v_node_type = 'FOREACH' THEN
    SELECT foreach_collection_var, coalesce(foreach_parallel, false)
    INTO v_fcoll, v_fpar
    FROM wf.workflow_node WHERE id = p_workflow_node_id;

    IF v_fcoll IS NULL OR btrim(v_fcoll) = '' THEN
      UPDATE wf.node_execution SET status = 'FAILED', engine_error_code = 10011,
        engine_error_message = 'FOREACH missing collection variable.', ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_pex;
      UPDATE wf.workflow_instance SET status = 'FAILED', completed_at_utc = (now() AT TIME ZONE 'utc') WHERE id = p_workflow_instance_id;
      RETURN;
    END IF;

    v_coll_json := wf.wf_get_scope_variable_json(p_workflow_instance_id, v_pex, v_fcoll);
    v_flen := wf.wf_json_array_length(v_coll_json);

    IF v_flen IS NULL THEN
      UPDATE wf.node_execution SET status = 'FAILED', engine_error_code = 10011,
        engine_error_message = 'FOREACH collection is not a JSON array.', ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_pex;
      UPDATE wf.workflow_instance SET status = 'FAILED', completed_at_utc = (now() AT TIME ZONE 'utc') WHERE id = p_workflow_instance_id;
      RETURN;
    END IF;

    IF v_flen = 0 THEN
      UPDATE wf.node_execution SET status = 'SUCCEEDED', ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_pex;
      CALL wf.wf_engine_on_composite_complete(v_pex);
      RETURN;
    END IF;

    SELECT e.child_node_id INTO v_body FROM wf.workflow_edge e
    WHERE e.parent_node_id = p_workflow_node_id AND e.branch_kind = 'BODY'
    ORDER BY e.child_order ASC LIMIT 1;

    IF v_body IS NULL THEN
      UPDATE wf.node_execution SET status = 'FAILED', engine_error_code = 10010,
        engine_error_message = 'FOREACH missing BODY child.', ended_at_utc = (now() AT TIME ZONE 'utc') WHERE id = v_pex;
      UPDATE wf.workflow_instance SET status = 'FAILED', completed_at_utc = (now() AT TIME ZONE 'utc') WHERE id = p_workflow_instance_id;
      RETURN;
    END IF;

    INSERT INTO wf.loop_state (workflow_instance_id, control_node_id, scope_node_execution_id, current_iteration, repeat_target_count)
    VALUES (p_workflow_instance_id, p_workflow_node_id, v_pex, 0, v_flen);

    IF v_fpar THEN
      v_fi := 0;
      WHILE v_fi < v_flen LOOP
        CALL wf.wf_engine_activate(p_workflow_instance_id, v_body, v_pex, v_fi + 1, NULL, v_fi);
        v_fi := v_fi + 1;
      END LOOP;
      RETURN;
    END IF;

    CALL wf.wf_engine_activate(p_workflow_instance_id, v_body, v_pex, 1, NULL, NULL);
    RETURN;
  END IF;
END;
$$;
