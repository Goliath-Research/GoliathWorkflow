/*
  Study operator SQL contracts (PostgreSQL twin of sql_mssql/portal_study_ops_api.sql).

  Deploy after portal_contract_api.sql, portal_study_pipeline_api.sql,
  portal_ops_recovery_api.sql.

  Study start queue (Portal intent, Python bake) is cfg_study_start_request.sql.
*/

ALTER TABLE wf.node_execution
  ADD COLUMN IF NOT EXISTS stop_requested boolean NOT NULL DEFAULT false;

CREATE SCHEMA IF NOT EXISTS portal;

CREATE OR REPLACE FUNCTION portal.fn_redact_json_credentials(p_payload jsonb)
RETURNS jsonb
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  v jsonb := p_payload;
BEGIN
  IF v IS NULL THEN
    RETURN NULL;
  END IF;

  v := v - 'credentials';
  IF jsonb_typeof(v->'fastqSource') = 'object' THEN
    v := v #- '{fastqSource,credentials}';
  END IF;
  IF jsonb_typeof(v->'fastqStorage') = 'object' THEN
    v := v #- '{fastqStorage,credentials}';
  END IF;
  IF jsonb_typeof(v->'sampleDestination') = 'object' THEN
    v := v #- '{sampleDestination,credentials}';
  END IF;
  IF jsonb_typeof(v->'sampleStorage') = 'object' THEN
    v := v #- '{sampleStorage,credentials}';
  END IF;
  IF jsonb_typeof(v->'h5Destination') = 'object' THEN
    v := v #- '{h5Destination,credentials}';
  END IF;
  IF jsonb_typeof(v->'h5Storage') = 'object' THEN
    v := v #- '{h5Storage,credentials}';
  END IF;

  IF jsonb_typeof(v->'samples') = 'array' THEN
    v := jsonb_set(
      v,
      '{samples}',
      COALESCE((
        SELECT jsonb_agg(portal.fn_redact_json_credentials(elem))
        FROM jsonb_array_elements(v->'samples') elem
      ), '[]'::jsonb)
    );
  END IF;

  RETURN v;
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_link_study_instance(
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
BEGIN
  IF p_study_row_id IS NULL OR p_study_row_id <= 0 THEN
    RAISE EXCEPTION 'study_row_id is required';
  END IF;
  IF p_workflow_instance_id IS NULL OR p_workflow_instance_id <= 0 THEN
    RAISE EXCEPTION 'workflow_instance_id is required';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM cfg.study s WHERE s.id = p_study_row_id) THEN
    RAISE EXCEPTION 'cfg.study not found';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM wf.workflow_instance i WHERE i.id = p_workflow_instance_id) THEN
    RAISE EXCEPTION 'workflow_instance not found';
  END IF;

  RETURN QUERY
  SELECT * FROM cfg.cfg_repo_link_study_instance(
    p_study_row_id,
    p_workflow_instance_id,
    p_domain_program_id,
    p_pipeline_profile_id,
    p_site_id,
    p_storage_profile_id,
    p_assay_procedure_id
  );
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_get_study_storage(p_study_row_id bigint)
RETURNS TABLE (
  study_row_id bigint,
  study_name text,
  fastq_source_endpoint_id bigint,
  fastq_source_name text,
  fastq_source_provider text,
  fastq_source_status text,
  sample_destination_endpoint_id bigint,
  sample_destination_name text,
  sample_destination_provider text,
  sample_destination_status text
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    s.id,
    s.name,
    NULLIF(s.document_json #>> '{storage,fastqSourceEndpointId}', '')::bigint,
    src.name,
    src.provider,
    src.status,
    NULLIF(s.document_json #>> '{storage,sampleDestinationEndpointId}', '')::bigint,
    dst.name,
    dst.provider,
    dst.status
  FROM cfg.study s
  LEFT JOIN cfg.storage_endpoint src
    ON src.id = NULLIF(s.document_json #>> '{storage,fastqSourceEndpointId}', '')::bigint
  LEFT JOIN cfg.storage_endpoint dst
    ON dst.id = NULLIF(s.document_json #>> '{storage,sampleDestinationEndpointId}', '')::bigint
  WHERE s.id = p_study_row_id;
$$;

CREATE OR REPLACE FUNCTION portal.sp_set_study_storage(
  p_study_row_id bigint,
  p_fastq_source_endpoint_id bigint DEFAULT NULL,
  p_sample_destination_endpoint_id bigint DEFAULT NULL
)
RETURNS TABLE (
  study_row_id bigint,
  study_name text,
  fastq_source_endpoint_id bigint,
  fastq_source_name text,
  fastq_source_provider text,
  fastq_source_status text,
  sample_destination_endpoint_id bigint,
  sample_destination_name text,
  sample_destination_provider text,
  sample_destination_status text
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_doc jsonb;
BEGIN
  IF p_study_row_id IS NULL OR p_study_row_id <= 0 THEN
    RAISE EXCEPTION 'study_row_id is required';
  END IF;
  SELECT document_json INTO v_doc FROM cfg.study WHERE id = p_study_row_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'cfg.study not found';
  END IF;

  IF p_fastq_source_endpoint_id IS NOT NULL
     AND NOT EXISTS (
       SELECT 1 FROM cfg.storage_endpoint e
       WHERE e.id = p_fastq_source_endpoint_id AND e.status = 'published'
     ) THEN
    RAISE EXCEPTION 'fastq_source_endpoint_id must be a published storage endpoint';
  END IF;
  IF p_sample_destination_endpoint_id IS NOT NULL
     AND NOT EXISTS (
       SELECT 1 FROM cfg.storage_endpoint e
       WHERE e.id = p_sample_destination_endpoint_id AND e.status = 'published'
     ) THEN
    RAISE EXCEPTION 'sample_destination_endpoint_id must be a published storage endpoint';
  END IF;

  v_doc := COALESCE(v_doc, '{}'::jsonb);
  IF jsonb_typeof(v_doc->'storage') IS DISTINCT FROM 'object' THEN
    v_doc := jsonb_set(v_doc, '{storage}', '{}'::jsonb, true);
  END IF;
  IF p_fastq_source_endpoint_id IS NULL THEN
    v_doc := v_doc #- '{storage,fastqSourceEndpointId}';
  ELSE
    v_doc := jsonb_set(v_doc, '{storage,fastqSourceEndpointId}', to_jsonb(p_fastq_source_endpoint_id), true);
  END IF;
  IF p_sample_destination_endpoint_id IS NULL THEN
    v_doc := v_doc #- '{storage,sampleDestinationEndpointId}';
  ELSE
    v_doc := jsonb_set(v_doc, '{storage,sampleDestinationEndpointId}', to_jsonb(p_sample_destination_endpoint_id), true);
  END IF;

  UPDATE cfg.study
  SET document_json = v_doc,
      content_hash = encode(digest(v_doc::text, 'sha256'), 'hex'),
      updated_at_utc = now() AT TIME ZONE 'utc'
  WHERE id = p_study_row_id;

  RETURN QUERY SELECT * FROM portal.sp_get_study_storage(p_study_row_id);
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_get_study_action_config_overlay(p_study_row_id bigint)
RETURNS TABLE (
  study_row_id bigint,
  study_name text,
  action_config_overlay jsonb
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    s.id,
    s.name,
    COALESCE(s.document_json -> 'actionConfig', '{}'::jsonb)
  FROM cfg.study s
  WHERE s.id = p_study_row_id;
$$;

-- Replace study document_json.actionConfig with the supplied nested object.
-- HPO promote must merge dotted trial overrides first (fn_apply_dotted_action_config).
CREATE OR REPLACE FUNCTION portal.sp_set_study_action_config_overlay(
  p_study_row_id bigint,
  p_action_config_overlay jsonb
)
RETURNS TABLE (
  study_row_id bigint,
  study_name text,
  action_config_overlay jsonb
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_doc jsonb;
BEGIN
  IF p_study_row_id IS NULL OR p_study_row_id <= 0 THEN
    RAISE EXCEPTION 'study_row_id is required';
  END IF;
  IF p_action_config_overlay IS NULL OR jsonb_typeof(p_action_config_overlay) <> 'object' THEN
    RAISE EXCEPTION 'action_config_overlay must be a JSON object';
  END IF;

  SELECT document_json INTO v_doc FROM cfg.study WHERE id = p_study_row_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'cfg.study not found';
  END IF;

  v_doc := jsonb_set(COALESCE(v_doc, '{}'::jsonb), '{actionConfig}', p_action_config_overlay, true);

  UPDATE cfg.study
  SET document_json = v_doc,
      content_hash = encode(digest(v_doc::text, 'sha256'), 'hex'),
      updated_at_utc = now() AT TIME ZONE 'utc'
  WHERE id = p_study_row_id;

  RETURN QUERY SELECT * FROM portal.sp_get_study_action_config_overlay(p_study_row_id);
END;
$$;

-- Deep-merge for next-run Guardrails compose (JSON null deletes a leaf).
CREATE OR REPLACE FUNCTION portal.fn_jsonb_deep_merge(p_base jsonb, p_overlay jsonb)
RETURNS jsonb
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  result jsonb;
  rec record;
BEGIN
  IF p_overlay IS NULL OR jsonb_typeof(p_overlay) <> 'object' THEN
    RETURN CASE
      WHEN p_base IS NULL OR jsonb_typeof(p_base) <> 'object' THEN '{}'::jsonb
      ELSE p_base
    END;
  END IF;
  result := CASE
    WHEN p_base IS NULL OR jsonb_typeof(p_base) <> 'object' THEN '{}'::jsonb
    ELSE p_base
  END;
  FOR rec IN SELECT key, value FROM jsonb_each(p_overlay)
  LOOP
    IF rec.value = 'null'::jsonb THEN
      result := result - rec.key;
    ELSIF jsonb_typeof(rec.value) = 'object' AND jsonb_typeof(result->rec.key) = 'object' THEN
      result := jsonb_set(
        result,
        ARRAY[rec.key],
        portal.fn_jsonb_deep_merge(result->rec.key, rec.value),
        true
      );
    ELSE
      result := jsonb_set(result, ARRAY[rec.key], rec.value, true);
    END IF;
  END LOOP;
  RETURN result;
END;
$$;

-- Overlay such that deep_merge(baseline, overlay) equals edited.
CREATE OR REPLACE FUNCTION portal.fn_jsonb_sparse_diff(p_baseline jsonb, p_edited jsonb)
RETURNS jsonb
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  baseline jsonb := COALESCE(p_baseline, '{}'::jsonb);
  edited jsonb := COALESCE(p_edited, '{}'::jsonb);
  result jsonb := '{}'::jsonb;
  rec record;
  child jsonb;
BEGIN
  IF jsonb_typeof(baseline) <> 'object' THEN
    baseline := '{}'::jsonb;
  END IF;
  IF jsonb_typeof(edited) <> 'object' THEN
    edited := '{}'::jsonb;
  END IF;
  FOR rec IN SELECT key, value FROM jsonb_each(edited)
  LOOP
    IF rec.value = 'null'::jsonb THEN
      IF baseline ? rec.key THEN
        result := result || jsonb_build_object(rec.key, null);
      END IF;
    ELSIF jsonb_typeof(rec.value) = 'object' AND jsonb_typeof(baseline->rec.key) = 'object' THEN
      child := portal.fn_jsonb_sparse_diff(baseline->rec.key, rec.value);
      IF child <> '{}'::jsonb THEN
        result := result || jsonb_build_object(rec.key, child);
      END IF;
    ELSIF (baseline->rec.key) IS DISTINCT FROM rec.value THEN
      result := result || jsonb_build_object(rec.key, rec.value);
    END IF;
  END LOOP;
  FOR rec IN SELECT key FROM jsonb_each(baseline)
  LOOP
    IF NOT (edited ? rec.key) THEN
      result := result || jsonb_build_object(rec.key, null);
    END IF;
  END LOOP;
  RETURN result;
END;
$$;

-- Editor bind surface: alignment_qc + extraction_qc, without workflow identity paths.
CREATE OR REPLACE FUNCTION portal.fn_jsonb_guardrail_slice(p_action_config jsonb)
RETURNS jsonb
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  src jsonb := COALESCE(p_action_config, '{}'::jsonb);
  aq jsonb;
  eq jsonb;
  out jsonb := '{}'::jsonb;
BEGIN
  aq := src->'alignment_qc';
  IF jsonb_typeof(aq) = 'object' THEN
    aq := aq - 'sample_paths' - 'output_dir' - 'validate_schema'
            - 'genome_fasta' - 'reference_fasta';
    out := jsonb_set(out, '{alignment_qc}', aq, true);
  ELSIF aq = 'null'::jsonb THEN
    out := jsonb_set(out, '{alignment_qc}', 'null'::jsonb, true);
  END IF;
  eq := src->'extraction_qc';
  IF jsonb_typeof(eq) = 'object' THEN
    eq := eq - 'sample_paths';
    out := jsonb_set(out, '{extraction_qc}', eq, true);
  ELSIF eq = 'null'::jsonb THEN
    out := jsonb_set(out, '{extraction_qc}', 'null'::jsonb, true);
  END IF;
  RETURN out;
END;
$$;

CREATE OR REPLACE FUNCTION portal.fn_study_guardrails_inherited(p_study_row_id bigint)
RETURNS TABLE (
  site_name text,
  pipeline_profile text,
  pipeline_procedure text,
  inherited_guardrails jsonb
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_doc jsonb;
  v_site_name text;
  v_site jsonb := '{}'::jsonb;
  v_profile jsonb := '{}'::jsonb;
  v_procedure jsonb := '{}'::jsonb;
BEGIN
  SELECT document_json INTO v_doc FROM cfg.study WHERE id = p_study_row_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'cfg.study not found';
  END IF;
  v_doc := COALESCE(v_doc, '{}'::jsonb);

  SELECT s.name, COALESCE(s.document_json->'actionConfig', '{}'::jsonb)
  INTO v_site_name, v_site
  FROM cfg.site s
  WHERE s.status = 'published'
  ORDER BY CASE WHEN s.name = 'default' THEN 0 ELSE 1 END, s.id DESC
  LIMIT 1;

  SELECT COALESCE(p.document_json->'actionConfig', '{}'::jsonb)
  INTO v_profile
  FROM cfg.pipeline_profile p
  WHERE p.name = v_doc->>'pipelineProfile'
    AND p.status IN ('published', 'retired')
  ORDER BY p.id DESC
  LIMIT 1;

  SELECT COALESCE(a.document_json->'actionConfig', '{}'::jsonb)
  INTO v_procedure
  FROM cfg.assay_procedure a
  WHERE a.name = v_doc->>'pipelineProcedure'
    AND a.status IN ('published', 'retired')
  ORDER BY a.id DESC
  LIMIT 1;

  RETURN QUERY SELECT
    v_site_name,
    v_doc->>'pipelineProfile',
    v_doc->>'pipelineProcedure',
    portal.fn_jsonb_deep_merge(
      portal.fn_jsonb_deep_merge(
        portal.fn_jsonb_guardrail_slice(v_site),
        portal.fn_jsonb_guardrail_slice(v_profile)
      ),
      portal.fn_jsonb_guardrail_slice(v_procedure)
    );
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_get_study_guardrails_editor(p_study_row_id bigint)
RETURNS TABLE (
  study_row_id bigint,
  study_name text,
  site_name text,
  pipeline_profile text,
  pipeline_procedure text,
  schema_id text,
  inherited_guardrails jsonb,
  study_guardrail_overlay jsonb,
  effective_guardrails jsonb
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_name text;
  v_overlay jsonb;
  v_inherited jsonb;
  v_site text;
  v_profile text;
  v_procedure text;
BEGIN
  IF p_study_row_id IS NULL OR p_study_row_id <= 0 THEN
    RAISE EXCEPTION 'study_row_id is required';
  END IF;

  SELECT s.name, COALESCE(s.document_json->'actionConfig', '{}'::jsonb)
  INTO v_name, v_overlay
  FROM cfg.study s
  WHERE s.id = p_study_row_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'cfg.study not found';
  END IF;

  SELECT i.site_name, i.pipeline_profile, i.pipeline_procedure, i.inherited_guardrails
  INTO v_site, v_profile, v_procedure, v_inherited
  FROM portal.fn_study_guardrails_inherited(p_study_row_id) i;

  RETURN QUERY SELECT
    p_study_row_id,
    v_name,
    v_site,
    v_profile,
    v_procedure,
    'study_action_config_overlay'::text,
    v_inherited,
    portal.fn_jsonb_guardrail_slice(v_overlay),
    portal.fn_jsonb_deep_merge(v_inherited, portal.fn_jsonb_guardrail_slice(v_overlay));
END;
$$;

-- Bind SchemaPropertyGrid to effective_guardrails + study_action_config_overlay schema.
-- Persist only the computed diff; other actionConfig keys (HPO validation, …) stay.
CREATE OR REPLACE FUNCTION portal.sp_set_study_guardrails_editor(
  p_study_row_id bigint,
  p_edited_effective jsonb
)
RETURNS TABLE (
  study_row_id bigint,
  study_name text,
  site_name text,
  pipeline_profile text,
  pipeline_procedure text,
  schema_id text,
  inherited_guardrails jsonb,
  study_guardrail_overlay jsonb,
  effective_guardrails jsonb
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_doc jsonb;
  v_existing jsonb;
  v_inherited jsonb;
  v_edited jsonb;
  v_diff jsonb;
  v_new jsonb;
  rec record;
BEGIN
  IF p_study_row_id IS NULL OR p_study_row_id <= 0 THEN
    RAISE EXCEPTION 'study_row_id is required';
  END IF;
  IF p_edited_effective IS NULL OR jsonb_typeof(p_edited_effective) <> 'object' THEN
    RAISE EXCEPTION 'edited_effective must be a JSON object (full working document)';
  END IF;

  SELECT document_json INTO v_doc FROM cfg.study WHERE id = p_study_row_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'cfg.study not found';
  END IF;
  v_doc := COALESCE(v_doc, '{}'::jsonb);
  v_existing := COALESCE(v_doc->'actionConfig', '{}'::jsonb);
  IF jsonb_typeof(v_existing) <> 'object' THEN
    v_existing := '{}'::jsonb;
  END IF;

  SELECT i.inherited_guardrails INTO v_inherited
  FROM portal.fn_study_guardrails_inherited(p_study_row_id) i;

  v_edited := portal.fn_jsonb_guardrail_slice(p_edited_effective);
  v_diff := portal.fn_jsonb_sparse_diff(v_inherited, v_edited);

  v_new := v_existing - 'alignment_qc' - 'extraction_qc';
  FOR rec IN SELECT key, value FROM jsonb_each(v_diff)
  LOOP
    IF rec.value IS NULL OR rec.value = 'null'::jsonb THEN
      CONTINUE;
    END IF;
    v_new := jsonb_set(v_new, ARRAY[rec.key], rec.value, true);
  END LOOP;

  v_doc := jsonb_set(v_doc, '{actionConfig}', v_new, true);

  UPDATE cfg.study
  SET document_json = v_doc,
      content_hash = encode(digest(v_doc::text, 'sha256'), 'hex'),
      updated_at_utc = now() AT TIME ZONE 'utc'
  WHERE id = p_study_row_id;

  RETURN QUERY SELECT * FROM portal.sp_get_study_guardrails_editor(p_study_row_id);
END;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'portal' AND p.proname = 'sp_create_and_start_instance'
  LOOP
    EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION portal.sp_create_and_start_instance(
  p_workflow_version_id bigint,
  p_context_json jsonb DEFAULT NULL,
  p_scope_id int DEFAULT NULL,
  p_study_row_id bigint DEFAULT NULL,
  p_domain_program_id bigint DEFAULT NULL,
  p_pipeline_profile_id bigint DEFAULT NULL,
  p_site_id bigint DEFAULT NULL,
  p_storage_profile_id bigint DEFAULT NULL,
  p_assay_procedure_id bigint DEFAULT NULL
)
RETURNS TABLE (
  id bigint,
  workflow_version_id bigint,
  status text
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_instance_id bigint;
  v_pack varchar(32);
  v_allowed boolean;
  v_cid int;
  v_def_id bigint;
  v_cwe_enabled boolean;
  v_max_runs int;
  v_period_type text;
  v_period_start timestamptz;
  v_runs int := 0;
  v_now timestamptz := now() AT TIME ZONE 'utc';
BEGIN
  IF p_scope_id IS NOT NULL THEN
    SELECT a.is_allowed, a.contract_id
      INTO v_allowed, v_cid
    FROM "Contract".spcontractvalidatescopeaccess(p_scope_id, v_now) a;

    IF NOT COALESCE(v_allowed, false) THEN
      RAISE EXCEPTION 'NO_ACTIVE_CONTRACT_FOR_SCOPE';
    END IF;

    v_pack := portal.fn_infer_process_pack_from_context(p_context_json);
    IF NOT EXISTS (
      SELECT 1 FROM portal.fn_contract_entitled_modalities(p_scope_id) m
      WHERE m.modality = v_pack
    ) THEN
      RAISE EXCEPTION 'PROCESS_PACK_NOT_ENTITLED';
    END IF;

    SELECT wv.workflow_def_id INTO v_def_id
    FROM wf.workflow_version wv
    WHERE wv.id = p_workflow_version_id;
    IF v_def_id IS NULL THEN
      RAISE EXCEPTION 'workflow_version_id not found';
    END IF;

    SELECT e."Enabled", e."MaxRunsPerPeriod", e."PeriodType"
      INTO v_cwe_enabled, v_max_runs, v_period_type
    FROM "Contract"."ContractWorkflowEntitlements" e
    WHERE e."ContractID" = v_cid AND e."WorkflowDefID" = v_def_id;

    IF v_cwe_enabled IS NOT NULL AND NOT v_cwe_enabled THEN
      RAISE EXCEPTION 'WORKFLOW_NOT_ENTITLED';
    END IF;

    IF COALESCE(v_cwe_enabled, false) AND v_max_runs IS NOT NULL AND v_period_type IS NOT NULL THEN
      v_period_start := CASE v_period_type
        WHEN 'DAY' THEN date_trunc('day', v_now)
        WHEN 'WEEK' THEN date_trunc('week', v_now)
        WHEN 'MONTH' THEN date_trunc('month', v_now)
      END;
      SELECT COALESCE(w."RunsExecuted", 0) INTO v_runs
      FROM "Contract"."WorkflowUsageCounters" w
      WHERE w."ContractID" = v_cid
        AND w."ScopeID" = p_scope_id
        AND w."WorkflowDefID" = v_def_id
        AND w."PeriodType" = v_period_type
        AND w."PeriodStartUtc" = v_period_start;
      IF COALESCE(v_runs, 0) >= v_max_runs THEN
        RAISE EXCEPTION 'WORKFLOW_QUOTA_EXCEEDED';
      END IF;
    END IF;
  END IF;

  SELECT created.id INTO v_instance_id
  FROM wf.wf_repo_create_workflow_instance(p_workflow_version_id, p_context_json) AS created;

  CALL wf.sp_start_workflow_instance(v_instance_id);

  IF p_study_row_id IS NOT NULL THEN
    PERFORM portal.sp_link_study_instance(
      p_study_row_id,
      v_instance_id,
      p_domain_program_id,
      p_pipeline_profile_id,
      p_site_id,
      p_storage_profile_id,
      p_assay_procedure_id
    );
  END IF;

  RETURN QUERY SELECT * FROM wf.wf_repo_get_workflow_instance(v_instance_id);
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_get_workflow_instance_header(p_workflow_instance_id bigint)
RETURNS TABLE (
  workflow_instance_id bigint,
  status text,
  workflow_version_id bigint,
  workflow_def_id bigint,
  workflow_name text,
  instance_kind text,
  version_major int,
  version_minor int,
  started_at_utc timestamptz,
  completed_at_utc timestamptz,
  study_row_id bigint,
  study_name text,
  pipeline_profile_id bigint,
  pipeline_profile text,
  assay_procedure_id bigint,
  assay_procedure text,
  context_pipeline_profile text,
  context_pipeline_procedure text,
  project_path text,
  primary_analyte text,
  sample_count bigint,
  failed_count bigint,
  running_count bigint,
  queued_count bigint,
  succeeded_count bigint,
  task_count bigint
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    i.id,
    i.status,
    i.workflow_version_id,
    d.id,
    d.name,
    wf.fn_instance_kind(d.name),
    v.version_major,
    v.version_minor,
    i.started_at_utc,
    i.completed_at_utc,
    l.study_row_id,
    st.name,
    l.pipeline_profile_id,
    pp.name,
    l.assay_procedure_id,
    ap.name,
    i.context_json ->> 'pipelineProfile',
    i.context_json ->> 'pipelineProcedure',
    i.context_json ->> 'projectPath',
    i.context_json ->> 'primaryAnalyte',
    CASE
      WHEN jsonb_typeof(i.context_json -> 'samples') = 'array'
        THEN jsonb_array_length(i.context_json -> 'samples')
      ELSE 0
    END,
    COUNT(*) FILTER (WHERE ne.status = 'FAILED'),
    COUNT(*) FILTER (WHERE ne.status = 'RUNNING'),
    COUNT(*) FILTER (WHERE ne.status IN ('READY', 'PENDING')),
    COUNT(*) FILTER (WHERE ne.status = 'SUCCEEDED'),
    COUNT(ne.id)
  FROM wf.workflow_instance i
  INNER JOIN wf.workflow_version v ON v.id = i.workflow_version_id
  INNER JOIN wf.workflow_def d ON d.id = v.workflow_def_id
  LEFT JOIN cfg.study_instance_link l ON l.workflow_instance_id = i.id
  LEFT JOIN cfg.study st ON st.id = l.study_row_id
  LEFT JOIN cfg.pipeline_profile pp ON pp.id = l.pipeline_profile_id
  LEFT JOIN cfg.assay_procedure ap ON ap.id = l.assay_procedure_id
  LEFT JOIN wf.node_execution ne ON ne.workflow_instance_id = i.id
  WHERE i.id = p_workflow_instance_id
  GROUP BY
    i.id, i.status, i.workflow_version_id, d.id, d.name,
    v.version_major, v.version_minor, i.started_at_utc, i.completed_at_utc,
    i.context_json, l.study_row_id, st.name, l.pipeline_profile_id, pp.name,
    l.assay_procedure_id, ap.name;
$$;

CREATE OR REPLACE FUNCTION portal.sp_get_instance_config(p_workflow_instance_id bigint)
RETURNS TABLE (
  workflow_instance_id bigint,
  execution_scope_key text,
  context_json_redacted jsonb,
  execution_scope_config_redacted jsonb,
  resolved_config_json jsonb
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM wf.workflow_instance i WHERE i.id = p_workflow_instance_id) THEN
    RAISE EXCEPTION 'workflow_instance not found';
  END IF;

  RETURN QUERY
  SELECT
    i.id,
    es.set_key,
    portal.fn_redact_json_credentials(i.context_json),
    portal.fn_redact_json_credentials(es.config_json),
    COALESCE((
      SELECT jsonb_object_agg(sv.var_name, sv.value_json)
      FROM wf.scope_variable sv
      WHERE sv.workflow_instance_id = i.id
        AND sv.var_name LIKE 'resolvedConfig__%'
    ), '{}'::jsonb)
  FROM wf.workflow_instance i
  LEFT JOIN wf.execution_scope es ON es.id = i.execution_scope_id
  WHERE i.id = p_workflow_instance_id;
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_get_instance_sample_progress(p_workflow_instance_id bigint)
RETURNS TABLE (
  node_execution_id bigint,
  sample_id text,
  stage_key text,
  stage_seq smallint,
  action_name text,
  node_key text,
  status text,
  result_code int,
  engine_error_code int,
  engine_error_message text,
  attempt_no int,
  stop_requested boolean,
  started_at_utc timestamptz,
  completed_at_utc timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    ne.id,
    COALESCE(ne.input_json ->> 'sampleId', ne.input_json ->> 'sample_id'),
    COALESCE(st.stage_key, 'other'),
    COALESCE(st.stage_seq, 999::smallint),
    wa.action_name,
    wn.node_key,
    ne.status,
    ne.result_code,
    ne.engine_error_code,
    ne.engine_error_message,
    ne.attempt_no,
    ne.stop_requested,
    ne.started_at_utc,
    ne.ended_at_utc
  FROM wf.node_execution ne
  INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
  LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
  LEFT JOIN LATERAL wf.fn_pipeline_stage_for_action(wa.action_name) st ON true
  WHERE ne.workflow_instance_id = p_workflow_instance_id
    AND COALESCE(ne.input_json ->> 'sampleId', ne.input_json ->> 'sample_id') IS NOT NULL
  ORDER BY 2, COALESCE(st.stage_seq, 999::smallint), ne.id;
$$;

CREATE OR REPLACE FUNCTION portal.sp_fail_node(
  p_node_execution_id bigint,
  p_error_message text DEFAULT NULL
)
RETURNS TABLE (
  node_execution_id bigint,
  status text,
  engine_error_code int,
  instance_status text
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_status text;
  v_instance_id bigint;
BEGIN
  IF p_node_execution_id IS NULL OR p_node_execution_id <= 0 THEN
    RAISE EXCEPTION 'node_execution_id is required';
  END IF;

  SELECT ne.status, ne.workflow_instance_id
    INTO v_status, v_instance_id
  FROM wf.node_execution ne
  WHERE ne.id = p_node_execution_id
  FOR UPDATE;

  IF v_instance_id IS NULL THEN
    RAISE EXCEPTION 'node_execution not found';
  END IF;
  IF v_status NOT IN ('READY', 'PENDING') THEN
    RAISE EXCEPTION 'Only READY or PENDING tasks can be operator-failed. Use Stop for in-flight.';
  END IF;

  DELETE FROM wf.task_lease WHERE node_execution_id = p_node_execution_id;

  UPDATE wf.node_execution
  SET status = 'FAILED',
      result_code = 4098,
      engine_error_code = 4098,
      engine_error_message = COALESCE(NULLIF(btrim(p_error_message), ''), 'OPERATOR_FAILED'),
      ended_at_utc = now() AT TIME ZONE 'utc',
      stop_requested = false
  WHERE id = p_node_execution_id;

  RETURN QUERY
  SELECT ne.id, ne.status, ne.engine_error_code, i.status
  FROM wf.node_execution ne
  INNER JOIN wf.workflow_instance i ON i.id = ne.workflow_instance_id
  WHERE ne.id = p_node_execution_id;
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_stop_node(
  p_node_execution_id bigint,
  p_error_message text DEFAULT NULL
)
RETURNS TABLE (
  node_execution_id bigint,
  status text,
  stop_requested boolean,
  command text
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_status text;
  v_can_stop boolean;
BEGIN
  IF p_node_execution_id IS NULL OR p_node_execution_id <= 0 THEN
    RAISE EXCEPTION 'node_execution_id is required';
  END IF;

  SELECT ne.status, COALESCE(wa.can_stop, true)
    INTO v_status, v_can_stop
  FROM wf.node_execution ne
  INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
  LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
  WHERE ne.id = p_node_execution_id;

  IF v_status IS NULL THEN
    RAISE EXCEPTION 'node_execution not found';
  END IF;
  IF v_status <> 'RUNNING' THEN
    RAISE EXCEPTION 'Only RUNNING tasks can be stopped';
  END IF;
  IF NOT COALESCE(v_can_stop, true) THEN
    RAISE EXCEPTION 'This action cannot be stopped (catalog can_stop=false)';
  END IF;

  UPDATE wf.node_execution
  SET stop_requested = true,
      engine_error_code = COALESCE(engine_error_code, 4099),
      engine_error_message = COALESCE(NULLIF(btrim(p_error_message), ''), 'STOP_REQUESTED')
  WHERE id = p_node_execution_id;

  RETURN QUERY
  SELECT ne.id, ne.status, ne.stop_requested, 'STOP'::text
  FROM wf.node_execution ne
  WHERE ne.id = p_node_execution_id;
END;
$$;

-- Drain READY/PENDING and mark the instance CANCELLED. Engine activate/continue
-- refuse new work unless workflow_instance.status is still RUNNING.
CREATE OR REPLACE FUNCTION portal.sp_cancel_instance(
  p_workflow_instance_id bigint,
  p_error_message text DEFAULT NULL,
  p_stop_inflight boolean DEFAULT false
)
RETURNS TABLE (
  workflow_instance_id bigint,
  status text,
  queued_cancelled bigint
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_status text;
  v_reason text := COALESCE(NULLIF(btrim(p_error_message), ''), 'OPERATOR_CANCELLED');
  v_queued bigint := 0;
BEGIN
  IF p_workflow_instance_id IS NULL OR p_workflow_instance_id <= 0 THEN
    RAISE EXCEPTION 'workflow_instance_id is required';
  END IF;

  SELECT i.status INTO v_status
  FROM wf.workflow_instance i
  WHERE i.id = p_workflow_instance_id
  FOR UPDATE;

  IF v_status IS NULL THEN
    RAISE EXCEPTION 'workflow_instance not found';
  END IF;
  IF v_status = 'COMPLETED' THEN
    RAISE EXCEPTION 'Cannot cancel a COMPLETED instance';
  END IF;
  IF v_status = 'CANCELLED' THEN
    RETURN QUERY SELECT p_workflow_instance_id, v_status, 0::bigint;
    RETURN;
  END IF;

  DELETE FROM wf.task_lease tl
  USING wf.node_execution ne
  WHERE ne.id = tl.node_execution_id
    AND ne.workflow_instance_id = p_workflow_instance_id
    AND ne.status IN ('READY', 'PENDING');

  UPDATE wf.node_execution
  SET status = 'CANCELLED',
      result_code = 4097,
      engine_error_code = 4097,
      engine_error_message = v_reason,
      ended_at_utc = now() AT TIME ZONE 'utc',
      stop_requested = false
  WHERE workflow_instance_id = p_workflow_instance_id
    AND status IN ('READY', 'PENDING');
  GET DIAGNOSTICS v_queued = ROW_COUNT;

  IF COALESCE(p_stop_inflight, false) THEN
    UPDATE wf.node_execution ne
    SET stop_requested = true,
        engine_error_code = COALESCE(ne.engine_error_code, 4099),
        engine_error_message = COALESCE(ne.engine_error_message, v_reason)
    FROM wf.workflow_node wn
    LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
    WHERE wn.id = ne.workflow_node_id
      AND ne.workflow_instance_id = p_workflow_instance_id
      AND ne.status = 'RUNNING'
      AND COALESCE(wa.can_stop, true);
  END IF;

  UPDATE wf.workflow_instance
  SET status = 'CANCELLED',
      completed_at_utc = now() AT TIME ZONE 'utc'
  WHERE id = p_workflow_instance_id;

  CALL wf.wf_repo_upsert_instance_extension(
    p_workflow_instance_id,
    'portal.operator_cancel',
    jsonb_build_object('reason', v_reason)
  );

  RETURN QUERY SELECT p_workflow_instance_id, 'CANCELLED'::text, v_queued;
END;
$$;

-- Same drain as cancel, instance FAILED. Engine continue/activate still require
-- status = RUNNING, so in-flight success cannot enqueue later stages.

CREATE OR REPLACE FUNCTION portal.sp_fail_instance(
  p_workflow_instance_id bigint,
  p_error_message text DEFAULT NULL,
  p_stop_inflight boolean DEFAULT false
)
RETURNS TABLE (
  workflow_instance_id bigint,
  status text,
  queued_failed bigint
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_status text;
  v_reason text := COALESCE(NULLIF(btrim(p_error_message), ''), 'OPERATOR_FAILED');
  v_queued bigint := 0;
BEGIN
  IF p_workflow_instance_id IS NULL OR p_workflow_instance_id <= 0 THEN
    RAISE EXCEPTION 'workflow_instance_id is required';
  END IF;

  SELECT i.status INTO v_status
  FROM wf.workflow_instance i
  WHERE i.id = p_workflow_instance_id
  FOR UPDATE;

  IF v_status IS NULL THEN
    RAISE EXCEPTION 'workflow_instance not found';
  END IF;
  IF v_status = 'COMPLETED' THEN
    RAISE EXCEPTION 'Cannot fail a COMPLETED instance';
  END IF;
  IF v_status = 'FAILED' THEN
    RETURN QUERY SELECT p_workflow_instance_id, v_status, 0::bigint;
    RETURN;
  END IF;

  DELETE FROM wf.task_lease tl
  USING wf.node_execution ne
  WHERE ne.id = tl.node_execution_id
    AND ne.workflow_instance_id = p_workflow_instance_id
    AND ne.status IN ('READY', 'PENDING');

  UPDATE wf.node_execution
  SET status = 'FAILED',
      result_code = 4098,
      engine_error_code = 4098,
      engine_error_message = v_reason,
      ended_at_utc = now() AT TIME ZONE 'utc',
      stop_requested = false
  WHERE workflow_instance_id = p_workflow_instance_id
    AND status IN ('READY', 'PENDING');
  GET DIAGNOSTICS v_queued = ROW_COUNT;

  IF COALESCE(p_stop_inflight, false) THEN
    UPDATE wf.node_execution ne
    SET stop_requested = true,
        engine_error_code = COALESCE(ne.engine_error_code, 4099),
        engine_error_message = COALESCE(ne.engine_error_message, v_reason)
    FROM wf.workflow_node wn
    LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
    WHERE wn.id = ne.workflow_node_id
      AND ne.workflow_instance_id = p_workflow_instance_id
      AND ne.status = 'RUNNING'
      AND COALESCE(wa.can_stop, true);
  END IF;

  UPDATE wf.workflow_instance
  SET status = 'FAILED',
      completed_at_utc = now() AT TIME ZONE 'utc'
  WHERE id = p_workflow_instance_id;

  CALL wf.wf_repo_upsert_instance_extension(
    p_workflow_instance_id,
    'portal.operator_fail',
    jsonb_build_object('reason', v_reason)
  );

  RETURN QUERY SELECT p_workflow_instance_id, 'FAILED'::text, v_queued;
END;
$$;

CREATE OR REPLACE FUNCTION wf.sp_worker_heartbeat(
  p_node_execution_id bigint,
  p_worker_id bigint,
  p_worker_token text,
  p_extend_seconds int DEFAULT 300
)
RETURNS TABLE (rows_updated int, desired_state text, command text)
LANGUAGE plpgsql
AS $$
DECLARE
  v_now timestamptz := (now() AT TIME ZONE 'utc');
  v_rows int;
  v_desired_state text := 'ACTIVE';
  v_command text := 'NONE';
  v_stop boolean := false;
BEGIN
  CALL wf.wf_worker_authenticate(p_worker_id, p_worker_token);

  UPDATE wf.task_lease tl
  SET lease_expires_at_utc = v_now + make_interval(secs => p_extend_seconds),
      heartbeat_at_utc = v_now
  WHERE tl.node_execution_id = p_node_execution_id
    AND tl.worker_id = p_worker_id;

  GET DIAGNOSTICS v_rows = ROW_COUNT;

  SELECT coalesce(w.desired_state, 'ACTIVE')
    INTO v_desired_state
  FROM wf.worker w
  WHERE w.id = p_worker_id;

  SELECT coalesce(ne.stop_requested, false)
    INTO v_stop
  FROM wf.node_execution ne
  WHERE ne.id = p_node_execution_id;

  v_command := CASE
    WHEN v_stop THEN 'STOP'
    WHEN v_desired_state = 'DRAINING' THEN 'DRAIN'
    WHEN v_desired_state = 'STOPPING' THEN 'STOP'
    ELSE 'NONE'
  END;

  RETURN QUERY SELECT v_rows, v_desired_state, v_command;
END;
$$;
