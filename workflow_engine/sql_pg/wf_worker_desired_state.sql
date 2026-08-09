/*
  Additive: wf.worker.desired_state + portal.sp_set_worker_desired_state.
  Apply before/with 01_worker_api.sql so claim/heartbeat can read desired_state.
*/

ALTER TABLE wf.worker
  ADD COLUMN IF NOT EXISTS desired_state varchar(32) NOT NULL DEFAULT 'ACTIVE';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'worker_desired_state_check'
      AND conrelid = 'wf.worker'::regclass
  ) THEN
    ALTER TABLE wf.worker
      ADD CONSTRAINT worker_desired_state_check
      CHECK (desired_state IN ('ACTIVE', 'DRAINING', 'STOPPING'));
  END IF;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

CREATE OR REPLACE FUNCTION portal.sp_set_worker_desired_state(
  p_worker_id bigint,
  p_desired_state text,
  p_cluster_id bigint DEFAULT NULL
)
RETURNS TABLE (
  worker_id bigint,
  desired_state text,
  rows_updated int
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_state text := upper(btrim(coalesce(p_desired_state, '')));
  v_rows int := 0;
BEGIN
  IF v_state NOT IN ('ACTIVE', 'DRAINING', 'STOPPING') THEN
    RAISE EXCEPTION 'desired_state must be ACTIVE, DRAINING, or STOPPING'
      USING ERRCODE = '22023';
  END IF;

  IF p_worker_id IS NOT NULL THEN
    UPDATE wf.worker w
    SET desired_state = v_state,
        updated_at_utc = (now() AT TIME ZONE 'utc')
    WHERE w.id = p_worker_id
      AND (p_cluster_id IS NULL OR w.cluster_id = p_cluster_id);
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN QUERY
    SELECT w.id, w.desired_state::text, v_rows
    FROM wf.worker w
    WHERE w.id = p_worker_id;
    RETURN;
  END IF;

  IF p_cluster_id IS NULL THEN
    RAISE EXCEPTION 'worker_id or cluster_id is required' USING ERRCODE = '22023';
  END IF;

  UPDATE wf.worker w
  SET desired_state = v_state,
      updated_at_utc = (now() AT TIME ZONE 'utc')
  WHERE w.cluster_id = p_cluster_id;
  GET DIAGNOSTICS v_rows = ROW_COUNT;

  RETURN QUERY
  SELECT w.id, w.desired_state::text, v_rows
  FROM wf.worker w
  WHERE w.cluster_id = p_cluster_id
  ORDER BY w.id;
END;
$$;
