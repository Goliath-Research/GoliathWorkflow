-- Explicit wf data type registry.
-- schema_json is the JSON Schema document SchemaPropertyGrid binds.
-- kind / data_type_field / element_type_id are a SQL index over that document
-- (lossy: no ge/le, descriptions, additionalProperties).
-- Prerequisites: wf.workflow_action

CREATE TABLE IF NOT EXISTS wf.data_type (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name text NOT NULL,
  version text NOT NULL DEFAULT '1',
  status varchar(32) NOT NULL DEFAULT 'published',
  kind varchar(32) NOT NULL,
  element_type_id bigint NULL REFERENCES wf.data_type (id),
  content_hash text NULL,
  schema_json jsonb NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CONSTRAINT uq_wf_data_type_name_version UNIQUE (name, version),
  CONSTRAINT ck_wf_data_type_status CHECK (status IN ('draft', 'published', 'retired')),
  CONSTRAINT ck_wf_data_type_kind CHECK (
    kind IN ('string', 'int', 'bool', 'number', 'datetime', 'bytes', 'enum', 'object', 'array', 'any')
  )
);

ALTER TABLE wf.data_type
  ADD COLUMN IF NOT EXISTS schema_json jsonb NULL;

DO $ck$
BEGIN
  ALTER TABLE wf.data_type
    ADD CONSTRAINT ck_wf_data_type_element_kind
    CHECK (element_type_id IS NULL OR kind = 'array');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$ck$;

CREATE TABLE IF NOT EXISTS wf.data_type_field (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  data_type_id bigint NOT NULL REFERENCES wf.data_type (id) ON DELETE CASCADE,
  field_name text NOT NULL,
  field_type_id bigint NOT NULL REFERENCES wf.data_type (id),
  required boolean NOT NULL DEFAULT false,
  ordinal int NOT NULL DEFAULT 0,
  CONSTRAINT uq_wf_dtf_name UNIQUE (data_type_id, field_name)
);

CREATE INDEX IF NOT EXISTS ix_wf_dtf_owner ON wf.data_type_field (data_type_id);

CREATE TABLE IF NOT EXISTS wf.data_type_enum_value (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  data_type_id bigint NOT NULL REFERENCES wf.data_type (id) ON DELETE CASCADE,
  value text NOT NULL,
  ordinal int NOT NULL DEFAULT 0,
  CONSTRAINT uq_wf_dtev_value UNIQUE (data_type_id, value)
);

ALTER TABLE wf.workflow_action
  ADD COLUMN IF NOT EXISTS input_type_id bigint NULL REFERENCES wf.data_type (id);
ALTER TABLE wf.workflow_action
  ADD COLUMN IF NOT EXISTS output_type_id bigint NULL REFERENCES wf.data_type (id);
ALTER TABLE wf.workflow_action
  ADD COLUMN IF NOT EXISTS implementation_status varchar(32) NULL;
ALTER TABLE wf.workflow_action
  ADD COLUMN IF NOT EXISTS can_pause boolean NOT NULL DEFAULT false;
ALTER TABLE wf.workflow_action
  ADD COLUMN IF NOT EXISTS can_continue boolean NOT NULL DEFAULT false;
ALTER TABLE wf.workflow_action
  ADD COLUMN IF NOT EXISTS can_stop boolean NOT NULL DEFAULT true;

DROP FUNCTION IF EXISTS wf.wf_repo_upsert_data_type(text, text, text, text, text, text, text);
DROP FUNCTION IF EXISTS wf.wf_repo_upsert_data_type(text, text, text, text, text, text, text, jsonb);

CREATE OR REPLACE FUNCTION wf.wf_repo_upsert_data_type(
  p_name text,
  p_version text DEFAULT '1',
  p_status text DEFAULT 'published',
  p_kind text DEFAULT 'object',
  p_element_type_name text DEFAULT NULL,
  p_element_type_version text DEFAULT '1',
  p_content_hash text DEFAULT NULL,
  p_schema_json jsonb DEFAULT NULL
)
RETURNS TABLE(
  id bigint,
  name text,
  version text,
  status text,
  kind text,
  element_type_id bigint
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_ver text := COALESCE(NULLIF(p_version, ''), '1');
  v_st text := COALESCE(NULLIF(p_status, ''), 'published');
  v_element_id bigint;
  v_id bigint;
BEGIN
  IF p_element_type_name IS NOT NULL AND btrim(p_element_type_name) <> '' THEN
    SELECT t.id INTO v_element_id
    FROM wf.data_type t
    WHERE t.name = p_element_type_name
      AND (p_element_type_version IS NULL OR t.version = p_element_type_version)
    ORDER BY t.id DESC
    LIMIT 1;
  END IF;

  INSERT INTO wf.data_type AS dt(name, version, status, kind, element_type_id, content_hash, schema_json)
  VALUES (p_name, v_ver, v_st, p_kind, v_element_id, p_content_hash, p_schema_json)
  ON CONFLICT ON CONSTRAINT uq_wf_data_type_name_version DO UPDATE SET
    status = EXCLUDED.status,
    kind = EXCLUDED.kind,
    element_type_id = COALESCE(EXCLUDED.element_type_id, dt.element_type_id),
    content_hash = COALESCE(EXCLUDED.content_hash, dt.content_hash),
    schema_json = COALESCE(EXCLUDED.schema_json, dt.schema_json),
    updated_at_utc = (now() AT TIME ZONE 'utc')
  RETURNING dt.id INTO v_id;

  RETURN QUERY
  SELECT t.id, t.name, t.version, t.status::text, t.kind::text, t.element_type_id
  FROM wf.data_type t WHERE t.id = v_id;
END;
$$;

CREATE OR REPLACE FUNCTION wf.wf_repo_replace_data_type_fields(
  p_type_name text,
  p_type_version text DEFAULT '1',
  p_fields jsonb DEFAULT '[]'::jsonb
)
RETURNS TABLE(
  id bigint,
  data_type_id bigint,
  field_name text,
  field_type_id bigint,
  required boolean,
  ordinal int
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_type_id bigint;
  elem jsonb;
  v_field_type_id bigint;
BEGIN
  SELECT t.id INTO v_type_id
  FROM wf.data_type t
  WHERE t.name = p_type_name
    AND t.version = COALESCE(NULLIF(p_type_version, ''), '1')
  ORDER BY t.id DESC
  LIMIT 1;
  IF v_type_id IS NULL THEN
    RAISE EXCEPTION 'wf.data_type not found: %', p_type_name;
  END IF;

  DELETE FROM wf.data_type_field f WHERE f.data_type_id = v_type_id;

  FOR elem IN SELECT * FROM jsonb_array_elements(COALESCE(p_fields, '[]'::jsonb))
  LOOP
    SELECT t.id INTO v_field_type_id
    FROM wf.data_type t
    WHERE t.name = elem->>'field_type_name'
      AND t.version = COALESCE(NULLIF(elem->>'field_type_version', ''), '1')
    ORDER BY t.id DESC
    LIMIT 1;
    IF v_field_type_id IS NULL THEN
      CONTINUE;
    END IF;
    INSERT INTO wf.data_type_field (data_type_id, field_name, field_type_id, required, ordinal)
    VALUES (
      v_type_id,
      elem->>'field_name',
      v_field_type_id,
      COALESCE((elem->>'required')::boolean, false),
      COALESCE((elem->>'ordinal')::int, 0)
    );
  END LOOP;

  RETURN QUERY
  SELECT f.id, f.data_type_id, f.field_name, f.field_type_id, f.required, f.ordinal
  FROM wf.data_type_field f
  WHERE f.data_type_id = v_type_id
  ORDER BY f.ordinal, f.field_name;
END;
$$;

CREATE OR REPLACE FUNCTION wf.wf_repo_replace_data_type_enum_values(
  p_type_name text,
  p_type_version text DEFAULT '1',
  p_values jsonb DEFAULT '[]'::jsonb
)
RETURNS TABLE(
  id bigint,
  data_type_id bigint,
  value text,
  ordinal int
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_type_id bigint;
  i int := 0;
  v text;
BEGIN
  SELECT t.id INTO v_type_id
  FROM wf.data_type t
  WHERE t.name = p_type_name
    AND t.version = COALESCE(NULLIF(p_type_version, ''), '1')
  ORDER BY t.id DESC
  LIMIT 1;
  IF v_type_id IS NULL THEN
    RAISE EXCEPTION 'wf.data_type not found: %', p_type_name;
  END IF;

  DELETE FROM wf.data_type_enum_value e WHERE e.data_type_id = v_type_id;

  FOR v IN SELECT jsonb_array_elements_text(COALESCE(p_values, '[]'::jsonb))
  LOOP
    INSERT INTO wf.data_type_enum_value (data_type_id, value, ordinal)
    VALUES (v_type_id, v, i);
    i := i + 1;
  END LOOP;

  RETURN QUERY
  SELECT e.id, e.data_type_id, e.value, e.ordinal
  FROM wf.data_type_enum_value e
  WHERE e.data_type_id = v_type_id
  ORDER BY e.ordinal, e.value;
END;
$$;

CREATE OR REPLACE FUNCTION wf.wf_repo_bind_action_types(
  p_action_name text,
  p_input_type_name text DEFAULT NULL,
  p_output_type_name text DEFAULT NULL,
  p_type_version text DEFAULT '1',
  p_implementation_status text DEFAULT NULL,
  p_can_pause boolean DEFAULT NULL,
  p_can_continue boolean DEFAULT NULL,
  p_can_stop boolean DEFAULT NULL
)
RETURNS TABLE(
  id bigint,
  action_name text,
  input_type_id bigint,
  output_type_id bigint,
  input_type_name text,
  output_type_name text,
  implementation_status text,
  can_pause boolean,
  can_continue boolean,
  can_stop boolean
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_action_id bigint;
  v_in bigint;
  v_out bigint;
BEGIN
  SELECT a.id INTO v_action_id FROM wf.workflow_action a WHERE a.action_name = p_action_name;
  IF v_action_id IS NULL THEN
    RAISE EXCEPTION 'wf.workflow_action not found: %', p_action_name;
  END IF;

  IF p_input_type_name IS NOT NULL AND btrim(p_input_type_name) <> '' THEN
    SELECT t.id INTO v_in FROM wf.data_type t
    WHERE t.name = p_input_type_name
      AND t.version = COALESCE(NULLIF(p_type_version, ''), '1')
    ORDER BY t.id DESC LIMIT 1;
  END IF;
  IF p_output_type_name IS NOT NULL AND btrim(p_output_type_name) <> '' THEN
    SELECT t.id INTO v_out FROM wf.data_type t
    WHERE t.name = p_output_type_name
      AND t.version = COALESCE(NULLIF(p_type_version, ''), '1')
    ORDER BY t.id DESC LIMIT 1;
  END IF;

  UPDATE wf.workflow_action a
  SET input_type_id = COALESCE(v_in, a.input_type_id),
      output_type_id = COALESCE(v_out, a.output_type_id),
      implementation_status = COALESCE(p_implementation_status, a.implementation_status),
      can_pause = COALESCE(p_can_pause, a.can_pause),
      can_continue = COALESCE(p_can_continue, a.can_continue),
      can_stop = COALESCE(p_can_stop, a.can_stop)
  WHERE a.id = v_action_id;

  RETURN QUERY
  SELECT
    a.id, a.action_name, a.input_type_id, a.output_type_id,
    tin.name, tout.name, a.implementation_status::text,
    a.can_pause, a.can_continue, a.can_stop
  FROM wf.workflow_action a
  LEFT JOIN wf.data_type tin ON tin.id = a.input_type_id
  LEFT JOIN wf.data_type tout ON tout.id = a.output_type_id
  WHERE a.id = v_action_id;
END;
$$;

CREATE OR REPLACE FUNCTION wf.wf_repo_list_data_types(
  p_published_only boolean DEFAULT true
)
RETURNS TABLE(
  id bigint,
  name text,
  version text,
  status text,
  kind text,
  element_type_id bigint,
  element_type_name text,
  content_hash text,
  created_at_utc timestamptz,
  updated_at_utc timestamptz,
  field_count bigint
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    t.id, t.name, t.version, t.status::text, t.kind::text, t.element_type_id,
    et.name, t.content_hash, t.created_at_utc, t.updated_at_utc,
    (SELECT COUNT(*) FROM wf.data_type_field f WHERE f.data_type_id = t.id)
  FROM wf.data_type t
  LEFT JOIN wf.data_type et ON et.id = t.element_type_id
  WHERE (NOT p_published_only OR t.status = 'published')
  ORDER BY t.name, t.version;
$$;

DROP FUNCTION IF EXISTS portal.sp_get_data_type(text, text);
DROP FUNCTION IF EXISTS wf.wf_repo_get_data_type(text, text);

CREATE OR REPLACE FUNCTION wf.wf_repo_get_data_type(
  p_name text,
  p_version text DEFAULT NULL
)
RETURNS TABLE(
  id bigint,
  name text,
  version text,
  status text,
  kind text,
  element_type_id bigint,
  element_type_name text,
  content_hash text,
  created_at_utc timestamptz,
  updated_at_utc timestamptz,
  schema_json jsonb
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    t.id, t.name, t.version, t.status::text, t.kind::text, t.element_type_id,
    et.name, t.content_hash, t.created_at_utc, t.updated_at_utc, t.schema_json
  FROM wf.data_type t
  LEFT JOIN wf.data_type et ON et.id = t.element_type_id
  WHERE t.name = p_name
    AND (p_version IS NULL OR t.version = p_version)
  ORDER BY t.id DESC
  LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION wf.wf_repo_list_data_type_fields(
  p_name text,
  p_version text DEFAULT NULL
)
RETURNS TABLE(
  id bigint,
  field_name text,
  field_type_id bigint,
  field_type_name text,
  field_type_kind text,
  required boolean,
  ordinal int
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    f.id, f.field_name, f.field_type_id, ft.name, ft.kind::text, f.required, f.ordinal
  FROM wf.data_type t
  INNER JOIN wf.data_type_field f ON f.data_type_id = t.id
  INNER JOIN wf.data_type ft ON ft.id = f.field_type_id
  WHERE t.id = (
    SELECT x.id FROM wf.data_type x
    WHERE x.name = p_name AND (p_version IS NULL OR x.version = p_version)
    ORDER BY x.id DESC LIMIT 1
  )
  ORDER BY f.ordinal, f.field_name;
$$;

CREATE SCHEMA IF NOT EXISTS portal;

CREATE OR REPLACE FUNCTION portal.sp_list_data_types(
  p_published_only boolean DEFAULT true
)
RETURNS TABLE(
  id bigint,
  name text,
  version text,
  status text,
  kind text,
  element_type_id bigint,
  element_type_name text,
  content_hash text,
  created_at_utc timestamptz,
  updated_at_utc timestamptz,
  field_count bigint
)
LANGUAGE sql
STABLE
AS $$
  SELECT * FROM wf.wf_repo_list_data_types(p_published_only);
$$;

DROP FUNCTION IF EXISTS portal.sp_get_data_type(text, text);

CREATE OR REPLACE FUNCTION portal.sp_get_data_type(
  p_name text,
  p_version text DEFAULT NULL
)
RETURNS TABLE(
  id bigint,
  name text,
  version text,
  status text,
  kind text,
  element_type_id bigint,
  element_type_name text,
  content_hash text,
  created_at_utc timestamptz,
  updated_at_utc timestamptz,
  schema_json jsonb
)
LANGUAGE sql
STABLE
AS $$
  SELECT * FROM wf.wf_repo_get_data_type(p_name, p_version);
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_data_type_fields(
  p_name text,
  p_version text DEFAULT NULL
)
RETURNS TABLE(
  id bigint,
  field_name text,
  field_type_id bigint,
  field_type_name text,
  field_type_kind text,
  required boolean,
  ordinal int
)
LANGUAGE sql
STABLE
AS $$
  SELECT * FROM wf.wf_repo_list_data_type_fields(p_name, p_version);
$$;

DROP FUNCTION IF EXISTS portal.sp_list_workflow_actions();
CREATE OR REPLACE FUNCTION portal.sp_list_workflow_actions()
RETURNS TABLE(
  id bigint,
  action_name text,
  capability text,
  execution_mode text,
  cli_tool text,
  in_process_handler text,
  implementation_status text,
  can_pause boolean,
  can_continue boolean,
  can_stop boolean,
  input_type_id bigint,
  input_type_name text,
  output_type_id bigint,
  output_type_name text
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    a.id, a.action_name, a.capability, a.execution_mode, a.cli_tool, a.in_process_handler,
    a.implementation_status, a.can_pause, a.can_continue, a.can_stop,
    a.input_type_id, tin.name, a.output_type_id, tout.name
  FROM wf.workflow_action a
  LEFT JOIN wf.data_type tin ON tin.id = a.input_type_id
  LEFT JOIN wf.data_type tout ON tout.id = a.output_type_id
  ORDER BY a.action_name;
$$;

DROP FUNCTION IF EXISTS portal.sp_get_workflow_action(text);
CREATE OR REPLACE FUNCTION portal.sp_get_workflow_action(p_action_name text)
RETURNS TABLE(
  id bigint,
  action_name text,
  capability text,
  execution_mode text,
  cli_tool text,
  in_process_handler text,
  implementation_status text,
  can_pause boolean,
  can_continue boolean,
  can_stop boolean,
  input_type_id bigint,
  input_type_name text,
  output_type_id bigint,
  output_type_name text
)
LANGUAGE sql
STABLE
AS $$
  SELECT * FROM portal.sp_list_workflow_actions() a
  WHERE a.action_name = p_action_name;
$$;

-- Overwrite the blob-only getter from wf_action_schema.sql. Bind the editor
-- to schema_json on the bound wf.data_type; fall back to legacy blobs.
CREATE OR REPLACE FUNCTION wf.wf_repo_get_action_schema(
  p_action_name text,
  p_direction text
)
RETURNS TABLE (
  action_name text,
  direction text,
  schema_id text,
  schema_json jsonb
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    a.action_name,
    p_direction,
    CASE WHEN p_direction = 'input' THEN tin.name ELSE tout.name END,
    COALESCE(
      CASE WHEN p_direction = 'input' THEN tin.schema_json ELSE tout.schema_json END,
      s.schema_json,
      jsonb_build_object(
        'type', 'object',
        'title', COALESCE(
          CASE WHEN p_direction = 'input' THEN tin.name ELSE tout.name END,
          p_action_name
        )
      )
    )
  FROM wf.workflow_action a
  LEFT JOIN wf.data_type tin ON tin.id = a.input_type_id
  LEFT JOIN wf.data_type tout ON tout.id = a.output_type_id
  LEFT JOIN wf.workflow_action_schema s
    ON s.workflow_action_id = a.id AND s.direction = p_direction
  WHERE a.action_name = p_action_name;
$$;

-- Affinity list_actions deploys before this file; overwrite has_* flags so
-- Config Editor sees a schema when the bound type has schema_json.
CREATE OR REPLACE FUNCTION wf.wf_repo_list_actions()
RETURNS TABLE (
  action_name text,
  capability text,
  has_input_schema boolean,
  has_output_schema boolean,
  execution_mode text,
  cli_tool text,
  in_process_handler text,
  argv_map jsonb,
  max_per_worker integer,
  exclusive_worker boolean,
  affinity_key_field text,
  prefer_previous_worker boolean,
  prefer_continue_group boolean
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    a.action_name,
    a.capability,
    (
      tin.schema_json IS NOT NULL
      OR EXISTS (
        SELECT 1 FROM wf.workflow_action_schema si
        WHERE si.workflow_action_id = a.id AND si.direction = 'input'
      )
    ) AS has_input_schema,
    (
      tout.schema_json IS NOT NULL
      OR EXISTS (
        SELECT 1 FROM wf.workflow_action_schema so
        WHERE so.workflow_action_id = a.id AND so.direction = 'output'
      )
    ) AS has_output_schema,
    a.execution_mode,
    a.cli_tool,
    a.in_process_handler,
    a.argv_map,
    a.max_per_worker,
    a.exclusive_worker,
    a.affinity_key_field,
    a.prefer_previous_worker,
    a.prefer_continue_group
  FROM wf.workflow_action a
  LEFT JOIN wf.data_type tin ON tin.id = a.input_type_id
  LEFT JOIN wf.data_type tout ON tout.id = a.output_type_id
  ORDER BY a.action_name;
$$;
