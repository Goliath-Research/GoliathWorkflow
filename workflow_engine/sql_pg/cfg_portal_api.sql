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
