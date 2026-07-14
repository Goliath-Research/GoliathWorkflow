-- Portal cluster + worker enrollment allowlist (PostgreSQL)
-- Ensure security columns exist on older DBs where 00_schema predated them.
ALTER TABLE wf.cluster
  ADD COLUMN IF NOT EXISTS allowed_source_cidrs jsonb NULL,
  ADD COLUMN IF NOT EXISTS entra_client_id text NULL,
  ADD COLUMN IF NOT EXISTS arc_resource_id text NULL;

CREATE OR REPLACE FUNCTION portal.sp_upsert_cluster(
  p_cluster_key text,
  p_name text DEFAULT NULL,
  p_shared_storage_uri text DEFAULT '/work/epimethyl',
  p_worker_mount_path text DEFAULT '/work/epimethyl',
  p_allowed_source_cidrs jsonb DEFAULT NULL,
  p_status text DEFAULT 'ACTIVE'
)
RETURNS TABLE (
  id bigint,
  cluster_key text,
  name text,
  status varchar,
  allowed_source_cidrs jsonb,
  shared_storage_uri text,
  worker_mount_path text
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_name text := COALESCE(NULLIF(btrim(p_name), ''), p_cluster_key);
BEGIN
  INSERT INTO wf.cluster AS c (
    cluster_key, name, shared_storage_uri, worker_mount_path, status, allowed_source_cidrs
  )
  VALUES (
    p_cluster_key, v_name, p_shared_storage_uri, p_worker_mount_path, COALESCE(p_status, 'ACTIVE'), p_allowed_source_cidrs
  )
  ON CONFLICT (cluster_key) DO UPDATE SET
    name = EXCLUDED.name,
    shared_storage_uri = COALESCE(EXCLUDED.shared_storage_uri, c.shared_storage_uri),
    worker_mount_path = COALESCE(EXCLUDED.worker_mount_path, c.worker_mount_path),
    allowed_source_cidrs = COALESCE(EXCLUDED.allowed_source_cidrs, c.allowed_source_cidrs),
    status = COALESCE(EXCLUDED.status, c.status),
    updated_at_utc = now() AT TIME ZONE 'utc';

  RETURN QUERY
  SELECT c.id, c.cluster_key, c.name, c.status, c.allowed_source_cidrs, c.shared_storage_uri, c.worker_mount_path
  FROM wf.cluster c
  WHERE c.cluster_key = p_cluster_key;
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_clusters()
RETURNS TABLE (
  id bigint,
  cluster_key text,
  name text,
  status varchar,
  allowed_source_cidrs jsonb,
  shared_storage_uri text,
  worker_mount_path text,
  arc_resource_id text,
  created_at_utc timestamptz,
  updated_at_utc timestamptz
)
LANGUAGE sql
AS $$
  SELECT
    c.id, c.cluster_key, c.name, c.status, c.allowed_source_cidrs,
    c.shared_storage_uri, c.worker_mount_path, c.arc_resource_id,
    c.created_at_utc, c.updated_at_utc
  FROM wf.cluster c
  ORDER BY c.cluster_key;
$$;

CREATE OR REPLACE FUNCTION portal.sp_upsert_worker_enrollment(
  p_cluster_key text,
  p_public_ip text,
  p_external_worker_key text
)
RETURNS TABLE (
  id bigint,
  cluster_key text,
  public_ip text,
  external_worker_key text,
  status varchar,
  enrolled_worker_id bigint,
  enrolled_at_utc timestamptz,
  created_at_utc timestamptz
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_cluster_id bigint;
  v_host text;
  v_slash32 text;
  v_cidrs jsonb;
BEGIN
  SELECT c.id INTO v_cluster_id FROM wf.cluster c WHERE c.cluster_key = p_cluster_key;
  IF v_cluster_id IS NULL THEN
    RAISE EXCEPTION 'Unknown cluster_key; upsert cluster first' USING ERRCODE = 'P0001';
  END IF;

  INSERT INTO wf.worker_enrollment AS e (cluster_id, public_ip, external_worker_key, status)
  VALUES (v_cluster_id, btrim(p_public_ip), btrim(p_external_worker_key), 'PENDING')
  ON CONFLICT (cluster_id, external_worker_key) DO UPDATE SET
    public_ip = EXCLUDED.public_ip,
    status = CASE WHEN e.status = 'REVOKED' THEN 'PENDING' ELSE e.status END,
    updated_at_utc = now() AT TIME ZONE 'utc';

  v_host := split_part(btrim(p_public_ip), '/', 1);
  v_slash32 := v_host || '/32';
  SELECT c.allowed_source_cidrs INTO v_cidrs FROM wf.cluster c WHERE c.id = v_cluster_id;
  IF v_cidrs IS NULL OR v_cidrs = '[]'::jsonb THEN
    v_cidrs := jsonb_build_array(v_slash32);
  ELSIF NOT (v_cidrs ? v_slash32) THEN
    v_cidrs := v_cidrs || jsonb_build_array(v_slash32);
  END IF;
  UPDATE wf.cluster
  SET allowed_source_cidrs = v_cidrs, updated_at_utc = now() AT TIME ZONE 'utc'
  WHERE id = v_cluster_id;

  RETURN QUERY
  SELECT e.id, c.cluster_key, e.public_ip, e.external_worker_key, e.status,
         e.enrolled_worker_id, e.enrolled_at_utc, e.created_at_utc
  FROM wf.worker_enrollment e
  JOIN wf.cluster c ON c.id = e.cluster_id
  WHERE e.cluster_id = v_cluster_id AND e.external_worker_key = btrim(p_external_worker_key);
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_worker_enrollments(p_cluster_key text DEFAULT NULL)
RETURNS TABLE (
  id bigint,
  cluster_key text,
  public_ip text,
  external_worker_key text,
  status varchar,
  enrolled_worker_id bigint,
  enrolled_at_utc timestamptz,
  created_at_utc timestamptz
)
LANGUAGE sql
AS $$
  SELECT e.id, c.cluster_key, e.public_ip, e.external_worker_key, e.status,
         e.enrolled_worker_id, e.enrolled_at_utc, e.created_at_utc
  FROM wf.worker_enrollment e
  JOIN wf.cluster c ON c.id = e.cluster_id
  WHERE p_cluster_key IS NULL OR c.cluster_key = p_cluster_key
  ORDER BY c.cluster_key, e.external_worker_key;
$$;

CREATE OR REPLACE FUNCTION portal.sp_revoke_worker_enrollment(
  p_cluster_key text,
  p_external_worker_key text
)
RETURNS TABLE (
  id bigint,
  cluster_key text,
  external_worker_key text,
  status varchar
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_cluster_id bigint;
BEGIN
  SELECT c.id INTO v_cluster_id FROM wf.cluster c WHERE c.cluster_key = p_cluster_key;
  IF v_cluster_id IS NULL THEN
    RAISE EXCEPTION 'Unknown cluster_key' USING ERRCODE = 'P0001';
  END IF;

  UPDATE wf.worker_enrollment e
  SET status = 'REVOKED', updated_at_utc = now() AT TIME ZONE 'utc'
  WHERE e.cluster_id = v_cluster_id AND e.external_worker_key = p_external_worker_key;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Enrollment row not found' USING ERRCODE = 'P0001';
  END IF;

  RETURN QUERY
  SELECT e.id, c.cluster_key, e.external_worker_key, e.status
  FROM wf.worker_enrollment e
  JOIN wf.cluster c ON c.id = e.cluster_id
  WHERE e.cluster_id = v_cluster_id AND e.external_worker_key = p_external_worker_key;
END;
$$;
