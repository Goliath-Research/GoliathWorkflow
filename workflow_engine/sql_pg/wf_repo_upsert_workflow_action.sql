/*
  PostgreSQL: bootstrap upsert for wf.workflow_action (name / capability / schema ref).

  SUPERSEDED for full catalog seed: deploy ``wf_action_dispatch_metadata.sql`` after
  this file. That script adds execution_mode / cli_tool / in_process_handler / argv_map
  and replaces this procedure with the 7-parameter version used by
  ``seed_action_catalog.py`` and the admin gateway.

  Kept as a bootstrap so databases without dispatch columns can still upsert names.
  Prerequisites: 00_schema.sql (workflow_action)
*/

CREATE OR REPLACE PROCEDURE wf.wf_repo_upsert_workflow_action(
  IN p_action_name text,
  IN p_capability text,
  IN p_payload_schema_ref text DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
BEGIN
  IF p_action_name IS NULL OR btrim(p_action_name) = '' THEN
    RETURN;
  END IF;

  INSERT INTO wf.workflow_action (action_name, capability, payload_schema_ref)
  VALUES (p_action_name, p_capability, p_payload_schema_ref)
  ON CONFLICT (action_name) DO UPDATE SET
    capability = EXCLUDED.capability,
    payload_schema_ref = COALESCE(EXCLUDED.payload_schema_ref, wf.workflow_action.payload_schema_ref);
END;
$$;
