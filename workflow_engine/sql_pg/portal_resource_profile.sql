/*
  Portal resource profiles (domain config — NOT wf workflow engine).
  Archive defaults prefer a named cfg.storage_endpoint (DB SoT).
*/

CREATE SCHEMA IF NOT EXISTS portal;

CREATE TABLE IF NOT EXISTS portal.resource_profile (
  profile_key text NOT NULL PRIMARY KEY,
  profile_type text NOT NULL DEFAULT 's3_object_storage',
  profile_json jsonb NOT NULL,
  status varchar(32) NOT NULL DEFAULT 'ACTIVE',
  created_at_utc timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  updated_at_utc timestamptz NULL,
  CHECK (status IN ('ACTIVE','DISABLED'))
);

INSERT INTO cfg.credential (name, version, status, content_hash, provider, auth_mode, secret_json)
SELECT
  'epimethyl-archive-keys',
  '1',
  'published',
  md5('{"authMode":"explicit_keys","accessKeyId":"REPLACE_WITH_ACCESS_KEY","secretAccessKey":"REPLACE_WITH_SECRET_KEY"}'),
  's3',
  'explicit_keys',
  '{"authMode":"explicit_keys","accessKeyId":"REPLACE_WITH_ACCESS_KEY","secretAccessKey":"REPLACE_WITH_SECRET_KEY"}'::jsonb
WHERE NOT EXISTS (
  SELECT 1 FROM cfg.credential WHERE name = 'epimethyl-archive-keys' AND version = '1'
);

INSERT INTO cfg.storage_endpoint (name, version, status, content_hash, provider, location_json, credential_name)
SELECT
  'epimethyl-archive',
  '1',
  'published',
  md5('{"type":"s3","bucket":"epimethyl","region":"us-east-1","endpointUrl":"https://s3.us-east-1.myqnapcloud.io","prefixBase":"samples/","scope":"archive"}'),
  's3',
  '{"type":"s3","bucket":"epimethyl","region":"us-east-1","endpointUrl":"https://s3.us-east-1.myqnapcloud.io","prefixBase":"samples/","scope":"archive"}'::jsonb,
  'epimethyl-archive-keys'
WHERE NOT EXISTS (
  SELECT 1 FROM cfg.storage_endpoint WHERE name = 'epimethyl-archive' AND version = '1'
);

INSERT INTO cfg.storage_endpoint (name, version, status, content_hash, provider, location_json, credential_name)
SELECT
  'epimethyl-genomes',
  '1',
  'published',
  md5('{"type":"s3","bucket":"epimethyl","region":"us-east-1","endpointUrl":"https://s3.us-east-1.myqnapcloud.io","prefixBase":"genomes/","scope":"shared"}'),
  's3',
  '{"type":"s3","bucket":"epimethyl","region":"us-east-1","endpointUrl":"https://s3.us-east-1.myqnapcloud.io","prefixBase":"genomes/","scope":"shared"}'::jsonb,
  'epimethyl-archive-keys'
WHERE NOT EXISTS (
  SELECT 1 FROM cfg.storage_endpoint WHERE name = 'epimethyl-genomes' AND version = '1'
);

INSERT INTO portal.resource_profile (profile_key, profile_type, profile_json, status)
SELECT
  'epimethyl-samples',
  'cfg_storage_endpoint_ref',
  '{"sampleStorageEndpoint":"epimethyl-archive","prefixBase":"samples/","scope":"archive"}'::jsonb,
  'ACTIVE'
WHERE NOT EXISTS (
  SELECT 1 FROM portal.resource_profile WHERE profile_key = 'epimethyl-samples'
);

UPDATE portal.resource_profile
SET profile_json = '{"sampleStorageEndpoint":"epimethyl-archive","prefixBase":"samples/","scope":"archive"}'::jsonb,
    profile_type = 'cfg_storage_endpoint_ref',
    updated_at_utc = (now() AT TIME ZONE 'utc')
WHERE profile_key = 'epimethyl-samples'
  AND profile_json::text LIKE '%REPLACE_WITH_ACCESS_KEY%';
