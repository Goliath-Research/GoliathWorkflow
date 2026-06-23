/*
  Portal resource profiles (domain config — NOT wf workflow engine).
  Used for internal archive storage defaults (e.g. myQNAPcloud S3 h5Storage).
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

INSERT INTO portal.resource_profile (profile_key, profile_type, profile_json, status)
SELECT
  'epimethyl-samples',
  's3_object_storage',
  '{
    "type": "s3",
    "bucket": "epimethyl",
    "region": "us-east-1",
    "endpointUrl": "https://s3.us-east-1.myqnapcloud.io",
    "prefixBase": "samples/",
    "credentials": {
      "authMode": "explicit_keys",
      "accessKeyId": "REPLACE_WITH_ACCESS_KEY",
      "secretAccessKey": "REPLACE_WITH_SECRET_KEY"
    }
  }'::jsonb,
  'ACTIVE'
WHERE NOT EXISTS (
  SELECT 1 FROM portal.resource_profile WHERE profile_key = 'epimethyl-samples'
);
