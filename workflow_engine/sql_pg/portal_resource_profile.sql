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
  'goliath-archive-keys',
  '1',
  'published',
  md5('{"authMode":"explicit_keys","accessKeyId":"REPLACE_WITH_ACCESS_KEY","secretAccessKey":"REPLACE_WITH_SECRET_KEY"}'),
  's3',
  'explicit_keys',
  '{"authMode":"explicit_keys","accessKeyId":"REPLACE_WITH_ACCESS_KEY","secretAccessKey":"REPLACE_WITH_SECRET_KEY"}'::jsonb
WHERE NOT EXISTS (
  SELECT 1 FROM cfg.credential WHERE name = 'goliath-archive-keys' AND version = '1'
);

INSERT INTO cfg.storage_endpoint (name, version, status, content_hash, provider, location_json, credential_name)
SELECT
  'goliath-archive',
  '1',
  'published',
  md5('{"type":"s3","bucket":"goliath","region":"us-east-1","endpointUrl":"https://s3.us-east-1.myqnapcloud.io","prefixBase":"samples/","scope":"archive"}'),
  's3',
  '{"type":"s3","bucket":"goliath","region":"us-east-1","endpointUrl":"https://s3.us-east-1.myqnapcloud.io","prefixBase":"samples/","scope":"archive"}'::jsonb,
  'goliath-archive-keys'
WHERE NOT EXISTS (
  SELECT 1 FROM cfg.storage_endpoint WHERE name = 'goliath-archive' AND version = '1'
);

INSERT INTO cfg.storage_endpoint (name, version, status, content_hash, provider, location_json, credential_name)
SELECT
  'goliath-fastq',
  '1',
  'published',
  md5('{"type":"s3","bucket":"goliath","region":"us-east-1","endpointUrl":"https://s3.us-east-1.myqnapcloud.io","prefixBase":"samples/","scope":"lab_ingress"}'),
  's3',
  '{"type":"s3","bucket":"goliath","region":"us-east-1","endpointUrl":"https://s3.us-east-1.myqnapcloud.io","prefixBase":"samples/","scope":"lab_ingress"}'::jsonb,
  'goliath-archive-keys'
WHERE NOT EXISTS (
  SELECT 1 FROM cfg.storage_endpoint WHERE name = 'goliath-fastq' AND version = '1'
);

INSERT INTO cfg.storage_endpoint (name, version, status, content_hash, provider, location_json, credential_name)
SELECT
  'goliath-genomes',
  '1',
  'published',
  md5('{"type":"s3","bucket":"goliath","region":"us-east-1","endpointUrl":"https://s3.us-east-1.myqnapcloud.io","prefixBase":"genomes/","scope":"shared"}'),
  's3',
  '{"type":"s3","bucket":"goliath","region":"us-east-1","endpointUrl":"https://s3.us-east-1.myqnapcloud.io","prefixBase":"genomes/","scope":"shared"}'::jsonb,
  'goliath-archive-keys'
WHERE NOT EXISTS (
  SELECT 1 FROM cfg.storage_endpoint WHERE name = 'goliath-genomes' AND version = '1'
);

INSERT INTO portal.resource_profile (profile_key, profile_type, profile_json, status)
SELECT
  'goliath-samples',
  'cfg_storage_endpoint_ref',
  '{"sampleStorageEndpoint":"goliath-archive","prefixBase":"samples/","scope":"archive"}'::jsonb,
  'ACTIVE'
WHERE NOT EXISTS (
  SELECT 1 FROM portal.resource_profile WHERE profile_key = 'goliath-samples'
);

UPDATE portal.resource_profile
SET profile_json = '{"sampleStorageEndpoint":"goliath-archive","prefixBase":"samples/","scope":"archive"}'::jsonb,
    profile_type = 'cfg_storage_endpoint_ref',
    updated_at_utc = (now() AT TIME ZONE 'utc')
WHERE profile_key = 'goliath-samples'
  AND profile_json::text LIKE '%REPLACE_WITH_ACCESS_KEY%';

INSERT INTO cfg.storage_profile (name, version, status, content_hash, document_json)
SELECT
  'goliath-samples',
  '1',
  'published',
  md5('{"fastqStorageEndpoint":"goliath-fastq","sampleStorageEndpoint":"goliath-archive"}'),
  '{"fastqStorageEndpoint":"goliath-fastq","sampleStorageEndpoint":"goliath-archive"}'::jsonb
WHERE NOT EXISTS (
  SELECT 1 FROM cfg.storage_profile WHERE name = 'goliath-samples' AND version = '1'
);

UPDATE cfg.storage_profile
SET document_json = '{"fastqStorageEndpoint":"goliath-fastq","sampleStorageEndpoint":"goliath-archive"}'::jsonb,
    content_hash = md5('{"fastqStorageEndpoint":"goliath-fastq","sampleStorageEndpoint":"goliath-archive"}'),
    status = 'published',
    updated_at_utc = (now() AT TIME ZONE 'utc')
WHERE name = 'goliath-samples' AND version = '1'
  AND document_json::text NOT LIKE '%fastqStorageEndpoint%';
