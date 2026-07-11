/*
  Portal workflow repository API (PostgreSQL).
  EpiPortal calls these functions directly — never the REST gateway.
*/

CREATE SCHEMA IF NOT EXISTS portal;

ALTER TABLE wf.workflow_def
  ADD COLUMN IF NOT EXISTS source varchar(32) NOT NULL DEFAULT 'system';

-- Explicit columns: wf.wf_repo_list_actions also returns dispatch metadata.
CREATE OR REPLACE FUNCTION portal.sp_list_workflow_actions()
RETURNS TABLE (
  action_name text,
  capability text,
  has_input_schema boolean,
  has_output_schema boolean
)
LANGUAGE sql
STABLE
AS $$
  SELECT action_name, capability, has_input_schema, has_output_schema
  FROM wf.wf_repo_list_actions();
$$;

CREATE OR REPLACE FUNCTION portal.sp_get_action_schema(
  p_action_name text,
  p_direction text
)
RETURNS TABLE (
  action_name text,
  direction text,
  schema_json jsonb,
  schema_id text
)
LANGUAGE sql
STABLE
AS $$
  SELECT * FROM wf.wf_repo_get_action_schema(p_action_name, p_direction);
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_workflow_definitions(
  p_source_filter text DEFAULT NULL
)
RETURNS TABLE (
  workflow_def_id bigint,
  name text,
  source text,
  workflow_version_id bigint,
  version_major int,
  version_minor int
)
LANGUAGE sql
STABLE
AS $$
  SELECT wd.id AS workflow_def_id,
         wd.name,
         COALESCE(wd.source, 'system') AS source,
         wv.id AS workflow_version_id,
         wv.version_major,
         wv.version_minor
  FROM wf.workflow_def wd
  LEFT JOIN LATERAL (
    SELECT id, version_major, version_minor
    FROM wf.workflow_version
    WHERE workflow_def_id = wd.id AND is_active = true
    ORDER BY version_major DESC, version_minor DESC
    LIMIT 1
  ) wv ON true
  WHERE p_source_filter IS NULL OR COALESCE(wd.source, 'system') = p_source_filter
  ORDER BY wd.name;
$$;

CREATE OR REPLACE FUNCTION portal.sp_create_workflow_graph(p_spec jsonb)
RETURNS TABLE (
  workflow_def_id bigint,
  workflow_version_id bigint,
  root_node_id bigint,
  name text
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_node jsonb;
  v_action text;
  v_result jsonb;
  v_def_id bigint;
BEGIN
  IF p_spec IS NULL THEN
    RAISE EXCEPTION 'workflow spec is required';
  END IF;

  FOR v_node IN SELECT value FROM jsonb_array_elements(p_spec->'nodes')
  LOOP
    v_action := v_node->>'action';
    IF v_action IS NOT NULL AND NOT EXISTS (
      SELECT 1 FROM wf.workflow_action WHERE action_name = v_action
    ) THEN
      RAISE EXCEPTION 'Unknown action in workflow graph: %', v_action;
    END IF;
  END LOOP;

  v_result := wf.wf_repo_create_workflow_graph(p_spec);
  v_def_id := (v_result->>'workflow_def_id')::bigint;
  UPDATE wf.workflow_def SET source = 'portal' WHERE id = v_def_id;

  RETURN QUERY
  SELECT (v_result->>'workflow_def_id')::bigint,
         (v_result->>'workflow_version_id')::bigint,
         (v_result->>'root_node_id')::bigint,
         v_result->>'name';
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_create_and_start_instance(
  p_workflow_version_id bigint,
  p_context_json jsonb DEFAULT NULL
)
RETURNS TABLE (
  id bigint,
  workflow_version_id bigint,
  status text
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_instance_id bigint;
BEGIN
  SELECT id INTO v_instance_id
  FROM wf.wf_repo_create_workflow_instance(p_workflow_version_id, p_context_json);

  CALL wf.sp_start_workflow_instance(v_instance_id);

  RETURN QUERY SELECT * FROM wf.wf_repo_get_workflow_instance(v_instance_id);
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_get_instance_tasks(p_workflow_instance_id bigint)
RETURNS TABLE (
  node_execution_id bigint,
  status text,
  result_code int,
  attempt_no int,
  node_key text,
  action_name text,
  capability text,
  input_json jsonb,
  output_json jsonb,
  started_at_utc timestamptz,
  completed_at_utc timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT ne.id AS node_execution_id,
         ne.status,
         ne.result_code,
         ne.attempt_no,
         wn.node_key,
         wa.action_name,
         wa.capability,
         ne.input_json,
         ne.output_json,
         ne.started_at_utc,
         ne.ended_at_utc AS completed_at_utc
  FROM wf.node_execution ne
  INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
  LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
  WHERE ne.workflow_instance_id = p_workflow_instance_id
  ORDER BY ne.id;
$$;
