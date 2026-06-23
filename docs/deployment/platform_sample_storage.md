# Platform sample object storage (myQNAPcloud / S3-compatible)

Long-term archive for sample FASTQs and methylation HDF5 files lives in **S3-compatible object storage** (production: myQNAPcloud One). Credentials and endpoint are stored in the database — not in worker env files.

## Database table

`wf.platform_sample_storage` (deploy [`wf_platform_sample_storage.sql`](../../workflow_engine/sql/wf_platform_sample_storage.sql) on Azure SQL or [`sql_pg/wf_platform_sample_storage.sql`](../../workflow_engine/sql_pg/wf_platform_sample_storage.sql) on PostgreSQL).

| Column | Purpose |
|--------|---------|
| `storage_key` | Logical name (`epimethyl-samples` is the default) |
| `bucket` | S3 bucket (`epimethyl`) |
| `base_prefix` | Folder prefix under bucket (`samples/` → `epimethyl/samples/{sampleId}/`) |
| `endpoint_url` | S3 API endpoint (`https://s3.us-east-1.myqnapcloud.io`) |
| `region` | Signing region (`us-east-1`) |
| `access_key_id` / `secret_access_key` | myQNAPcloud access key pair |

### Configure credentials (operator)

After deploy, replace seed placeholders:

```sql
UPDATE wf.platform_sample_storage
SET access_key_id = '<ACCESS_KEY>',
    secret_access_key = '<SECRET_KEY>',
    updated_at_utc = SYSUTCDATETIME()
WHERE storage_key = 'epimethyl-samples';
```

PostgreSQL: use `updated_at_utc = (now() AT TIME ZONE 'utc')`.

## Sample prep API

When `fastqStorage` / `h5Storage` are omitted, `POST /v1/studies/sample-prep/start` loads the active row for `storageKey` (default `epimethyl-samples`) and materializes:

- **Ingress:** `sample.download_fastq` reads `*.fastq.gz` from `s3://epimethyl/samples/{sampleId}/`
- **Archive:** `sample.upload_h5` writes `{chr}-{ctx}.h5` to the same per-sample prefix after extract

Minimal start (platform storage from DB):

```http
POST /v1/studies/sample-prep/start
{
  "projectPath": "/work/epimethyl/data/project_....json",
  "workflow_version_id": <sample_prep_version>,
  "sampleCsvs": ["/work/.../healthy.csv", "/work/.../pca.csv"]
}
```

Override storage key:

```json
{ "storageKey": "epimethyl-samples", "projectPath": "...", ... }
```

Explicit `fastqStorage` / `h5Storage` in the request body still override the database defaults.

## Security

- Credentials flow in **task `input_json`** (planned by gateway, stored in workflow instance context) — same pattern as other object storage actions.
- Workers use **explicit_keys** auth against the myQNAPcloud endpoint; prefer rotating keys via SQL update on `wf.platform_sample_storage`.
- Portal RBAC users do not receive raw storage secrets from this table; only the gateway middle tier reads them when starting sample prep.
