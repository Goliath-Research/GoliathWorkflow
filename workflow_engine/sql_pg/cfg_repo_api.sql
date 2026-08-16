-- cfg repository API (PostgreSQL): upsert / get / list / publish / set compiled version

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'cfg' AND p.proname = '_content_hash'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION cfg._content_hash(doc jsonb)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT md5(doc::text);
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'cfg' AND p.proname = 'cfg_repo_upsert'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION cfg.cfg_repo_upsert(
  p_kind text,
  p_name text,
  p_version text,
  p_status text,
  p_document jsonb,
  p_secret jsonb DEFAULT NULL,
  p_provider text DEFAULT NULL,
  p_auth_mode text DEFAULT NULL,
  p_credential_name text DEFAULT NULL,
  p_study_id text DEFAULT NULL,
  p_implementation_status text DEFAULT NULL
)
RETURNS TABLE(id bigint)
LANGUAGE plpgsql
AS $$
DECLARE
  v_hash text := cfg._content_hash(COALESCE(p_document, p_secret, '{}'::jsonb));
  v_id bigint;
  v_status text := COALESCE(NULLIF(p_status, ''), 'draft');
  v_version text := COALESCE(NULLIF(p_version, ''), '1');
BEGIN
  IF p_kind = 'site' THEN
    INSERT INTO cfg.site(name, version, status, content_hash, document_json)
    VALUES (p_name, v_version, v_status, v_hash, p_document)
    ON CONFLICT (name, version) DO UPDATE SET
      status = EXCLUDED.status,
      content_hash = EXCLUDED.content_hash,
      document_json = EXCLUDED.document_json,
      updated_at_utc = (now() AT TIME ZONE 'utc')
    RETURNING cfg.site.id INTO v_id;
  ELSIF p_kind = 'pipeline_profile' THEN
    INSERT INTO cfg.pipeline_profile(name, version, status, content_hash, document_json)
    VALUES (p_name, v_version, v_status, v_hash, p_document)
    ON CONFLICT (name, version) DO UPDATE SET
      status = EXCLUDED.status,
      content_hash = EXCLUDED.content_hash,
      document_json = EXCLUDED.document_json,
      updated_at_utc = (now() AT TIME ZONE 'utc')
    RETURNING cfg.pipeline_profile.id INTO v_id;
  ELSIF p_kind = 'assay_procedure' THEN
    INSERT INTO cfg.assay_procedure(name, version, status, content_hash, document_json)
    VALUES (p_name, v_version, v_status, v_hash, p_document)
    ON CONFLICT (name, version) DO UPDATE SET
      status = EXCLUDED.status,
      content_hash = EXCLUDED.content_hash,
      document_json = EXCLUDED.document_json,
      updated_at_utc = (now() AT TIME ZONE 'utc')
    RETURNING cfg.assay_procedure.id INTO v_id;
  ELSIF p_kind = 'analyte' THEN
    INSERT INTO cfg.analyte(name, version, status, content_hash, document_json)
    VALUES (p_name, v_version, v_status, v_hash, p_document)
    ON CONFLICT (name, version) DO UPDATE SET
      status = EXCLUDED.status,
      content_hash = EXCLUDED.content_hash,
      document_json = EXCLUDED.document_json,
      updated_at_utc = (now() AT TIME ZONE 'utc')
    RETURNING cfg.analyte.id INTO v_id;
  ELSIF p_kind = 'domain_program' THEN
    INSERT INTO cfg.domain_program(name, version, status, content_hash, document_json)
    VALUES (p_name, v_version, v_status, v_hash, p_document)
    ON CONFLICT (name, version) DO UPDATE SET
      status = EXCLUDED.status,
      content_hash = EXCLUDED.content_hash,
      document_json = EXCLUDED.document_json,
      updated_at_utc = (now() AT TIME ZONE 'utc')
    RETURNING cfg.domain_program.id INTO v_id;
  ELSIF p_kind = 'study' THEN
    INSERT INTO cfg.study(name, version, status, content_hash, document_json, study_id)
    VALUES (p_name, v_version, v_status, v_hash, p_document, p_study_id)
    ON CONFLICT (name, version) DO UPDATE SET
      status = EXCLUDED.status,
      content_hash = EXCLUDED.content_hash,
      document_json = EXCLUDED.document_json,
      study_id = COALESCE(EXCLUDED.study_id, cfg.study.study_id),
      updated_at_utc = (now() AT TIME ZONE 'utc')
    RETURNING cfg.study.id INTO v_id;
  ELSIF p_kind = 'credential' THEN
    INSERT INTO cfg.credential(name, version, status, content_hash, provider, auth_mode, secret_json)
    VALUES (p_name, v_version, v_status, v_hash, COALESCE(p_provider, 'unknown'), COALESCE(p_auth_mode, 'unknown'), COALESCE(p_secret, p_document))
    ON CONFLICT (name, version) DO UPDATE SET
      status = EXCLUDED.status,
      content_hash = EXCLUDED.content_hash,
      provider = EXCLUDED.provider,
      auth_mode = EXCLUDED.auth_mode,
      secret_json = EXCLUDED.secret_json,
      updated_at_utc = (now() AT TIME ZONE 'utc')
    RETURNING cfg.credential.id INTO v_id;
  ELSIF p_kind = 'storage_endpoint' THEN
    INSERT INTO cfg.storage_endpoint(name, version, status, content_hash, provider, location_json, credential_name)
    VALUES (p_name, v_version, v_status, v_hash, COALESCE(p_provider, p_document->>'type', 'unknown'), p_document, p_credential_name)
    ON CONFLICT (name, version) DO UPDATE SET
      status = EXCLUDED.status,
      content_hash = EXCLUDED.content_hash,
      provider = EXCLUDED.provider,
      location_json = EXCLUDED.location_json,
      credential_name = COALESCE(EXCLUDED.credential_name, cfg.storage_endpoint.credential_name),
      updated_at_utc = (now() AT TIME ZONE 'utc')
    RETURNING cfg.storage_endpoint.id INTO v_id;
  ELSIF p_kind = 'storage_profile' THEN
    INSERT INTO cfg.storage_profile(name, version, status, content_hash, document_json)
    VALUES (p_name, v_version, v_status, v_hash, p_document)
    ON CONFLICT (name, version) DO UPDATE SET
      status = EXCLUDED.status,
      content_hash = EXCLUDED.content_hash,
      document_json = EXCLUDED.document_json,
      updated_at_utc = (now() AT TIME ZONE 'utc')
    RETURNING cfg.storage_profile.id INTO v_id;
  ELSIF p_kind = 'reference_asset' THEN
    INSERT INTO cfg.reference_asset(name, version, status, content_hash, document_json)
    VALUES (p_name, v_version, v_status, v_hash, p_document)
    ON CONFLICT (name, version) DO UPDATE SET
      status = EXCLUDED.status,
      content_hash = EXCLUDED.content_hash,
      document_json = EXCLUDED.document_json,
      updated_at_utc = (now() AT TIME ZONE 'utc')
    RETURNING cfg.reference_asset.id INTO v_id;
  ELSIF p_kind = 'action_definition' THEN
    RAISE EXCEPTION 'cfg.action_definition retired; seed wf via seed_action_catalog / methyl-cfg sync-actions';
  ELSIF p_kind = 'enrichment_library_preset' THEN
    INSERT INTO cfg.enrichment_library_preset(name, version, status, content_hash, document_json)
    VALUES (p_name, v_version, v_status, v_hash, p_document)
    ON CONFLICT (name, version) DO UPDATE SET
      status = EXCLUDED.status,
      content_hash = EXCLUDED.content_hash,
      document_json = EXCLUDED.document_json,
      updated_at_utc = (now() AT TIME ZONE 'utc')
    RETURNING cfg.enrichment_library_preset.id INTO v_id;
  ELSE
    RAISE EXCEPTION 'unknown cfg kind: %', p_kind;
  END IF;
  id := v_id;
  RETURN NEXT;
END;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'cfg' AND p.proname = 'cfg_repo_get'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION cfg.cfg_repo_get(
  p_kind text,
  p_name text,
  p_version text DEFAULT NULL,
  p_published_only boolean DEFAULT false
)
RETURNS TABLE(
  id bigint,
  name text,
  version text,
  status text,
  content_hash text,
  document_json jsonb,
  secret_redacted jsonb,
  extra jsonb
)
LANGUAGE plpgsql
AS $$
BEGIN
  IF p_kind = 'credential' THEN
    RETURN QUERY
    SELECT c.id, c.name, c.version, c.status::text, c.content_hash,
           jsonb_build_object('provider', c.provider, 'authMode', c.auth_mode),
           jsonb_build_object('authMode', c.auth_mode),
           jsonb_build_object('provider', c.provider, 'authMode', c.auth_mode)
    FROM cfg.credential c
    WHERE c.name = p_name
      AND (p_version IS NULL OR c.version = p_version)
      AND (NOT p_published_only OR c.status = 'published')
    ORDER BY c.id DESC
    LIMIT 1;
  ELSIF p_kind = 'storage_endpoint' THEN
    RETURN QUERY
    SELECT e.id, e.name, e.version, e.status::text, e.content_hash, e.location_json,
           NULL::jsonb,
           jsonb_build_object('provider', e.provider, 'credentialName', e.credential_name)
    FROM cfg.storage_endpoint e
    WHERE e.name = p_name
      AND (p_version IS NULL OR e.version = p_version)
      AND (NOT p_published_only OR e.status = 'published')
    ORDER BY e.id DESC
    LIMIT 1;
  ELSIF p_kind = 'site' THEN
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash, s.document_json, NULL::jsonb, NULL::jsonb
    FROM cfg.site s WHERE s.name = p_name AND (p_version IS NULL OR s.version = p_version)
      AND (NOT p_published_only OR s.status = 'published') ORDER BY s.id DESC LIMIT 1;
  ELSIF p_kind = 'pipeline_profile' THEN
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash, s.document_json, NULL::jsonb, NULL::jsonb
    FROM cfg.pipeline_profile s WHERE s.name = p_name AND (p_version IS NULL OR s.version = p_version)
      AND (NOT p_published_only OR s.status = 'published') ORDER BY s.id DESC LIMIT 1;
  ELSIF p_kind = 'assay_procedure' THEN
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash, s.document_json, NULL::jsonb, NULL::jsonb
    FROM cfg.assay_procedure s WHERE s.name = p_name AND (p_version IS NULL OR s.version = p_version)
      AND (NOT p_published_only OR s.status = 'published') ORDER BY s.id DESC LIMIT 1;
  ELSIF p_kind = 'analyte' THEN
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash, s.document_json, NULL::jsonb, NULL::jsonb
    FROM cfg.analyte s WHERE s.name = p_name AND (p_version IS NULL OR s.version = p_version)
      AND (NOT p_published_only OR s.status = 'published') ORDER BY s.id DESC LIMIT 1;
  ELSIF p_kind = 'domain_program' THEN
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash, s.document_json, NULL::jsonb,
      jsonb_build_object('compiledWorkflowVersionId', s.compiled_workflow_version_id)
    FROM cfg.domain_program s WHERE s.name = p_name AND (p_version IS NULL OR s.version = p_version)
      AND (NOT p_published_only OR s.status = 'published') ORDER BY s.id DESC LIMIT 1;
  ELSIF p_kind = 'study' THEN
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash, s.document_json, NULL::jsonb,
      jsonb_build_object('studyId', s.study_id)
    FROM cfg.study s WHERE s.name = p_name AND (p_version IS NULL OR s.version = p_version)
      AND (NOT p_published_only OR s.status = 'published') ORDER BY s.id DESC LIMIT 1;
  ELSIF p_kind = 'storage_profile' THEN
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash, s.document_json, NULL::jsonb, NULL::jsonb
    FROM cfg.storage_profile s WHERE s.name = p_name AND (p_version IS NULL OR s.version = p_version)
      AND (NOT p_published_only OR s.status = 'published') ORDER BY s.id DESC LIMIT 1;
  ELSIF p_kind = 'reference_asset' THEN
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash, s.document_json, NULL::jsonb, NULL::jsonb
    FROM cfg.reference_asset s WHERE s.name = p_name AND (p_version IS NULL OR s.version = p_version)
      AND (NOT p_published_only OR s.status = 'published') ORDER BY s.id DESC LIMIT 1;
  ELSIF p_kind = 'action_definition' THEN
    RAISE EXCEPTION 'cfg.action_definition retired; use portal.sp_get_workflow_action / wf.data_type';
  ELSIF p_kind = 'enrichment_library_preset' THEN
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash, s.document_json, NULL::jsonb, NULL::jsonb
    FROM cfg.enrichment_library_preset s WHERE s.name = p_name AND (p_version IS NULL OR s.version = p_version)
      AND (NOT p_published_only OR s.status = 'published') ORDER BY s.id DESC LIMIT 1;
  ELSE
    RAISE EXCEPTION 'unknown cfg kind: %', p_kind;
  END IF;
END;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'cfg' AND p.proname = 'cfg_repo_list'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION cfg.cfg_repo_list(
  p_kind text,
  p_published_only boolean DEFAULT false
)
RETURNS TABLE(
  id bigint,
  name text,
  version text,
  status text,
  content_hash text
)
LANGUAGE plpgsql
AS $$
BEGIN
  IF p_kind = 'site' THEN
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash FROM cfg.site s
      WHERE NOT p_published_only OR s.status = 'published' ORDER BY s.name, s.version;
  ELSIF p_kind = 'pipeline_profile' THEN
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash FROM cfg.pipeline_profile s
      WHERE NOT p_published_only OR s.status = 'published' ORDER BY s.name, s.version;
  ELSIF p_kind = 'assay_procedure' THEN
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash FROM cfg.assay_procedure s
      WHERE NOT p_published_only OR s.status = 'published' ORDER BY s.name, s.version;
  ELSIF p_kind = 'analyte' THEN
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash FROM cfg.analyte s
      WHERE NOT p_published_only OR s.status = 'published' ORDER BY s.name, s.version;
  ELSIF p_kind = 'domain_program' THEN
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash FROM cfg.domain_program s
      WHERE NOT p_published_only OR s.status = 'published' ORDER BY s.name, s.version;
  ELSIF p_kind = 'study' THEN
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash FROM cfg.study s
      WHERE NOT p_published_only OR s.status = 'published' ORDER BY s.name, s.version;
  ELSIF p_kind = 'credential' THEN
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash FROM cfg.credential s
      WHERE NOT p_published_only OR s.status = 'published' ORDER BY s.name, s.version;
  ELSIF p_kind = 'storage_endpoint' THEN
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash FROM cfg.storage_endpoint s
      WHERE NOT p_published_only OR s.status = 'published' ORDER BY s.name, s.version;
  ELSIF p_kind = 'storage_profile' THEN
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash FROM cfg.storage_profile s
      WHERE NOT p_published_only OR s.status = 'published' ORDER BY s.name, s.version;
  ELSIF p_kind = 'reference_asset' THEN
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash FROM cfg.reference_asset s
      WHERE NOT p_published_only OR s.status = 'published' ORDER BY s.name, s.version;
  ELSIF p_kind = 'action_definition' THEN
    RAISE EXCEPTION 'cfg.action_definition retired; use portal.sp_list_workflow_actions';
  ELSIF p_kind = 'enrichment_library_preset' THEN
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash FROM cfg.enrichment_library_preset s
      WHERE NOT p_published_only OR s.status = 'published' ORDER BY s.name, s.version;
  ELSE
    RAISE EXCEPTION 'unknown cfg kind: %', p_kind;
  END IF;
END;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'cfg' AND p.proname = 'cfg_repo_publish'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION cfg.cfg_repo_publish(
  p_kind text,
  p_name text,
  p_version text
)
RETURNS TABLE(id bigint)
LANGUAGE plpgsql
AS $$
DECLARE v_id bigint;
BEGIN
  IF p_kind = 'site' THEN
    UPDATE cfg.site SET status = 'published', updated_at_utc = (now() AT TIME ZONE 'utc')
    WHERE name = p_name AND version = p_version RETURNING cfg.site.id INTO v_id;
  ELSIF p_kind = 'pipeline_profile' THEN
    UPDATE cfg.pipeline_profile SET status = 'published', updated_at_utc = (now() AT TIME ZONE 'utc')
    WHERE name = p_name AND version = p_version RETURNING cfg.pipeline_profile.id INTO v_id;
  ELSIF p_kind = 'assay_procedure' THEN
    UPDATE cfg.assay_procedure SET status = 'published', updated_at_utc = (now() AT TIME ZONE 'utc')
    WHERE name = p_name AND version = p_version RETURNING cfg.assay_procedure.id INTO v_id;
  ELSIF p_kind = 'analyte' THEN
    UPDATE cfg.analyte SET status = 'published', updated_at_utc = (now() AT TIME ZONE 'utc')
    WHERE name = p_name AND version = p_version RETURNING cfg.analyte.id INTO v_id;
  ELSIF p_kind = 'domain_program' THEN
    UPDATE cfg.domain_program SET status = 'published', updated_at_utc = (now() AT TIME ZONE 'utc')
    WHERE name = p_name AND version = p_version RETURNING cfg.domain_program.id INTO v_id;
  ELSIF p_kind = 'study' THEN
    UPDATE cfg.study SET status = 'published', updated_at_utc = (now() AT TIME ZONE 'utc')
    WHERE name = p_name AND version = p_version RETURNING cfg.study.id INTO v_id;
  ELSIF p_kind = 'credential' THEN
    UPDATE cfg.credential SET status = 'published', updated_at_utc = (now() AT TIME ZONE 'utc')
    WHERE name = p_name AND version = p_version RETURNING cfg.credential.id INTO v_id;
  ELSIF p_kind = 'storage_endpoint' THEN
    UPDATE cfg.storage_endpoint SET status = 'published', updated_at_utc = (now() AT TIME ZONE 'utc')
    WHERE name = p_name AND version = p_version RETURNING cfg.storage_endpoint.id INTO v_id;
  ELSIF p_kind = 'storage_profile' THEN
    UPDATE cfg.storage_profile SET status = 'published', updated_at_utc = (now() AT TIME ZONE 'utc')
    WHERE name = p_name AND version = p_version RETURNING cfg.storage_profile.id INTO v_id;
  ELSIF p_kind = 'reference_asset' THEN
    UPDATE cfg.reference_asset SET status = 'published', updated_at_utc = (now() AT TIME ZONE 'utc')
    WHERE name = p_name AND version = p_version RETURNING cfg.reference_asset.id INTO v_id;
  ELSIF p_kind = 'action_definition' THEN
    RAISE EXCEPTION 'cfg.action_definition retired; use wf.workflow_action';
  ELSIF p_kind = 'enrichment_library_preset' THEN
    UPDATE cfg.enrichment_library_preset SET status = 'published', updated_at_utc = (now() AT TIME ZONE 'utc')
    WHERE name = p_name AND version = p_version RETURNING cfg.enrichment_library_preset.id INTO v_id;
  ELSE
    RAISE EXCEPTION 'unknown cfg kind: %', p_kind;
  END IF;
  IF v_id IS NULL THEN
    RAISE EXCEPTION 'cfg object not found: %.%@%', p_kind, p_name, p_version;
  END IF;
  id := v_id;
  RETURN NEXT;
END;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'cfg' AND p.proname = 'cfg_repo_set_compiled_version'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION cfg.cfg_repo_set_compiled_version(
  p_name text,
  p_version text,
  p_workflow_version_id bigint
)
RETURNS TABLE(id bigint)
LANGUAGE plpgsql
AS $$
DECLARE
  v_id bigint;
  v_def_id bigint;
  v_hash text;
BEGIN
  SELECT workflow_def_id INTO v_def_id
  FROM wf.workflow_version
  WHERE wf.workflow_version.id = p_workflow_version_id;
  IF v_def_id IS NULL THEN
    RAISE EXCEPTION 'workflow_version_id not found: %', p_workflow_version_id;
  END IF;

  UPDATE cfg.domain_program
  SET compiled_workflow_version_id = p_workflow_version_id,
      workflow_def_id = v_def_id,
      updated_at_utc = (now() AT TIME ZONE 'utc')
  WHERE name = p_name AND version = p_version
  RETURNING cfg.domain_program.id, cfg.domain_program.content_hash INTO v_id, v_hash;

  IF v_id IS NULL THEN
    RAISE EXCEPTION 'domain_program not found: %@%', p_name, p_version;
  END IF;

  INSERT INTO cfg.program_publish (domain_program_id, workflow_def_id, workflow_version_id, content_hash)
  VALUES (v_id, v_def_id, p_workflow_version_id, v_hash)
  ON CONFLICT (domain_program_id, workflow_version_id) DO NOTHING;

  id := v_id;
  RETURN NEXT;
END;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'cfg' AND p.proname = 'cfg_repo_link_action'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION cfg.cfg_repo_link_action(
  p_action_name text,
  p_version text DEFAULT '1'
)
RETURNS TABLE(id bigint, workflow_action_id bigint)
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION
    'cfg.cfg_repo_link_action retired; use wf.workflow_action + wf.data_type (seed_action_catalog)';
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

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'cfg' AND p.proname = 'cfg_repo_link_reference_asset'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION cfg.cfg_repo_link_reference_asset(
  p_asset_name text,
  p_version text DEFAULT '1',
  p_storage_endpoint_id bigint DEFAULT NULL,
  p_asset_type text DEFAULT NULL
)
RETURNS TABLE(id bigint, storage_endpoint_id bigint, asset_type text)
LANGUAGE plpgsql
AS $$
DECLARE
  v_id bigint;
  v_se bigint;
  v_at text;
BEGIN
  UPDATE cfg.reference_asset ra
  SET storage_endpoint_id = COALESCE(p_storage_endpoint_id, ra.storage_endpoint_id),
      asset_type = COALESCE(p_asset_type, ra.asset_type),
      updated_at_utc = (now() AT TIME ZONE 'utc')
  WHERE ra.name = p_asset_name AND ra.version = p_version
  RETURNING ra.id, ra.storage_endpoint_id, ra.asset_type INTO v_id, v_se, v_at;
  IF v_id IS NULL THEN
    RAISE EXCEPTION 'reference_asset not found: %@%', p_asset_name, p_version;
  END IF;
  id := v_id;
  storage_endpoint_id := v_se;
  asset_type := v_at;
  RETURN NEXT;
END;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'cfg' AND p.proname = 'cfg_repo_link_site_asset'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION cfg.cfg_repo_link_site_asset(
  p_site_id bigint,
  p_reference_asset_id bigint,
  p_asset_role text
)
RETURNS TABLE(id bigint)
LANGUAGE plpgsql
AS $$
DECLARE v_id bigint;
BEGIN
  INSERT INTO cfg.site_reference_asset (site_id, reference_asset_id, asset_role)
  VALUES (p_site_id, p_reference_asset_id, p_asset_role)
  ON CONFLICT (site_id, asset_role) DO UPDATE
    SET reference_asset_id = EXCLUDED.reference_asset_id
  RETURNING cfg.site_reference_asset.id INTO v_id;
  id := v_id;
  RETURN NEXT;
END;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'cfg' AND p.proname = 'cfg_repo_get_credential_secret'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION cfg.cfg_repo_get_credential_secret(
  p_name text,
  p_version text DEFAULT NULL
)
RETURNS TABLE(id bigint, name text, version text, provider text, auth_mode text, secret_json jsonb)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  RETURN QUERY
  SELECT c.id, c.name, c.version, c.provider, c.auth_mode, c.secret_json
  FROM cfg.credential c
  WHERE c.name = p_name
    AND (p_version IS NULL OR c.version = p_version)
    AND c.status = 'published'
  ORDER BY c.id DESC
  LIMIT 1;
END;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'cfg' AND p.proname = 'cfg_repo_set_study_group'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION cfg.cfg_repo_set_study_group(
  p_study_row_id bigint,
  p_role text,
  p_label text,
  p_list_filename text
)
RETURNS TABLE(id bigint, study_row_id bigint, role text, label text, list_filename text)
LANGUAGE plpgsql
AS $$
DECLARE v_id bigint;
BEGIN
  IF p_role NOT IN ('control', 'disease') THEN
    RAISE EXCEPTION 'study_group role must be control or disease';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM cfg.study s WHERE s.id = p_study_row_id) THEN
    RAISE EXCEPTION 'cfg.study not found: %', p_study_row_id;
  END IF;
  INSERT INTO cfg.study_group (study_row_id, role, label, list_filename)
  VALUES (p_study_row_id, p_role, p_label, p_list_filename)
  ON CONFLICT (study_row_id, role, label) DO UPDATE SET
    list_filename = EXCLUDED.list_filename,
    updated_at_utc = (now() AT TIME ZONE 'utc')
  RETURNING cfg.study_group.id INTO v_id;
  RETURN QUERY
  SELECT g.id, g.study_row_id, g.role::text, g.label, g.list_filename
  FROM cfg.study_group g WHERE g.id = v_id;
END;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'cfg' AND p.proname = 'cfg_repo_set_study_group_members'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION cfg.cfg_repo_set_study_group_members(
  p_study_group_id bigint,
  p_members jsonb
)
RETURNS TABLE(
  id bigint,
  study_group_id bigint,
  portal_sample_id int,
  lab_sample_id int,
  processing_sample_key text
)
LANGUAGE plpgsql
AS $$
DECLARE
  elem jsonb;
  v_portal int;
  v_lab int;
  v_key text;
  v_resolved text;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM cfg.study_group g WHERE g.id = p_study_group_id) THEN
    RAISE EXCEPTION 'cfg.study_group not found: %', p_study_group_id;
  END IF;

  DELETE FROM cfg.study_group_member WHERE study_group_id = p_study_group_id;

  FOR elem IN SELECT * FROM jsonb_array_elements(COALESCE(p_members, '[]'::jsonb))
  LOOP
    v_portal := (elem->>'portalSampleId')::int;
    v_lab := NULLIF(elem->>'labSampleId', '')::int;
    v_key := NULLIF(btrim(elem->>'processingSampleKey'), '');
    -- Soft resolve: prefer explicit key; portal LabSamples lookup when table exists is app-side.
    v_resolved := v_key;
    IF v_resolved IS NULL THEN
      RAISE EXCEPTION 'cannot resolve processing_sample_key for portalSampleId=%', v_portal;
    END IF;
    INSERT INTO cfg.study_group_member (
      study_group_id, portal_sample_id, lab_sample_id, processing_sample_key
    ) VALUES (p_study_group_id, v_portal, v_lab, v_resolved);
  END LOOP;

  UPDATE cfg.study_group SET updated_at_utc = (now() AT TIME ZONE 'utc')
  WHERE id = p_study_group_id;

  RETURN QUERY
  SELECT m.id, m.study_group_id, m.portal_sample_id, m.lab_sample_id, m.processing_sample_key
  FROM cfg.study_group_member m
  WHERE m.study_group_id = p_study_group_id
  ORDER BY m.processing_sample_key;
END;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'cfg' AND p.proname = 'cfg_repo_list_study_groups'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION cfg.cfg_repo_list_study_groups(p_study_row_id bigint)
RETURNS TABLE(
  id bigint,
  study_row_id bigint,
  role text,
  label text,
  list_filename text,
  member_count bigint
)
LANGUAGE sql
AS $$
  SELECT g.id, g.study_row_id, g.role::text, g.label, g.list_filename,
         (SELECT COUNT(*) FROM cfg.study_group_member m WHERE m.study_group_id = g.id)
  FROM cfg.study_group g
  WHERE g.study_row_id = p_study_row_id
  ORDER BY g.role, g.label;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'cfg' AND p.proname = 'cfg_repo_list_study_group_members'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION cfg.cfg_repo_list_study_group_members(p_study_group_id bigint)
RETURNS TABLE(
  id bigint,
  study_group_id bigint,
  portal_sample_id int,
  lab_sample_id int,
  processing_sample_key text
)
LANGUAGE sql
AS $$
  SELECT m.id, m.study_group_id, m.portal_sample_id, m.lab_sample_id, m.processing_sample_key
  FROM cfg.study_group_member m
  WHERE m.study_group_id = p_study_group_id
  ORDER BY m.processing_sample_key;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'cfg' AND p.proname = 'cfg_repo_materialize_study_lists'
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION cfg.cfg_repo_materialize_study_lists(
  p_study_row_id bigint,
  p_work_root text DEFAULT '/work'
)
RETURNS TABLE(
  study_group_id bigint,
  role text,
  label text,
  list_filename text,
  csv_path text,
  sample_keys text
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_study_id text;
  v_doc jsonb;
  v_data_root text;
  v_groups jsonb;
BEGIN
  SELECT COALESCE(s.study_id, s.name), s.document_json
  INTO v_study_id, v_doc
  FROM cfg.study s WHERE s.id = p_study_row_id;
  IF v_study_id IS NULL THEN
    RAISE EXCEPTION 'cfg.study not found: %', p_study_row_id;
  END IF;

  v_data_root := p_work_root || '/projects/' || v_study_id || '/data';

  SELECT COALESCE(jsonb_agg(
    jsonb_build_object(
      'role', g.role,
      'label', g.label,
      'listFilename', g.list_filename,
      'samplePath', v_data_root || '/' || g.list_filename
    ) ORDER BY g.role, g.label
  ), '[]'::jsonb)
  INTO v_groups
  FROM cfg.study_group g
  WHERE g.study_row_id = p_study_row_id;

  v_doc := jsonb_set(COALESCE(v_doc, '{}'::jsonb), '{cfgStudyGroups}', v_groups, true);
  UPDATE cfg.study
  SET document_json = v_doc,
      content_hash = md5(v_doc::text),
      updated_at_utc = (now() AT TIME ZONE 'utc')
  WHERE id = p_study_row_id;

  RETURN QUERY
  SELECT
    g.id,
    g.role::text,
    g.label,
    g.list_filename,
    v_data_root || '/' || g.list_filename,
    (SELECT string_agg(m.processing_sample_key, E'\n' ORDER BY m.processing_sample_key)
     FROM cfg.study_group_member m WHERE m.study_group_id = g.id)
  FROM cfg.study_group g
  WHERE g.study_row_id = p_study_row_id
  ORDER BY g.role, g.label;
END;
$$;
