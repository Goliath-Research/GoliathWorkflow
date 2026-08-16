/*
  cfg hyperparameter search ledger + portal API (PostgreSQL).

  The portal UI owns the notion of a "hyperparameter search": a grid of trials,
  each of which becomes one wf.workflow_instance bound to a process-agnostic
  wf.execution_scope. These cfg tables give the UI a typed, queryable record of
  the search, its grid, and the trial -> instance mapping. wf stays agnostic.

  EpiPortal calls the portal.sp_* functions directly (never the REST gateway).
  Grid/overlay JSON conforms to the exported Pydantic schemas
  (schemas/config/hyperparam_*.schema.json).

  Prerequisites:
  - cfg_schema.sql, cfg_registry_tables.sql (cfg.study)
  - wf_execution_scope.sql (wf.execution_scope), wf workflow_instance
*/

CREATE SCHEMA IF NOT EXISTS portal;

CREATE TABLE IF NOT EXISTS cfg.hyperparameter_search_run (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  study_row_id bigint NULL REFERENCES cfg.study(id),
  display_name text NULL,
  base_context_hash text NULL,
  grid_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  objective_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'created',
  created_by text NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  CONSTRAINT ck_cfg_hsr_status CHECK (status IN (
    'created', 'running', 'completed', 'failed', 'cancelled'
  ))
);

CREATE INDEX IF NOT EXISTS ix_cfg_hsr_study ON cfg.hyperparameter_search_run(study_row_id);

CREATE TABLE IF NOT EXISTS cfg.hyperparameter_trial (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  search_id bigint NOT NULL REFERENCES cfg.hyperparameter_search_run(id) ON DELETE CASCADE,
  trial_index int NOT NULL,
  overrides_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  workflow_instance_id bigint NULL REFERENCES wf.workflow_instance(id) ON DELETE SET NULL,
  execution_scope_key text NULL,
  status text NOT NULL DEFAULT 'pending',
  objective double precision NULL,
  feasible boolean NULL,
  result_json jsonb NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  CONSTRAINT uq_cfg_ht_search_index UNIQUE (search_id, trial_index)
);

CREATE INDEX IF NOT EXISTS ix_cfg_ht_search ON cfg.hyperparameter_trial(search_id);
CREATE INDEX IF NOT EXISTS ix_cfg_ht_instance ON cfg.hyperparameter_trial(workflow_instance_id);

-- Create a search run and return its id. Instance creation happens in the portal
-- middle-tier (Python) because PostgreSQL cannot write /work and finalization is
-- an in-process step; trials are then recorded via sp_add_hyperparam_trial.
DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'portal' AND p.proname = 'sp_start_hyperparam_grid'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION portal.sp_start_hyperparam_grid(
  p_study_row_id bigint,
  p_display_name text,
  p_grid_json jsonb,
  p_objective_json jsonb DEFAULT '{}'::jsonb,
  p_base_context_hash text DEFAULT NULL,
  p_created_by text DEFAULT NULL
)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
  v_id bigint;
BEGIN
  INSERT INTO cfg.hyperparameter_search_run (
    study_row_id, display_name, base_context_hash, grid_json, objective_json, status, created_by
  ) VALUES (
    p_study_row_id,
    NULLIF(btrim(p_display_name), ''),
    p_base_context_hash,
    coalesce(p_grid_json, '{}'::jsonb),
    coalesce(p_objective_json, '{}'::jsonb),
    'running',
    p_created_by
  )
  RETURNING id INTO v_id;
  RETURN v_id;
END;
$$;

CREATE OR REPLACE PROCEDURE portal.sp_add_hyperparam_trial(
  IN p_search_id bigint,
  IN p_trial_index int,
  IN p_overrides_json jsonb,
  IN p_workflow_instance_id bigint,
  IN p_execution_scope_key text
)
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO cfg.hyperparameter_trial (
    search_id, trial_index, overrides_json, workflow_instance_id, execution_scope_key, status
  ) VALUES (
    p_search_id,
    p_trial_index,
    coalesce(p_overrides_json, '{}'::jsonb),
    p_workflow_instance_id,
    p_execution_scope_key,
    'started'
  )
  ON CONFLICT (search_id, trial_index) DO UPDATE SET
    overrides_json = EXCLUDED.overrides_json,
    workflow_instance_id = EXCLUDED.workflow_instance_id,
    execution_scope_key = EXCLUDED.execution_scope_key,
    status = 'started',
    updated_at_utc = (now() AT TIME ZONE 'utc');
END;
$$;

CREATE OR REPLACE PROCEDURE portal.sp_score_hyperparam_trial(
  IN p_search_id bigint,
  IN p_trial_index int,
  IN p_objective double precision,
  IN p_feasible boolean,
  IN p_result_json jsonb DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE cfg.hyperparameter_trial
  SET objective = p_objective,
      feasible = p_feasible,
      result_json = p_result_json,
      status = 'scored',
      updated_at_utc = (now() AT TIME ZONE 'utc')
  WHERE search_id = p_search_id AND trial_index = p_trial_index;
END;
$$;

CREATE OR REPLACE PROCEDURE portal.sp_set_hyperparam_search_status(
  IN p_search_id bigint,
  IN p_status text
)
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE cfg.hyperparameter_search_run
  SET status = p_status,
      updated_at_utc = (now() AT TIME ZONE 'utc')
  WHERE id = p_search_id;
END;
$$;

-- UI read: trials joined to live instance status.
DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'portal' AND p.proname = 'sp_get_hyperparam_search'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION portal.sp_get_hyperparam_search(
  p_search_id bigint
)
RETURNS TABLE (
  search_id bigint,
  search_status text,
  trial_index int,
  overrides_json jsonb,
  workflow_instance_id bigint,
  execution_scope_key text,
  instance_status text,
  trial_status text,
  objective double precision,
  feasible boolean
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    r.id AS search_id,
    r.status AS search_status,
    t.trial_index,
    t.overrides_json,
    t.workflow_instance_id,
    t.execution_scope_key,
    i.status AS instance_status,
    t.status AS trial_status,
    t.objective,
    t.feasible
  FROM cfg.hyperparameter_search_run r
  LEFT JOIN cfg.hyperparameter_trial t ON t.search_id = r.id
  LEFT JOIN wf.workflow_instance i ON i.id = t.workflow_instance_id
  WHERE r.id = p_search_id
  ORDER BY t.trial_index;
$$;
