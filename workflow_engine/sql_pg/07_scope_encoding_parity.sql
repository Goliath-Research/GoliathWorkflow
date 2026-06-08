/*
  PostgreSQL canonical JSON-value encoding for scope variables.
  Deploy after 06_scope_writepath_parity.sql.
*/

CREATE OR REPLACE FUNCTION wf.wf_json_encode_scalar(p_raw_value text)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  v_trimmed text := btrim(p_raw_value);
  v_as_bigint bigint;
  v_as_float double precision;
  v_rounded text;
BEGIN
  IF p_raw_value IS NULL THEN
    RETURN 'null';
  END IF;
  IF v_trimmed IN ('true', 'false') THEN
    RETURN v_trimmed;
  END IF;
  BEGIN
    v_as_bigint := v_trimmed::bigint;
    IF v_as_bigint::text = v_trimmed THEN
      RETURN v_trimmed;
    END IF;
  EXCEPTION WHEN others THEN NULL;
  END;
  BEGIN
    v_as_float := v_trimmed::double precision;
    v_rounded := v_as_float::text;
    IF v_rounded = v_trimmed THEN
      RETURN v_trimmed;
    END IF;
  EXCEPTION WHEN others THEN NULL;
  END;
  RETURN wf.wf_json_fragment_from_string(p_raw_value);
END;
$$;

CREATE OR REPLACE FUNCTION wf.wf_json_encode_jsonb_value(p_val jsonb)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
  IF p_val IS NULL OR p_val = 'null'::jsonb THEN
    RETURN 'null';
  END IF;
  CASE jsonb_typeof(p_val)
    WHEN 'string' THEN RETURN wf.wf_json_fragment_from_string(p_val #>> '{}');
    WHEN 'number' THEN RETURN p_val::text;
    WHEN 'boolean' THEN RETURN p_val::text;
    ELSE RETURN p_val::text;
  END CASE;
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
DECLARE
  v_raw text;
  v_trimmed text;
  v_v int;
BEGIN
  v_raw := wf.wf_get_scope_variable_json(
    p_workflow_instance_id, p_start_scope_node_execution_id, p_var_name
  );
  IF v_raw IS NULL THEN
    RETURN NULL;
  END IF;
  v_trimmed := btrim(v_raw);
  BEGIN
    v_v := v_trimmed::int;
    RETURN v_v;
  EXCEPTION WHEN others THEN NULL;
  END;
  IF length(v_trimmed) >= 2 AND left(v_trimmed, 1) = '"' AND right(v_trimmed, 1) = '"' THEN
    BEGIN
      RETURN substring(v_trimmed from 2 for length(v_trimmed) - 2)::int;
    EXCEPTION WHEN others THEN NULL;
    END;
  END IF;
  RETURN NULL;
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
    CALL wf.wf_set_scope_variable(
      p_workflow_instance_id, 0, v_key, wf.wf_json_encode_jsonb_value(v_val)
    );
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
  v_elem jsonb;
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
            v_elem := jsonb_path_query_first(v_oj::jsonb, v_jp::jsonpath);
          EXCEPTION WHEN others THEN
            v_elem := NULL;
          END;
          IF v_elem IS NULL THEN
            v_frag := 'null';
          ELSIF jsonb_typeof(v_elem) IN ('object', 'array') THEN
            v_frag := v_elem::text;
          ELSE
            v_frag := wf.wf_json_encode_jsonb_value(v_elem);
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
