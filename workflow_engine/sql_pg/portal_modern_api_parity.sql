/*
  PostgreSQL parity for modern portal.sp_* procedures present in Azure SQL but not yet in
  sql_pg.  All routines are FUNCTION … RETURNS TABLE (idiomatic PG); callers treat them
  identically to the MSSQL PROCEDURE equivalents.

  Depends on:
    cfg_schema.sql / cfg_registry_tables.sql  – cfg.site, cfg.study, cfg.storage_profile,
                                                cfg.reference_asset, cfg.site_reference_asset,
                                                cfg.domain_program, cfg.study_instance_link,
                                                cfg.program_publish
    cfg_wf_relationships.sql                  – cfg.site_reference_asset, cfg.study_instance_link
    cfg_repo_api.sql                          – cfg.cfg_repo_upsert, cfg.cfg_repo_publish
    portal_clinical_schema.sql                – portal."Diseases", portal."Groups",
                                                portal."GroupSamples", portal."Samples",
                                                portal."Customers"
    00_schema.sql                             – wf.workflow_def, wf.workflow_version,
                                                wf.workflow_node, wf.workflow_instance,
                                                wf.node_execution, wf.task_lease, wf.worker
    cfg_portal_api.sql                        – portal.sp_list/get_domain_programs (for
                                                sp_publish_domain_program cross-dep)
    cfg_hyperparameter_search.sql             – cfg.hyperparam_search
*/

-- ──────────────────────────────────────────────────────────────────────────────
-- HELPER: drop any conflicting PROCEDURE or FUNCTION overload so CREATE OR
-- REPLACE works even when the argument list changed between deploys.
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION portal._drop_if_proc(p_schema text, p_name text)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = p_schema AND p.proname = p_name
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION  IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END;
$$;

-- ══════════════════════════════════════════════════════════════════════════════
-- SITE
-- ══════════════════════════════════════════════════════════════════════════════

SELECT portal._drop_if_proc('portal','sp_list_sites');
CREATE OR REPLACE FUNCTION portal.sp_list_sites(
  p_published_only boolean DEFAULT false
)
RETURNS TABLE(
  id bigint, name text, version text, status text, content_hash text
)
LANGUAGE sql STABLE AS $$
  SELECT s.id, s.name, s.version, s.status::text, s.content_hash
  FROM cfg.site s
  WHERE (NOT p_published_only OR s.status = 'published')
  ORDER BY s.name, s.version;
$$;

SELECT portal._drop_if_proc('portal','sp_get_site');
CREATE OR REPLACE FUNCTION portal.sp_get_site(
  p_name text,
  p_version text DEFAULT NULL
)
RETURNS TABLE(
  id bigint, name text, version text, status text, content_hash text,
  document_json jsonb
)
LANGUAGE sql STABLE AS $$
  SELECT s.id, s.name, s.version, s.status::text, s.content_hash, s.document_json
  FROM cfg.site s
  WHERE s.name = p_name AND (p_version IS NULL OR s.version = p_version)
  ORDER BY s.id DESC
  LIMIT 1;
$$;

SELECT portal._drop_if_proc('portal','sp_upsert_site');
CREATE OR REPLACE FUNCTION portal.sp_upsert_site(
  p_name text,
  p_version text,
  p_status text,
  p_document jsonb
)
RETURNS TABLE(id bigint)
LANGUAGE sql AS $$
  SELECT * FROM cfg.cfg_repo_upsert('site', p_name, p_version, p_status, p_document);
$$;

SELECT portal._drop_if_proc('portal','sp_publish_site');
CREATE OR REPLACE FUNCTION portal.sp_publish_site(
  p_name text,
  p_version text
)
RETURNS TABLE(id bigint)
LANGUAGE sql AS $$
  SELECT * FROM cfg.cfg_repo_publish('site', p_name, p_version);
$$;

-- ══════════════════════════════════════════════════════════════════════════════
-- STUDY
-- ══════════════════════════════════════════════════════════════════════════════

SELECT portal._drop_if_proc('portal','sp_list_studies');
CREATE OR REPLACE FUNCTION portal.sp_list_studies(
  p_published_only boolean DEFAULT false
)
RETURNS TABLE(
  id bigint, name text, version text, status text, content_hash text, study_id text
)
LANGUAGE sql STABLE AS $$
  SELECT s.id, s.name, s.version, s.status::text, s.content_hash, s.study_id
  FROM cfg.study s
  WHERE (NOT p_published_only OR s.status = 'published')
  ORDER BY s.name, s.version;
$$;

SELECT portal._drop_if_proc('portal','sp_get_study');
CREATE OR REPLACE FUNCTION portal.sp_get_study(
  p_name text,
  p_version text DEFAULT NULL
)
RETURNS TABLE(
  id bigint, name text, version text, status text, content_hash text,
  document_json jsonb, study_id text
)
LANGUAGE sql STABLE AS $$
  SELECT s.id, s.name, s.version, s.status::text, s.content_hash, s.document_json, s.study_id
  FROM cfg.study s
  WHERE s.name = p_name AND (p_version IS NULL OR s.version = p_version)
  ORDER BY s.id DESC
  LIMIT 1;
$$;

SELECT portal._drop_if_proc('portal','sp_upsert_study');
CREATE OR REPLACE FUNCTION portal.sp_upsert_study(
  p_name text,
  p_version text,
  p_status text,
  p_document jsonb,
  p_study_id text DEFAULT NULL
)
RETURNS TABLE(id bigint)
LANGUAGE sql AS $$
  SELECT * FROM cfg.cfg_repo_upsert(
    'study', p_name, p_version, p_status, p_document,
    NULL, NULL, NULL, NULL, p_study_id
  );
$$;

-- Resolve most-recent published version; returns study row + project data root path.
SELECT portal._drop_if_proc('portal','sp_resolve_study_archive');
CREATE OR REPLACE FUNCTION portal.sp_resolve_study_archive(
  p_study_name text,
  p_work_root text DEFAULT '/work'
)
RETURNS TABLE(
  id bigint, name text, version text, study_id text,
  document_json jsonb, archive_root text
)
LANGUAGE sql STABLE AS $$
  SELECT
    s.id, s.name, s.version, s.study_id, s.document_json,
    p_work_root || '/projects/' || COALESCE(s.study_id, s.name) AS archive_root
  FROM cfg.study s
  WHERE s.name = p_study_name AND s.status = 'published'
  ORDER BY s.id DESC
  LIMIT 1;
$$;

-- ══════════════════════════════════════════════════════════════════════════════
-- DISEASES / GROUPS / SAMPLES (clinical portal data)
-- ══════════════════════════════════════════════════════════════════════════════

SELECT portal._drop_if_proc('portal','sp_list_diseases');
CREATE OR REPLACE FUNCTION portal.sp_list_diseases()
RETURNS TABLE(
  id integer, name text, parent_id integer
)
LANGUAGE sql STABLE AS $$
  SELECT d."ID", d."Name"::text, d."ParentID"
  FROM portal."Diseases" d
  ORDER BY d."ID";
$$;

SELECT portal._drop_if_proc('portal','sp_list_groups_for_disease');
CREATE OR REPLACE FUNCTION portal.sp_list_groups_for_disease(
  p_disease_id integer,
  p_customer_id integer DEFAULT NULL
)
RETURNS TABLE(
  id integer, name text, description text, customer_id integer, sample_count bigint
)
LANGUAGE sql STABLE AS $$
  SELECT
    g."ID",
    g."Name"::text,
    g."Description"::text,
    g."CustomerID",
    COUNT(gs."SampleID") AS sample_count
  FROM portal."Groups" g
  LEFT JOIN portal."GroupSamples" gs ON gs."GroupID" = g."ID"
  LEFT JOIN portal."Samples" s ON s."ID" = gs."SampleID"
  WHERE (s."DiseaseID" = p_disease_id OR p_disease_id IS NULL)
    AND (p_customer_id IS NULL OR g."CustomerID" = p_customer_id)
  GROUP BY g."ID", g."Name", g."Description", g."CustomerID"
  ORDER BY g."Name";
$$;

SELECT portal._drop_if_proc('portal','sp_list_groups_for_study_enrollment');
CREATE OR REPLACE FUNCTION portal.sp_list_groups_for_study_enrollment(
  p_customer_id integer DEFAULT NULL
)
RETURNS TABLE(
  id integer, name text, description text, customer_id integer, sample_count bigint
)
LANGUAGE sql STABLE AS $$
  SELECT
    g."ID",
    g."Name"::text,
    g."Description"::text,
    g."CustomerID",
    COUNT(gs."SampleID") AS sample_count
  FROM portal."Groups" g
  LEFT JOIN portal."GroupSamples" gs ON gs."GroupID" = g."ID"
  WHERE (p_customer_id IS NULL OR g."CustomerID" = p_customer_id)
  GROUP BY g."ID", g."Name", g."Description", g."CustomerID"
  ORDER BY g."Name";
$$;

SELECT portal._drop_if_proc('portal','sp_list_group_samples_for_enrollment');
CREATE OR REPLACE FUNCTION portal.sp_list_group_samples_for_enrollment(
  p_group_id integer
)
RETURNS TABLE(
  portal_sample_id integer, patient_id integer, customer_id integer,
  disease_id integer, age numeric, bmi numeric
)
LANGUAGE sql STABLE AS $$
  SELECT
    s."ID"        AS portal_sample_id,
    s."PatientID",
    s."CustomerID",
    s."DiseaseID",
    s."Age",
    s."BMI"
  FROM portal."Samples" s
  JOIN portal."GroupSamples" gs ON gs."SampleID" = s."ID"
  WHERE gs."GroupID" = p_group_id
  ORDER BY s."ID";
$$;

SELECT portal._drop_if_proc('portal','sp_list_group_sample_names');
CREATE OR REPLACE FUNCTION portal.sp_list_group_sample_names(
  p_group_id integer
)
RETURNS TABLE(
  portal_sample_id integer, lab_sample_id integer, processing_sample_key text
)
LANGUAGE sql STABLE AS $$
  SELECT
    s."ID"  AS portal_sample_id,
    ls."ID" AS lab_sample_id,
    ls."Sample"::text AS processing_sample_key
  FROM portal."Samples" s
  JOIN portal."GroupSamples" gs ON gs."SampleID" = s."ID"
  LEFT JOIN portal."LabSamples" ls ON ls."SampleID" = s."ID"
  WHERE gs."GroupID" = p_group_id
  ORDER BY s."ID", ls."ID";
$$;

-- ══════════════════════════════════════════════════════════════════════════════
-- SESSION / CUSTOMER
-- ══════════════════════════════════════════════════════════════════════════════

-- Returns the session info and, when the active scope has an institution-linked customer,
-- the customer record.  RBAC.Sessions.ActiveScopeID → RBAC.Scopes.InstitutionID →
-- portal.CustomerInstitutions → portal.Customers.
-- When the scope has no institution mapping the customer columns are NULL.
SELECT portal._drop_if_proc('portal','sp_get_session_customer');
CREATE OR REPLACE FUNCTION portal.sp_get_session_customer(
  p_session_id integer
)
RETURNS TABLE(
  session_id integer, user_id integer, scope_id integer,
  customer_id integer, customer_name text
)
LANGUAGE sql STABLE AS $$
  SELECT
    s."ID"              AS session_id,
    s."UserID"          AS user_id,
    s."ActiveScopeID"   AS scope_id,
    c."ID"              AS customer_id,
    c."Name"::text      AS customer_name
  FROM "RBAC"."Sessions" s
  LEFT JOIN "RBAC"."Scopes" sc ON sc."ScopeID" = s."ActiveScopeID"
  LEFT JOIN portal."CustomerInstitutions" ci ON ci."InstitutionID" = sc."InstitutionID"
  LEFT JOIN portal."Customers" c ON c."ID" = ci."CustomerID"
  WHERE s."ID" = p_session_id;
$$;

-- ══════════════════════════════════════════════════════════════════════════════
-- REFERENCE ASSETS
-- ══════════════════════════════════════════════════════════════════════════════

SELECT portal._drop_if_proc('portal','sp_list_reference_assets');
CREATE OR REPLACE FUNCTION portal.sp_list_reference_assets(
  p_published_only boolean DEFAULT false,
  p_asset_type text DEFAULT NULL
)
RETURNS TABLE(
  id bigint, name text, version text, status text, content_hash text,
  asset_type text, storage_endpoint_id bigint
)
LANGUAGE sql STABLE AS $$
  SELECT
    ra.id, ra.name, ra.version, ra.status::text, ra.content_hash,
    ra.asset_type, ra.storage_endpoint_id
  FROM cfg.reference_asset ra
  WHERE (NOT p_published_only OR ra.status = 'published')
    AND (p_asset_type IS NULL OR ra.asset_type = p_asset_type)
  ORDER BY ra.name, ra.version;
$$;

SELECT portal._drop_if_proc('portal','sp_get_reference_asset');
CREATE OR REPLACE FUNCTION portal.sp_get_reference_asset(
  p_name text,
  p_version text DEFAULT NULL
)
RETURNS TABLE(
  id bigint, name text, version text, status text, content_hash text,
  document_json jsonb, asset_type text, storage_endpoint_id bigint
)
LANGUAGE sql STABLE AS $$
  SELECT
    ra.id, ra.name, ra.version, ra.status::text, ra.content_hash,
    ra.document_json, ra.asset_type, ra.storage_endpoint_id
  FROM cfg.reference_asset ra
  WHERE ra.name = p_name AND (p_version IS NULL OR ra.version = p_version)
  ORDER BY ra.id DESC
  LIMIT 1;
$$;

SELECT portal._drop_if_proc('portal','sp_list_site_reference_assets');
CREATE OR REPLACE FUNCTION portal.sp_list_site_reference_assets(
  p_site_name text DEFAULT NULL,
  p_site_id bigint DEFAULT NULL
)
RETURNS TABLE(
  link_id bigint, site_id bigint, site_name text,
  reference_asset_id bigint, asset_name text, asset_role text,
  storage_endpoint_id bigint, asset_status text
)
LANGUAGE sql STABLE AS $$
  SELECT
    v.link_id, v.site_id, v.site_name,
    v.reference_asset_id, v.asset_name, v.asset_role,
    v.storage_endpoint_id, v.asset_status::text
  FROM cfg.v_site_reference_asset v
  WHERE (p_site_id IS NULL OR v.site_id = p_site_id)
    AND (p_site_name IS NULL OR v.site_name = p_site_name)
  ORDER BY v.site_name, v.asset_role;
$$;

-- ══════════════════════════════════════════════════════════════════════════════
-- STORAGE PROFILES
-- ══════════════════════════════════════════════════════════════════════════════

SELECT portal._drop_if_proc('portal','sp_list_storage_profiles');
CREATE OR REPLACE FUNCTION portal.sp_list_storage_profiles(
  p_published_only boolean DEFAULT false
)
RETURNS TABLE(
  id bigint, name text, version text, status text, content_hash text
)
LANGUAGE sql STABLE AS $$
  SELECT sp.id, sp.name, sp.version, sp.status::text, sp.content_hash
  FROM cfg.storage_profile sp
  WHERE (NOT p_published_only OR sp.status = 'published')
  ORDER BY sp.name, sp.version;
$$;

-- ══════════════════════════════════════════════════════════════════════════════
-- WORKFLOW GRAPH / INSTANCES
-- ══════════════════════════════════════════════════════════════════════════════

SELECT portal._drop_if_proc('portal','sp_get_workflow_graph');
CREATE OR REPLACE FUNCTION portal.sp_get_workflow_graph(
  p_workflow_version_id bigint
)
RETURNS TABLE(
  workflow_def_id bigint, workflow_def_name text,
  workflow_version_id bigint, version_major int, version_minor int,
  is_active boolean, root_node_id bigint
)
LANGUAGE sql STABLE AS $$
  SELECT
    wd.id AS workflow_def_id, wd.name AS workflow_def_name,
    wv.id AS workflow_version_id, wv.version_major, wv.version_minor,
    wv.is_active, wv.root_node_id
  FROM wf.workflow_version wv
  JOIN wf.workflow_def wd ON wd.id = wv.workflow_def_id
  WHERE wv.id = p_workflow_version_id;
$$;

SELECT portal._drop_if_proc('portal','sp_get_workflow_instance');
CREATE OR REPLACE FUNCTION portal.sp_get_workflow_instance(
  p_workflow_instance_id bigint
)
RETURNS TABLE(
  id bigint, workflow_version_id bigint,
  workflow_def_id bigint, workflow_def_name text,
  status text, context_json jsonb,
  started_at_utc timestamptz, completed_at_utc timestamptz
)
LANGUAGE sql STABLE AS $$
  SELECT
    wi.id, wi.workflow_version_id,
    wd.id AS workflow_def_id, wd.name AS workflow_def_name,
    wi.status::text, wi.context_json,
    wi.started_at_utc, wi.completed_at_utc
  FROM wf.workflow_instance wi
  JOIN wf.workflow_version wv ON wv.id = wi.workflow_version_id
  JOIN wf.workflow_def wd ON wd.id = wv.workflow_def_id
  WHERE wi.id = p_workflow_instance_id;
$$;

-- ══════════════════════════════════════════════════════════════════════════════
-- WORKFLOW DEF / VERSION / NODES
-- ══════════════════════════════════════════════════════════════════════════════

SELECT portal._drop_if_proc('portal','sp_list_workflow_defs');
CREATE OR REPLACE FUNCTION portal.sp_list_workflow_defs(
  p_source_filter text DEFAULT NULL
)
RETURNS TABLE(
  workflow_def_id bigint, name text, source text,
  active_version_id bigint, version_major int, version_minor int
)
LANGUAGE sql STABLE AS $$
  SELECT
    wd.id AS workflow_def_id,
    wd.name,
    COALESCE(wd.source, 'system') AS source,
    wv.id AS active_version_id,
    wv.version_major,
    wv.version_minor
  FROM wf.workflow_def wd
  LEFT JOIN LATERAL (
    SELECT id, version_major, version_minor
    FROM wf.workflow_version v2
    WHERE v2.workflow_def_id = wd.id AND v2.is_active = true
    ORDER BY v2.version_major DESC, v2.version_minor DESC
    LIMIT 1
  ) wv ON true
  WHERE p_source_filter IS NULL OR COALESCE(wd.source, 'system') = p_source_filter
  ORDER BY wd.name;
$$;

SELECT portal._drop_if_proc('portal','sp_list_workflow_versions');
CREATE OR REPLACE FUNCTION portal.sp_list_workflow_versions(
  p_workflow_def_id bigint DEFAULT NULL,
  p_workflow_def_name text DEFAULT NULL
)
RETURNS TABLE(
  workflow_version_id bigint, workflow_def_id bigint,
  workflow_def_name text, version_major int, version_minor int,
  is_active boolean, root_node_id bigint
)
LANGUAGE sql STABLE AS $$
  SELECT
    wv.id AS workflow_version_id, wv.workflow_def_id,
    wd.name AS workflow_def_name,
    wv.version_major, wv.version_minor,
    wv.is_active, wv.root_node_id
  FROM wf.workflow_version wv
  JOIN wf.workflow_def wd ON wd.id = wv.workflow_def_id
  WHERE (p_workflow_def_id IS NULL OR wv.workflow_def_id = p_workflow_def_id)
    AND (p_workflow_def_name IS NULL OR wd.name = p_workflow_def_name)
  ORDER BY wv.workflow_def_id, wv.version_major DESC, wv.version_minor DESC;
$$;

SELECT portal._drop_if_proc('portal','sp_list_workflow_nodes');
CREATE OR REPLACE FUNCTION portal.sp_list_workflow_nodes(
  p_workflow_version_id bigint
)
RETURNS TABLE(
  id bigint, workflow_version_id bigint, node_type text,
  node_key text, action_name text, capability text
)
LANGUAGE sql STABLE AS $$
  SELECT
    wn.id, wn.workflow_version_id, wn.node_type::text,
    wn.node_key,
    wa.action_name, wa.capability
  FROM wf.workflow_node wn
  LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
  WHERE wn.workflow_version_id = p_workflow_version_id
  ORDER BY wn.id;
$$;

SELECT portal._drop_if_proc('portal','sp_activate_workflow_version');
CREATE OR REPLACE FUNCTION portal.sp_activate_workflow_version(
  p_workflow_version_id bigint
)
RETURNS TABLE(
  workflow_version_id bigint, workflow_def_id bigint,
  version_major int, version_minor int, is_active boolean
)
LANGUAGE plpgsql AS $$
DECLARE
  v_def_id bigint;
BEGIN
  SELECT workflow_def_id INTO v_def_id
  FROM wf.workflow_version
  WHERE id = p_workflow_version_id;

  IF v_def_id IS NULL THEN
    RAISE EXCEPTION 'workflow_version % not found', p_workflow_version_id;
  END IF;

  -- Deactivate all versions for this def then activate the requested one.
  UPDATE wf.workflow_version SET is_active = false
  WHERE workflow_def_id = v_def_id;

  UPDATE wf.workflow_version SET is_active = true
  WHERE id = p_workflow_version_id;

  RETURN QUERY
  SELECT wv.id, wv.workflow_def_id, wv.version_major, wv.version_minor, wv.is_active
  FROM wf.workflow_version wv
  WHERE wv.id = p_workflow_version_id;
END;
$$;

SELECT portal._drop_if_proc('portal','sp_resolve_active_workflow_version');
CREATE OR REPLACE FUNCTION portal.sp_resolve_active_workflow_version(
  p_workflow_def_name text
)
RETURNS TABLE(
  workflow_version_id bigint, workflow_def_id bigint,
  workflow_def_name text, version_major int, version_minor int,
  root_node_id bigint
)
LANGUAGE sql STABLE AS $$
  SELECT
    wv.id AS workflow_version_id, wv.workflow_def_id,
    wd.name AS workflow_def_name,
    wv.version_major, wv.version_minor, wv.root_node_id
  FROM wf.workflow_version wv
  JOIN wf.workflow_def wd ON wd.id = wv.workflow_def_id
  WHERE wd.name = p_workflow_def_name AND wv.is_active = true
  ORDER BY wv.version_major DESC, wv.version_minor DESC
  LIMIT 1;
$$;

-- ══════════════════════════════════════════════════════════════════════════════
-- WORKFLOW GRAPH SAVE (repo write)
-- ══════════════════════════════════════════════════════════════════════════════

SELECT portal._drop_if_proc('portal','sp_save_workflow_graph');
CREATE OR REPLACE FUNCTION portal.sp_save_workflow_graph(p_spec jsonb)
RETURNS TABLE(
  workflow_def_id bigint, workflow_version_id bigint,
  root_node_id bigint, name text
)
LANGUAGE plpgsql AS $$
DECLARE
  v_result jsonb;
  v_def_id bigint;
BEGIN
  v_result := wf.wf_repo_create_workflow_graph(p_spec);
  v_def_id := (v_result->>'workflow_def_id')::bigint;
  UPDATE wf.workflow_def SET source = 'portal' WHERE id = v_def_id;

  RETURN QUERY
  SELECT (v_result->>'workflow_def_id')::bigint,
         (v_result->>'workflow_version_id')::bigint,
         (v_result->>'root_node_id')::bigint,
         v_result->>'name';
END;
$$;

-- ══════════════════════════════════════════════════════════════════════════════
-- NODE CONFIG / TEMPLATE
-- ══════════════════════════════════════════════════════════════════════════════

-- Ensure the node-config override table exists.
CREATE TABLE IF NOT EXISTS cfg.node_config (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workflow_node_id bigint NOT NULL REFERENCES wf.workflow_node(id) ON DELETE CASCADE,
  config_json jsonb NOT NULL,
  saved_by text NULL,
  saved_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  CONSTRAINT uq_cfg_node_config_node UNIQUE (workflow_node_id)
);

SELECT portal._drop_if_proc('portal','sp_get_node_config');
CREATE OR REPLACE FUNCTION portal.sp_get_node_config(
  p_workflow_node_id bigint
)
RETURNS TABLE(
  id bigint, workflow_node_id bigint, node_key text,
  node_type text, action_name text, config_json jsonb, saved_at_utc timestamptz
)
LANGUAGE sql STABLE AS $$
  SELECT
    nc.id, nc.workflow_node_id, wn.node_key,
    wn.node_type::text,
    wa.action_name,
    nc.config_json,
    nc.saved_at_utc
  FROM cfg.node_config nc
  JOIN wf.workflow_node wn ON wn.id = nc.workflow_node_id
  LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
  WHERE nc.workflow_node_id = p_workflow_node_id;
$$;

SELECT portal._drop_if_proc('portal','sp_save_node_template');
CREATE OR REPLACE FUNCTION portal.sp_save_node_template(
  p_workflow_node_id bigint,
  p_config_json jsonb,
  p_saved_by text DEFAULT NULL
)
RETURNS TABLE(id bigint, workflow_node_id bigint, saved_at_utc timestamptz)
LANGUAGE plpgsql AS $$
DECLARE v_id bigint;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM wf.workflow_node WHERE id = p_workflow_node_id) THEN
    RAISE EXCEPTION 'workflow_node % not found', p_workflow_node_id;
  END IF;

  INSERT INTO cfg.node_config (workflow_node_id, config_json, saved_by)
  VALUES (p_workflow_node_id, p_config_json, p_saved_by)
  ON CONFLICT (workflow_node_id) DO UPDATE SET
    config_json = EXCLUDED.config_json,
    saved_by = COALESCE(EXCLUDED.saved_by, cfg.node_config.saved_by),
    saved_at_utc = now() AT TIME ZONE 'utc'
  RETURNING cfg.node_config.id INTO v_id;

  RETURN QUERY
  SELECT nc.id, nc.workflow_node_id, nc.saved_at_utc
  FROM cfg.node_config nc WHERE nc.id = v_id;
END;
$$;

-- ══════════════════════════════════════════════════════════════════════════════
-- DOMAIN PROGRAM PUBLISH
-- ══════════════════════════════════════════════════════════════════════════════

-- Publishes a DomainProgram document and records the compiled workflow version link.
-- MSSQL equivalent records a row in cfg.program_publish; PG parity does the same.
SELECT portal._drop_if_proc('portal','sp_publish_domain_program');
CREATE OR REPLACE FUNCTION portal.sp_publish_domain_program(
  p_name text,
  p_version text,
  p_workflow_version_id bigint DEFAULT NULL
)
RETURNS TABLE(id bigint, name text, version text, status text, workflow_version_id bigint)
LANGUAGE plpgsql AS $$
DECLARE
  v_dp_id bigint;
  v_wv_id bigint := p_workflow_version_id;
  v_wd_id bigint;
BEGIN
  -- Publish the cfg doc
  SELECT dp_row.id INTO v_dp_id
  FROM cfg.cfg_repo_publish('domain_program', p_name, p_version) dp_row;

  IF v_dp_id IS NULL THEN
    RAISE EXCEPTION 'domain_program % @ % not found or already retired', p_name, p_version;
  END IF;

  -- If a workflow_version_id supplied, link it and record the publish
  IF v_wv_id IS NOT NULL THEN
    SELECT wd_id INTO v_wd_id
    FROM (
      SELECT wv.workflow_def_id AS wd_id
      FROM wf.workflow_version wv WHERE wv.id = v_wv_id
    ) sub;

    UPDATE cfg.domain_program
    SET compiled_workflow_version_id = v_wv_id,
        workflow_def_id = v_wd_id,
        updated_at_utc = now() AT TIME ZONE 'utc'
    WHERE id = v_dp_id;

    INSERT INTO cfg.program_publish (domain_program_id, workflow_def_id, workflow_version_id, content_hash)
    SELECT v_dp_id, v_wd_id, v_wv_id, dp.content_hash
    FROM cfg.domain_program dp WHERE dp.id = v_dp_id
    ON CONFLICT (domain_program_id, workflow_version_id) DO NOTHING;
  END IF;

  RETURN QUERY
  SELECT dp.id, dp.name, dp.version, dp.status::text,
         dp.compiled_workflow_version_id
  FROM cfg.domain_program dp WHERE dp.id = v_dp_id;
END;
$$;

-- ══════════════════════════════════════════════════════════════════════════════
-- PROJECT (cfg.study_instance_link)
-- ══════════════════════════════════════════════════════════════════════════════

SELECT portal._drop_if_proc('portal','sp_project_list');
CREATE OR REPLACE FUNCTION portal.sp_project_list(
  p_study_name text DEFAULT NULL
)
RETURNS TABLE(
  id bigint, study_row_id bigint, study_name text, study_id text,
  workflow_instance_id bigint, instance_status text,
  domain_program_id bigint, pipeline_profile_id bigint,
  site_id bigint, storage_profile_id bigint,
  created_at_utc timestamptz
)
LANGUAGE sql STABLE AS $$
  SELECT
    sil.id, sil.study_row_id, s.name AS study_name, s.study_id,
    sil.workflow_instance_id, wi.status::text AS instance_status,
    sil.domain_program_id, sil.pipeline_profile_id,
    sil.site_id, sil.storage_profile_id,
    sil.created_at_utc
  FROM cfg.study_instance_link sil
  JOIN cfg.study s ON s.id = sil.study_row_id
  LEFT JOIN wf.workflow_instance wi ON wi.id = sil.workflow_instance_id
  WHERE p_study_name IS NULL OR s.name = p_study_name
  ORDER BY sil.created_at_utc DESC;
$$;

SELECT portal._drop_if_proc('portal','sp_project_get');
CREATE OR REPLACE FUNCTION portal.sp_project_get(
  p_workflow_instance_id bigint
)
RETURNS TABLE(
  id bigint, study_row_id bigint, study_name text, study_id text,
  workflow_instance_id bigint, instance_status text,
  domain_program_id bigint, pipeline_profile_id bigint,
  site_id bigint, storage_profile_id bigint,
  context_json jsonb, created_at_utc timestamptz
)
LANGUAGE sql STABLE AS $$
  SELECT
    sil.id, sil.study_row_id, s.name AS study_name, s.study_id,
    sil.workflow_instance_id, wi.status::text AS instance_status,
    sil.domain_program_id, sil.pipeline_profile_id,
    sil.site_id, sil.storage_profile_id,
    wi.context_json, sil.created_at_utc
  FROM cfg.study_instance_link sil
  JOIN cfg.study s ON s.id = sil.study_row_id
  LEFT JOIN wf.workflow_instance wi ON wi.id = sil.workflow_instance_id
  WHERE sil.workflow_instance_id = p_workflow_instance_id;
$$;

SELECT portal._drop_if_proc('portal','sp_project_save');
CREATE OR REPLACE FUNCTION portal.sp_project_save(
  p_study_row_id bigint,
  p_workflow_instance_id bigint,
  p_domain_program_id bigint DEFAULT NULL,
  p_pipeline_profile_id bigint DEFAULT NULL,
  p_site_id bigint DEFAULT NULL,
  p_storage_profile_id bigint DEFAULT NULL
)
RETURNS TABLE(id bigint, study_row_id bigint, workflow_instance_id bigint)
LANGUAGE plpgsql AS $$
DECLARE v_id bigint;
BEGIN
  INSERT INTO cfg.study_instance_link (
    study_row_id, workflow_instance_id, domain_program_id,
    pipeline_profile_id, site_id, storage_profile_id
  )
  VALUES (
    p_study_row_id, p_workflow_instance_id, p_domain_program_id,
    p_pipeline_profile_id, p_site_id, p_storage_profile_id
  )
  ON CONFLICT (workflow_instance_id) DO UPDATE SET
    study_row_id        = EXCLUDED.study_row_id,
    domain_program_id   = COALESCE(EXCLUDED.domain_program_id, cfg.study_instance_link.domain_program_id),
    pipeline_profile_id = COALESCE(EXCLUDED.pipeline_profile_id, cfg.study_instance_link.pipeline_profile_id),
    site_id             = COALESCE(EXCLUDED.site_id, cfg.study_instance_link.site_id),
    storage_profile_id  = COALESCE(EXCLUDED.storage_profile_id, cfg.study_instance_link.storage_profile_id)
  RETURNING cfg.study_instance_link.id INTO v_id;

  RETURN QUERY
  SELECT sil.id, sil.study_row_id, sil.workflow_instance_id
  FROM cfg.study_instance_link sil WHERE sil.id = v_id;
END;
$$;

-- Resolve archive path for a project (study + instance).
SELECT portal._drop_if_proc('portal','sp_project_resolve_archive');
CREATE OR REPLACE FUNCTION portal.sp_project_resolve_archive(
  p_workflow_instance_id bigint,
  p_work_root text DEFAULT '/work'
)
RETURNS TABLE(
  study_name text, study_id text, archive_root text, context_json jsonb
)
LANGUAGE sql STABLE AS $$
  SELECT
    s.name AS study_name,
    s.study_id,
    p_work_root || '/projects/' || COALESCE(s.study_id, s.name) AS archive_root,
    wi.context_json
  FROM cfg.study_instance_link sil
  JOIN cfg.study s ON s.id = sil.study_row_id
  LEFT JOIN wf.workflow_instance wi ON wi.id = sil.workflow_instance_id
  WHERE sil.workflow_instance_id = p_workflow_instance_id;
$$;

-- ══════════════════════════════════════════════════════════════════════════════
-- OPS / MONITORING
-- ══════════════════════════════════════════════════════════════════════════════

SELECT portal._drop_if_proc('portal','sp_list_ops_instances');
CREATE OR REPLACE FUNCTION portal.sp_list_ops_instances(
  p_status_filter text DEFAULT NULL,
  p_limit int DEFAULT 100
)
RETURNS TABLE(
  instance_id bigint, workflow_def_name text, version_major int, version_minor int,
  status text, study_name text, started_at_utc timestamptz, completed_at_utc timestamptz
)
LANGUAGE sql STABLE AS $$
  SELECT
    wi.id AS instance_id,
    wd.name AS workflow_def_name,
    wv.version_major, wv.version_minor,
    wi.status::text,
    s.name AS study_name,
    wi.started_at_utc,
    wi.completed_at_utc
  FROM wf.workflow_instance wi
  JOIN wf.workflow_version wv ON wv.id = wi.workflow_version_id
  JOIN wf.workflow_def wd ON wd.id = wv.workflow_def_id
  LEFT JOIN cfg.study_instance_link sil ON sil.workflow_instance_id = wi.id
  LEFT JOIN cfg.study s ON s.id = sil.study_row_id
  WHERE p_status_filter IS NULL OR wi.status::text = p_status_filter
  ORDER BY wi.id DESC
  LIMIT p_limit;
$$;

SELECT portal._drop_if_proc('portal','sp_list_recent_instances');
CREATE OR REPLACE FUNCTION portal.sp_list_recent_instances(
  p_hours_back int DEFAULT 24,
  p_limit int DEFAULT 50
)
RETURNS TABLE(
  instance_id bigint, workflow_def_name text, status text,
  study_name text, started_at_utc timestamptz, completed_at_utc timestamptz
)
LANGUAGE sql STABLE AS $$
  SELECT
    wi.id AS instance_id,
    wd.name AS workflow_def_name,
    wi.status::text,
    s.name AS study_name,
    wi.started_at_utc,
    wi.completed_at_utc
  FROM wf.workflow_instance wi
  JOIN wf.workflow_version wv ON wv.id = wi.workflow_version_id
  JOIN wf.workflow_def wd ON wd.id = wv.workflow_def_id
  LEFT JOIN cfg.study_instance_link sil ON sil.workflow_instance_id = wi.id
  LEFT JOIN cfg.study s ON s.id = sil.study_row_id
  WHERE wi.started_at_utc >= (now() AT TIME ZONE 'utc') - (p_hours_back || ' hours')::interval
  ORDER BY wi.started_at_utc DESC
  LIMIT p_limit;
$$;

SELECT portal._drop_if_proc('portal','sp_list_stale_leases');
CREATE OR REPLACE FUNCTION portal.sp_list_stale_leases(
  p_grace_seconds int DEFAULT 60
)
RETURNS TABLE(
  node_execution_id bigint, workflow_instance_id bigint,
  worker_id bigint, lease_expires_at_utc timestamptz,
  stale_for_seconds numeric
)
LANGUAGE sql STABLE AS $$
  SELECT
    ne.id AS node_execution_id,
    ne.workflow_instance_id,
    tl.worker_id,
    tl.lease_expires_at_utc,
    EXTRACT(EPOCH FROM (now() AT TIME ZONE 'utc' - tl.lease_expires_at_utc)) AS stale_for_seconds
  FROM wf.task_lease tl
  JOIN wf.node_execution ne ON ne.id = tl.node_execution_id
  WHERE tl.lease_expires_at_utc < (now() AT TIME ZONE 'utc') - (p_grace_seconds || ' seconds')::interval
  ORDER BY tl.lease_expires_at_utc;
$$;

SELECT portal._drop_if_proc('portal','sp_list_worker_health');
CREATE OR REPLACE FUNCTION portal.sp_list_worker_health(
  p_cluster_key text DEFAULT NULL
)
RETURNS TABLE(
  worker_id bigint, cluster_id bigint, cluster_key text,
  external_worker_key text, display_name text, hostname text,
  status text, desired_state text, capabilities jsonb,
  last_seen_at_utc timestamptz, created_at_utc timestamptz
)
LANGUAGE sql STABLE AS $$
  SELECT
    w.id AS worker_id, c.id AS cluster_id, c.cluster_key,
    w.external_worker_key, w.display_name, w.hostname,
    w.status::text, w.desired_state::text, w.capabilities,
    w.last_seen_at_utc, w.created_at_utc
  FROM wf.worker w
  JOIN wf.cluster c ON c.id = w.cluster_id
  WHERE p_cluster_key IS NULL OR c.cluster_key = p_cluster_key
  ORDER BY c.cluster_key, w.id;
$$;

-- ══════════════════════════════════════════════════════════════════════════════
-- HYPERPARAMETER SEARCHES
-- ══════════════════════════════════════════════════════════════════════════════

-- Lists hyperparameter search runs (cfg.hyperparameter_search_run).
-- Runs are linked to a study directly via study_row_id; trials are tracked
-- in cfg.hyperparameter_trial.
SELECT portal._drop_if_proc('portal','sp_list_hyperparam_searches');
CREATE OR REPLACE FUNCTION portal.sp_list_hyperparam_searches(
  p_status_filter text DEFAULT NULL,
  p_study_row_id bigint DEFAULT NULL
)
RETURNS TABLE(
  id bigint, study_row_id bigint, study_name text,
  display_name text, status text, grid_json jsonb,
  created_at_utc timestamptz, updated_at_utc timestamptz
)
LANGUAGE sql STABLE AS $$
  SELECT
    hs.id, hs.study_row_id,
    s.name AS study_name,
    hs.display_name,
    hs.status,
    hs.grid_json,
    hs.created_at_utc, hs.updated_at_utc
  FROM cfg.hyperparameter_search_run hs
  LEFT JOIN cfg.study s ON s.id = hs.study_row_id
  WHERE (p_status_filter IS NULL OR hs.status = p_status_filter)
    AND (p_study_row_id IS NULL OR hs.study_row_id = p_study_row_id)
  ORDER BY hs.created_at_utc DESC;
$$;
