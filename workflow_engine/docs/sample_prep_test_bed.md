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

## Local smoke (stubbed externals)

```bash
source .venv/bin/activate
export WORKER_STUB_EXTERNAL=1
bash scripts/bootstrap_sample_prep_smoke_fixtures.sh
bash scripts/smoke_sample_prep.sh
```

Bootstrap writes fixtures under `.smoke/sample_prep/` (Parabricks metrics JSON + placeholder FASTQs). With `WORKER_STUB_EXTERNAL=1`, download/align/extract/QC handlers that are stubbed return synthetic pass artifacts — this validates the **workflow graph + DB claim path**, not real Parabricks/methylGrapher science.

## Real-data canary (GPU, on-demand)

For periodical confirmation of the full SamplePrep science path on one public WGBS
sample (linear + stock Giraffe + methylGrapher), use the real canary — **not** the
stub smoke and **not** catalog/golden PR tests.

| Piece | Path |
|-------|------|
| Pinned provenance | [`tests/real_data/sample_prep_canary/provenance.json`](../../tests/real_data/sample_prep_canary/provenance.json) (`SRR28293403` / HG00621) |
| Config example | [`tests/real_data/sample_prep_canary/registry.example.json`](../../tests/real_data/sample_prep_canary/registry.example.json) |
| Provision FASTQs | `bash scripts/provision_sample_prep_canary.sh` |
| Run canary | `bash scripts/smoke_sample_prep_real.sh --tier subset` |
| ADO pipeline | [`ci/azure-pipelines-sample-prep-canary.yml`](../../ci/azure-pipelines-sample-prep-canary.yml) |
| Checklist | [`workers/tests/test_methylgrapher_wgbs_canary.md`](../../workers/tests/test_methylgrapher_wgbs_canary.md) |

```bash
source .venv/bin/activate
unset WORKER_STUB_EXTERNAL
# One-time: download SRA, write subset, checksum, stage under fastqStorage root
# Stages under /work/genomes/pangenome/canary/... (HPRC/methylGrapher provenance)
bash scripts/provision_sample_prep_canary.sh --subset-pairs 2000000
scripts/sync_genomes_to_s3.sh --only pangenome/canary
# Merge checksums into site testing.sample_prep_canary
# (fastq_storage.basePath=/work/genomes/pangenome)
export METHYL_SITE_CONFIG=/work/site/methyl_site.json
bash scripts/smoke_sample_prep_real.sh --tier subset
# After subset passes (expensive):
bash scripts/smoke_sample_prep_real.sh --tier full
```

**Interpretation**

- `linear` — biological reference (Parabricks `fq2bam_meth` + MethylExtract).
- `pangenome` — stock Giraffe **engineering comparator only** (workflow/artifacts; no methylation parity).
- `pangenome_wgbs` — methylGrapher BS path; compared to linear via operator-set thresholds.

Retain qualification JSON/JUnit/Markdown under the canary report directory for longitudinal
comparison. NVIDIA does not publish a WGBS FASTQ fixture; GSE261315 is the citable public source.

## Linear vs pangenome_wgbs comparison (experiment-only)

Use this when evaluating whether methylGrapher WGBS improves usable CpG read support vs linear
on real lab samples (plasma + buffy), with alignment wall time as a cost metric.

**Compute asymmetry (do not confuse with canary GPU label):** linear arms use **Parabricks GPU**;
`pangenome_wgbs` arms use the **CPU-only** methylGrapher(+vg) Docker image. A “GPU worker” is
still required for the linear arm and for MethylExtractor on linear, but methylGrapher itself
never uses CUDA — longer wall time on the same GH200 is expected.

| Piece | Path |
|-------|------|
| Runner | `bash scripts/compare_sample_prep_linear_vs_wgbs.sh` |
| Core | [`ops/sample_prep_mode_compare.py`](../ops/sample_prep_mode_compare.py) |
| Helpers | [`packages/methylutils/.../sample_prep_mode_compare.py`](../../packages/methylutils/methyl_utils/testing/sample_prep_mode_compare.py) |
| Example inputs | [`tests/real_data/sample_prep_mode_compare/`](../../tests/real_data/sample_prep_mode_compare/) |
| Reports | `/work/samples/_comparisons/<stamp>/` (+ `latest` symlink) |

### Layout (lab/QNAP FASTQ root + temporary mode trees)

Laboratories and QNAP store FASTQs **directly under** `/work/samples/<sampleId>/` — there is
**no** `/fastq` child folder. Keep that contract.

`linear/` and `pangenome_wgbs/` exist **only for this dual-align experiment** so both BAM/QC/H5
trees can coexist. They are **not** a new production or lab/QNAP convention. Once one mode wins
consistently, return to a single flat `/work/samples/<sampleId>/` tree.

```text
/work/samples/<sampleId>/
  <sampleId>_1.fastq.gz          # shared; same layout as QNAP / lab delivery
  <sampleId>_2.fastq.gz
  linear/                        # experiment-only: BAM, QC, H5, manifests
  pangenome_wgbs/                # experiment-only: BAM/GAF, QC, H5, manifests
```

### Run

```bash
source .venv/bin/activate
unset WORKER_STUB_EXTERNAL

# Plan four start payloads (2 samples × 2 modes) without touching the DB:
bash scripts/compare_sample_prep_linear_vs_wgbs.sh --dry-run

# One-time root FASTQ download from lab storage, then both arms:
bash scripts/compare_sample_prep_linear_vs_wgbs.sh \
  --fastq-storage-json /path/to/lab_fastq_storage.json \
  --thresholds-json tests/real_data/sample_prep_mode_compare/thresholds.example.json

# Or when non-empty root FASTQs already exist:
bash scripts/compare_sample_prep_linear_vs_wgbs.sh \
  --reuse-local-fastq \
  --thresholds-json tests/real_data/sample_prep_mode_compare/thresholds.example.json
```

Each arm sets `sampleDir` to the mode subdirectory, `alignmentMode` accordingly, and
`deleteFastqs: false`. Root FASTQs are hardlinked into the mode dir before start so aligners
see them without a second cloud pull.

### No-archive until after review

Starts **omit** `sampleStorage` / `sampleDestination`. `sample.archive_sample` then skips with
`archiveSkipped=true` (does not overwrite QNAP). Do **not** archive mid-experiment.

### Promote / archive the winning arm

After reviewing `/work/samples/_comparisons/latest/comparison.md`:

1. Copy or move the winning mode tree’s BAM/QC/H5/manifests up to the flat sample root (or
   re-run SamplePrep once with `alignmentMode` set to the winner and `sampleDir` =
   `/work/samples/<sampleId>/`).
2. Start a normal SamplePrep (or archive-only path) **with** `sampleStorage` so QNAP receives a
   single arm.
3. Remove the unused experiment mode subdirectory when no longer needed.

Hypothesis framing in the report: **pangenome_wgbs improves usable read support at CpG
positions** (coverage/site yield); alignment runtime is a cost metric — not a stock-Giraffe
methylation-biology claim. Finish a live 4-arm execute (plasma + buffy × linear +
`pangenome_wgbs`) and review `/work/samples/_comparisons/latest/comparison.md` before deciding
whether the CpG-quality gain justifies the CPU wall-time cost.

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
