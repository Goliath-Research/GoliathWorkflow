# Production study runbook

End-to-end operator checklist for real FASTQ → HDF5 → validation on `/work/epimethyl`.

**Platform install (gateway + Arc workers + enroll):** see [production-platform.md](production-platform.md) first. This page focuses on study execution and gateway security detail.

## Prerequisites

- [ ] Shared storage mounted at `/work/epimethyl` on all worker nodes
- [ ] `bash scripts/verify_e2e_node.sh` passes on GPU workers
- [ ] Workflow REST gateway running on dedicated Linux VM (`methyl-gateway` systemd unit; see `deploy/env/gateway.mssql.env.example` / `gateway.security.env.example`)
- [ ] Database schema deployed (Azure SQL for production portal)
- [ ] Action catalog seeded (`seed_action_catalog.py`)
- [ ] Workflow definitions deployed (`deploy_workflow_definitions.sh`)
- [ ] Workers **Arc Connected**, portal-preregistered by public IP, enrolled via gateway, systemd running
- [ ] Reference FASTA and project JSON on shared storage
- [ ] Portal middle-tier using Azure SQL `portal.sp_*` (not the worker gateway)

**Reference genomes on myQNAPcloud:** Keep a durable copy of `/work/genomes` (linear + annotation + pangenome) in bucket `epimethyl` for future deployments. Sync with Access Key / Secret Key via S3 (not rsync):

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
scripts/sync_genomes_to_s3.sh --dry-run
scripts/sync_genomes_to_s3.sh
# optional: scripts/sync_genomes_to_s3.sh --only linear|annotation|pangenome
# or a leaf path: --only pangenome/GRCh38/d9-bs/1.70
```

Destination: `s3://epimethyl/genomes/` at `https://s3.us-east-1.myqnapcloud.io`. Full upload map, pin→asset resolution, and Phase 0 provision: [reference-inventory-qnap.md](reference-inventory-qnap.md).

## Stage 1 — SamplePrepPipeline

See [`workflow_engine/docs/portal_study_lifecycle.md`](../../workflow_engine/docs/portal_study_lifecycle.md), [`workflow_engine/sql_mssql/SamplePrepFlow.md`](../../workflow_engine/sql_mssql/SamplePrepFlow.md), and the SamplePrep test bed [`workflow_engine/docs/sample_prep_test_bed.md`](../../workflow_engine/docs/sample_prep_test_bed.md).

**Alignment modes:** each sample uses one path from instance/profile `alignmentMode` — `linear` (`parabricks.fq2bam`), `pangenome` (stock Giraffe), or `pangenome_wgbs` (methylGrapher dual C2T/G2A via `sample.methylgrapher_wgbs_align` / `sample.methylgrapher_wgbs_extract`). Procedure `buffy_wgbs_pangenome_gene_fc` selects `pangenome_wgbs`. Program checks `useWgbsPangenome` **before** `usePangenome` — do not fall back to stock Giraffe when the BS bundle is missing.

**WGBS pangenome operator checklist:**

- [ ] Site `pangenome_wgbs_genome` / `actionConfig.methylgrapher_wgbs` provisioned (`pangenome-grch38-d9-bs-1.70` on QNAP → `/work/genomes/…/d9-bs/1.70`)
- [ ] `METHYL_METHYLGRAPHER_IMAGE` pinned on GPU workers (see [`workers/docker/methylgrapher/README.md`](../../workers/docker/methylgrapher/README.md))
- [ ] Canary passed before promoting `buffy_wgbs_pangenome_gene_fc` in production (`bash scripts/smoke_sample_prep_real.sh --tier subset`; checklist [`workers/tests/test_methylgrapher_wgbs_canary.md`](../../workers/tests/test_methylgrapher_wgbs_canary.md); ADO [`ci/azure-pipelines-sample-prep-canary.yml`](../../ci/azure-pipelines-sample-prep-canary.yml))

**Recommended start:** portal SQL after planning (`portal.sp_create_and_start_instance`). For CI / Admin CLI:

```bash
methyl-study-start sample-prep-start request.json
# request.json: projectPath, workflow_version_id, fastqStorage, sampleCsvs, ...
```

**Ingress vs retention:** `fastqStorage` must point at **laboratory-owned** storage (never inferred from myQNAPcloud). Sample archive (`sampleStorage` / `sampleDestination`; legacy alias `h5Storage`) defaults from `portal.resource_profile` → published `cfg.storage_endpoint` (e.g. `epimethyl-archive`) when omitted. See [portal_resource_profile.md](portal_resource_profile.md).

**Local smoke (stub worker):**

```bash
export WORKER_STUB_EXTERNAL=1
bash scripts/smoke_sample_prep.sh
```

Poll until **COMPLETED**. Do not start validation until all samples have per-chromosome HDF5s under `/work/samples/{id}/` (and remote archive when `sampleDestination` is configured).

**Sample archive:** After extraction QC disposition, `sample.archive_sample` uploads a curated bundle (QC JSON, optional FASTQs, H5 including patterns) to S3/Azure/NFS per `sampleDestination`. Modes: `full` (extraction pass) or `qc_only` (terminal fail). Local HDF5 files are retained for validation; BAM is never uploaded. Retired action: `sample.upload_h5` — use `sample.archive_sample`.

**FASTQ retention:** SamplePrep keeps FASTQs until final QC (pass or final fail after any trim/realign retry). Remediation runs `sample.trim_fastq` → the **same** alignment mode with `forceRealign` → `methyl_qc` retry before optional `delete_fastqs`.

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

Recommended: portal SQL after planning. For CI / Admin CLI:

```bash
methyl-study-start validation-start request.json
# request.json: projectPath, workflow_version_id, featureIterations, seed, ...
```

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Parabricks tasks fail | `verify_parabricks.sh`, NGC login, `nvidia-ctk` |
| methylGrapher WGBS tasks fail | `METHYL_METHYLGRAPHER_IMAGE`, BS bundle under `d9-bs/1.70`, canary checklist |
| Extract fails | `verify_methyl_extractor.sh`, `HDF5_PLUGIN_PATH`; WGBS pangenome path uses `methylgrapher.wgbs_extract` |
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
# Optional legacy flags (gateway is worker-only; Entra is not used for HTTP admin)
GATEWAY_REQUIRE_ENTRA=0
AZURE_TENANT_ID=<tenant>
GATEWAY_ENTRA_AUDIENCE=api://methyl-gateway
```

| Identity | Routes | Auth |
|----------|--------|------|
| **Worker** | `POST /v1/workers/*` | `worker_id` + `worker_token` over HTTPS |

**EpiPortal does not call the gateway.** Portal workflow builder and instance lifecycle use Azure SQL procs (`portal.sp_*`). See [`workflow_engine/docs/portal_study_lifecycle.md`](../../workflow_engine/docs/portal_study_lifecycle.md).

Release automation (direct DB from a privileged host or CI secret):

```bash
export BACKEND_DB=mssql
# AZURE_SQL_* credentials
bash scripts/deploy_workflow_definitions.sh
python workflow_engine/sql_mssql/seed_action_catalog.py --use-db
```

### Cluster registration + Tier C IP bind (phase 3)

Deploy security columns and worker enrollment:

- [`workflow_engine/sql_mssql/wf_cluster_security_columns.sql`](../../workflow_engine/sql_mssql/wf_cluster_security_columns.sql)
- [`workflow_engine/sql_mssql/wf_worker_enrollment.sql`](../../workflow_engine/sql_mssql/wf_worker_enrollment.sql)
- [`workflow_engine/sql_mssql/portal_worker_enrollment_api.sql`](../../workflow_engine/sql_mssql/portal_worker_enrollment_api.sql)

(PostgreSQL: `sql_pg/` counterparts.)

**Production:** Portal upserts each VM public IP (`portal.sp_upsert_worker_enrollment`).
On the worker (no DB credentials):

```bash
export WORKER_API_BASE=https://gateway.example.com/v1
methyl-worker enroll --api-base "$WORKER_API_BASE" --cluster gpu-west --key "$(hostname -s)"
```

Day-2 claim/submit uses the issued token. Production gateway security:

```bash
GATEWAY_WORKER_IP_BIND=1
GATEWAY_TRUSTED_PROXY_CIDRS=127.0.0.1/32
# Required in production — reject workers without matching Arc resource id:
GATEWAY_REQUIRE_ARC_ATTEST=1
```

**Dev/bootstrap only** (`scripts/register_worker.py` with Azure SQL / Postgres env on a trusted host):

```bash
bash scripts/register_worker.sh --cluster gpu-west --key "$(hostname -s)" \
  --allowed-cidr 203.0.113.0/24 --allowed-cidr 198.51.100.10/32 \
  --require-arc
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
# Worker-only gateway: health is public; admin paths return 404
curl -sS -o /dev/null -w '%{http_code}\n' https://gateway/v1/health
curl -sS -o /dev/null -w '%{http_code}\n' -X POST https://gateway/v1/admin/catalog/seed \
  -H 'Content-Type: application/json' -d '{}'
# Expect: health 200, admin 404

# Catalog seed (direct DB, not gateway):
set -a && source /work/epimethyl/env/gateway.env && set +a
python workflow_engine/sql_mssql/seed_action_catalog.py
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

Production gateway hardening: `GATEWAY_REQUIRE_ARC_ATTEST=1` rejects worker polls when `X-Arc-Resource-Id` does not match the enrolled Arc machine (see [production-platform.md](production-platform.md)).

