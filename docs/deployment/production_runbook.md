# Production study runbook

End-to-end operator checklist for real FASTQ → HDF5 → validation on `/work/epimethyl`.

## Prerequisites

- [ ] Shared storage mounted at `/work/epimethyl` on all worker nodes
- [ ] `bash scripts/verify_e2e_node.sh` passes on GPU workers
- [ ] Workflow REST gateway running on dedicated Linux VM (`methyl-gateway` systemd unit; see `deploy/env/gateway.postgres.env.example` or `gateway.mssql.env.example`)
- [ ] Database schema deployed (Azure SQL phase 1 or Azure PostgreSQL phase 2)
- [ ] Action catalog seeded (`seed_action_catalog.py`)
- [ ] Workflow definitions deployed (`deploy_workflow_definitions.sh`)
- [ ] Workers registered and systemd units running (`WORKER_API_BASE` → gateway VM)
- [ ] Reference FASTA and project JSON on shared storage
- [ ] Portal or API client pointed at `WORKER_API_BASE`

## Stage 1 — SamplePrepPipeline

See [`workflow_engine/docs/portal_study_lifecycle.md`](../../workflow_engine/docs/portal_study_lifecycle.md) and the SamplePrep test bed [`workflow_engine/docs/sample_prep_test_bed.md`](../../workflow_engine/docs/sample_prep_test_bed.md).

**Recommended start:**

```http
POST /v1/studies/sample-prep/start
{
  "projectPath": "/work/epimethyl/data/project_....json",
  "workflow_version_id": <from workflow_versions.json SamplePrepPipeline>,
  "fastqStorage": {
    "type": "s3",
    "bucket": "<laboratory-cohort-bucket>",
    "region": "us-west-2",
    "credentials": { "authMode": "instance_profile" }
  },
  "sampleCsvs": ["/work/.../healthy.csv", "/work/.../pca.csv"]
}
```

**Ingress vs retention:** `fastqStorage` must point at **laboratory-owned** storage (never inferred from myQNAPcloud). HDF5 archive (`h5Storage`) defaults from `portal.resource_profile` when omitted. See [portal_resource_profile.md](portal_resource_profile.md).

**Manual instance** (hand-built `context_json`):

```http
POST /v1/workflows/instances
{
  "workflow_version_id": <from workflow_versions.json SamplePrepPipeline>,
  "context_json": {
    "projectPath": "/work/epimethyl/data/project_....json",
    "primaryAnalyte": "buffy_coat",
    "isCfdna": false,
    "referenceFasta": "/work/epimethyl/data/reference.fa",
    "samples": [ ... ]
  }
}
```

**Local smoke (stub worker):**

```bash
export WORKER_STUB_EXTERNAL=1
bash scripts/smoke_sample_prep.sh
```

Poll until **COMPLETED**. Do not start validation until all samples have per-chromosome HDF5s archived (when `h5Storage` is configured) and present locally under `/work/samples/{id}/`.

**HDF5 archive:** After `sample.methyl_extract`, `sample.upload_h5` copies `{chr}-{ctx}.h5` to S3/Azure/NFS per instance `h5Storage` + per-sample prefix. Local files are retained for validation and BAM deletion.

**FASTQ retention:** SamplePrep keeps FASTQs until final QC (pass or final fail after any trim/realign retry). Samples with `REALIGN_READ2_TRIM` run `sample.trim_fastq` → Parabricks `forceRealign` → `methyl_qc` retry before `delete_fastqs`.

**Cohort screening (existing QC JSONs):**

```bash
source .venv/bin/activate
python scripts/alignment_qc_cohort_screening.py \
  --qc-dir /work/AlignmentQC \
  --group healthy=/path/healthy_samples.csv \
  --group pca=/path/pca_samples.csv \
  --out /work/AlignmentQC/screening_report
```

Review `remediation_manifest.csv` for batch remediation via `SamplePrepRemediationPipeline` (`deploy_workflow_definitions.sh` compiles both programs).

## Stage 2 — StudyValidationLifecycle

Recommended:

```http
POST /v1/studies/validation/start
{
  "projectPath": "/work/epimethyl/data/project_....json",
  "workflow_version_id": <from workflow_versions.json StudyValidationLifecycle>,
  "featureIterations": 30,
  "seed": 42
}
```

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Parabricks tasks fail | `verify_parabricks.sh`, NGC login, `nvidia-ctk` |
| Extract fails | `verify_methyl_extractor.sh`, `HDF5_PLUGIN_PATH` |
| Worker idle | `WORKER_CAPABILITY` filter vs task capability |
| FOREACH errors | `08_foreach_support.sql` applied on PostgreSQL |

Platform notes: [`platform_matrix.md`](platform_matrix.md).  
Worker env: [`worker_node.md`](worker_node.md).

## Gateway VM — Azure managed identity

Use managed identity on the dedicated Linux gateway VM so the process never stores SQL passwords.

**Azure SQL (phase 1):**

1. Enable system- or user-assigned managed identity on the gateway VM.
2. In Azure SQL, add the MI as an Entra ID user (or use a group that includes it) with `db_datareader` / `db_datawriter` / execute on `wf` procedures as required.
3. Set in `gateway.env`:
   ```bash
   BACKEND_DB=mssql
   WF_USE_MANAGED_IDENTITY=1
   AZURE_SQL_SERVER=<server>.database.windows.net
   AZURE_SQL_DB=MethylPipeline
   # AZURE_CLIENT_ID=<user-assigned MI client id>   # omit for system-assigned
   ```
4. Do **not** set `AZURE_SQL_USER` / `AZURE_SQL_PASSWORD` when MI is enabled.
5. Restart: `sudo systemctl restart methyl-gateway`.

**Azure Database for PostgreSQL (phase 2):**

1. Create an Entra principal for the MI in PostgreSQL (Azure portal → Microsoft Entra ID admins, or `pgaadauth_create_principal`).
2. Set `POSTGRES_USER` to that principal name and `WF_USE_MANAGED_IDENTITY=1` (see `deploy/env/gateway.postgres.env.example`).

**Verify on the VM:**

```bash
curl -s http://127.0.0.1:8080/v1/health
# IMDS (system-assigned): curl -H Metadata:true \
#   "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https://database.windows.net/"
```

Token refresh is handled inside the gateway (cached ~55 minutes). ODBC Driver 18 for SQL Server must be installed for MSSQL MI.

## Gateway security (mixed worker topology)

Tiered model: **TLS edge** → **Entra JWT for control-plane APIs** → **registered cluster + worker token for workers** → optional **cluster CIDR bind** for public-tier workers → **Azure SQL private endpoint**.

### TLS reverse proxy (phase 1)

1. `methyl-gateway` binds loopback only (`WF_GATEWAY_HOST=127.0.0.1` in [`deploy/env/gateway.security.env.example`](../../deploy/env/gateway.security.env.example)).
2. Install TLS certs under `/etc/ssl/methyl-gateway/` (`fullchain.pem`, `privkey.pem`).
3. Run `bash scripts/setup_gateway_nginx.sh --hostname <gateway-fqdn>`.
4. NSG: **close public 8080**; allow **443** from VPN CIDR and known worker egress only.
5. Set `WORKER_API_BASE=https://<gateway-fqdn>/v1` on all workers.

### Entra ID — two gateway identities (phase 2)

Merge [`deploy/env/gateway.security.env.example`](../../deploy/env/gateway.security.env.example) into `gateway.env`:

```bash
GATEWAY_REQUIRE_ENTRA=1
AZURE_TENANT_ID=<tenant>
GATEWAY_ENTRA_AUDIENCE=api://methyl-gateway   # app registration Application ID URI
GATEWAY_ENTRA_ADMIN_ROLES=WorkflowEngineAdmin   # CI / release operator app role
```

| Identity | Routes | Auth |
|----------|--------|------|
| **Worker** | `POST /v1/workers/*` | `worker_id` + `worker_token` over HTTPS |
| **Admin** | `POST /v1/admin/*` (+ legacy `/v1/studies/*`, `/v1/workflows/*`, `/v1/actions*`) | `Authorization: Bearer <entra-jwt>` with admin app role |

**EpiPortal does not call the gateway.** Portal workflow builder and instance lifecycle use Azure SQL procs (`portal.sp_*`). See [`workflow_engine/docs/portal_study_lifecycle.md`](../../workflow_engine/docs/portal_study_lifecycle.md).

Release automation (no direct SQL creds on operator laptops):

```bash
export WORKER_API_BASE=https://<gateway-fqdn>/v1
export GATEWAY_ADMIN_BEARER_TOKEN=$(az account get-access-token --resource api://methyl-gateway --query accessToken -o tsv)
bash scripts/deploy_workflow_definitions.sh
python workflow_engine/sql_mssql/seed_action_catalog.py --use-gateway
```

Legacy operator routes remain as **admin-only CI aliases** when Entra is enabled; they are not for portal UI.

### Cluster registration + Tier C IP bind (phase 3)

Deploy [`workflow_engine/sql_mssql/wf_cluster_security_columns.sql`](../../workflow_engine/sql_mssql/wf_cluster_security_columns.sql) (Azure SQL) or [`workflow_engine/sql_pg/wf_cluster_security_columns.sql`](../../workflow_engine/sql_pg/wf_cluster_security_columns.sql) (PostgreSQL).

Register workers (both backends via gateway DB env):

```bash
bash scripts/register_worker.sh --cluster gpu-west --key "$(hostname -s)" \
  --allowed-cidr 203.0.113.0/24 --allowed-cidr 198.51.100.10/32 \
  --require-arc
```

On the gateway VM for public-tier clusters:

```bash
GATEWAY_WORKER_IP_BIND=1
GATEWAY_TRUSTED_PROXY_CIDRS=127.0.0.1/32
# Optional Arc attestation:
# GATEWAY_REQUIRE_ARC_ATTEST=1
```

### Azure SQL private endpoint (data plane)

Workers never connect to SQL directly. Lock down the database to the gateway only:

1. Create a **private endpoint** for Azure SQL in the gateway VNet.
2. Azure portal → SQL server → **Networking** → disable **public network access**.
3. Remove per-operator IP firewall rules; retain only private-endpoint path.
4. Confirm gateway MI is the sole Entra SQL principal with `wf` execute rights.
5. From the gateway VM: `curl -s http://127.0.0.1:8080/v1/health` (gateway) then verify workflow deploy still works.

### Verification

```bash
bash scripts/test_gateway_remote.sh --ssh-only
# Operator API without JWT should 401 when GATEWAY_REQUIRE_ENTRA=1:
curl -sS -o /dev/null -w '%{http_code}\n' -X POST https://gateway/v1/workflows/instances \
  -H 'Content-Type: application/json' -d '{"workflow_version_id":1}'
```

## Arc compliance and incident response

Arc onboarding is a **production prerequisite** for worker VMs. See [arc_worker_runbook.md](arc_worker_runbook.md).

### Defender for Servers

1. Enable **Defender for Servers Plan 2** on all Arc-enabled worker machines.
2. Route high-severity alerts to the security operations channel (email, Teams, or ticketing).
3. On **High** or **Critical** malware / compromise findings on a worker Arc machine:
   - Set `wf.cluster.status = 'DISABLED'` for the bound cluster (or disable the individual worker row).
   - Stop `methyl-worker.service` on affected nodes: `sudo systemctl stop methyl-worker.service`.
   - Revoke worker token if needed: re-register or set worker `status` inactive in DB.
   - Investigate before re-enabling; require clean Defender scan + Arc **Connected** + policy compliance.

### Microsoft Sentinel

1. Connect Arc / AMA logs to a Log Analytics workspace used by Sentinel.
2. Create analytics rules (or use built-in) for:
   - Arc agent **Disconnected** > 15 minutes on `phi=true` machines
   - Guest Configuration **non-compliant** on worker resource groups
   - Unusual volume of failed `POST /v1/workers/*` (gateway access logs, if forwarded)
3. Playbook (manual or Logic App): on correlated alert, disable cluster and notify on-call.

### Cluster disable procedure

```sql
-- PostgreSQL example
UPDATE wf.cluster SET status = 'DISABLED', updated_at_utc = now() AT TIME ZONE 'utc'
WHERE cluster_key = 'gpu-west';
```

Re-enable only after Arc shows **Connected**, policy compliance is green, and security sign-off.

Optional gateway hardening: `GATEWAY_REQUIRE_ARC_ATTEST=1` rejects worker polls when `X-Arc-Resource-Id` does not match `wf.cluster.arc_resource_id`.

