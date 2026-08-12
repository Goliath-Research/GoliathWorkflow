/*
  LEGACY — PostgreSQL workflow action JSON Schema blobs.

  Seeding is retired. Prefer wf.data_type + workflow_action.input/output_type_id
  (wf_data_type.sql). Table kept for read compatibility.

  Prerequisites: 00_schema.sql (workflow_action)

  Note: wf.wf_repo_list_actions is NOT defined here. A 4-column bootstrap would
  collide on re-deploy with the 8-column canonical version from
  wf_action_dispatch_metadata.sql (PostgreSQL 42P13: CREATE OR REPLACE cannot
  change RETURNS TABLE). Deploy that script next in the ordered set.
*/

CREATE TABLE IF NOT EXISTS wf.workflow_action_schema (
  workflow_action_id bigint NOT NULL REFERENCES wf.workflow_action(id) ON DELETE CASCADE,
  direction varchar(16) NOT NULL CHECK (direction IN ('input', 'output')),
  schema_json jsonb NOT NULL,
  schema_id text NULL,
  updated_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  PRIMARY KEY (workflow_action_id, direction)
);

CREATE INDEX IF NOT EXISTS ix_was_action ON wf.workflow_action_schema(workflow_action_id);

CREATE OR REPLACE PROCEDURE wf.wf_repo_upsert_action_schema(
  IN p_action_name text,
  IN p_direction text,
  IN p_schema_json jsonb,
  IN p_schema_id text DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_action_id bigint;
BEGIN
  IF p_action_name IS NULL OR btrim(p_action_name) = ''
     OR p_direction IS NULL OR p_direction NOT IN ('input', 'output')
     OR p_schema_json IS NULL THEN
    RETURN;
  END IF;

  SELECT id INTO v_action_id
  FROM wf.workflow_action
  WHERE action_name = p_action_name;

  IF v_action_id IS NULL THEN
    RETURN;
  END IF;

  INSERT INTO wf.workflow_action_schema (workflow_action_id, direction, schema_json, schema_id)
  VALUES (v_action_id, p_direction, p_schema_json, p_schema_id)
  ON CONFLICT (workflow_action_id, direction) DO UPDATE SET
    schema_json = EXCLUDED.schema_json,
    schema_id = EXCLUDED.schema_id,
    updated_at_utc = (now() AT TIME ZONE 'utc');

  IF p_direction = 'input' AND p_schema_id IS NOT NULL THEN
    UPDATE wf.workflow_action
    SET payload_schema_ref = p_schema_id
    WHERE id = v_action_id;
  END IF;
END;
$$;

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
  SELECT a.action_name, s.direction, s.schema_id, s.schema_json
  FROM wf.workflow_action a
  INNER JOIN wf.workflow_action_schema s ON s.workflow_action_id = a.id
  WHERE a.action_name = p_action_name
    AND s.direction = p_direction;
$$;
