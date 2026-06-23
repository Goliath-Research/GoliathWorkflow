# Platform sample archive storage (myQNAPcloud / S3-compatible)

**Retention storage** for processed sample artifacts (methylation HDF5 and future long-term archives) lives in **S3-compatible object storage** (production: myQNAPcloud One). Credentials and endpoint are stored in the database — not in worker env files.

This is **not** the source for initial FASTQ ingress.

## Ingress vs retention

| Stage | Storage owner | Config source |
|-------|---------------|---------------|
| **First processing** — download FASTQs | Laboratory (external S3, Azure Blob, etc.) | **`fastqStorage` required** on every `POST /v1/studies/sample-prep/start` |
| **After extract** — archive `{chr}-{ctx}.h5` | MethylPipeline (myQNAPcloud) | **`h5Storage`** from `wf.platform_sample_storage` when omitted |

The pipeline must **never** assume FASTQs already live in myQNAPcloud. Laboratory storage is always explicit per study/cohort.

## Database table

`wf.platform_sample_storage` (deploy [`wf_platform_sample_storage.sql`](../../workflow_engine/sql/wf_platform_sample_storage.sql) on Azure SQL or [`sql_pg/wf_platform_sample_storage.sql`](../../workflow_engine/sql_pg/wf_platform_sample_storage.sql) on PostgreSQL).

| Column | Purpose |
|--------|---------|
| `storage_key` | Logical name (`epimethyl-samples` is the default archive profile) |
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

**Required:** laboratory `fastqStorage` on every start request.

**Optional default:** internal `h5Storage` from DB when omitted (`archiveStorageKey` defaults to `epimethyl-samples`).

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
  "sampleCsvs": ["/work/.../healthy.csv", "/work/.../pca.csv"]
}
```

- **Ingress:** `sample.download_fastq` reads from the laboratory `fastqStorage` + per-sample prefix.
- **Archive:** `sample.upload_h5` writes `{chr}-{ctx}.h5` to myQNAPcloud under `epimethyl/samples/{sampleId}/` when `h5Storage` is configured (from DB or explicit body).

Override archive profile:

```json
{ "archiveStorageKey": "epimethyl-samples", ... }
```

(`storageKey` is accepted as a legacy alias for `archiveStorageKey`.)

## Security

- Archive credentials flow in **task `input_json`** for upload steps only.
- Laboratory credentials flow in **task `input_json`** for download steps — supplied per study, not from `wf.platform_sample_storage`.
- Portal RBAC users do not receive raw secrets from the platform table; only the gateway reads them when starting sample prep.
