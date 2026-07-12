-- cfg registry tables (versioned JSON documents). Credentials never materialize to /work.

CREATE TABLE IF NOT EXISTS cfg.site (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name text NOT NULL,
  version text NOT NULL DEFAULT '1',
  status varchar(32) NOT NULL DEFAULT 'draft',
  content_hash text NOT NULL,
  document_json jsonb NOT NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CONSTRAINT uq_cfg_site_name_version UNIQUE (name, version),
  CONSTRAINT ck_cfg_site_status CHECK (status IN ('draft', 'published', 'retired'))
);

CREATE TABLE IF NOT EXISTS cfg.pipeline_profile (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name text NOT NULL,
  version text NOT NULL DEFAULT '1',
  status varchar(32) NOT NULL DEFAULT 'draft',
  content_hash text NOT NULL,
  document_json jsonb NOT NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CONSTRAINT uq_cfg_pipeline_profile_name_version UNIQUE (name, version),
  CONSTRAINT ck_cfg_pipeline_profile_status CHECK (status IN ('draft', 'published', 'retired'))
);

CREATE TABLE IF NOT EXISTS cfg.domain_program (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name text NOT NULL,
  version text NOT NULL DEFAULT '1',
  status varchar(32) NOT NULL DEFAULT 'draft',
  content_hash text NOT NULL,
  document_json jsonb NOT NULL,
  compiled_workflow_version_id bigint NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CONSTRAINT uq_cfg_domain_program_name_version UNIQUE (name, version),
  CONSTRAINT ck_cfg_domain_program_status CHECK (status IN ('draft', 'published', 'retired'))
);

CREATE TABLE IF NOT EXISTS cfg.study (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name text NOT NULL,
  version text NOT NULL DEFAULT '1',
  status varchar(32) NOT NULL DEFAULT 'draft',
  content_hash text NOT NULL,
  document_json jsonb NOT NULL,
  study_id text NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CONSTRAINT uq_cfg_study_name_version UNIQUE (name, version),
  CONSTRAINT ck_cfg_study_status CHECK (status IN ('draft', 'published', 'retired'))
);

CREATE TABLE IF NOT EXISTS cfg.credential (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name text NOT NULL,
  version text NOT NULL DEFAULT '1',
  status varchar(32) NOT NULL DEFAULT 'draft',
  content_hash text NOT NULL,
  provider text NOT NULL,
  auth_mode text NOT NULL,
  secret_json jsonb NOT NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CONSTRAINT uq_cfg_credential_name_version UNIQUE (name, version),
  CONSTRAINT ck_cfg_credential_status CHECK (status IN ('draft', 'published', 'retired'))
);

CREATE TABLE IF NOT EXISTS cfg.storage_endpoint (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name text NOT NULL,
  version text NOT NULL DEFAULT '1',
  status varchar(32) NOT NULL DEFAULT 'draft',
  content_hash text NOT NULL,
  provider text NOT NULL,
  location_json jsonb NOT NULL,
  credential_name text NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CONSTRAINT uq_cfg_storage_endpoint_name_version UNIQUE (name, version),
  CONSTRAINT ck_cfg_storage_endpoint_status CHECK (status IN ('draft', 'published', 'retired'))
);

CREATE TABLE IF NOT EXISTS cfg.storage_profile (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name text NOT NULL,
  version text NOT NULL DEFAULT '1',
  status varchar(32) NOT NULL DEFAULT 'draft',
  content_hash text NOT NULL,
  document_json jsonb NOT NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CONSTRAINT uq_cfg_storage_profile_name_version UNIQUE (name, version),
  CONSTRAINT ck_cfg_storage_profile_status CHECK (status IN ('draft', 'published', 'retired'))
);

CREATE TABLE IF NOT EXISTS cfg.reference_asset (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name text NOT NULL,
  version text NOT NULL DEFAULT '1',
  status varchar(32) NOT NULL DEFAULT 'draft',
  content_hash text NOT NULL,
  document_json jsonb NOT NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CONSTRAINT uq_cfg_reference_asset_name_version UNIQUE (name, version),
  CONSTRAINT ck_cfg_reference_asset_status CHECK (status IN ('draft', 'published', 'retired'))
);

CREATE TABLE IF NOT EXISTS cfg.action_definition (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name text NOT NULL,
  version text NOT NULL DEFAULT '1',
  status varchar(32) NOT NULL DEFAULT 'draft',
  content_hash text NOT NULL,
  document_json jsonb NOT NULL,
  implementation_status varchar(32) NOT NULL DEFAULT 'present',
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CONSTRAINT uq_cfg_action_definition_name_version UNIQUE (name, version),
  CONSTRAINT ck_cfg_action_definition_status CHECK (status IN ('draft', 'published', 'retired')),
  CONSTRAINT ck_cfg_action_implementation CHECK (implementation_status IN ('scaffolded', 'present', 'retired'))
);
