-- cfg repository API (PostgreSQL): upsert / get / list / publish / set compiled version

CREATE OR REPLACE FUNCTION cfg._content_hash(doc jsonb)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT md5(doc::text);
$$;

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
    INSERT INTO cfg.action_definition(name, version, status, content_hash, document_json, implementation_status)
    VALUES (p_name, v_version, v_status, v_hash, p_document, COALESCE(p_implementation_status, 'present'))
    ON CONFLICT (name, version) DO UPDATE SET
      status = EXCLUDED.status,
      content_hash = EXCLUDED.content_hash,
      document_json = EXCLUDED.document_json,
      implementation_status = EXCLUDED.implementation_status,
      updated_at_utc = (now() AT TIME ZONE 'utc')
    RETURNING cfg.action_definition.id INTO v_id;
  ELSE
    RAISE EXCEPTION 'unknown cfg kind: %', p_kind;
  END IF;
  id := v_id;
  RETURN NEXT;
END;
$$;

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
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash, s.document_json, NULL::jsonb,
      jsonb_build_object('implementationStatus', s.implementation_status)
    FROM cfg.action_definition s WHERE s.name = p_name AND (p_version IS NULL OR s.version = p_version)
      AND (NOT p_published_only OR s.status = 'published') ORDER BY s.id DESC LIMIT 1;
  ELSE
    RAISE EXCEPTION 'unknown cfg kind: %', p_kind;
  END IF;
END;
$$;

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
    RETURN QUERY SELECT s.id, s.name, s.version, s.status::text, s.content_hash FROM cfg.action_definition s
      WHERE NOT p_published_only OR s.status = 'published' ORDER BY s.name, s.version;
  ELSE
    RAISE EXCEPTION 'unknown cfg kind: %', p_kind;
  END IF;
END;
$$;

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
    UPDATE cfg.action_definition SET status = 'published', updated_at_utc = (now() AT TIME ZONE 'utc')
    WHERE name = p_name AND version = p_version RETURNING cfg.action_definition.id INTO v_id;
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

CREATE OR REPLACE FUNCTION cfg.cfg_repo_set_compiled_version(
  p_name text,
  p_version text,
  p_workflow_version_id bigint
)
RETURNS TABLE(id bigint)
LANGUAGE plpgsql
AS $$
DECLARE v_id bigint;
BEGIN
  UPDATE cfg.domain_program
  SET compiled_workflow_version_id = p_workflow_version_id,
      updated_at_utc = (now() AT TIME ZONE 'utc')
  WHERE name = p_name AND version = p_version
  RETURNING cfg.domain_program.id INTO v_id;
  IF v_id IS NULL THEN
    RAISE EXCEPTION 'domain_program not found: %@%', p_name, p_version;
  END IF;
  id := v_id;
  RETURN NEXT;
END;
$$;

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
