# Production study runbook

End-to-end operator checklist for real FASTQ → HDF5 → validation on `/work/epimethyl`.

## Prerequisites

- [ ] Shared storage mounted at `/work/epimethyl` on all worker nodes
- [ ] `bash scripts/verify_e2e_node.sh` passes on GPU workers
- [ ] Workflow REST gateway running on dedicated Linux VM (`methyl-gateway` systemd unit; see `deploy/env/gateway.*.env.example`)
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
    "bucket": "methyl-cohort",
    "region": "us-east-1",
    "credentials": { "authMode": "instance_profile" }
  },
  "sampleCsvs": ["/work/.../healthy.csv", "/work/.../pca.csv"]
}
```

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

Poll until **COMPLETED**. Do not start validation until all samples have per-chromosome HDF5s.

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
