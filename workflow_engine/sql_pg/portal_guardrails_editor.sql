-- Layered SamplePrep guardrail editors (PostgreSQL).
-- Site persists the full published window; profile / procedure persist a sparse overlay.
-- Study GET/SET remain in portal_study_ops_api.sql (schema_id study_action_config_overlay).
--
-- Prerequisites: portal_study_ops_api.sql (fn_jsonb_deep_merge, fn_jsonb_sparse_diff,
-- fn_jsonb_guardrail_slice), cfg.site / pipeline_profile / assay_procedure.

CREATE SCHEMA IF NOT EXISTS portal;

CREATE OR REPLACE FUNCTION portal.fn_jsonb_default_site_action_config()
RETURNS jsonb
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v jsonb := '{}'::jsonb;
BEGIN
  SELECT COALESCE(s.document_json->'actionConfig', '{}'::jsonb)
  INTO v
  FROM cfg.site s
  WHERE s.status = 'published'
  ORDER BY CASE WHEN s.name = 'default' THEN 0 ELSE 1 END, s.id DESC
  LIMIT 1;
  RETURN COALESCE(v, '{}'::jsonb);
END;
$$;

CREATE OR REPLACE FUNCTION portal.fn_jsonb_profile_action_config(p_name text)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v jsonb := '{}'::jsonb;
BEGIN
  IF p_name IS NULL OR btrim(p_name) = '' THEN
    RETURN '{}'::jsonb;
  END IF;
  SELECT COALESCE(p.document_json->'actionConfig', '{}'::jsonb)
  INTO v
  FROM cfg.pipeline_profile p
  WHERE p.name = p_name
    AND p.status IN ('published', 'retired')
  ORDER BY p.id DESC
  LIMIT 1;
  RETURN COALESCE(v, '{}'::jsonb);
END;
$$;

CREATE OR REPLACE FUNCTION portal.fn_jsonb_full_window_ok(p_doc jsonb)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT
    (p_doc #>> '{alignment_qc,core_guardrails,min_pf_percent}') IS NOT NULL
    AND (p_doc #>> '{alignment_qc,core_guardrails,min_q30_percent}') IS NOT NULL
    AND (p_doc #>> '{alignment_qc,core_guardrails,min_mean_quality}') IS NOT NULL
    AND (p_doc #>> '{alignment_qc,core_guardrails,min_quality_post20}') IS NOT NULL
    AND (p_doc #>> '{alignment_qc,core_guardrails,max_at_dropout}') IS NOT NULL
    AND (p_doc #>> '{alignment_qc,core_guardrails,max_gc_dropout}') IS NOT NULL
    AND (p_doc #>> '{alignment_qc,core_guardrails,median_insert_min_bp}') IS NOT NULL
    AND (p_doc #>> '{alignment_qc,core_guardrails,median_insert_max_bp}') IS NOT NULL
    AND (p_doc #>> '{alignment_qc,core_guardrails,max_deamination_qscore}') IS NOT NULL
    AND (p_doc #>> '{alignment_qc,core_guardrails,min_oxog_qscore}') IS NOT NULL
    AND (p_doc #>> '{extraction_qc,guardrails,min_cpg_weighted_mean_coverage}') IS NOT NULL
    AND (p_doc #>> '{extraction_qc,guardrails,max_chh_methylation_level}') IS NOT NULL
    AND (p_doc #>> '{extraction_qc,guardrails,max_chg_methylation_level}') IS NOT NULL
    AND (p_doc #>> '{extraction_qc,guardrails,min_autosomal_coverage_uniformity_ratio}') IS NOT NULL
    AND (p_doc #>> '{extraction_qc,guardrails,max_discard_fraction}') IS NOT NULL
$$;

CREATE OR REPLACE FUNCTION portal.fn_jsonb_replace_guardrail_keys(p_existing jsonb, p_qc jsonb)
RETURNS jsonb
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  v_new jsonb := COALESCE(p_existing, '{}'::jsonb);
  rec record;
BEGIN
  IF jsonb_typeof(v_new) <> 'object' THEN
    v_new := '{}'::jsonb;
  END IF;
  v_new := v_new - 'alignment_qc' - 'extraction_qc';
  IF p_qc IS NULL OR jsonb_typeof(p_qc) <> 'object' THEN
    RETURN v_new;
  END IF;
  FOR rec IN SELECT key, value FROM jsonb_each(p_qc)
  LOOP
    IF rec.value IS NULL OR rec.value = 'null'::jsonb THEN
      CONTINUE;
    END IF;
    v_new := jsonb_set(v_new, ARRAY[rec.key], rec.value, true);
  END LOOP;
  RETURN v_new;
END;
$$;

CREATE OR REPLACE FUNCTION portal.fn_guardrail_draft_version(p_status text, p_version text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE
    WHEN lower(COALESCE(p_status, '')) = 'draft'
      THEN COALESCE(NULLIF(btrim(p_version), ''), '1')
    ELSE COALESCE(NULLIF(btrim(p_version), ''), '1') || '-draft'
  END;
$$;

-- ── site ───────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION portal.sp_get_site_guardrails_editor(p_site_row_id bigint)
RETURNS TABLE (
  site_row_id bigint,
  site_name text,
  schema_id text,
  effective_guardrails jsonb
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_name text;
  v_ac jsonb;
BEGIN
  IF p_site_row_id IS NULL OR p_site_row_id <= 0 THEN
    RAISE EXCEPTION 'site_row_id is required';
  END IF;
  SELECT s.name, COALESCE(s.document_json->'actionConfig', '{}'::jsonb)
  INTO v_name, v_ac
  FROM cfg.site s
  WHERE s.id = p_site_row_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'cfg.site not found';
  END IF;
  RETURN QUERY SELECT
    p_site_row_id,
    v_name,
    'sample_prep_guardrails'::text,
    portal.fn_jsonb_guardrail_slice(v_ac);
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_set_site_guardrails_editor(
  p_site_row_id bigint,
  p_edited_effective jsonb
)
RETURNS TABLE (
  site_row_id bigint,
  site_name text,
  schema_id text,
  effective_guardrails jsonb
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_doc jsonb;
  v_existing jsonb;
  v_edited jsonb;
  v_new jsonb;
BEGIN
  IF p_site_row_id IS NULL OR p_site_row_id <= 0 THEN
    RAISE EXCEPTION 'site_row_id is required';
  END IF;
  IF p_edited_effective IS NULL OR jsonb_typeof(p_edited_effective) <> 'object' THEN
    RAISE EXCEPTION 'edited_effective must be a JSON object (full working document)';
  END IF;

  SELECT document_json INTO v_doc FROM cfg.site WHERE id = p_site_row_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'cfg.site not found';
  END IF;
  v_doc := COALESCE(v_doc, '{}'::jsonb);
  v_existing := COALESCE(v_doc->'actionConfig', '{}'::jsonb);
  IF jsonb_typeof(v_existing) <> 'object' THEN
    v_existing := '{}'::jsonb;
  END IF;

  v_edited := portal.fn_jsonb_guardrail_slice(p_edited_effective);
  IF NOT portal.fn_jsonb_full_window_ok(v_edited) THEN
    RAISE EXCEPTION 'site guardrails require the full published window';
  END IF;

  v_new := portal.fn_jsonb_replace_guardrail_keys(v_existing, v_edited);
  v_doc := jsonb_set(v_doc, '{actionConfig}', v_new, true);

  UPDATE cfg.site
  SET document_json = v_doc,
      content_hash = cfg._content_hash(v_doc),
      updated_at_utc = now() AT TIME ZONE 'utc'
  WHERE id = p_site_row_id;

  RETURN QUERY SELECT * FROM portal.sp_get_site_guardrails_editor(p_site_row_id);
END;
$$;

-- ── profile ────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION portal.sp_get_profile_guardrails_editor(p_pipeline_profile_id bigint)
RETURNS TABLE (
  pipeline_profile_id bigint,
  pipeline_profile text,
  version text,
  status text,
  site_name text,
  schema_id text,
  inherited_guardrails jsonb,
  profile_guardrail_overlay jsonb,
  effective_guardrails jsonb
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_name text;
  v_version text;
  v_status text;
  v_overlay jsonb;
  v_inherited jsonb;
  v_site text;
BEGIN
  IF p_pipeline_profile_id IS NULL OR p_pipeline_profile_id <= 0 THEN
    RAISE EXCEPTION 'pipeline_profile_id is required';
  END IF;
  SELECT p.name, p.version, p.status::text, COALESCE(p.document_json->'actionConfig', '{}'::jsonb)
  INTO v_name, v_version, v_status, v_overlay
  FROM cfg.pipeline_profile p
  WHERE p.id = p_pipeline_profile_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'cfg.pipeline_profile not found';
  END IF;

  SELECT s.name INTO v_site
  FROM cfg.site s
  WHERE s.status = 'published'
  ORDER BY CASE WHEN s.name = 'default' THEN 0 ELSE 1 END, s.id DESC
  LIMIT 1;

  v_inherited := portal.fn_jsonb_guardrail_slice(portal.fn_jsonb_default_site_action_config());
  v_overlay := portal.fn_jsonb_guardrail_slice(v_overlay);

  RETURN QUERY SELECT
    p_pipeline_profile_id,
    v_name,
    v_version,
    v_status,
    v_site,
    'sample_prep_guardrails_overlay'::text,
    v_inherited,
    v_overlay,
    portal.fn_jsonb_deep_merge(v_inherited, v_overlay);
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_set_profile_guardrails_editor(
  p_pipeline_profile_id bigint,
  p_edited_effective jsonb
)
RETURNS TABLE (
  pipeline_profile_id bigint,
  pipeline_profile text,
  version text,
  status text,
  site_name text,
  schema_id text,
  inherited_guardrails jsonb,
  profile_guardrail_overlay jsonb,
  effective_guardrails jsonb
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_name text;
  v_version text;
  v_status text;
  v_save_version text;
  v_new_id bigint;
  v_doc jsonb;
  v_existing jsonb;
  v_inherited jsonb;
  v_edited jsonb;
  v_diff jsonb;
  v_new jsonb;
BEGIN
  IF p_pipeline_profile_id IS NULL OR p_pipeline_profile_id <= 0 THEN
    RAISE EXCEPTION 'pipeline_profile_id is required';
  END IF;
  IF p_edited_effective IS NULL OR jsonb_typeof(p_edited_effective) <> 'object' THEN
    RAISE EXCEPTION 'edited_effective must be a JSON object (full working document)';
  END IF;

  SELECT name, version, status::text, document_json
  INTO v_name, v_version, v_status, v_doc
  FROM cfg.pipeline_profile WHERE id = p_pipeline_profile_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'cfg.pipeline_profile not found';
  END IF;
  v_doc := COALESCE(v_doc, '{}'::jsonb);
  v_existing := COALESCE(v_doc->'actionConfig', '{}'::jsonb);
  IF jsonb_typeof(v_existing) <> 'object' THEN
    v_existing := '{}'::jsonb;
  END IF;

  v_inherited := portal.fn_jsonb_guardrail_slice(portal.fn_jsonb_default_site_action_config());
  v_edited := portal.fn_jsonb_guardrail_slice(p_edited_effective);
  v_diff := portal.fn_jsonb_sparse_diff(v_inherited, v_edited);
  v_new := portal.fn_jsonb_replace_guardrail_keys(v_existing, v_diff);
  v_doc := jsonb_set(v_doc, '{actionConfig}', v_new, true);
  v_save_version := portal.fn_guardrail_draft_version(v_status, v_version);

  SELECT u.id INTO v_new_id
  FROM cfg.cfg_repo_upsert(
    'pipeline_profile', v_name, v_save_version, 'draft', v_doc
  ) AS u;

  RETURN QUERY SELECT * FROM portal.sp_get_profile_guardrails_editor(v_new_id);
END;
$$;

-- ── assay procedure ────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION portal.sp_get_assay_procedure_guardrails_editor(p_assay_procedure_id bigint)
RETURNS TABLE (
  assay_procedure_id bigint,
  pipeline_procedure text,
  version text,
  status text,
  pipeline_profile text,
  site_name text,
  schema_id text,
  inherited_guardrails jsonb,
  procedure_guardrail_overlay jsonb,
  effective_guardrails jsonb
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_name text;
  v_version text;
  v_status text;
  v_doc jsonb;
  v_overlay jsonb;
  v_inherited jsonb;
  v_profile text;
  v_site text;
BEGIN
  IF p_assay_procedure_id IS NULL OR p_assay_procedure_id <= 0 THEN
    RAISE EXCEPTION 'assay_procedure_id is required';
  END IF;
  SELECT a.name, a.version, a.status::text, COALESCE(a.document_json, '{}'::jsonb)
  INTO v_name, v_version, v_status, v_doc
  FROM cfg.assay_procedure a
  WHERE a.id = p_assay_procedure_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'cfg.assay_procedure not found';
  END IF;

  v_profile := v_doc->>'pipelineProfile';
  SELECT s.name INTO v_site
  FROM cfg.site s
  WHERE s.status = 'published'
  ORDER BY CASE WHEN s.name = 'default' THEN 0 ELSE 1 END, s.id DESC
  LIMIT 1;

  v_inherited := portal.fn_jsonb_deep_merge(
    portal.fn_jsonb_guardrail_slice(portal.fn_jsonb_default_site_action_config()),
    portal.fn_jsonb_guardrail_slice(portal.fn_jsonb_profile_action_config(v_profile))
  );
  v_overlay := portal.fn_jsonb_guardrail_slice(COALESCE(v_doc->'actionConfig', '{}'::jsonb));

  RETURN QUERY SELECT
    p_assay_procedure_id,
    v_name,
    v_version,
    v_status,
    v_profile,
    v_site,
    'sample_prep_guardrails_overlay'::text,
    v_inherited,
    v_overlay,
    portal.fn_jsonb_deep_merge(v_inherited, v_overlay);
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_set_assay_procedure_guardrails_editor(
  p_assay_procedure_id bigint,
  p_edited_effective jsonb
)
RETURNS TABLE (
  assay_procedure_id bigint,
  pipeline_procedure text,
  version text,
  status text,
  pipeline_profile text,
  site_name text,
  schema_id text,
  inherited_guardrails jsonb,
  procedure_guardrail_overlay jsonb,
  effective_guardrails jsonb
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_name text;
  v_version text;
  v_status text;
  v_save_version text;
  v_new_id bigint;
  v_doc jsonb;
  v_existing jsonb;
  v_inherited jsonb;
  v_edited jsonb;
  v_diff jsonb;
  v_new jsonb;
  v_profile text;
BEGIN
  IF p_assay_procedure_id IS NULL OR p_assay_procedure_id <= 0 THEN
    RAISE EXCEPTION 'assay_procedure_id is required';
  END IF;
  IF p_edited_effective IS NULL OR jsonb_typeof(p_edited_effective) <> 'object' THEN
    RAISE EXCEPTION 'edited_effective must be a JSON object (full working document)';
  END IF;

  SELECT name, version, status::text, document_json
  INTO v_name, v_version, v_status, v_doc
  FROM cfg.assay_procedure WHERE id = p_assay_procedure_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'cfg.assay_procedure not found';
  END IF;
  v_doc := COALESCE(v_doc, '{}'::jsonb);
  v_existing := COALESCE(v_doc->'actionConfig', '{}'::jsonb);
  IF jsonb_typeof(v_existing) <> 'object' THEN
    v_existing := '{}'::jsonb;
  END IF;

  v_profile := v_doc->>'pipelineProfile';
  v_inherited := portal.fn_jsonb_deep_merge(
    portal.fn_jsonb_guardrail_slice(portal.fn_jsonb_default_site_action_config()),
    portal.fn_jsonb_guardrail_slice(portal.fn_jsonb_profile_action_config(v_profile))
  );
  v_edited := portal.fn_jsonb_guardrail_slice(p_edited_effective);
  v_diff := portal.fn_jsonb_sparse_diff(v_inherited, v_edited);
  v_new := portal.fn_jsonb_replace_guardrail_keys(v_existing, v_diff);
  v_doc := jsonb_set(v_doc, '{actionConfig}', v_new, true);
  v_save_version := portal.fn_guardrail_draft_version(v_status, v_version);

  SELECT u.id INTO v_new_id
  FROM cfg.cfg_repo_upsert(
    'assay_procedure', v_name, v_save_version, 'draft', v_doc
  ) AS u;

  RETURN QUERY SELECT * FROM portal.sp_get_assay_procedure_guardrails_editor(v_new_id);
END;
$$;
