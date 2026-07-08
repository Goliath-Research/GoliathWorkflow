/*
  MethylPipeline wf schema - hyperparameter set registry and action result ledger (PostgreSQL).

  Prerequisites:
  - 00_schema.sql (workflow_instance, wf.instance_extension)
  - 02_repository_api.sql or wf_instance_extension.sql (wf_repo_upsert_instance_extension)
*/

CREATE TABLE IF NOT EXISTS wf.hyperparameter_set (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  set_key text NOT NULL,
  display_name text NULL,
  config_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  UNIQUE (set_key)
);

CREATE INDEX IF NOT EXISTS ix_hps_set_key ON wf.hyperparameter_set(set_key);

ALTER TABLE wf.workflow_instance
  ADD COLUMN IF NOT EXISTS hyperparameter_set_id bigint NULL
  REFERENCES wf.hyperparameter_set(id);

CREATE INDEX IF NOT EXISTS ix_wi_hyperparameter_set
  ON wf.workflow_instance(hyperparameter_set_id);

CREATE TABLE IF NOT EXISTS wf.hyperparameter_set_action_entry (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  hyperparameter_set_id bigint NOT NULL REFERENCES wf.hyperparameter_set(id) ON DELETE CASCADE,
  workflow_instance_id bigint NOT NULL REFERENCES wf.workflow_instance(id) ON DELETE CASCADE,
  action_name text NOT NULL,
  run_key text NOT NULL DEFAULT 'default',
  content_key text NOT NULL,
  recorded_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  UNIQUE (hyperparameter_set_id, action_name, run_key)
);

CREATE INDEX IF NOT EXISTS ix_hpse_instance
  ON wf.hyperparameter_set_action_entry(workflow_instance_id);

CREATE INDEX IF NOT EXISTS ix_hpse_set
  ON wf.hyperparameter_set_action_entry(hyperparameter_set_id);

CREATE OR REPLACE FUNCTION wf.wf_repo_upsert_hyperparameter_set(
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

  INSERT INTO wf.hyperparameter_set (set_key, display_name, config_json)
  VALUES (p_set_key, NULLIF(btrim(p_display_name), ''), coalesce(p_config_json, '{}'::jsonb))
  ON CONFLICT (set_key) DO UPDATE SET
    display_name = coalesce(EXCLUDED.display_name, wf.hyperparameter_set.display_name),
    config_json = EXCLUDED.config_json
  RETURNING id INTO v_id;

  RETURN v_id;
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_apply_hyperparameter_set(
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

  v_set_id := wf.wf_repo_upsert_hyperparameter_set(
    p_set_key,
    p_display_name,
    coalesce(p_config_json, '{}'::jsonb)
  );

  UPDATE wf.workflow_instance
  SET hyperparameter_set_id = v_set_id
  WHERE id = p_workflow_instance_id;

  IF p_persist_extension THEN
    CALL wf.wf_repo_upsert_instance_extension(
      p_workflow_instance_id,
      'methyl.hyperparameter.set',
      jsonb_build_object(
        'hyperparamSetId', p_set_key,
        'hyperparamSetName', p_display_name,
        'config', coalesce(p_config_json, '{}'::jsonb)
      )
    );
  END IF;
END;
$$;

CREATE OR REPLACE PROCEDURE wf.wf_repo_upsert_hyperparameter_action_entry(
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

  SELECT hs.id INTO v_set_id
  FROM wf.hyperparameter_set hs
  WHERE hs.set_key = p_set_key;

  IF v_set_id IS NULL THEN
    v_set_id := wf.wf_repo_upsert_hyperparameter_set(p_set_key, NULL, '{}'::jsonb);
  END IF;

  INSERT INTO wf.hyperparameter_set_action_entry (
    hyperparameter_set_id,
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
  ON CONFLICT (hyperparameter_set_id, action_name, run_key) DO UPDATE SET
    content_key = EXCLUDED.content_key,
    workflow_instance_id = EXCLUDED.workflow_instance_id,
    recorded_at_utc = (now() AT TIME ZONE 'utc');
END;
$$;

CREATE OR REPLACE FUNCTION wf.wf_repo_get_hyperparameter_set(
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
  SELECT hs.id, hs.set_key, hs.display_name, hs.config_json, hs.created_at_utc
  FROM wf.hyperparameter_set hs
  WHERE hs.set_key = p_set_key;
$$;

CREATE OR REPLACE FUNCTION wf.wf_repo_list_hyperparameter_action_entries(
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
  FROM wf.hyperparameter_set_action_entry e
  JOIN wf.hyperparameter_set hs ON hs.id = e.hyperparameter_set_id
  WHERE hs.set_key = p_set_key
  ORDER BY e.action_name, e.run_key;
$$;

CREATE OR REPLACE FUNCTION wf.wf_repo_get_action_submit_context(
  p_node_execution_id bigint
)
RETURNS TABLE (
  workflow_instance_id bigint,
  hyperparam_set_key text,
  action_name text,
  input_json jsonb
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    ne.workflow_instance_id,
    coalesce(wi.context_json ->> 'hyperparamSetId', hs.set_key) AS hyperparam_set_key,
    wa.action_name,
    ne.input_json
  FROM wf.node_execution ne
  JOIN wf.workflow_instance wi ON wi.id = ne.workflow_instance_id
  LEFT JOIN wf.hyperparameter_set hs ON hs.id = wi.hyperparameter_set_id
  JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
  LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
  WHERE ne.id = p_node_execution_id;
$$;
