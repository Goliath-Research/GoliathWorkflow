/*
  PostgreSQL: dispatch metadata columns on wf.workflow_action + canonical 7-arg upsert
  and wf.wf_repo_list_actions (8-column RETURNS TABLE).

  Deploy after wf_repo_upsert_workflow_action.sql (3-arg bootstrap). This script is
  required for seed_action_catalog.py / admin catalog seed / GET /v1/actions dispatch fields.
  Prerequisites: 00_schema.sql, wf_action_schema.sql (schema table; list_actions lives here only
  so re-deploys do not hit 42P13 from a narrower CREATE OR REPLACE earlier in the set).
*/

ALTER TABLE wf.workflow_action
  ADD COLUMN IF NOT EXISTS execution_mode text NULL,
  ADD COLUMN IF NOT EXISTS cli_tool text NULL,
  ADD COLUMN IF NOT EXISTS in_process_handler text NULL,
  ADD COLUMN IF NOT EXISTS argv_map jsonb NULL;

-- Supersede the 3-arg bootstrap (different arg list = separate overload in PG).
DROP PROCEDURE IF EXISTS wf.wf_repo_upsert_workflow_action(text, text, text);

CREATE OR REPLACE PROCEDURE wf.wf_repo_upsert_workflow_action(
  IN p_action_name text,
  IN p_capability text,
  IN p_payload_schema_ref text DEFAULT NULL,
  IN p_execution_mode text DEFAULT NULL,
  IN p_cli_tool text DEFAULT NULL,
  IN p_in_process_handler text DEFAULT NULL,
  IN p_argv_map jsonb DEFAULT NULL
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
    argv_map
  )
  VALUES (
    p_action_name,
    p_capability,
    p_payload_schema_ref,
    p_execution_mode,
    p_cli_tool,
    p_in_process_handler,
    p_argv_map
  )
  ON CONFLICT (action_name) DO UPDATE SET
    capability = EXCLUDED.capability,
    payload_schema_ref = COALESCE(EXCLUDED.payload_schema_ref, wf.workflow_action.payload_schema_ref),
    execution_mode = COALESCE(EXCLUDED.execution_mode, wf.workflow_action.execution_mode),
    cli_tool = COALESCE(EXCLUDED.cli_tool, wf.workflow_action.cli_tool),
    in_process_handler = COALESCE(EXCLUDED.in_process_handler, wf.workflow_action.in_process_handler),
    argv_map = COALESCE(EXCLUDED.argv_map, wf.workflow_action.argv_map);
END;
$$;

-- CREATE OR REPLACE cannot widen RETURNS TABLE (42P13). Drop first; CASCADE
-- removes dependents such as portal.sp_list_workflow_actions (reapplied later).
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
  argv_map jsonb
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
    a.argv_map
  FROM wf.workflow_action a
  ORDER BY a.action_name;
$$;
