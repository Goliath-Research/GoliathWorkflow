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

CREATE OR REPLACE FUNCTION portal.sp_list_cfg_actions()
RETURNS TABLE(id bigint, name text, version text, status text, content_hash text)
LANGUAGE sql
AS $$
  SELECT * FROM cfg.cfg_repo_list('action_definition', false);
$$;

CREATE OR REPLACE FUNCTION portal.sp_get_cfg_action(
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
  SELECT * FROM cfg.cfg_repo_get('action_definition', p_name, p_version, false);
$$;
