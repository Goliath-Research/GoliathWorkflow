-- wf.worker_enrollment + wf.sp_worker_enroll (PostgreSQL)
CREATE TABLE IF NOT EXISTS wf.worker_enrollment (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  cluster_id bigint NOT NULL REFERENCES wf.cluster(id),
  public_ip text NOT NULL,
  external_worker_key text NOT NULL,
  status varchar(32) NOT NULL DEFAULT 'PENDING',
  enrolled_worker_id bigint NULL REFERENCES wf.worker(id),
  enrolled_at_utc timestamptz NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  UNIQUE (cluster_id, public_ip),
  UNIQUE (cluster_id, external_worker_key),
  CHECK (status IN ('PENDING', 'ENROLLED', 'REVOKED'))
);

CREATE INDEX IF NOT EXISTS ix_we_cluster_status ON wf.worker_enrollment(cluster_id, status);

CREATE OR REPLACE FUNCTION wf.sp_worker_enroll(
  p_cluster_key text,
  p_external_worker_key text,
  p_client_ip text,
  p_token_hash_hex text,
  p_capabilities_json jsonb DEFAULT '[]'::jsonb,
  p_arc_resource_id text DEFAULT NULL
)
RETURNS TABLE(worker_id bigint)
LANGUAGE plpgsql
AS $$
DECLARE
  v_cluster_id bigint;
  v_enroll_id bigint;
  v_allow_ip text;
  v_enroll_status text;
  v_allow_host text;
  v_worker_id bigint;
  v_caps jsonb := COALESCE(p_capabilities_json, '[]'::jsonb);
BEGIN
  IF NULLIF(btrim(p_cluster_key), '') IS NULL THEN
    RAISE EXCEPTION 'cluster_key is required' USING ERRCODE = 'P0001';
  END IF;
  IF NULLIF(btrim(p_external_worker_key), '') IS NULL THEN
    RAISE EXCEPTION 'external_worker_key is required' USING ERRCODE = 'P0001';
  END IF;
  IF NULLIF(btrim(p_client_ip), '') IS NULL THEN
    RAISE EXCEPTION 'client_ip is required' USING ERRCODE = 'P0001';
  END IF;
  IF NULLIF(btrim(p_token_hash_hex), '') IS NULL THEN
    RAISE EXCEPTION 'token_hash_hex is required' USING ERRCODE = 'P0001';
  END IF;

  SELECT c.id INTO v_cluster_id
  FROM wf.cluster c
  WHERE c.cluster_key = p_cluster_key AND c.status = 'ACTIVE';

  IF v_cluster_id IS NULL THEN
    RAISE EXCEPTION 'Unknown or disabled cluster' USING ERRCODE = 'P0001';
  END IF;

  SELECT e.id, e.public_ip, e.status
  INTO v_enroll_id, v_allow_ip, v_enroll_status
  FROM wf.worker_enrollment e
  WHERE e.cluster_id = v_cluster_id
    AND e.external_worker_key = p_external_worker_key;

  IF v_enroll_id IS NULL THEN
    RAISE EXCEPTION 'No enrollment allowlist entry for this worker key' USING ERRCODE = 'P0001';
  END IF;
  IF v_enroll_status = 'REVOKED' THEN
    RAISE EXCEPTION 'Enrollment has been revoked' USING ERRCODE = 'P0001';
  END IF;

  v_allow_host := split_part(btrim(v_allow_ip), '/', 1);
  IF btrim(p_client_ip) <> btrim(v_allow_ip) AND btrim(p_client_ip) <> v_allow_host THEN
    RAISE EXCEPTION 'client IP does not match preregistered enrollment IP' USING ERRCODE = 'P0001';
  END IF;

  IF NULLIF(btrim(COALESCE(p_arc_resource_id, '')), '') IS NOT NULL THEN
    UPDATE wf.cluster
    SET arc_resource_id = COALESCE(arc_resource_id, btrim(p_arc_resource_id)),
        updated_at_utc = now() AT TIME ZONE 'utc'
    WHERE id = v_cluster_id;
  END IF;

  INSERT INTO wf.worker (cluster_id, external_worker_key, display_name, capabilities, status)
  VALUES (v_cluster_id, p_external_worker_key, p_external_worker_key, v_caps, 'REGISTERED')
  ON CONFLICT (external_worker_key) DO UPDATE SET
    cluster_id = EXCLUDED.cluster_id,
    capabilities = EXCLUDED.capabilities,
    status = 'REGISTERED',
    updated_at_utc = now() AT TIME ZONE 'utc'
  RETURNING id INTO v_worker_id;

  DELETE FROM wf.worker_token WHERE worker_id = v_worker_id;
  INSERT INTO wf.worker_token (worker_id, token_hash, status)
  VALUES (v_worker_id, decode(p_token_hash_hex, 'hex'), 'ACTIVE');

  UPDATE wf.worker_enrollment
  SET status = 'ENROLLED',
      enrolled_worker_id = v_worker_id,
      enrolled_at_utc = now() AT TIME ZONE 'utc',
      updated_at_utc = now() AT TIME ZONE 'utc'
  WHERE id = v_enroll_id;

  RETURN QUERY SELECT v_worker_id;
END;
$$;
