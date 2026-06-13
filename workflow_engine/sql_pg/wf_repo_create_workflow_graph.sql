/*
  PostgreSQL: create a workflow definition graph from a JSON spec.

  Spec shape matches WorkflowDefinitionSpec (see workflow_engine/contract/workflow_definition_spec.py).

  Returns jsonb: { workflow_def_id, workflow_version_id, root_node_id, name }
*/

CREATE OR REPLACE FUNCTION wf.wf_repo_create_workflow_graph(p_spec jsonb)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
  v_def_id bigint;
  v_ver_id bigint;
  v_root_node_id bigint;
  v_node jsonb;
  v_edge jsonb;
  v_binding jsonb;
  v_node_id bigint;
  v_parent_id bigint;
  v_child_id bigint;
  v_action_id bigint;
  v_node_ids jsonb := '{}'::jsonb;
  v_name text;
  v_root_key text;
  v_allowed_node_types text[] := ARRAY[
    'ACTION','SEQUENCE','PARALLEL','IF','SWITCH','REPEAT','WHILE','FOREACH'
  ];
  v_allowed_branch_kinds text[] := ARRAY[
    'SEQUENCE','PARALLEL','THEN','ELSE','CASE','DEFAULT','BODY'
  ];
BEGIN
  IF p_spec IS NULL THEN
    RAISE EXCEPTION 'workflow spec is required';
  END IF;

  v_name := p_spec->>'name';
  IF v_name IS NULL OR btrim(v_name) = '' THEN
    RAISE EXCEPTION 'workflow spec missing name';
  END IF;

  v_root_key := p_spec->>'root_node_key';
  IF v_root_key IS NULL OR btrim(v_root_key) = '' THEN
    RAISE EXCEPTION 'workflow spec missing root_node_key';
  END IF;

  IF p_spec->'nodes' IS NULL OR jsonb_typeof(p_spec->'nodes') <> 'array' THEN
    RAISE EXCEPTION 'workflow spec requires nodes array';
  END IF;

  INSERT INTO wf.workflow_def (name, description)
  VALUES (v_name, p_spec->>'description')
  RETURNING id INTO v_def_id;

  INSERT INTO wf.workflow_version (workflow_def_id, version_major, version_minor, is_active)
  VALUES (
    v_def_id,
    COALESCE((p_spec->>'version_major')::int, 1),
    COALESCE((p_spec->>'version_minor')::int, 0),
    COALESCE((p_spec->>'is_active')::boolean, true)
  )
  RETURNING id INTO v_ver_id;

  FOR v_node IN SELECT value FROM jsonb_array_elements(p_spec->'nodes')
  LOOP
    IF NOT (v_node->>'node_type' = ANY (v_allowed_node_types)) THEN
      RAISE EXCEPTION 'invalid node_type % for node %', v_node->>'node_type', v_node->>'node_key';
    END IF;

    v_action_id := NULL;
    IF v_node->>'action_name' IS NOT NULL AND btrim(v_node->>'action_name') <> '' THEN
      SELECT id INTO v_action_id
      FROM wf.workflow_action
      WHERE action_name = v_node->>'action_name';

      IF v_action_id IS NULL THEN
        RAISE EXCEPTION 'unknown action_name % on node %', v_node->>'action_name', v_node->>'node_key';
      END IF;
    END IF;

    INSERT INTO wf.workflow_node (
      workflow_version_id,
      node_type,
      node_key,
      workflow_action_id,
      repeat_count,
      condition_ref_node_key,
      switch_ref_node_key,
      condition_var,
      switch_var,
      foreach_collection_var,
      foreach_item_var,
      foreach_index_var,
      foreach_parallel
    )
    VALUES (
      v_ver_id,
      v_node->>'node_type',
      v_node->>'node_key',
      v_action_id,
      NULLIF(v_node->>'repeat_count', '')::int,
      NULLIF(v_node->>'condition_ref_node_key', ''),
      NULLIF(v_node->>'switch_ref_node_key', ''),
      NULLIF(v_node->>'condition_var', ''),
      NULLIF(v_node->>'switch_var', ''),
      NULLIF(v_node->>'foreach_collection_var', ''),
      NULLIF(v_node->>'foreach_item_var', ''),
      NULLIF(v_node->>'foreach_index_var', ''),
      CASE
        WHEN v_node ? 'foreach_parallel' THEN (v_node->>'foreach_parallel')::boolean
        ELSE NULL
      END
    )
    RETURNING id INTO v_node_id;

    v_node_ids := v_node_ids || jsonb_build_object(v_node->>'node_key', v_node_id);

    IF v_node ? 'input_template' THEN
      INSERT INTO wf.workflow_input_template (workflow_node_id, template_json)
      VALUES (v_node_id, v_node->'input_template');
    END IF;
  END LOOP;

  FOR v_edge IN SELECT value FROM jsonb_array_elements(COALESCE(p_spec->'edges', '[]'::jsonb))
  LOOP
    IF v_edge->>'branch_kind' IS NOT NULL
       AND NOT (v_edge->>'branch_kind' = ANY (v_allowed_branch_kinds)) THEN
      RAISE EXCEPTION 'invalid branch_kind %', v_edge->>'branch_kind';
    END IF;

    v_parent_id := (v_node_ids->>(v_edge->>'parent_node_key'))::bigint;
    v_child_id := (v_node_ids->>(v_edge->>'child_node_key'))::bigint;

    IF v_parent_id IS NULL OR v_child_id IS NULL THEN
      RAISE EXCEPTION 'edge references unknown node: % -> %',
        v_edge->>'parent_node_key', v_edge->>'child_node_key';
    END IF;

    INSERT INTO wf.workflow_edge (
      parent_node_id,
      child_node_id,
      child_order,
      branch_kind,
      condition_expr,
      switch_case_value,
      is_default
    )
    VALUES (
      v_parent_id,
      v_child_id,
      COALESCE((v_edge->>'child_order')::int, 0),
      NULLIF(v_edge->>'branch_kind', ''),
      NULLIF(v_edge->>'condition_expr', ''),
      NULLIF(v_edge->>'switch_case_value', '')::int,
      COALESCE((v_edge->>'is_default')::boolean, false)
    );
  END LOOP;

  FOR v_binding IN SELECT value FROM jsonb_array_elements(COALESCE(p_spec->'input_bindings', '[]'::jsonb))
  LOOP
    v_node_id := (v_node_ids->>(v_binding->>'node_key'))::bigint;
    IF v_node_id IS NULL THEN
      RAISE EXCEPTION 'input_binding references unknown node_key %', v_binding->>'node_key';
    END IF;
    INSERT INTO wf.workflow_input_binding (
      workflow_node_id, target_json_path, source_expr, is_required
    )
    VALUES (
      v_node_id,
      v_binding->>'target_json_path',
      v_binding->>'source_expr',
      COALESCE((v_binding->>'is_required')::boolean, false)
    );
  END LOOP;

  FOR v_binding IN SELECT value FROM jsonb_array_elements(COALESCE(p_spec->'output_bindings', '[]'::jsonb))
  LOOP
    v_node_id := (v_node_ids->>(v_binding->>'node_key'))::bigint;
    IF v_node_id IS NULL THEN
      RAISE EXCEPTION 'output_binding references unknown node_key %', v_binding->>'node_key';
    END IF;
    INSERT INTO wf.variable_output_binding (
      workflow_node_id, var_name, source_kind, source_json_path
    )
    VALUES (
      v_node_id,
      v_binding->>'var_name',
      v_binding->>'source_kind',
      NULLIF(v_binding->>'source_json_path', '')
    );
  END LOOP;

  FOR v_binding IN SELECT value FROM jsonb_array_elements(COALESCE(p_spec->'scope_defaults', '[]'::jsonb))
  LOOP
    v_node_id := (v_node_ids->>(v_binding->>'node_key'))::bigint;
    IF v_node_id IS NULL THEN
      RAISE EXCEPTION 'scope_default references unknown node_key %', v_binding->>'node_key';
    END IF;
    INSERT INTO wf.node_scope_default (workflow_node_id, var_name, default_expr)
    VALUES (v_node_id, v_binding->>'var_name', v_binding->>'default_expr');
  END LOOP;

  v_root_node_id := (v_node_ids->>v_root_key)::bigint;
  IF v_root_node_id IS NULL THEN
    RAISE EXCEPTION 'root_node_key % not found among nodes', v_root_key;
  END IF;

  UPDATE wf.workflow_version
  SET root_node_id = v_root_node_id
  WHERE id = v_ver_id;

  RETURN jsonb_build_object(
    'workflow_def_id', v_def_id,
    'workflow_version_id', v_ver_id,
    'root_node_id', v_root_node_id,
    'name', v_name
  );
END;
$$;
