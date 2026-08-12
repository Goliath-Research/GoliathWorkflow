/*
  Portal-facing DomainProgram tree CRUD against cfg.domain_program.
*/
CREATE OR REPLACE FUNCTION portal.sp_list_domain_programs(
  p_published_only boolean DEFAULT false
)
RETURNS TABLE(id bigint, name text, version text, status text, content_hash text)
LANGUAGE sql
AS $$
  SELECT * FROM cfg.cfg_repo_list('domain_program', p_published_only);
$$;

CREATE OR REPLACE FUNCTION portal.sp_get_domain_program(
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
  secret_redacted jsonb,
  extra jsonb
)
LANGUAGE sql
AS $$
  SELECT * FROM cfg.cfg_repo_get('domain_program', p_name, p_version, false);
$$;

CREATE OR REPLACE FUNCTION portal.sp_upsert_domain_program(
  p_name text,
  p_version text,
  p_status text,
  p_document jsonb
)
RETURNS TABLE(id bigint)
LANGUAGE sql
AS $$
  SELECT * FROM cfg.cfg_repo_upsert(
    'domain_program', p_name, p_version, p_status, p_document
  );
$$;

/* Deprecated aliases — actions live in wf; use portal.sp_list/get_workflow_actions. */
CREATE OR REPLACE FUNCTION portal.sp_list_cfg_actions()
RETURNS TABLE(
  id bigint,
  action_name text,
  capability text,
  execution_mode text,
  cli_tool text,
  in_process_handler text,
  implementation_status text,
  can_pause boolean,
  can_continue boolean,
  can_stop boolean,
  input_type_id bigint,
  input_type_name text,
  output_type_id bigint,
  output_type_name text
)
LANGUAGE sql
STABLE
AS $$
  SELECT * FROM portal.sp_list_workflow_actions();
$$;

CREATE OR REPLACE FUNCTION portal.sp_get_cfg_action(
  p_name text,
  p_version text DEFAULT NULL
)
RETURNS TABLE(
  id bigint,
  action_name text,
  capability text,
  execution_mode text,
  cli_tool text,
  in_process_handler text,
  implementation_status text,
  can_pause boolean,
  can_continue boolean,
  can_stop boolean,
  input_type_id bigint,
  input_type_name text,
  output_type_id bigint,
  output_type_name text
)
LANGUAGE sql
STABLE
AS $$
  SELECT * FROM portal.sp_get_workflow_action(p_name);
$$;

CREATE OR REPLACE FUNCTION portal.sp_set_study_group(
  p_study_row_id bigint,
  p_role text,
  p_label text,
  p_list_filename text
)
RETURNS TABLE(id bigint, study_row_id bigint, role text, label text, list_filename text)
LANGUAGE sql
AS $$
  SELECT * FROM cfg.cfg_repo_set_study_group(p_study_row_id, p_role, p_label, p_list_filename);
$$;

CREATE OR REPLACE FUNCTION portal.sp_set_study_group_members(
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
LANGUAGE sql
AS $$
  SELECT * FROM cfg.cfg_repo_set_study_group_members(p_study_group_id, p_members);
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_study_groups(p_study_row_id bigint)
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
  SELECT * FROM cfg.cfg_repo_list_study_groups(p_study_row_id);
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_study_group_members(p_study_group_id bigint)
RETURNS TABLE(
  id bigint,
  study_group_id bigint,
  portal_sample_id int,
  lab_sample_id int,
  processing_sample_key text
)
LANGUAGE sql
AS $$
  SELECT * FROM cfg.cfg_repo_list_study_group_members(p_study_group_id);
$$;

CREATE OR REPLACE FUNCTION portal.sp_materialize_study_lists(
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
LANGUAGE sql
AS $$
  SELECT * FROM cfg.cfg_repo_materialize_study_lists(p_study_row_id, p_work_root);
$$;

/*
  Storage accounts + credentials (DB SoT for EpiPortal).
  Lab/infra admins upsert+publish; list/get never return secret bodies.
*/

CREATE OR REPLACE FUNCTION portal.sp_list_storage_endpoints(
  p_published_only boolean DEFAULT true
)
RETURNS TABLE(
  id bigint,
  name text,
  version text,
  status text,
  content_hash text,
  provider text,
  credential_name text,
  location_json jsonb
)
LANGUAGE sql
AS $$
  SELECT e.id, e.name, e.version, e.status::text, e.content_hash,
         e.provider, e.credential_name, e.location_json
  FROM cfg.storage_endpoint e
  WHERE (NOT p_published_only OR e.status = 'published')
  ORDER BY e.name, e.version;
$$;

CREATE OR REPLACE FUNCTION portal.sp_get_storage_endpoint(
  p_name text,
  p_version text DEFAULT NULL
)
RETURNS TABLE(
  id bigint,
  name text,
  version text,
  status text,
  content_hash text,
  provider text,
  credential_name text,
  location_json jsonb
)
LANGUAGE sql
AS $$
  SELECT e.id, e.name, e.version, e.status::text, e.content_hash,
         e.provider, e.credential_name, e.location_json
  FROM cfg.storage_endpoint e
  WHERE e.name = p_name AND (p_version IS NULL OR e.version = p_version)
  ORDER BY e.id DESC
  LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION portal.sp_upsert_storage_endpoint(
  p_name text,
  p_version text,
  p_status text,
  p_location jsonb,
  p_provider text DEFAULT NULL,
  p_credential_name text DEFAULT NULL
)
RETURNS TABLE(id bigint)
LANGUAGE sql
AS $$
  SELECT * FROM cfg.cfg_repo_upsert(
    'storage_endpoint', p_name, p_version, p_status, p_location,
    NULL, p_provider, NULL, p_credential_name
  );
$$;

CREATE OR REPLACE FUNCTION portal.sp_publish_storage_endpoint(
  p_name text,
  p_version text
)
RETURNS TABLE(id bigint)
LANGUAGE sql
AS $$
  SELECT * FROM cfg.cfg_repo_publish('storage_endpoint', p_name, p_version);
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_credentials(
  p_published_only boolean DEFAULT true
)
RETURNS TABLE(
  id bigint,
  name text,
  version text,
  status text,
  content_hash text,
  provider text,
  auth_mode text
)
LANGUAGE sql
AS $$
  SELECT c.id, c.name, c.version, c.status::text, c.content_hash, c.provider, c.auth_mode
  FROM cfg.credential c
  WHERE (NOT p_published_only OR c.status = 'published')
  ORDER BY c.name, c.version;
$$;

CREATE OR REPLACE FUNCTION portal.sp_get_credential(
  p_name text,
  p_version text DEFAULT NULL
)
RETURNS TABLE(
  id bigint,
  name text,
  version text,
  status text,
  content_hash text,
  provider text,
  auth_mode text
)
LANGUAGE sql
AS $$
  SELECT c.id, c.name, c.version, c.status::text, c.content_hash, c.provider, c.auth_mode
  FROM cfg.credential c
  WHERE c.name = p_name AND (p_version IS NULL OR c.version = p_version)
  ORDER BY c.id DESC
  LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION portal.sp_upsert_credential(
  p_name text,
  p_version text,
  p_status text,
  p_secret jsonb,
  p_provider text DEFAULT NULL,
  p_auth_mode text DEFAULT NULL
)
RETURNS TABLE(id bigint)
LANGUAGE sql
AS $$
  SELECT * FROM cfg.cfg_repo_upsert(
    'credential', p_name, p_version, p_status, NULL, p_secret,
    p_provider,
    COALESCE(p_auth_mode, p_secret->>'authMode')
  );
$$;

CREATE OR REPLACE FUNCTION portal.sp_publish_credential(
  p_name text,
  p_version text
)
RETURNS TABLE(id bigint)
LANGUAGE sql
AS $$
  SELECT * FROM cfg.cfg_repo_publish('credential', p_name, p_version);
$$;
