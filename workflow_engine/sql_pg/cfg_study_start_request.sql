/*
  cfg.study_start_request + portal start-queue API (PostgreSQL twin).
  Deploy after portal_study_ops_api.sql.
*/

CREATE SCHEMA IF NOT EXISTS portal;

CREATE TABLE IF NOT EXISTS cfg.study_start_request (
  id                     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  study_row_id           bigint NOT NULL REFERENCES cfg.study(id),
  stage                  varchar(32) NOT NULL,
  workflow_version_id    bigint NOT NULL,
  pipeline_profile_id    bigint NULL,
  assay_procedure_id     bigint NULL,
  site_id                bigint NULL,
  storage_profile_id     bigint NULL,
  request_json           jsonb NOT NULL DEFAULT '{}'::jsonb,
  status                 varchar(32) NOT NULL DEFAULT 'queued',
  error_message          text NULL,
  workflow_instance_id   bigint NULL,
  claimed_by             text NULL,
  claimed_at_utc         timestamptz NULL,
  lease_expires_at_utc   timestamptz NULL,
  created_by             text NULL,
  created_at_utc         timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc         timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  CONSTRAINT ck_ssr_stage CHECK (stage IN ('sample_prep', 'study_validation')),
  CONSTRAINT ck_ssr_status CHECK (status IN ('draft', 'queued', 'running', 'succeeded', 'failed'))
);

CREATE INDEX IF NOT EXISTS ix_ssr_status_lease
  ON cfg.study_start_request(status, lease_expires_at_utc, id);
CREATE INDEX IF NOT EXISTS ix_ssr_study
  ON cfg.study_start_request(study_row_id);

CREATE OR REPLACE FUNCTION portal.fn_study_start_stage(p_workflow_name text)
RETURNS varchar(32)
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE
    WHEN lower(coalesce(p_workflow_name, '')) LIKE '%sample%prep%'
      OR lower(coalesce(p_workflow_name, '')) LIKE '%sample_prep%'
      THEN 'sample_prep'
    WHEN lower(coalesce(p_workflow_name, '')) LIKE '%study%validation%'
      OR lower(coalesce(p_workflow_name, '')) LIKE '%validation%lifecycle%'
      THEN 'study_validation'
    ELSE NULL
  END;
$$;

DROP FUNCTION IF EXISTS portal.sp_list_study_start_stages(bigint);
CREATE OR REPLACE FUNCTION portal.sp_list_study_start_stages(p_study_row_id bigint)
RETURNS TABLE (
  stage varchar(32),
  workflow_def_id bigint,
  workflow_name text,
  workflow_version_id bigint,
  version_major int,
  version_minor int,
  existing_count bigint
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
  IF p_study_row_id IS NULL OR p_study_row_id <= 0 THEN
    RAISE EXCEPTION 'study_row_id is required';
  END IF;

  RETURN QUERY
  SELECT
    st.stage,
    st.workflow_def_id,
    st.workflow_name,
    st.workflow_version_id,
    st.version_major,
    st.version_minor,
    (
      SELECT count(*)
      FROM cfg.study_instance_link l
      JOIN wf.workflow_instance i ON i.id = l.workflow_instance_id
      JOIN wf.workflow_version v2 ON v2.id = i.workflow_version_id
      JOIN wf.workflow_def d2 ON d2.id = v2.workflow_def_id
      WHERE l.study_row_id = p_study_row_id
        AND portal.fn_study_start_stage(d2.name) = st.stage
    ) AS existing_count
  FROM (
    SELECT
      portal.fn_study_start_stage(d.name) AS stage,
      d.id AS workflow_def_id,
      d.name AS workflow_name,
      v.id AS workflow_version_id,
      v.version_major,
      v.version_minor,
      row_number() OVER (
        PARTITION BY portal.fn_study_start_stage(d.name)
        ORDER BY v.is_active DESC, v.version_major DESC, v.version_minor DESC, v.id DESC
      ) AS rn
    FROM wf.workflow_def d
    JOIN wf.workflow_version v ON v.workflow_def_id = d.id
    WHERE v.is_active
      AND v.root_node_id IS NOT NULL
      AND portal.fn_study_start_stage(d.name) IS NOT NULL
  ) st
  WHERE st.rn = 1
  ORDER BY CASE st.stage WHEN 'sample_prep' THEN 0 ELSE 1 END;
END;
$$;

DROP FUNCTION IF EXISTS portal.sp_preview_study_start(bigint, text, bigint, text, text);
CREATE OR REPLACE FUNCTION portal.sp_preview_study_start(
  p_study_row_id bigint,
  p_stage text,
  p_workflow_version_id bigint DEFAULT NULL,
  p_pipeline_profile text DEFAULT NULL,
  p_pipeline_procedure text DEFAULT NULL
)
RETURNS TABLE (
  study_row_id bigint,
  study_name text,
  stage varchar(32),
  workflow_def_id bigint,
  workflow_name text,
  workflow_version_id bigint,
  version_label text,
  pipeline_profile text,
  pipeline_profile_id bigint,
  pipeline_procedure text,
  assay_procedure_id bigint,
  site_id bigint,
  storage_profile_id bigint,
  research_mode text,
  primary_analyte text,
  project_path text,
  storage_caption text,
  reference_caption text,
  cohort_caption text,
  guardrails_caption text,
  guardrails_pinned boolean,
  cohort_json jsonb,
  request_json jsonb,
  existing_kind_count bigint,
  eligible boolean
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_name text;
  v_doc jsonb;
  v_ver bigint := p_workflow_version_id;
  v_wf text;
  v_def bigint;
  v_major int;
  v_minor int;
  v_profile text := nullif(btrim(p_pipeline_profile), '');
  v_procedure text := nullif(btrim(p_pipeline_procedure), '');
  v_profile_id bigint;
  v_assay_id bigint;
  v_site bigint;
  v_research text;
  v_analyte text;
  v_project text;
  v_overlay jsonb;
  v_pinned boolean;
  v_cohort jsonb;
  v_cohort_caption text;
  v_storage_caption text;
  v_guard text;
  v_existing bigint;
  v_request jsonb;
  v_sample_count bigint;
BEGIN
  IF p_study_row_id IS NULL OR p_study_row_id <= 0 THEN
    RAISE EXCEPTION 'study_row_id is required';
  END IF;
  IF p_stage NOT IN ('sample_prep', 'study_validation') THEN
    RAISE EXCEPTION 'stage must be sample_prep or study_validation';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM cfg.study s WHERE s.id = p_study_row_id AND s.status = 'published') THEN
    RAISE EXCEPTION 'cfg.study not found or not published';
  END IF;

  SELECT s.name, coalesce(s.document_json, '{}'::jsonb),
         s.default_pipeline_profile_id, s.default_assay_procedure_id
    INTO v_name, v_doc, v_profile_id, v_assay_id
  FROM cfg.study s WHERE s.id = p_study_row_id;

  IF v_ver IS NULL THEN
    SELECT v.id, d.name, d.id, v.version_major, v.version_minor
      INTO v_ver, v_wf, v_def, v_major, v_minor
    FROM wf.workflow_def d
    JOIN wf.workflow_version v ON v.workflow_def_id = d.id
    WHERE v.is_active AND v.root_node_id IS NOT NULL
      AND portal.fn_study_start_stage(d.name) = p_stage
    ORDER BY v.version_major DESC, v.version_minor DESC, v.id DESC
    LIMIT 1;
  ELSE
    SELECT d.name, d.id, v.version_major, v.version_minor
      INTO v_wf, v_def, v_major, v_minor
    FROM wf.workflow_version v
    JOIN wf.workflow_def d ON d.id = v.workflow_def_id
    WHERE v.id = v_ver;
    IF v_wf IS NULL THEN
      RAISE EXCEPTION 'workflow_version_id not found';
    END IF;
    IF portal.fn_study_start_stage(v_wf) <> p_stage THEN
      RAISE EXCEPTION 'workflow_version_id does not match stage';
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM wf.workflow_version v
      WHERE v.id = v_ver AND v.is_active AND v.root_node_id IS NOT NULL
    ) THEN
      RAISE EXCEPTION 'workflow version is not published with a root node';
    END IF;
  END IF;

  IF v_ver IS NULL THEN
    RAISE EXCEPTION 'No published workflow version for this stage';
  END IF;

  IF v_profile IS NULL THEN
    SELECT coalesce(pp.name, v_doc->>'pipelineProfile') INTO v_profile
    FROM (SELECT 1) x
    LEFT JOIN cfg.pipeline_profile pp ON pp.id = v_profile_id;
  END IF;
  IF v_procedure IS NULL THEN
    SELECT coalesce(ap.name, v_doc->>'pipelineProcedure') INTO v_procedure
    FROM (SELECT 1) x
    LEFT JOIN cfg.assay_procedure ap ON ap.id = v_assay_id;
  END IF;

  IF v_profile IS NOT NULL AND v_profile_id IS NULL THEN
    SELECT p.id INTO v_profile_id
    FROM cfg.pipeline_profile p
    WHERE p.name = v_profile AND p.status = 'published'
    ORDER BY p.id DESC LIMIT 1;
  END IF;
  IF v_procedure IS NOT NULL AND v_assay_id IS NULL THEN
    SELECT p.id INTO v_assay_id
    FROM cfg.assay_procedure p
    WHERE p.name = v_procedure AND p.status = 'published'
    ORDER BY p.id DESC LIMIT 1;
  END IF;

  v_research := v_doc->>'researchMode';
  v_analyte := coalesce(v_doc #>> '{regulatory,primary_analyte}', v_doc->>'primaryAnalyte');
  SELECT s.id INTO v_site
  FROM cfg.site s
  WHERE s.status = 'published'
  ORDER BY CASE WHEN s.name = 'default' THEN 0 ELSE 1 END, s.id DESC
  LIMIT 1;

  SELECT concat(
           '/work/projects/',
           coalesce(nullif(btrim(s.study_id), ''), s.name),
           '/configs/project_',
           s.name,
           '.json'
         )
    INTO v_project
  FROM cfg.study s WHERE s.id = p_study_row_id;

  v_overlay := coalesce(v_doc->'actionConfig', '{}'::jsonb);
  v_pinned := v_overlay IS NOT NULL AND v_overlay <> '{}'::jsonb;
  v_guard := CASE
    WHEN v_pinned THEN 'Pinned study overlay (edit on Studies -> Guardrails)'
    ELSE 'Inherited from site / profile / procedure'
  END;

  SELECT coalesce(jsonb_agg(jsonb_build_object(
           'role', g.role, 'label', g.label, 'member_count',
           (SELECT count(*) FROM cfg.study_group_member m WHERE m.study_group_id = g.id)
         )), '[]'::jsonb)
    INTO v_cohort
  FROM cfg.study_group g
  WHERE g.study_row_id = p_study_row_id;

  SELECT count(DISTINCT g.id), count(m.id)
    INTO v_sample_count, v_existing
  FROM cfg.study_group g
  LEFT JOIN cfg.study_group_member m ON m.study_group_id = g.id
  WHERE g.study_row_id = p_study_row_id;
  v_cohort_caption := concat(coalesce(v_sample_count, 0), ' group(s), ', coalesce(v_existing, 0), ' sample(s)');

  SELECT concat(
           'FASTQ: ', coalesce(src.name, '(unset)'),
           ' | archive: ', coalesce(dst.name, '(unset)')
         )
    INTO v_storage_caption
  FROM cfg.study s
  LEFT JOIN cfg.storage_endpoint src
    ON src.id = nullif(s.document_json #>> '{storage,fastqSourceEndpointId}', '')::bigint
  LEFT JOIN cfg.storage_endpoint dst
    ON dst.id = nullif(s.document_json #>> '{storage,sampleDestinationEndpointId}', '')::bigint
  WHERE s.id = p_study_row_id;

  SELECT count(*) INTO v_existing
  FROM cfg.study_instance_link l
  JOIN wf.workflow_instance i ON i.id = l.workflow_instance_id
  JOIN wf.workflow_version v ON v.id = i.workflow_version_id
  JOIN wf.workflow_def d ON d.id = v.workflow_def_id
  WHERE l.study_row_id = p_study_row_id
    AND portal.fn_study_start_stage(d.name) = p_stage;

  v_request := jsonb_build_object(
    'study_row_id', p_study_row_id,
    'study_name', v_name,
    'stage', p_stage,
    'workflow_version_id', v_ver,
    'workflow_name', v_wf,
    'pipelineProfile', v_profile,
    'pipelineProcedure', v_procedure,
    'researchMode', v_research,
    'primaryAnalyte', v_analyte,
    'projectPath', v_project,
    'actionConfig', coalesce(v_overlay, '{}'::jsonb),
    'cohort', coalesce(v_cohort, '[]'::jsonb)
  );

  study_row_id := p_study_row_id;
  study_name := v_name;
  stage := p_stage;
  workflow_def_id := v_def;
  workflow_name := v_wf;
  workflow_version_id := v_ver;
  version_label := concat('v', v_major, '.', v_minor);
  pipeline_profile := v_profile;
  pipeline_profile_id := v_profile_id;
  pipeline_procedure := v_procedure;
  assay_procedure_id := v_assay_id;
  site_id := v_site;
  storage_profile_id := NULL;
  research_mode := v_research;
  primary_analyte := v_analyte;
  project_path := v_project;
  storage_caption := v_storage_caption;
  reference_caption := 'Site reference assets (materialized /work) - not edited here';
  cohort_caption := v_cohort_caption;
  guardrails_caption := v_guard;
  guardrails_pinned := v_pinned;
  cohort_json := coalesce(v_cohort, '[]'::jsonb);
  request_json := v_request;
  existing_kind_count := coalesce(v_existing, 0);
  eligible := true;
  RETURN NEXT;
END;
$$;

DROP FUNCTION IF EXISTS portal.sp_request_study_start(bigint, text, bigint, jsonb, bigint, bigint, bigint, bigint, text, int);
CREATE OR REPLACE FUNCTION portal.sp_request_study_start(
  p_study_row_id bigint,
  p_stage text,
  p_workflow_version_id bigint,
  p_request_json jsonb,
  p_pipeline_profile_id bigint DEFAULT NULL,
  p_assay_procedure_id bigint DEFAULT NULL,
  p_site_id bigint DEFAULT NULL,
  p_storage_profile_id bigint DEFAULT NULL,
  p_created_by text DEFAULT NULL,
  p_scope_id int DEFAULT NULL
)
RETURNS TABLE (
  request_id bigint,
  status varchar(32),
  study_row_id bigint,
  stage varchar(32),
  workflow_version_id bigint
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_id bigint;
  v_wf text;
BEGIN
  IF p_scope_id IS NOT NULL THEN
    RAISE EXCEPTION 'Contract quota UI is out of scope; pass NULL scope_id';
  END IF;
  IF p_study_row_id IS NULL OR p_study_row_id <= 0 THEN
    RAISE EXCEPTION 'study_row_id is required';
  END IF;
  IF p_stage NOT IN ('sample_prep', 'study_validation') THEN
    RAISE EXCEPTION 'stage must be sample_prep or study_validation';
  END IF;
  IF p_workflow_version_id IS NULL OR p_workflow_version_id <= 0 THEN
    RAISE EXCEPTION 'workflow_version_id is required';
  END IF;
  IF p_request_json IS NULL OR jsonb_typeof(p_request_json) <> 'object' THEN
    RAISE EXCEPTION 'request_json must be a JSON object';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM cfg.study s WHERE s.id = p_study_row_id AND s.status = 'published') THEN
    RAISE EXCEPTION 'cfg.study not found or not published';
  END IF;

  SELECT d.name INTO v_wf
  FROM wf.workflow_version v
  JOIN wf.workflow_def d ON d.id = v.workflow_def_id
  WHERE v.id = p_workflow_version_id AND v.is_active AND v.root_node_id IS NOT NULL;
  IF v_wf IS NULL THEN
    RAISE EXCEPTION 'workflow version is not published with a root node';
  END IF;
  IF portal.fn_study_start_stage(v_wf) <> p_stage THEN
    RAISE EXCEPTION 'workflow_version_id does not match stage';
  END IF;

  INSERT INTO cfg.study_start_request (
    study_row_id, stage, workflow_version_id,
    pipeline_profile_id, assay_procedure_id, site_id, storage_profile_id,
    request_json, status, created_by
  ) VALUES (
    p_study_row_id, p_stage, p_workflow_version_id,
    p_pipeline_profile_id, p_assay_procedure_id, p_site_id, p_storage_profile_id,
    p_request_json, 'queued', p_created_by
  )
  RETURNING id INTO v_id;

  RETURN QUERY
  SELECT r.id, r.status, r.study_row_id, r.stage, r.workflow_version_id
  FROM cfg.study_start_request r
  WHERE r.id = v_id;
END;
$$;

DROP FUNCTION IF EXISTS portal.sp_claim_study_start_request(text, int);
CREATE OR REPLACE FUNCTION portal.sp_claim_study_start_request(
  p_claimed_by text,
  p_lease_seconds int DEFAULT 600
)
RETURNS TABLE (
  request_id bigint,
  study_row_id bigint,
  stage varchar(32),
  workflow_version_id bigint,
  pipeline_profile_id bigint,
  assay_procedure_id bigint,
  site_id bigint,
  storage_profile_id bigint,
  request_json jsonb,
  status varchar(32),
  error_message text,
  workflow_instance_id bigint,
  claimed_by text,
  lease_expires_at_utc timestamptz
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_id bigint;
  v_now timestamptz := (now() AT TIME ZONE 'utc');
  v_lease int := coalesce(p_lease_seconds, 600);
BEGIN
  IF nullif(btrim(p_claimed_by), '') IS NULL THEN
    RAISE EXCEPTION 'claimed_by is required';
  END IF;
  IF v_lease < 30 THEN
    v_lease := 600;
  END IF;

  SELECT r.id INTO v_id
  FROM cfg.study_start_request r
  WHERE r.status = 'queued'
     OR (r.status = 'running' AND (r.lease_expires_at_utc IS NULL OR r.lease_expires_at_utc <= v_now))
  ORDER BY r.id
  FOR UPDATE SKIP LOCKED
  LIMIT 1;

  IF v_id IS NULL THEN
    RETURN;
  END IF;

  UPDATE cfg.study_start_request r
  SET status = 'running',
      claimed_by = p_claimed_by,
      claimed_at_utc = v_now,
      lease_expires_at_utc = v_now + make_interval(secs => v_lease),
      updated_at_utc = v_now
  WHERE r.id = v_id;

  RETURN QUERY
  SELECT
    r.id, r.study_row_id, r.stage, r.workflow_version_id,
    r.pipeline_profile_id, r.assay_procedure_id, r.site_id, r.storage_profile_id,
    r.request_json, r.status, r.error_message, r.workflow_instance_id,
    r.claimed_by, r.lease_expires_at_utc
  FROM cfg.study_start_request r
  WHERE r.id = v_id;
END;
$$;

DROP FUNCTION IF EXISTS portal.sp_get_study_start_request(bigint);
CREATE OR REPLACE FUNCTION portal.sp_get_study_start_request(p_request_id bigint)
RETURNS TABLE (
  request_id bigint,
  study_row_id bigint,
  stage varchar(32),
  workflow_version_id bigint,
  pipeline_profile_id bigint,
  assay_procedure_id bigint,
  site_id bigint,
  storage_profile_id bigint,
  request_json jsonb,
  status varchar(32),
  error_message text,
  workflow_instance_id bigint,
  claimed_by text,
  claimed_at_utc timestamptz,
  lease_expires_at_utc timestamptz,
  created_by text,
  created_at_utc timestamptz,
  updated_at_utc timestamptz
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
  IF p_request_id IS NULL OR p_request_id <= 0 THEN
    RAISE EXCEPTION 'request_id is required';
  END IF;
  RETURN QUERY
  SELECT
    r.id, r.study_row_id, r.stage, r.workflow_version_id,
    r.pipeline_profile_id, r.assay_procedure_id, r.site_id, r.storage_profile_id,
    r.request_json, r.status, r.error_message, r.workflow_instance_id,
    r.claimed_by, r.claimed_at_utc, r.lease_expires_at_utc,
    r.created_by, r.created_at_utc, r.updated_at_utc
  FROM cfg.study_start_request r
  WHERE r.id = p_request_id;
END;
$$;

DROP FUNCTION IF EXISTS portal.sp_complete_study_start_request(bigint, bigint);
CREATE OR REPLACE FUNCTION portal.sp_complete_study_start_request(
  p_request_id bigint,
  p_workflow_instance_id bigint
)
RETURNS TABLE (
  request_id bigint,
  study_row_id bigint,
  stage varchar(32),
  workflow_version_id bigint,
  pipeline_profile_id bigint,
  assay_procedure_id bigint,
  site_id bigint,
  storage_profile_id bigint,
  request_json jsonb,
  status varchar(32),
  error_message text,
  workflow_instance_id bigint,
  claimed_by text,
  claimed_at_utc timestamptz,
  lease_expires_at_utc timestamptz,
  created_by text,
  created_at_utc timestamptz,
  updated_at_utc timestamptz
)
LANGUAGE plpgsql
AS $$
BEGIN
  IF p_request_id IS NULL OR p_request_id <= 0 THEN
    RAISE EXCEPTION 'request_id is required';
  END IF;
  IF p_workflow_instance_id IS NULL OR p_workflow_instance_id <= 0 THEN
    RAISE EXCEPTION 'workflow_instance_id is required';
  END IF;

  UPDATE cfg.study_start_request
  SET status = 'succeeded',
      workflow_instance_id = p_workflow_instance_id,
      error_message = NULL,
      lease_expires_at_utc = NULL,
      updated_at_utc = (now() AT TIME ZONE 'utc')
  WHERE id = p_request_id AND status = 'running';

  IF NOT FOUND THEN
    RAISE EXCEPTION 'study_start_request not running';
  END IF;

  RETURN QUERY SELECT * FROM portal.sp_get_study_start_request(p_request_id);
END;
$$;

DROP FUNCTION IF EXISTS portal.sp_fail_study_start_request(bigint, text);
CREATE OR REPLACE FUNCTION portal.sp_fail_study_start_request(
  p_request_id bigint,
  p_error_message text
)
RETURNS TABLE (
  request_id bigint,
  study_row_id bigint,
  stage varchar(32),
  workflow_version_id bigint,
  pipeline_profile_id bigint,
  assay_procedure_id bigint,
  site_id bigint,
  storage_profile_id bigint,
  request_json jsonb,
  status varchar(32),
  error_message text,
  workflow_instance_id bigint,
  claimed_by text,
  claimed_at_utc timestamptz,
  lease_expires_at_utc timestamptz,
  created_by text,
  created_at_utc timestamptz,
  updated_at_utc timestamptz
)
LANGUAGE plpgsql
AS $$
BEGIN
  IF p_request_id IS NULL OR p_request_id <= 0 THEN
    RAISE EXCEPTION 'request_id is required';
  END IF;

  UPDATE cfg.study_start_request
  SET status = 'failed',
      error_message = left(coalesce(p_error_message, 'failed'), 4000),
      lease_expires_at_utc = NULL,
      updated_at_utc = (now() AT TIME ZONE 'utc')
  WHERE id = p_request_id AND status IN ('queued', 'running');

  IF NOT FOUND THEN
    RAISE EXCEPTION 'study_start_request not queued or running';
  END IF;

  RETURN QUERY SELECT * FROM portal.sp_get_study_start_request(p_request_id);
END;
$$;
