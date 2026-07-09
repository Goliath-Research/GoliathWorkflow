# SamplePrep test bed

Standalone integration test bed for **SamplePrepPipeline** (download → align → QC screening/remediation → optional fragmentomics → extract). Use this to validate workers, gateway, and workflow engine **without** starting StudyValidationLifecycle or group comparisons.

## Prerequisites

- **Azure SQL** `wf` schema deployed (default `BACKEND_DB=mssql`; see [`docs/deployment/production_runbook.md`](../../docs/deployment/production_runbook.md))
- Action catalog seeded: `bash scripts/refresh_sample_prep_test_bed.sh` (or `python workflow_engine/sql_mssql/seed_action_catalog.py` with `AZURE_SQL_*` env)
- Workflow definitions deployed: `bash scripts/deploy_workflow_definitions.sh`
- Worker-only REST gateway running ([`workflow_engine/rest/gateway.py`](../rest/gateway.py)) for task claim/submit
- Worker registered with `WORKER_STUB_EXTERNAL=1` for dry-run smoke, or full stack for production FASTQs

## Refresh test bed (Azure SQL)

```bash
source .venv/bin/activate
# Same env as the gateway (gateway.env on the gateway VM):
export BACKEND_DB=mssql
export AZURE_SQL_SERVER=<server>.database.windows.net
export AZURE_SQL_DB=MethylPipeline
export AZURE_SQL_USER=...
export AZURE_SQL_PASSWORD=...

bash scripts/refresh_sample_prep_test_bed.sh
```

This exports task schemas, seeds `wf.workflow_action` + JSON schemas, and deploys compiled SamplePrep via direct DB.

## Start via CI helper (recommended for smoke)

```bash
methyl-study-start sample-prep-start request.json
```

Example `request.json`:

```json
{
  "projectPath": "/work/.../project.json",
  "workflow_version_id": 12,
  "fastqStorage": {
    "type": "s3",
    "bucket": "methyl-cohort",
    "region": "us-east-1",
    "credentials": { "authMode": "instance_profile" }
  },
  "sampleStorage": {
    "type": "s3",
    "bucket": "methyl-archive",
    "region": "us-east-1",
    "prefixBase": "studies/plasma/",
    "credentials": { "authMode": "instance_profile" }
  },
  "sampleCsvs": [
    "/work/.../healthy.csv",
    "/work/.../pca.csv"
  ]
}
```

Alternative inputs:

| Field | Purpose |
|-------|---------|
| `samples[]` | Explicit `{ sampleId, sampleDir?, fastqPrefix?, fastqSource? }` |
| `sampleCsv` / `sampleCsvs` | One-column CSVs; names resolved with `samples_base_path` |
| `useProjectSamples: true` | Union cohort CSVs from project `controls` / `diseases` |
| `program_path` | Compile+register SamplePrep on the fly (defaults to `sample_prep.program.json`) |

Response (stdout JSON):

```json
{
  "instance_id": 101,
  "workflow_version_id": 12,
  "context_json": { "...": "..." },
  "n_samples": 240
}
```

Poll instance status via DB (`wf.wf_repo_get_workflow_instance` / portal procs) until **COMPLETED**.

## Planner-only (no start)

```python
from methyl_validation.sample_prep_planner import plan_sample_prep_context

context = plan_sample_prep_context({
    "projectPath": "/work/.../project.json",
    "fastqStorage": {
        "type": "s3",
        "bucket": "bucket",
        "credentials": {"authMode": "instance_profile"},
    },
    "sampleCsvs": ["/work/lists/cohort.csv"],
})
```

Then create/start via portal SQL (`portal.sp_create_and_start_instance`) with `workflow_version_id` and `context_json`.

## Local smoke

```bash
source .venv/bin/activate
export WORKER_STUB_EXTERNAL=1
bash scripts/bootstrap_sample_prep_smoke_fixtures.sh
bash scripts/smoke_sample_prep.sh
```


Bootstrap writes fixtures under `.smoke/sample_prep/` (Parabricks metrics JSON + placeholder FASTQs) so real `methyl_qc` runs while download/align/extract are stubbed.

## QC outcomes

After `sample.methyl_qc`, scope receives:

| Variable | Source |
|----------|--------|
| `qcPass` | `guardrails.overall_pass` |
| `qcDisposition` | `screening.disposition` |
| `trimFront2` / `trimTail2` | `screening.trim_*` |
| `remediateAlignment` | true when disposition is `REALIGN_TRIM` with non-zero trim |

After `sample.extraction_qc`, scope receives:

| Variable | Source |
|----------|--------|
| `extractionQcPass` | `guardrails.overall_pass` |

**Pass path:** optional fragmentomics → `methyl_extract` → `extraction_qc` → [`extractionQcPass`] `archive_sample` mode=`full` (when `sampleDestination` set) → `delete_fastqs` → `delete_bam`.

**Remediation:** `REALIGN_TRIM` → `trim_fastq` (fastp) → Parabricks `forceRealign` → `methyl_qc` retry → same pass path if retry passes.

**Reject path:** alignment or extraction QC fail → `archive_sample` mode=`qc_only` (when `sampleDestination` set) → `delete_fastqs` → `delete_bam` → `sample.qc_failed`.

Audit artifacts per sample:

- `{sampleDir}/{sampleId}.sample_prep_log.jsonl` — append-only prep log
- Alignment QC export with `qc_history` (retries append, never overwrite)

Offline cohort screening (existing QC JSONs, no workflow): `scripts/alignment_qc_cohort_screening.py`.

## Related

- Staged lifecycle: [`portal_study_lifecycle.md`](portal_study_lifecycle.md)
- Worker contract: [`../contract/sample_prep_capabilities.md`](../contract/sample_prep_capabilities.md)
- Production runbook: [`../../docs/deployment/production_runbook.md`](../../docs/deployment/production_runbook.md)
- Example planner output: [`../sql/instance_context_examples/sample_prep_from_planner.json`](../sql/instance_context_examples/sample_prep_from_planner.json)
