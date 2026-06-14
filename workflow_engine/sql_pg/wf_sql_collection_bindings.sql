/*
  Generic collection bindings: resolve JSON arrays into scope before FOREACH activation.

  Bindings are workflow-version metadata (populated by wf_repo_create_workflow_graph).
  wf_resolve_collection_bindings runs at sp_start_workflow_instance after context → scope-0.

  Kinds (engine-agnostic):
    jsonFile  — read JSON document from filesystem path in scope var path_var
    jsonPath  — extract array/object from scope var base_var at json_path (e.g. $.chromosomes)

  Prerequisites: 00_schema.sql, 03_engine_core.sql
*/

CREATE TABLE IF NOT EXISTS wf.workflow_collection_binding (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workflow_version_id bigint NOT NULL REFERENCES wf.workflow_version(id) ON DELETE CASCADE,
  bind_order int NOT NULL DEFAULT 0,
  scope_var text NOT NULL,
  source_kind text NOT NULL CHECK (source_kind IN ('jsonFile', 'jsonPath')),
  path_var text NULL,
  base_var text NULL,
  json_path text NULL,
  UNIQUE (workflow_version_id, scope_var)
);

CREATE INDEX IF NOT EXISTS ix_wcb_version ON wf.workflow_collection_binding(workflow_version_id, bind_order);

CREATE OR REPLACE FUNCTION wf.wf_json_unquote_string(p_json text)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
  IF p_json IS NULL OR btrim(p_json) = '' OR p_json = 'null' THEN
    RETURN NULL;
  END IF;
  IF left(btrim(p_json), 1) = '"' THEN
    RETURN p_json::jsonb #>> '{}';
  END IF;
  RETURN trim(both '"' from btrim(p_json));
END;
$$;

CREATE OR REPLACE FUNCTION wf.wf_json_path_to_pg(p_json_path text)
RETURNS text[]
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  v_path text;
  v_parts text[];
  v_part text;
BEGIN
  v_path := coalesce(p_json_path, '$.');
  v_path := regexp_replace(v_path, '^\$\.?', '');
  IF v_path = '' THEN
    RETURN ARRAY[]::text[];
  END IF;
  v_parts := string_to_array(v_path, '.');
  RETURN v_parts;
END;
$$;

CREATE OR REPLACE FUNCTION wf.wf_try_read_json_file(p_path text)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
  v_text text;
BEGIN
  IF p_path IS NULL OR btrim(p_path) = '' THEN
    RETURN NULL;
  END IF;
  BEGIN
    v_text := pg_read_file(p_path);
  EXCEPTION WHEN others THEN
    RETURN NULL;
  END;
  IF v_text IS NULL OR btrim(v_text) = '' THEN
    RETURN NULL;
  END IF;
  RETURN v_text::jsonb;
EXCEPTION WHEN others THEN
  RETURN NULL;
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_resolve_collection_bindings(
  IN p_workflow_instance_id bigint
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_version_id bigint;
  v_binding record;
  v_path text;
  v_base text;
  v_doc jsonb;
  v_extracted jsonb;
  v_pg_path text[];
BEGIN
  SELECT wi.workflow_version_id INTO v_version_id
  FROM wf.workflow_instance wi
  WHERE wi.id = p_workflow_instance_id;

  IF v_version_id IS NULL THEN
    RETURN;
  END IF;

  FOR v_binding IN
    SELECT scope_var, source_kind, path_var, base_var, json_path
    FROM wf.workflow_collection_binding
    WHERE workflow_version_id = v_version_id
    ORDER BY bind_order ASC, id ASC
  LOOP
    IF v_binding.source_kind = 'jsonFile' THEN
      v_path := wf.wf_json_unquote_string(
        wf.wf_get_scope_variable_json(p_workflow_instance_id, 0, v_binding.path_var)
      );
      v_doc := wf.wf_try_read_json_file(v_path);
      IF v_doc IS NULL THEN
        v_doc := wf.wf_get_scope_variable_json(p_workflow_instance_id, 0, v_binding.scope_var)::jsonb;
      END IF;
      IF v_doc IS NULL THEN
        RAISE EXCEPTION 'collection binding jsonFile failed for scope var % (path var %)',
          v_binding.scope_var, v_binding.path_var
          USING ERRCODE = '50001';
      END IF;
      CALL wf.wf_set_scope_variable(
        p_workflow_instance_id, 0, v_binding.scope_var, v_doc::text
      );

    ELSIF v_binding.source_kind = 'jsonPath' THEN
      v_base := wf.wf_get_scope_variable_json(p_workflow_instance_id, 0, v_binding.base_var);
      IF v_base IS NULL OR btrim(v_base) = '' THEN
        RAISE EXCEPTION 'collection binding jsonPath missing base var % for %',
          v_binding.base_var, v_binding.scope_var
          USING ERRCODE = '50001';
      END IF;
      v_pg_path := wf.wf_json_path_to_pg(v_binding.json_path);
      IF array_length(v_pg_path, 1) IS NULL THEN
        v_extracted := v_base::jsonb;
      ELSE
        v_extracted := v_base::jsonb #> v_pg_path;
      END IF;
      IF v_extracted IS NULL OR v_extracted = 'null'::jsonb THEN
        RAISE EXCEPTION 'collection binding jsonPath % on % produced null for %',
          v_binding.json_path, v_binding.base_var, v_binding.scope_var
          USING ERRCODE = '50001';
      END IF;
      CALL wf.wf_set_scope_variable(
        p_workflow_instance_id, 0, v_binding.scope_var, v_extracted::text
      );
    END IF;
  END LOOP;
END;
$$;
