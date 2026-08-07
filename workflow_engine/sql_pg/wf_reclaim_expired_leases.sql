/*
  Reclaim RUNNING node_executions whose task_lease has expired (or is missing).

  Parity with workflow_engine/sql_mssql/wf_reclaim_expired_leases.sql.

  Portal: SELECT * FROM portal.sp_reclaim_expired_leases(...);
  Claim path: PERFORM * FROM wf.sp_reclaim_expired_leases(NULL, 60, true);

  Deploy before (or with) 01_worker_api.sql — claim calls this quietly.
*/

CREATE SCHEMA IF NOT EXISTS portal;

CREATE OR REPLACE FUNCTION wf.sp_reclaim_expired_leases(
  p_workflow_instance_id bigint DEFAULT NULL,
  p_grace_seconds int DEFAULT 60,
  p_quiet boolean DEFAULT false
)
RETURNS TABLE (
  node_execution_id bigint,
  workflow_instance_id bigint,
  previous_worker_id bigint,
  lease_expired_at_utc timestamptz,
  reclaimed_at_utc timestamptz
)
LANGUAGE plpgsql
AS $$
#variable_conflict use_column
DECLARE
  v_grace int := GREATEST(COALESCE(p_grace_seconds, 0), 0);
  v_cutoff timestamptz := (now() AT TIME ZONE 'utc') - make_interval(secs => v_grace);
  v_now timestamptz := (now() AT TIME ZONE 'utc');
BEGIN
  RETURN QUERY
  WITH expired AS (
    SELECT ne.id AS node_execution_id,
           ne.workflow_instance_id,
           l.worker_id AS previous_worker_id,
           l.lease_expires_at_utc
    FROM wf.node_execution AS ne
    LEFT JOIN wf.task_lease AS l ON l.node_execution_id = ne.id
    WHERE ne.status = 'RUNNING'
      AND (
            l.node_execution_id IS NULL
         OR l.lease_expires_at_utc <= v_cutoff
      )
      AND (p_workflow_instance_id IS NULL OR ne.workflow_instance_id = p_workflow_instance_id)
    FOR UPDATE OF ne
  ),
  updated AS (
    UPDATE wf.node_execution AS ne
    SET status = 'READY',
        result_code = NULL,
        engine_error_code = NULL,
        engine_error_message = 'reclaimed: lease expired or missing',
        output_json = NULL,
        started_at_utc = NULL,
        ended_at_utc = NULL,
        attempt_no = COALESCE(ne.attempt_no, 0) + 1,
        available_at_utc = v_now
    FROM expired AS e
    WHERE ne.id = e.node_execution_id
      AND ne.status = 'RUNNING'
    RETURNING ne.id AS node_execution_id,
              ne.workflow_instance_id,
              e.previous_worker_id,
              e.lease_expires_at_utc
  ),
  deleted AS (
    DELETE FROM wf.task_lease AS l
    USING updated AS u
    WHERE l.node_execution_id = u.node_execution_id
    RETURNING l.node_execution_id
  )
  SELECT u.node_execution_id,
         u.workflow_instance_id,
         u.previous_worker_id,
         u.lease_expires_at_utc,
         v_now
  FROM updated AS u
  WHERE NOT p_quiet;
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_reclaim_expired_leases(
  p_workflow_instance_id bigint DEFAULT NULL,
  p_grace_seconds int DEFAULT 60
)
RETURNS TABLE (
  node_execution_id bigint,
  workflow_instance_id bigint,
  previous_worker_id bigint,
  lease_expired_at_utc timestamptz,
  reclaimed_at_utc timestamptz
)
LANGUAGE sql
AS $$
  SELECT *
  FROM wf.sp_reclaim_expired_leases(p_workflow_instance_id, p_grace_seconds, false);
$$;
