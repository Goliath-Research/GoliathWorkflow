/*
  MethylPipeline wf schema - execution scope registry and action result ledger (PostgreSQL).

  An "execution scope" is the workflow engine's process-agnostic identity for one
  fully-resolved configuration combination (a hash of the baked resolvedConfig__*
  slices). It carries no domain meaning: higher layers (cfg) attach the notion of a
  "hyperparameter" trial to a scope. The word "hyperparameter" deliberately does not
  appear in wf.

  Prerequisites:
  - 00_schema.sql (workflow_instance, wf.instance_extension)
  - 02_repository_api.sql or wf_instance_extension.sql (wf_repo_upsert_instance_extension)
*/

-- migration: rename legacy hyperparameter_set objects to execution_scope
DO $$
BEGIN
  IF to_regclass('wf.hyperparameter_set') IS NOT NULL
     AND to_regclass('wf.execution_scope') IS NULL THEN
    IF to_regclass('wf.hyperparameter_set_action_entry') IS NOT NULL THEN
      ALTER TABLE wf.hyperparameter_set_action_entry
        RENAME COLUMN hyperparameter_set_id TO execution_scope_id;
      ALTER TABLE wf.hyperparameter_set_action_entry
        RENAME TO execution_scope_action_entry;
    END IF;
    ALTER TABLE wf.workflow_instance
      RENAME COLUMN hyperparameter_set_id TO execution_scope_id;
    ALTER TABLE wf.hyperparameter_set RENAME TO execution_scope;
  END IF;
END
$$;

DROP FUNCTION IF EXISTS wf.wf_repo_upsert_hyperparameter_set(text, text, jsonb);
DROP PROCEDURE IF EXISTS wf.wf_apply_hyperparameter_set(bigint, text, text, jsonb, boolean);
DROP PROCEDURE IF EXISTS wf.wf_repo_upsert_hyperparameter_action_entry(text, bigint, text, text, text);
DROP FUNCTION IF EXISTS wf.wf_repo_get_hyperparameter_set(text);
DROP FUNCTION IF EXISTS wf.wf_repo_list_hyperparameter_action_entries(text);

CREATE TABLE IF NOT EXISTS wf.execution_scope (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  set_key text NOT NULL,
  display_name text NULL,
  config_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  UNIQUE (set_key)
);

CREATE INDEX IF NOT EXISTS ix_es_set_key ON wf.execution_scope(set_key);

ALTER TABLE wf.workflow_instance
  ADD COLUMN IF NOT EXISTS execution_scope_id bigint NULL
  REFERENCES wf.execution_scope(id);

CREATE INDEX IF NOT EXISTS ix_wi_execution_scope
  ON wf.workflow_instance(execution_scope_id);

CREATE TABLE IF NOT EXISTS wf.execution_scope_action_entry (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  execution_scope_id bigint NOT NULL REFERENCES wf.execution_scope(id) ON DELETE CASCADE,
  workflow_instance_id bigint NOT NULL REFERENCES wf.workflow_instance(id) ON DELETE CASCADE,
  action_name text NOT NULL,
  run_key text NOT NULL DEFAULT 'default',
  content_key text NOT NULL,
  recorded_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  UNIQUE (execution_scope_id, action_name, run_key)
);

CREATE INDEX IF NOT EXISTS ix_esae_instance
  ON wf.execution_scope_action_entry(workflow_instance_id);

CREATE INDEX IF NOT EXISTS ix_esae_scope
  ON wf.execution_scope_action_entry(execution_scope_id);

CREATE OR REPLACE FUNCTION wf.wf_repo_upsert_execution_scope(
  p_set_key text,
  p_display_name text DEFAULT NULL,
  p_config_json jsonb DEFAULT '{}'::jsonb
)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
  v_id bigint;
BEGIN
  IF p_set_key IS NULL OR btrim(p_set_key) = '' THEN
    RETURN NULL;
  END IF;

  INSERT INTO wf.execution_scope (set_key, display_name, config_json)
  VALUES (p_set_key, NULLIF(btrim(p_display_name), ''), coalesce(p_config_json, '{}'::jsonb))
  ON CONFLICT (set_key) DO UPDATE SET
    display_name = coalesce(EXCLUDED.display_name, wf.execution_scope.display_name),
    config_json = EXCLUDED.config_json
  RETURNING id INTO v_id;

  RETURN v_id;
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_apply_execution_scope(
  IN p_workflow_instance_id bigint,
  IN p_set_key text,
  IN p_display_name text DEFAULT NULL,
  IN p_config_json jsonb DEFAULT '{}'::jsonb,
  IN p_persist_extension boolean DEFAULT true
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_set_id bigint;
BEGIN
  IF p_set_key IS NULL OR btrim(p_set_key) = '' THEN
    RETURN;
  END IF;

  v_set_id := wf.wf_repo_upsert_execution_scope(
    p_set_key,
    p_display_name,
    coalesce(p_config_json, '{}'::jsonb)
  );

  UPDATE wf.workflow_instance
  SET execution_scope_id = v_set_id
  WHERE id = p_workflow_instance_id;

  IF p_persist_extension THEN
    CALL wf.wf_repo_upsert_instance_extension(
      p_workflow_instance_id,
      'methyl.execution.scope',
      jsonb_build_object(
        'executionScopeId', p_set_key,
        'executionScopeName', p_display_name,
        'config', coalesce(p_config_json, '{}'::jsonb)
      )
    );
  END IF;
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_repo_upsert_execution_scope_action_entry(
  IN p_set_key text,
  IN p_workflow_instance_id bigint,
  IN p_action_name text,
  IN p_run_key text,
  IN p_content_key text
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_set_id bigint;
BEGIN
  IF p_set_key IS NULL OR btrim(p_set_key) = ''
     OR p_action_name IS NULL OR btrim(p_action_name) = ''
     OR p_content_key IS NULL OR btrim(p_content_key) = '' THEN
    RETURN;
  END IF;

  SELECT es.id INTO v_set_id
  FROM wf.execution_scope es
  WHERE es.set_key = p_set_key;

  IF v_set_id IS NULL THEN
    v_set_id := wf.wf_repo_upsert_execution_scope(p_set_key, NULL, '{}'::jsonb);
  END IF;

  INSERT INTO wf.execution_scope_action_entry (
    execution_scope_id,
    workflow_instance_id,
    action_name,
    run_key,
    content_key
  ) VALUES (
    v_set_id,
    p_workflow_instance_id,
    p_action_name,
    coalesce(NULLIF(btrim(p_run_key), ''), 'default'),
    p_content_key
  )
  ON CONFLICT (execution_scope_id, action_name, run_key) DO UPDATE SET
    content_key = EXCLUDED.content_key,
    workflow_instance_id = EXCLUDED.workflow_instance_id,
    recorded_at_utc = (now() AT TIME ZONE 'utc');
END;
$$;

CREATE OR REPLACE FUNCTION wf.wf_repo_get_execution_scope(
  p_set_key text
)
RETURNS TABLE (
  id bigint,
  set_key text,
  display_name text,
  config_json jsonb,
  created_at_utc timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT es.id, es.set_key, es.display_name, es.config_json, es.created_at_utc
  FROM wf.execution_scope es
  WHERE es.set_key = p_set_key;
$$;

CREATE OR REPLACE FUNCTION wf.wf_repo_list_execution_scope_action_entries(
  p_set_key text
)
RETURNS TABLE (
  action_name text,
  run_key text,
  content_key text,
  workflow_instance_id bigint,
  recorded_at_utc timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT e.action_name, e.run_key, e.content_key, e.workflow_instance_id, e.recorded_at_utc
  FROM wf.execution_scope_action_entry e
  JOIN wf.execution_scope es ON es.id = e.execution_scope_id
  WHERE es.set_key = p_set_key
  ORDER BY e.action_name, e.run_key;
$$;

CREATE OR REPLACE FUNCTION wf.wf_repo_get_action_submit_context(
  p_node_execution_id bigint
)
RETURNS TABLE (
  workflow_instance_id bigint,
  execution_scope_key text,
  action_name text,
  input_json jsonb
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    ne.workflow_instance_id,
    coalesce(
      wi.context_json ->> 'executionScopeId',
      wi.context_json ->> 'hyperparamSetId',
      es.set_key
    ) AS execution_scope_key,
    wa.action_name,
    ne.input_json
  FROM wf.node_execution ne
  JOIN wf.workflow_instance wi ON wi.id = ne.workflow_instance_id
  LEFT JOIN wf.execution_scope es ON es.id = wi.execution_scope_id
  JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
  LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
  WHERE ne.id = p_node_execution_id;
$$;
