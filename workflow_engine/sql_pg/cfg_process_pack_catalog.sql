/*
  Process-pack catalog for portal Study / Start-run UX (PostgreSQL).

  - Ensures cfg.assay_procedure exists (also declared in cfg_registry_tables.sql).
  - Portal list/get + operator catalog pickers for pipeline profiles and assay procedures.
  - Study process defaults (pipelineProfile / pipelineProcedure / researchMode) on cfg.study.

  Prerequisites:
  - cfg_schema.sql, cfg_registry_tables.sql (cfg.pipeline_profile, cfg.study)
  - cfg_repo_api.sql with assay_procedure kind wired (upsert/publish)

  Deploy:
    psql -v ON_ERROR_STOP=1 -f workflow_engine/sql_pg/cfg_process_pack_catalog.sql
  Or via deploy_azure.sh (listed after cfg_portal_api.sql).
  Then seed rows:
    python scripts/sync_cfg_profiles_and_action_catalog.py --backend postgres --skip-seed
*/

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'cfg') THEN
    RAISE EXCEPTION 'Prerequisite missing: cfg schema (cfg_schema.sql)';
  END IF;
  IF to_regclass('cfg.pipeline_profile') IS NULL THEN
    RAISE EXCEPTION 'Prerequisite missing: cfg.pipeline_profile (cfg_registry_tables.sql)';
  END IF;
END $$;

CREATE SCHEMA IF NOT EXISTS portal;

CREATE TABLE IF NOT EXISTS cfg.assay_procedure (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name text NOT NULL,
  version text NOT NULL DEFAULT '1',
  status varchar(32) NOT NULL DEFAULT 'draft',
  content_hash text NOT NULL,
  document_json jsonb NOT NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CONSTRAINT uq_cfg_assay_procedure_name_version UNIQUE (name, version),
  CONSTRAINT ck_cfg_assay_procedure_status CHECK (status IN ('draft', 'published', 'retired'))
);

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'portal' AND p.proname = 'sp_list_pipeline_profiles'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION portal.sp_list_pipeline_profiles(
  p_published_only boolean DEFAULT false
)
RETURNS TABLE(
  id bigint,
  name text,
  version text,
  status text,
  content_hash text,
  document_json jsonb,
  created_at_utc timestamptz,
  updated_at_utc timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    p.id,
    p.name,
    p.version,
    p.status::text,
    p.content_hash,
    p.document_json,
    p.created_at_utc,
    p.updated_at_utc
  FROM cfg.pipeline_profile p
  WHERE (NOT p_published_only OR p.status = 'published')
  ORDER BY p.name, p.version;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'portal' AND p.proname = 'sp_get_pipeline_profile'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION portal.sp_get_pipeline_profile(
  p_name text,
  p_version text DEFAULT NULL
)
RETURNS TABLE(
  id bigint,
  name text,
  version text,
  status text,
  content_hash text,
  document_json jsonb,
  created_at_utc timestamptz,
  updated_at_utc timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    p.id,
    p.name,
    p.version,
    p.status::text,
    p.content_hash,
    p.document_json,
    p.created_at_utc,
    p.updated_at_utc
  FROM cfg.pipeline_profile p
  WHERE p.name = p_name
    AND (p_version IS NULL OR p.version = p_version)
  ORDER BY p.id DESC
  LIMIT 1;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'portal' AND p.proname = 'sp_list_pipeline_profile_catalog'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION portal.sp_list_pipeline_profile_catalog(
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
  research_modes jsonb
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
    p.document_json->'catalog'->'researchModes'
  FROM cfg.pipeline_profile p
  WHERE p.status = 'published'
    AND p.document_json->'catalog'->>'lifecycle' = 'active'
    AND (
      p.document_json->'catalog'->>'visibility' = 'operator'
      OR (p_include_advanced AND p.document_json->'catalog'->>'visibility' = 'advanced')
    )
  ORDER BY
    CASE p.document_json->'catalog'->>'family'
      WHEN 'samd' THEN 0
      WHEN 'staged' THEN 1
      ELSE 2
    END,
    p.name,
    p.version;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'portal' AND p.proname = 'sp_list_assay_procedures'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION portal.sp_list_assay_procedures(
  p_published_only boolean DEFAULT false
)
RETURNS TABLE(
  id bigint,
  name text,
  version text,
  status text,
  content_hash text,
  document_json jsonb,
  created_at_utc timestamptz,
  updated_at_utc timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    p.id,
    p.name,
    p.version,
    p.status::text,
    p.content_hash,
    p.document_json,
    p.created_at_utc,
    p.updated_at_utc
  FROM cfg.assay_procedure p
  WHERE (NOT p_published_only OR p.status = 'published')
  ORDER BY p.name, p.version;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'portal' AND p.proname = 'sp_get_assay_procedure'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION portal.sp_get_assay_procedure(
  p_name text,
  p_version text DEFAULT NULL
)
RETURNS TABLE(
  id bigint,
  name text,
  version text,
  status text,
  content_hash text,
  document_json jsonb,
  created_at_utc timestamptz,
  updated_at_utc timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    p.id,
    p.name,
    p.version,
    p.status::text,
    p.content_hash,
    p.document_json,
    p.created_at_utc,
    p.updated_at_utc
  FROM cfg.assay_procedure p
  WHERE p.name = p_name
    AND (p_version IS NULL OR p.version = p_version)
  ORDER BY p.id DESC
  LIMIT 1;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'portal' AND p.proname = 'sp_list_assay_procedure_catalog'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

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
    s.document_json->>'pipelineProfile',
    s.document_json->>'pipelineProcedure',
    s.document_json->>'researchMode',
    pp.document_json->'catalog'->>'title',
    ap.document_json->'catalog'->>'title'
  FROM cfg.study s
  LEFT JOIN LATERAL (
    SELECT document_json
    FROM cfg.pipeline_profile
    WHERE name = s.document_json->>'pipelineProfile'
      AND status IN ('published', 'retired')
    ORDER BY id DESC
    LIMIT 1
  ) pp ON TRUE
  LEFT JOIN LATERAL (
    SELECT document_json
    FROM cfg.assay_procedure
    WHERE name = s.document_json->>'pipelineProcedure'
      AND status IN ('published', 'retired')
    ORDER BY id DESC
    LIMIT 1
  ) ap ON TRUE
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
  pipeline_profile_title text,
  pipeline_procedure_title text
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_doc jsonb;
BEGIN
  SELECT document_json INTO v_doc FROM cfg.study WHERE id = p_study_row_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'cfg.study not found: %', p_study_row_id;
  END IF;
  v_doc := COALESCE(v_doc, '{}'::jsonb);

  IF p_pipeline_profile IS NOT NULL AND btrim(p_pipeline_profile) <> '' THEN
    IF NOT EXISTS (
      SELECT 1 FROM cfg.pipeline_profile p
      WHERE p.name = p_pipeline_profile
        AND p.status = 'published'
        AND p.document_json->'catalog'->>'lifecycle' = 'active'
        AND (
          p.document_json->'catalog'->>'visibility' = 'operator'
          OR (p_allow_advanced AND p.document_json->'catalog'->>'visibility' = 'advanced')
        )
    ) THEN
      RAISE EXCEPTION 'pipeline profile not in operator/advanced catalog: %', p_pipeline_profile;
    END IF;
  END IF;

  IF p_pipeline_procedure IS NOT NULL AND btrim(p_pipeline_procedure) <> '' THEN
    IF NOT EXISTS (
      SELECT 1 FROM cfg.assay_procedure p
      WHERE p.name = p_pipeline_procedure
        AND p.status = 'published'
        AND p.document_json->'catalog'->>'lifecycle' = 'active'
        AND (
          p.document_json->'catalog'->>'visibility' = 'operator'
          OR (p_allow_advanced AND p.document_json->'catalog'->>'visibility' = 'advanced')
        )
    ) THEN
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
      updated_at_utc = (now() AT TIME ZONE 'utc')
  WHERE id = p_study_row_id;

  RETURN QUERY SELECT * FROM portal.sp_get_study_process_defaults(p_study_row_id);
END;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'portal' AND p.proname IN (
      'sp_upsert_pipeline_profile', 'sp_publish_pipeline_profile',
      'sp_upsert_assay_procedure', 'sp_publish_assay_procedure'
    )
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION portal.sp_upsert_pipeline_profile(
  p_name text,
  p_version text,
  p_status text,
  p_document jsonb
)
RETURNS TABLE(id bigint)
LANGUAGE sql AS $$
  SELECT * FROM cfg.cfg_repo_upsert('pipeline_profile', p_name, p_version, p_status, p_document);
$$;

CREATE OR REPLACE FUNCTION portal.sp_publish_pipeline_profile(
  p_name text,
  p_version text
)
RETURNS TABLE(id bigint)
LANGUAGE sql AS $$
  SELECT * FROM cfg.cfg_repo_publish('pipeline_profile', p_name, p_version);
$$;

CREATE OR REPLACE FUNCTION portal.sp_upsert_assay_procedure(
  p_name text,
  p_version text,
  p_status text,
  p_document jsonb
)
RETURNS TABLE(id bigint)
LANGUAGE sql AS $$
  SELECT * FROM cfg.cfg_repo_upsert('assay_procedure', p_name, p_version, p_status, p_document);
$$;

CREATE OR REPLACE FUNCTION portal.sp_publish_assay_procedure(
  p_name text,
  p_version text
)
RETURNS TABLE(id bigint)
LANGUAGE sql AS $$
  SELECT * FROM cfg.cfg_repo_publish('assay_procedure', p_name, p_version);
$$;
