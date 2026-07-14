# Portal resource profiles (archive storage)

Internal **retention** storage for processed sample artifacts (methylation HDF5, future archives) is configured in the **`cfg` registry** (`cfg.storage_endpoint` + `cfg.credential`). `portal.resource_profile` holds a thin **pointer** used when study start omits `sampleStorage`.

## Ingress vs retention

| Stage | Storage owner | Config source |
|-------|---------------|---------------|
| **First processing** — download FASTQs | Laboratory (external S3, Azure Blob, etc.) | **`fastqStorage` required** on every study start (published lab endpoint selected in portal) |
| **After extract** — archive FASTQs, QC JSON, `{chr}-{ctx}.h5` | MethylPipeline (e.g. myQNAPcloud) | **`sampleStorage`** from named `cfg.storage_endpoint` via `portal.resource_profile` when omitted (`h5Storage` alias) |

The workflow engine stores resolved `fastqStorage` / `h5Storage` in `workflow_instance.context_json`. Workers never query SQL for storage accounts.

## Production authoring (EpiPortal only)

All storage accounts (lab ingress, archive, shared) are managed by **lab admins** or **infrastructure admins** (RBAC). EpiPortal validates JSON against [`schemas/domain/storage_location.schema.json`](../../schemas/domain/storage_location.schema.json) and calls:

| Proc | Purpose |
|------|---------|
| `portal.sp_upsert_credential` / `sp_publish_credential` | Write/publish secret body (`secret_json`) |
| `portal.sp_list_credentials` / `sp_get_credential` | **Redacted** — `authMode`, `content_hash`, never secret body |
| `portal.sp_upsert_storage_endpoint` / `sp_publish_storage_endpoint` | Location JSON + `credential_name` |
| `portal.sp_list_storage_endpoints` / `sp_get_storage_endpoint` | Location + credential name; never secret body |

`methyl-cfg upsert credential|storage_endpoint` is **dev / CI / bootstrap only**.

## Database: `portal.resource_profile`

Deploy [`workflow_engine/sql_mssql/portal_resource_profile.sql`](../../workflow_engine/sql_mssql/portal_resource_profile.sql) or PG twin (after `cfg` tables). Seed profile references the archive endpoint:

```json
{
  "sampleStorageEndpoint": "epimethyl-archive",
  "prefixBase": "samples/",
  "scope": "archive"
}
```

Bootstrap also seeds `cfg.storage_endpoint` `epimethyl-archive` + `cfg.credential` `epimethyl-archive-keys` with `REPLACE_WITH_*` placeholders — replace via portal before production use.

Legacy inline `credentials` inside `profile_json` still work for compatibility but are **not** the preferred shape.

| Column | Purpose |
|--------|---------|
| `profile_key` | Logical name (`epimethyl-samples` default) |
| `profile_type` | e.g. `cfg_storage_endpoint_ref` |
| `profile_json` | Endpoint ref or legacy full storage JSON |
| `status` | `ACTIVE` / `DISABLED` |

## Sample prep API

**Required:** laboratory `fastqStorage` on every start request (endpoint selected by operator among published redacted list; expansion injects secrets at schedule/study-start).

**Optional default:** `sampleStorage` from portal profile → cfg endpoint when omitted (`archiveProfileKey` defaults to `epimethyl-samples`).

```json
{
  "projectPath": "/work/projects/.../project_....json",
  "workflow_version_id": "<sample_prep_version>",
  "fastqStorage": {
    "type": "s3",
    "bucket": "lab-external-cohort",
    "region": "us-west-2",
    "credentials": { "authMode": "instance_profile" }
  },
  "sampleCsvs": ["/work/.../healthy.csv"]
}
```

## Worker delivery (dumb workers)

1. Study start / schedule expand embeds auth fields + `contentHash` into task `input_json`.
2. Workers authenticate to the gateway only (production: `GATEWAY_REQUIRE_ARC_ATTEST=1`, `X-Arc-Resource-Id`).
3. On transfer, workers refresh **node-local** Fernet cache under `/var/lib/methyl/storage-credentials/` when `contentHash` changes. Do **not** store secrets on `/work`.
4. Azure Key Vault on workers is optional, not required.

## Security

- Portal list/get APIs never return raw cloud keys.
- Gateway must not log credential bodies from claim/submit payloads.
- Laboratory credentials are study-bound; archive credentials come from infrastructure-admin endpoints.
- Do not put AccessKeys in project JSON under `/work/projects`.
