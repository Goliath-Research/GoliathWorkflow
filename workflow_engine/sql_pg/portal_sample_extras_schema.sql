/*
  Sole intentional JSON Schema column in the database.

  Portal sample extras / disease field contracts hold a flexible set of
  covariate-bound columns per disease or study. That shape is not a closed
  engine type — do NOT move it into wf.data_type.

  Engine / gateway / workers use explicit wf.data_type (+ fields) instead.
*/

CREATE SCHEMA IF NOT EXISTS portal;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'portal' AND table_name = 'samples'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'portal' AND table_name = 'samples' AND column_name = 'extras'
  ) THEN
    ALTER TABLE portal.samples ADD COLUMN extras jsonb NULL;
  ELSIF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'portal' AND table_name = 'Samples'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'portal' AND table_name = 'Samples' AND column_name = 'Extras'
  ) THEN
    ALTER TABLE portal."Samples" ADD COLUMN "Extras" jsonb NULL;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS portal.sample_field_contract (
  id bigserial PRIMARY KEY,
  name text NOT NULL,
  version text NOT NULL DEFAULT '1',
  status text NOT NULL DEFAULT 'published',
  disease_term text NULL,
  study_name text NULL,
  /* JSON Schema document — the only schema_json-style column in the DB */
  schema_json jsonb NOT NULL,
  content_hash text NULL,
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CONSTRAINT uq_portal_sample_field_contract UNIQUE (name, version),
  CONSTRAINT ck_portal_sfc_status CHECK (status IN ('draft', 'published', 'retired'))
);

CREATE OR REPLACE FUNCTION portal.sp_list_sample_field_contracts(
  p_published_only boolean DEFAULT true
)
RETURNS TABLE(
  id bigint,
  name text,
  version text,
  status text,
  disease_term text,
  study_name text,
  content_hash text,
  created_at_utc timestamptz,
  updated_at_utc timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT id, name, version, status, disease_term, study_name, content_hash,
         created_at_utc, updated_at_utc
  FROM portal.sample_field_contract
  WHERE (NOT p_published_only OR status = 'published')
  ORDER BY name, version;
$$;

CREATE OR REPLACE FUNCTION portal.sp_get_sample_field_contract(
  p_name text,
  p_version text DEFAULT NULL
)
RETURNS TABLE(
  id bigint,
  name text,
  version text,
  status text,
  disease_term text,
  study_name text,
  schema_json jsonb,
  content_hash text,
  created_at_utc timestamptz,
  updated_at_utc timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT id, name, version, status, disease_term, study_name,
         schema_json, content_hash, created_at_utc, updated_at_utc
  FROM portal.sample_field_contract
  WHERE name = p_name AND (p_version IS NULL OR version = p_version)
  ORDER BY id DESC
  LIMIT 1;
$$;
