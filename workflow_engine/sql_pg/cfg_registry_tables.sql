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

-- Specimen / matrix analytes (cfdna, buffy_coat, …) — versioned catalog documents.
CREATE TABLE IF NOT EXISTS cfg.analyte (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name text NOT NULL,
  version text NOT NULL DEFAULT '1',
  status varchar(32) NOT NULL DEFAULT 'draft',
  content_hash text NOT NULL,
  document_json jsonb NOT NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CONSTRAINT uq_cfg_analyte_name_version UNIQUE (name, version),
  CONSTRAINT ck_cfg_analyte_status CHECK (status IN ('draft', 'published', 'retired'))
);

CREATE TABLE IF NOT EXISTS cfg.domain_program (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name text NOT NULL,
  version text NOT NULL DEFAULT '1',
  status varchar(32) NOT NULL DEFAULT 'draft',
  content_hash text NOT NULL,
  document_json jsonb NOT NULL,
  compiled_workflow_version_id bigint NULL,
  workflow_def_id bigint NULL,
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
  credential_id bigint NULL,
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
  storage_endpoint_id bigint NULL,
  asset_type text NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CONSTRAINT uq_cfg_reference_asset_name_version UNIQUE (name, version),
  CONSTRAINT ck_cfg_reference_asset_status CHECK (status IN ('draft', 'published', 'retired'))
);

-- RETIRED — do not write. Actions + I/O types: wf.workflow_action + wf.data_type.
-- Table kept only so existing deployments do not fail on leftover rows.
CREATE TABLE IF NOT EXISTS cfg.action_definition (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name text NOT NULL,
  version text NOT NULL DEFAULT '1',
  status varchar(32) NOT NULL DEFAULT 'draft',
  content_hash text NOT NULL,
  document_json jsonb NOT NULL,
  implementation_status varchar(32) NOT NULL DEFAULT 'present',
  workflow_action_id bigint NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CONSTRAINT uq_cfg_action_definition_name_version UNIQUE (name, version),
  CONSTRAINT ck_cfg_action_definition_status CHECK (status IN ('draft', 'published', 'retired')),
  CONSTRAINT ck_cfg_action_implementation CHECK (implementation_status IN ('scaffolded', 'present', 'retired'))
);

-- Enrichment library presets (named Enrichr library sets, e.g. cancer-core, neuro-core).
-- Authored in packages/methylenricher/.../data/library_presets.json; synced via
-- methyl-cfg sync-library-presets. Config, not a workflow node.
CREATE TABLE IF NOT EXISTS cfg.enrichment_library_preset (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name text NOT NULL,
  version text NOT NULL DEFAULT '1',
  status varchar(32) NOT NULL DEFAULT 'draft',
  content_hash text NOT NULL,
  document_json jsonb NOT NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CONSTRAINT uq_cfg_enrichment_library_preset_name_version UNIQUE (name, version),
  CONSTRAINT ck_cfg_enrichment_library_preset_status CHECK (status IN ('draft', 'published', 'retired'))
);

-- Study analysis arms (portal.Samples FKs are soft refs on PG; MSSQL enforces portal FKs).
CREATE TABLE IF NOT EXISTS cfg.study_group (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  study_row_id bigint NOT NULL REFERENCES cfg.study (id) ON DELETE CASCADE,
  role varchar(32) NOT NULL,
  label text NOT NULL,
  list_filename text NOT NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CONSTRAINT uq_cfg_study_group_role_label UNIQUE (study_row_id, role, label),
  CONSTRAINT ck_cfg_study_group_role CHECK (role IN ('control', 'disease'))
);

CREATE INDEX IF NOT EXISTS IX_cfg_study_group_study ON cfg.study_group (study_row_id);

CREATE TABLE IF NOT EXISTS cfg.study_group_member (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  study_group_id bigint NOT NULL REFERENCES cfg.study_group (id) ON DELETE CASCADE,
  portal_sample_id int NOT NULL,
  lab_sample_id int NULL,
  processing_sample_key text NOT NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  CONSTRAINT uq_cfg_sgm_processing_key UNIQUE (study_group_id, processing_sample_key)
);

CREATE INDEX IF NOT EXISTS IX_cfg_sgm_group ON cfg.study_group_member (study_group_id);
CREATE INDEX IF NOT EXISTS IX_cfg_sgm_portal_sample ON cfg.study_group_member (portal_sample_id);
