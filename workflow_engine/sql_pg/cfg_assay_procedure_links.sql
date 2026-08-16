/*
  Explicit cfg relationships for assay procedures (PostgreSQL).

  Adds:
  - cfg.assay_procedure → default profile + SamplePrep/lifecycle DomainPrograms
  - cfg.study default profile/procedure FKs
  - cfg.study_instance_link.assay_procedure_id
  - views: cfg.v_assay_procedure, refreshed cfg.v_study_instance
  - cfg.cfg_repo_bind_assay_procedure
  - cfg.cfg_repo_link_study_instance gains p_assay_procedure_id

  Prerequisites:
  - cfg_process_pack_catalog.sql / cfg_registry_tables.sql
  - cfg_wf_relationships.sql
  - cfg_repo_api.sql
*/

DO $$
BEGIN
  IF to_regclass('cfg.assay_procedure') IS NULL THEN
    RAISE EXCEPTION 'Prerequisite missing: cfg.assay_procedure';
  END IF;
  IF to_regclass('cfg.study_instance_link') IS NULL THEN
    RAISE EXCEPTION 'Prerequisite missing: cfg.study_instance_link';
  END IF;
END $$;

ALTER TABLE cfg.assay_procedure
  ADD COLUMN IF NOT EXISTS primary_analyte text NULL;
ALTER TABLE cfg.assay_procedure
  ADD COLUMN IF NOT EXISTS default_pipeline_profile_id bigint NULL
    REFERENCES cfg.pipeline_profile(id);
ALTER TABLE cfg.assay_procedure
  ADD COLUMN IF NOT EXISTS sample_prep_program_id bigint NULL
    REFERENCES cfg.domain_program(id);
ALTER TABLE cfg.assay_procedure
  ADD COLUMN IF NOT EXISTS lifecycle_program_id bigint NULL
    REFERENCES cfg.domain_program(id);

CREATE INDEX IF NOT EXISTS ix_cfg_ap_analyte ON cfg.assay_procedure (primary_analyte);
CREATE INDEX IF NOT EXISTS ix_cfg_ap_default_profile ON cfg.assay_procedure (default_pipeline_profile_id);

ALTER TABLE cfg.study
  ADD COLUMN IF NOT EXISTS default_pipeline_profile_id bigint NULL
    REFERENCES cfg.pipeline_profile(id);
ALTER TABLE cfg.study
  ADD COLUMN IF NOT EXISTS default_assay_procedure_id bigint NULL
    REFERENCES cfg.assay_procedure(id);

ALTER TABLE cfg.study_instance_link
  ADD COLUMN IF NOT EXISTS assay_procedure_id bigint NULL
    REFERENCES cfg.assay_procedure(id);

CREATE INDEX IF NOT EXISTS ix_cfg_sil_assay ON cfg.study_instance_link (assay_procedure_id);

DROP VIEW IF EXISTS cfg.v_assay_procedure;
CREATE OR REPLACE VIEW cfg.v_assay_procedure AS
SELECT
  ap.id AS assay_procedure_id,
  ap.name AS procedure_name,
  ap.version AS procedure_version,
  ap.status,
  ap.primary_analyte,
  ap.default_pipeline_profile_id,
  pp.name AS default_pipeline_profile_name,
  ap.sample_prep_program_id,
  sp.name AS sample_prep_program_name,
  ap.lifecycle_program_id,
  lp.name AS lifecycle_program_name,
  ap.document_json->'catalog'->>'title' AS catalog_title,
  ap.document_json->'catalog'->>'visibility' AS catalog_visibility,
  ap.document_json->'catalog'->>'lifecycle' AS catalog_lifecycle
FROM cfg.assay_procedure ap
LEFT JOIN cfg.pipeline_profile pp ON pp.id = ap.default_pipeline_profile_id
LEFT JOIN cfg.domain_program sp ON sp.id = ap.sample_prep_program_id
LEFT JOIN cfg.domain_program lp ON lp.id = ap.lifecycle_program_id;

DROP VIEW IF EXISTS cfg.v_study_instance;
CREATE OR REPLACE VIEW cfg.v_study_instance AS
SELECT
  l.id AS link_id,
  l.study_row_id,
  s.name AS study_name,
  s.study_id,
  l.workflow_instance_id,
  i.status AS instance_status,
  i.workflow_version_id,
  l.domain_program_id,
  p.name AS program_name,
  l.pipeline_profile_id,
  pr.name AS profile_name,
  l.assay_procedure_id,
  ap.name AS assay_procedure_name,
  l.site_id,
  l.created_at_utc
FROM cfg.study_instance_link l
INNER JOIN cfg.study s ON s.id = l.study_row_id
INNER JOIN wf.workflow_instance i ON i.id = l.workflow_instance_id
LEFT JOIN cfg.domain_program p ON p.id = l.domain_program_id
LEFT JOIN cfg.pipeline_profile pr ON pr.id = l.pipeline_profile_id
LEFT JOIN cfg.assay_procedure ap ON ap.id = l.assay_procedure_id;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'cfg' AND p.proname = 'cfg_repo_bind_assay_procedure'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION cfg.cfg_repo_bind_assay_procedure(
  p_procedure_name text,
  p_procedure_version text DEFAULT '1',
  p_primary_analyte text DEFAULT NULL,
  p_default_pipeline_profile_name text DEFAULT NULL,
  p_sample_prep_program_name text DEFAULT NULL,
  p_lifecycle_program_name text DEFAULT NULL
)
RETURNS TABLE(
  id bigint,
  name text,
  primary_analyte text,
  default_pipeline_profile_id bigint,
  sample_prep_program_id bigint,
  lifecycle_program_id bigint
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_ap_id bigint;
  v_profile_id bigint;
  v_sp_id bigint;
  v_lc_id bigint;
BEGIN
  SELECT ap.id INTO v_ap_id
  FROM cfg.assay_procedure ap
  WHERE ap.name = p_procedure_name
    AND (p_procedure_version IS NULL OR ap.version = p_procedure_version)
  ORDER BY ap.id DESC
  LIMIT 1;
  IF v_ap_id IS NULL THEN
    RAISE EXCEPTION 'cfg.assay_procedure not found: %', p_procedure_name;
  END IF;

  IF p_default_pipeline_profile_name IS NOT NULL AND btrim(p_default_pipeline_profile_name) <> '' THEN
    SELECT pp.id INTO v_profile_id
    FROM cfg.pipeline_profile pp
    WHERE pp.name = p_default_pipeline_profile_name
    ORDER BY CASE pp.status WHEN 'published' THEN 0 WHEN 'retired' THEN 1 ELSE 2 END, pp.id DESC
    LIMIT 1;
  END IF;

  IF p_sample_prep_program_name IS NOT NULL AND btrim(p_sample_prep_program_name) <> '' THEN
    SELECT dp.id INTO v_sp_id
    FROM cfg.domain_program dp
    WHERE dp.name = p_sample_prep_program_name
    ORDER BY CASE dp.status WHEN 'published' THEN 0 ELSE 1 END, dp.id DESC
    LIMIT 1;
  END IF;

  IF p_lifecycle_program_name IS NOT NULL AND btrim(p_lifecycle_program_name) <> '' THEN
    SELECT dp.id INTO v_lc_id
    FROM cfg.domain_program dp
    WHERE dp.name = p_lifecycle_program_name
    ORDER BY CASE dp.status WHEN 'published' THEN 0 ELSE 1 END, dp.id DESC
    LIMIT 1;
  END IF;

  UPDATE cfg.assay_procedure ap
  SET primary_analyte = COALESCE(p_primary_analyte, ap.primary_analyte),
      default_pipeline_profile_id = COALESCE(v_profile_id, ap.default_pipeline_profile_id),
      sample_prep_program_id = COALESCE(v_sp_id, ap.sample_prep_program_id),
      lifecycle_program_id = COALESCE(v_lc_id, ap.lifecycle_program_id),
      updated_at_utc = (now() AT TIME ZONE 'utc')
  WHERE ap.id = v_ap_id;

  RETURN QUERY
  SELECT ap.id, ap.name, ap.primary_analyte, ap.default_pipeline_profile_id,
         ap.sample_prep_program_id, ap.lifecycle_program_id
  FROM cfg.assay_procedure ap
  WHERE ap.id = v_ap_id;
END;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'cfg' AND p.proname = 'cfg_repo_link_study_instance'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION cfg.cfg_repo_link_study_instance(
  p_study_row_id bigint,
  p_workflow_instance_id bigint,
  p_domain_program_id bigint DEFAULT NULL,
  p_pipeline_profile_id bigint DEFAULT NULL,
  p_site_id bigint DEFAULT NULL,
  p_storage_profile_id bigint DEFAULT NULL,
  p_assay_procedure_id bigint DEFAULT NULL
)
RETURNS TABLE(id bigint)
LANGUAGE plpgsql
AS $$
DECLARE v_id bigint;
BEGIN
  INSERT INTO cfg.study_instance_link (
    study_row_id, workflow_instance_id, domain_program_id, pipeline_profile_id,
    site_id, storage_profile_id, assay_procedure_id
  ) VALUES (
    p_study_row_id, p_workflow_instance_id, p_domain_program_id, p_pipeline_profile_id,
    p_site_id, p_storage_profile_id, p_assay_procedure_id
  )
  ON CONFLICT (workflow_instance_id) DO UPDATE SET
    study_row_id = EXCLUDED.study_row_id,
    domain_program_id = COALESCE(EXCLUDED.domain_program_id, cfg.study_instance_link.domain_program_id),
    pipeline_profile_id = COALESCE(EXCLUDED.pipeline_profile_id, cfg.study_instance_link.pipeline_profile_id),
    site_id = COALESCE(EXCLUDED.site_id, cfg.study_instance_link.site_id),
    storage_profile_id = COALESCE(EXCLUDED.storage_profile_id, cfg.study_instance_link.storage_profile_id),
    assay_procedure_id = COALESCE(EXCLUDED.assay_procedure_id, cfg.study_instance_link.assay_procedure_id)
  RETURNING cfg.study_instance_link.id INTO v_id;
  id := v_id;
  RETURN NEXT;
END;
$$;

-- Catalog filter with typed primary_analyte + FK columns
DROP FUNCTION IF EXISTS portal.sp_list_assay_procedure_catalog(text, boolean);
CREATE OR REPLACE FUNCTION portal.sp_list_assay_procedure_catalog(
  p_analyte text DEFAULT NULL,
  p_include_advanced boolean DEFAULT false
)
RETURNS TABLE(
  id bigint,
  name text,
  version text,
  status text,
  title text,
  summary text,
  visibility text,
  lifecycle text,
  family text,
  replaced_by text,
  primary_analyte text,
  default_pipeline_profile_id bigint,
  sample_prep_program_id bigint,
  lifecycle_program_id bigint,
  analyte_expectation jsonb,
  default_pipeline_profile text,
  default_research_mode text
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    p.id,
    p.name,
    p.version,
    p.status::text,
    p.document_json->'catalog'->>'title',
    p.document_json->'catalog'->>'summary',
    p.document_json->'catalog'->>'visibility',
    p.document_json->'catalog'->>'lifecycle',
    p.document_json->'catalog'->>'family',
    p.document_json->'catalog'->>'replacedBy',
    p.primary_analyte,
    p.default_pipeline_profile_id,
    p.sample_prep_program_id,
    p.lifecycle_program_id,
    p.document_json->'analyteExpectation',
    p.document_json->>'pipelineProfile',
    p.document_json->>'researchMode'
  FROM cfg.assay_procedure p
  WHERE p.status = 'published'
    AND p.document_json->'catalog'->>'lifecycle' = 'active'
    AND (
      p.document_json->'catalog'->>'visibility' = 'operator'
      OR (p_include_advanced AND p.document_json->'catalog'->>'visibility' = 'advanced')
    )
    AND (
      p_analyte IS NULL OR btrim(p_analyte) = ''
      OR lower(COALESCE(p.primary_analyte, '')) = lower(btrim(p_analyte))
      OR lower(p.document_json->>'analyteExpectation') = lower(btrim(p_analyte))
      OR EXISTS (
        SELECT 1
        FROM jsonb_array_elements_text(
          CASE
            WHEN jsonb_typeof(p.document_json->'analyteExpectation') = 'array'
              THEN p.document_json->'analyteExpectation'
            ELSE '[]'::jsonb
          END
        ) AS a(val)
        WHERE lower(a.val) = lower(btrim(p_analyte))
      )
    )
  ORDER BY p.name, p.version;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'portal' AND p.proname = 'sp_get_study_process_defaults'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION portal.sp_get_study_process_defaults(p_study_row_id bigint)
RETURNS TABLE(
  study_row_id bigint,
  study_name text,
  study_version text,
  pipeline_profile text,
  pipeline_procedure text,
  research_mode text,
  default_pipeline_profile_id bigint,
  default_assay_procedure_id bigint,
  pipeline_profile_title text,
  pipeline_procedure_title text
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    s.id,
    s.name,
    s.version,
    COALESCE(pp.name, s.document_json->>'pipelineProfile'),
    COALESCE(ap.name, s.document_json->>'pipelineProcedure'),
    s.document_json->>'researchMode',
    s.default_pipeline_profile_id,
    s.default_assay_procedure_id,
    pp.document_json->'catalog'->>'title',
    ap.document_json->'catalog'->>'title'
  FROM cfg.study s
  LEFT JOIN cfg.pipeline_profile pp ON pp.id = s.default_pipeline_profile_id
  LEFT JOIN cfg.assay_procedure ap ON ap.id = s.default_assay_procedure_id
  WHERE s.id = p_study_row_id;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'portal' AND p.proname = 'sp_set_study_process_defaults'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION portal.sp_set_study_process_defaults(
  p_study_row_id bigint,
  p_pipeline_profile text DEFAULT NULL,
  p_pipeline_procedure text DEFAULT NULL,
  p_research_mode text DEFAULT NULL,
  p_allow_advanced boolean DEFAULT false
)
RETURNS TABLE(
  study_row_id bigint,
  study_name text,
  study_version text,
  pipeline_profile text,
  pipeline_procedure text,
  research_mode text,
  default_pipeline_profile_id bigint,
  default_assay_procedure_id bigint,
  pipeline_profile_title text,
  pipeline_procedure_title text
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_doc jsonb;
  v_profile_id bigint;
  v_assay_id bigint;
BEGIN
  SELECT document_json INTO v_doc FROM cfg.study WHERE id = p_study_row_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'cfg.study not found: %', p_study_row_id;
  END IF;
  v_doc := COALESCE(v_doc, '{}'::jsonb);

  IF p_pipeline_profile IS NOT NULL AND btrim(p_pipeline_profile) <> '' THEN
    SELECT p.id INTO v_profile_id
    FROM cfg.pipeline_profile p
    WHERE p.name = p_pipeline_profile
      AND p.status = 'published'
      AND p.document_json->'catalog'->>'lifecycle' = 'active'
      AND (
        p.document_json->'catalog'->>'visibility' = 'operator'
        OR (p_allow_advanced AND p.document_json->'catalog'->>'visibility' = 'advanced')
      )
    ORDER BY p.id DESC
    LIMIT 1;
    IF v_profile_id IS NULL THEN
      RAISE EXCEPTION 'pipeline profile not in operator/advanced catalog: %', p_pipeline_profile;
    END IF;
  END IF;

  IF p_pipeline_procedure IS NOT NULL AND btrim(p_pipeline_procedure) <> '' THEN
    SELECT p.id INTO v_assay_id
    FROM cfg.assay_procedure p
    WHERE p.name = p_pipeline_procedure
      AND p.status = 'published'
      AND p.document_json->'catalog'->>'lifecycle' = 'active'
      AND (
        p.document_json->'catalog'->>'visibility' = 'operator'
        OR (p_allow_advanced AND p.document_json->'catalog'->>'visibility' = 'advanced')
      )
    ORDER BY p.id DESC
    LIMIT 1;
    IF v_assay_id IS NULL THEN
      RAISE EXCEPTION 'assay procedure not in operator/advanced catalog: %', p_pipeline_procedure;
    END IF;
  END IF;

  IF p_pipeline_profile IS NOT NULL THEN
    IF btrim(p_pipeline_profile) = '' THEN
      v_doc := v_doc - 'pipelineProfile';
    ELSE
      v_doc := jsonb_set(v_doc, '{pipelineProfile}', to_jsonb(p_pipeline_profile), true);
    END IF;
  END IF;
  IF p_pipeline_procedure IS NOT NULL THEN
    IF btrim(p_pipeline_procedure) = '' THEN
      v_doc := v_doc - 'pipelineProcedure';
    ELSE
      v_doc := jsonb_set(v_doc, '{pipelineProcedure}', to_jsonb(p_pipeline_procedure), true);
    END IF;
  END IF;
  IF p_research_mode IS NOT NULL THEN
    IF btrim(p_research_mode) = '' THEN
      v_doc := v_doc - 'researchMode';
    ELSE
      v_doc := jsonb_set(v_doc, '{researchMode}', to_jsonb(p_research_mode), true);
    END IF;
  END IF;

  UPDATE cfg.study
  SET document_json = v_doc,
      content_hash = md5(v_doc::text),
      default_pipeline_profile_id = CASE
        WHEN p_pipeline_profile IS NULL THEN default_pipeline_profile_id
        WHEN btrim(p_pipeline_profile) = '' THEN NULL
        ELSE v_profile_id
      END,
      default_assay_procedure_id = CASE
        WHEN p_pipeline_procedure IS NULL THEN default_assay_procedure_id
        WHEN btrim(p_pipeline_procedure) = '' THEN NULL
        ELSE v_assay_id
      END,
      updated_at_utc = (now() AT TIME ZONE 'utc')
  WHERE id = p_study_row_id;

  RETURN QUERY SELECT * FROM portal.sp_get_study_process_defaults(p_study_row_id);
END;
$$;
