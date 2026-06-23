# Portal resource profiles (archive storage)

Internal **retention** storage for processed sample artifacts (methylation HDF5, future archives) lives in **`portal.resource_profile`** — not in the `wf` workflow engine schema.

## Ingress vs retention

| Stage | Storage owner | Config source |
|-------|---------------|---------------|
| **First processing** — download FASTQs | Laboratory (external S3, Azure Blob, etc.) | **`fastqStorage` required** on every study start |
| **After extract** — archive FASTQs, QC JSON, `{chr}-{ctx}.h5` | MethylPipeline (myQNAPcloud) | **`sampleStorage`** from `portal.resource_profile` when omitted (`h5Storage` alias) |

The workflow engine only stores resolved `fastqStorage` / `h5Storage` in `workflow_instance.context_json`. It does not read portal tables.

## Database table

`portal.resource_profile` (deploy [`workflow_engine/sql/portal_resource_profile.sql`](../../workflow_engine/sql/portal_resource_profile.sql) on Azure SQL or [`workflow_engine/sql_pg/portal_resource_profile.sql`](../../workflow_engine/sql_pg/portal_resource_profile.sql) on PostgreSQL).

| Column | Purpose |
|--------|---------|
| `profile_key` | Logical name (`epimethyl-samples` default) |
| `profile_type` | Opaque tag for portal UI (e.g. `s3_object_storage`) |
| `profile_json` | JSON matching [`schemas/domain/h5_storage.schema.json`](../../schemas/domain/h5_storage.schema.json) defaults |
| `status` | `ACTIVE` / `DISABLED` |

Seed `profile_json` for myQNAPcloud:

```json
{
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
}
```

### Configure credentials (operator)

```sql
UPDATE portal.resource_profile
SET profile_json = JSON_MODIFY(
      JSON_MODIFY(profile_json, '$.credentials.accessKeyId', '<ACCESS_KEY>'),
      '$.credentials.secretAccessKey', '<SECRET_KEY>'),
    updated_at_utc = SYSUTCDATETIME()
WHERE profile_key = 'epimethyl-samples';
```

PostgreSQL:

```sql
UPDATE portal.resource_profile
SET profile_json = jsonb_set(
      jsonb_set(profile_json, '{credentials,accessKeyId}', '"<ACCESS_KEY>"'),
      '{credentials,secretAccessKey}', '"<SECRET_KEY>"'),
    updated_at_utc = (now() AT TIME ZONE 'utc')
WHERE profile_key = 'epimethyl-samples';
```

## Sample prep API

**Required:** laboratory `fastqStorage` on every start request.

**Optional default:** `sampleStorage` from portal profile when omitted (`archiveProfileKey` defaults to `epimethyl-samples`). Legacy `h5Storage` accepted.

```http
POST /v1/studies/sample-prep/start
{
  "projectPath": "/work/epimethyl/data/project_....json",
  "workflow_version_id": <sample_prep_version>,
  "fastqStorage": {
    "type": "s3",
    "bucket": "lab-external-cohort",
    "region": "us-west-2",
    "credentials": { "authMode": "instance_profile" }
  },
  "sampleCsvs": ["/work/.../healthy.csv"]
}
```

Legacy aliases: `archiveStorageKey`, `storageKey` → `archiveProfileKey`.

## Migration from wf.platform_sample_storage

If the mistaken `wf.platform_sample_storage` table was deployed:

1. Deploy `portal.resource_profile` and copy credentials into `profile_json`
2. Deploy code that reads portal schema
3. Run [`wf_drop_platform_sample_storage.sql`](../../workflow_engine/sql/wf_drop_platform_sample_storage.sql)

## Security

- Archive credentials appear in task `input_json` for upload steps only (after planner materialization).
- Laboratory credentials are supplied per study in `fastqStorage`, never from portal archive profiles.
- Portal RBAC users should not receive raw secrets; gateway middle tier reads profiles when starting sample prep.
