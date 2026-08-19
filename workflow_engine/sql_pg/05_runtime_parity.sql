/*
  PostgreSQL runtime parity: placeholder resolver and action input builder.
  Deploy after 03_engine_core.sql.
*/

CREATE OR REPLACE FUNCTION wf.wf_json_path_to_segments(p_path text)
RETURNS text[]
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  v text := btrim(p_path);
BEGIN
  IF v = '' OR v = '$' THEN
    RETURN ARRAY[]::text[];
  END IF;
  IF left(v, 2) = '$.' THEN
    v := substring(v from 3);
  ELSIF left(v, 1) = '$' THEN
    v := substring(v from 2);
  END IF;
  IF v = '' THEN
    RETURN ARRAY[]::text[];
  END IF;
  RETURN string_to_array(v, '.');
END;
$$;

CREATE OR REPLACE FUNCTION wf.wf_json_set_path(p_doc jsonb, p_path text, p_frag text)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
  v_segs text[];
  v_val jsonb;
BEGIN
  v_segs := wf.wf_json_path_to_segments(p_path);
  IF p_frag IS NULL OR btrim(p_frag) = '' THEN
    v_val := 'null'::jsonb;
  ELSE
    BEGIN
      v_val := p_frag::jsonb;
    EXCEPTION WHEN others THEN
      v_val := wf.wf_json_fragment_from_string(p_frag)::jsonb;
    END;
  END IF;
  RETURN jsonb_set(p_doc, v_segs, v_val, true);
END;
$$;

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
DECLARE
  v_rest text;
  v_dot int;
  v_nk text;
  v_tail text;
  v_rc int;
  v_jq text;
  v_var_name text;
  v_v text;
BEGIN
  p_failed := false;
  p_fail_code := NULL;
  p_fail_msg := NULL;

  IF position(' ' in p_token) > 0 OR position('+' in p_token) > 0 OR position('(' in p_token) > 0 THEN
    p_failed := true;
    p_fail_code := 10002;
    p_fail_msg := 'Unsupported placeholder expression.';
    RETURN;
  END IF;

  IF left(p_token, 9) = 'ctx.task.' THEN
    v_rest := substring(p_token from 10);
    v_dot := position('.' in v_rest);
    IF v_dot = 0 THEN
      p_failed := true;
      p_fail_code := 10002;
      p_fail_msg := 'Invalid ctx.task reference.';
      RETURN;
    END IF;
    v_nk := left(v_rest, v_dot - 1);
    v_tail := substring(v_rest from v_dot + 1);
    IF v_tail = 'resultCode' THEN
      v_rc := wf.wf_try_task_result_code(p_workflow_instance_id, v_nk);
      p_out_fragment := v_rc::text;
      RETURN;
    END IF;
    IF left(v_tail, 7) = 'output.' THEN
      v_jq := wf.wf_try_task_output_json(p_workflow_instance_id, v_nk, substring(v_tail from 8));
      p_out_fragment := v_jq;
      RETURN;
    END IF;
    p_failed := true;
    p_fail_code := 10002;
    p_fail_msg := 'Unsupported ctx.task tail.';
    RETURN;
  END IF;

  IF left(p_token, 4) = 'var.' THEN
    v_var_name := substring(p_token from 5);
    IF btrim(v_var_name) = '' THEN
      p_failed := true;
      p_fail_code := 10002;
      p_fail_msg := 'Empty scope variable name.';
      RETURN;
    END IF;
    v_v := wf.wf_get_scope_variable_json(p_workflow_instance_id, p_node_execution_id, v_var_name);
    IF v_v IS NULL AND v_var_name IN ('sampleDestination', 'h5Destination') THEN
      p_out_fragment := 'null';
      RETURN;
    END IF;
    IF v_v IS NULL THEN
      p_failed := true;
      p_fail_code := 10001;
      p_fail_msg := 'Missing scope variable: ' || v_var_name;
      RETURN;
    END IF;
    p_out_fragment := v_v;
    RETURN;
  END IF;

  IF left(p_token, 4) = 'ctx.' THEN
    SELECT ec.context_value_json INTO v_v
    FROM wf.execution_context ec
    WHERE ec.node_execution_id = p_node_execution_id AND ec.context_key = p_token;
    IF v_v IS NULL THEN
      p_failed := true;
      p_fail_code := 10001;
      p_fail_msg := 'Missing context value for ' || p_token;
      RETURN;
    END IF;
    p_out_fragment := v_v;
    RETURN;
  END IF;

  p_failed := true;
  p_fail_code := 10002;
  p_fail_msg := 'Unsupported token.';
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_resolve_placeholders(
  IN p_text text,
  IN p_node_execution_id bigint,
  IN p_workflow_instance_id bigint,
  OUT p_resolved text,
  OUT p_failed boolean,
  OUT p_fail_code int,
  OUT p_fail_msg text
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_start int;
  v_end int;
  v_token text;
  v_frag text;
  v_tf boolean;
  v_fc int;
  v_fm text;
BEGIN
  p_resolved := p_text;
  p_failed := false;
  p_fail_code := NULL;
  p_fail_msg := NULL;

  LOOP
    v_start := position('${' in p_resolved);
    EXIT WHEN v_start = 0;
    v_end := position('}' in substring(p_resolved from v_start + 2));
    IF v_end = 0 THEN
      EXIT;
    END IF;
    v_end := v_start + 1 + v_end;
    v_token := substring(p_resolved from v_start + 2 for v_end - v_start - 2);

    CALL wf.wf_resolve_token(
      v_token, p_node_execution_id, p_workflow_instance_id,
      v_frag, v_tf, v_fc, v_fm
    );
    IF v_tf THEN
      p_failed := true;
      p_fail_code := v_fc;
      p_fail_msg := v_fm;
      RETURN;
    END IF;

    p_resolved := overlay(
      p_resolved placing coalesce(v_frag, 'null') from v_start for v_end - v_start + 1
    );
  END LOOP;
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
RETURNS record
LANGUAGE plpgsql
AS $$
DECLARE
  v_template text;
  v_cur text;
  v_tf boolean;
  v_fc int;
  v_fm text;
  v_path text;
  v_expr text;
  v_req boolean;
  v_frag text;
  rec record;
BEGIN
  p_failed := false;
  p_fail_code := 0;
  p_fail_msg := NULL;

  SELECT coalesce(wit.template_json::text, '{}') INTO v_template
  FROM wf.workflow_input_template wit
  WHERE wit.workflow_node_id = p_workflow_node_id;
  IF v_template IS NULL THEN
    v_template := '{}';
  END IF;

  CALL wf.wf_resolve_placeholders(
    v_template, p_node_execution_id, p_workflow_instance_id,
    v_cur, v_tf, v_fc, v_fm
  );
  IF v_tf THEN
    p_failed := true;
    p_fail_code := v_fc;
    p_fail_msg := v_fm;
    RETURN;
  END IF;

  BEGIN
    p_final_json := v_cur::jsonb;
  EXCEPTION WHEN others THEN
    p_failed := true;
    p_fail_code := 10008;
    p_fail_msg := 'Template JSON is invalid after placeholder resolution.';
    RETURN;
  END;

  FOR rec IN
    SELECT wib.target_json_path, wib.source_expr, wib.is_required
    FROM wf.workflow_input_binding wib
    WHERE wib.workflow_node_id = p_workflow_node_id
    ORDER BY wib.id
  LOOP
    v_path := rec.target_json_path;
    v_expr := rec.source_expr;
    v_req := rec.is_required;

    CALL wf.wf_resolve_placeholders(
      v_expr, p_node_execution_id, p_workflow_instance_id,
      v_frag, v_tf, v_fc, v_fm
    );
    IF v_tf AND coalesce(v_req, false) THEN
      p_failed := true;
      p_fail_code := v_fc;
      p_fail_msg := v_fm;
      RETURN;
    END IF;
    IF v_tf AND NOT coalesce(v_req, false) THEN
      v_frag := 'null';
    END IF;
    IF left(btrim(v_path), 1) <> '$' THEN
      v_path := '$.' || v_path;
    END IF;
    p_final_json := wf.wf_json_set_path(p_final_json, v_path, v_frag);
  END LOOP;
END;
$$;
