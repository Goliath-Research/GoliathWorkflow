/*
  Catalog-driven soft worker affinity on wf.workflow_action / wf.node_execution.

  Columns (seeded from action catalog ``dispatch``):
    - affinity_key_field     name of an input_json field (opaque); NULL = no affinity
    - prefer_previous_worker soft stickiness to last completer of the same key
    - prefer_continue_group  prefer READY rows whose key already has SUCCEEDED work

  Runtime columns on wf.node_execution:
    - affinity_key             stamped at ACTION activation from input_json
    - completed_by_worker_id   set on claim; retained after lease delete

  Engine stays process-agnostic: it only reads these columns. Deploy after
  wf_action_dispatch_concurrency.sql (widens upsert from 9-arg to 12-arg).
  Claim ORDER BY lives in 01_worker_api.sql; activate stamping is applied here
  by replacing wf.wf_engine_activate after 08_foreach_support.sql.
*/

ALTER TABLE wf.workflow_action
  ADD COLUMN IF NOT EXISTS affinity_key_field text NULL,
  ADD COLUMN IF NOT EXISTS prefer_previous_worker boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS prefer_continue_group boolean NOT NULL DEFAULT false;

ALTER TABLE wf.node_execution
  ADD COLUMN IF NOT EXISTS affinity_key text NULL,
  ADD COLUMN IF NOT EXISTS completed_by_worker_id bigint NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_ne_completed_by_worker'
  ) THEN
    ALTER TABLE wf.node_execution
      ADD CONSTRAINT fk_ne_completed_by_worker
      FOREIGN KEY (completed_by_worker_id) REFERENCES wf.worker(id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_ne_instance_affinity_status
  ON wf.node_execution (workflow_instance_id, affinity_key, status)
  INCLUDE (completed_by_worker_id, ended_at_utc)
  WHERE affinity_key IS NOT NULL;

-- Drop prior overloads so the 12-arg signature is unambiguous.
DROP PROCEDURE IF EXISTS wf.wf_repo_upsert_workflow_action(
  text, text, text, text, text, text, jsonb, integer, boolean
);
DROP PROCEDURE IF EXISTS wf.wf_repo_upsert_workflow_action(
  text, text, text, text, text, text, jsonb
);
DROP PROCEDURE IF EXISTS wf.wf_repo_upsert_workflow_action(text, text, text);

CREATE OR REPLACE PROCEDURE wf.wf_repo_upsert_workflow_action(
  IN p_action_name text,
  IN p_capability text,
  IN p_payload_schema_ref text DEFAULT NULL,
  IN p_execution_mode text DEFAULT NULL,
  IN p_cli_tool text DEFAULT NULL,
  IN p_in_process_handler text DEFAULT NULL,
  IN p_argv_map jsonb DEFAULT NULL,
  IN p_max_per_worker integer DEFAULT NULL,
  IN p_exclusive_worker boolean DEFAULT NULL,
  IN p_affinity_key_field text DEFAULT NULL,
  IN p_prefer_previous_worker boolean DEFAULT NULL,
  IN p_prefer_continue_group boolean DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
BEGIN
  IF p_action_name IS NULL OR btrim(p_action_name) = '' THEN
    RETURN;
  END IF;

  INSERT INTO wf.workflow_action (
    action_name,
    capability,
    payload_schema_ref,
    execution_mode,
    cli_tool,
    in_process_handler,
    argv_map,
    max_per_worker,
    exclusive_worker,
    affinity_key_field,
    prefer_previous_worker,
    prefer_continue_group
  )
  VALUES (
    p_action_name,
    p_capability,
    p_payload_schema_ref,
    p_execution_mode,
    p_cli_tool,
    p_in_process_handler,
    p_argv_map,
    p_max_per_worker,
    coalesce(p_exclusive_worker, false),
    p_affinity_key_field,
    coalesce(p_prefer_previous_worker, false),
    coalesce(p_prefer_continue_group, false)
  )
  ON CONFLICT (action_name) DO UPDATE SET
    capability = EXCLUDED.capability,
    payload_schema_ref = COALESCE(EXCLUDED.payload_schema_ref, wf.workflow_action.payload_schema_ref),
    execution_mode = COALESCE(EXCLUDED.execution_mode, wf.workflow_action.execution_mode),
    cli_tool = COALESCE(EXCLUDED.cli_tool, wf.workflow_action.cli_tool),
    in_process_handler = COALESCE(EXCLUDED.in_process_handler, wf.workflow_action.in_process_handler),
    argv_map = COALESCE(EXCLUDED.argv_map, wf.workflow_action.argv_map),
    max_per_worker = EXCLUDED.max_per_worker,
    exclusive_worker = coalesce(EXCLUDED.exclusive_worker, false),
    affinity_key_field = EXCLUDED.affinity_key_field,
    prefer_previous_worker = coalesce(EXCLUDED.prefer_previous_worker, false),
    prefer_continue_group = coalesce(EXCLUDED.prefer_continue_group, false);
END;
$$;

DROP FUNCTION IF EXISTS wf.wf_repo_list_actions() CASCADE;

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
    EXISTS (
      SELECT 1 FROM wf.workflow_action_schema si
      WHERE si.workflow_action_id = a.id AND si.direction = 'input'
    ) AS has_input_schema,
    EXISTS (
      SELECT 1 FROM wf.workflow_action_schema so
      WHERE so.workflow_action_id = a.id AND so.direction = 'output'
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
  ORDER BY a.action_name;
$$;

-- Stamp helper used by wf_engine_activate after input_json is built.
CREATE OR REPLACE PROCEDURE wf.wf_stamp_affinity_key(
  IN p_node_execution_id bigint,
  IN p_workflow_node_id bigint,
  IN p_input_json jsonb
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_field text;
  v_key text;
BEGIN
  SELECT wa.affinity_key_field INTO v_field
  FROM wf.workflow_node wn
  INNER JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
  WHERE wn.id = p_workflow_node_id;

  IF v_field IS NULL OR v_field !~ '^[A-Za-z_][A-Za-z0-9_]*$' THEN
    RETURN;
  END IF;

  v_key := left(p_input_json ->> v_field, 256);
  UPDATE wf.node_execution
  SET affinity_key = v_key
  WHERE id = p_node_execution_id;
END;
$$;
