/*
  Platform long-term sample object storage (S3-compatible myQNAPcloud One).
  Deploy after wf_cluster_security_columns.sql (PostgreSQL wf schema).
*/

CREATE TABLE IF NOT EXISTS wf.platform_sample_storage (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  storage_key text NOT NULL UNIQUE,
  provider_type varchar(32) NOT NULL DEFAULT 's3',
  bucket text NOT NULL,
  region text NULL,
  endpoint_url text NOT NULL,
  access_key_id text NOT NULL,
  secret_access_key text NOT NULL,
  base_prefix text NOT NULL DEFAULT 'samples/',
  status varchar(32) NOT NULL DEFAULT 'ACTIVE',
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CHECK (status IN ('ACTIVE','DISABLED'))
);

INSERT INTO wf.platform_sample_storage (
  storage_key,
  bucket,
  region,
  endpoint_url,
  access_key_id,
  secret_access_key,
  base_prefix,
  status
)
SELECT
  'epimethyl-samples',
  'epimethyl',
  'us-east-1',
  'https://s3.us-east-1.myqnapcloud.io',
  'REPLACE_WITH_ACCESS_KEY',
  'REPLACE_WITH_SECRET_KEY',
  'samples/',
  'ACTIVE'
WHERE NOT EXISTS (
  SELECT 1 FROM wf.platform_sample_storage WHERE storage_key = 'epimethyl-samples'
);
