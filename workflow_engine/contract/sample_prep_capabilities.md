# Sample prep worker capabilities

Contract for **SamplePrepPipeline** remote workers. All workers use the standard poll/submit protocol ([`../workers/WORKER_PROTOCOL.md`](../../workers/WORKER_PROTOCOL.md)).

## Result codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `> 0` | Success with optional semantic payload (avoid for gate variables) |
| `< 0` | Permanent failure — instance marks **FAILED** |

QC gate variable `qcPass` comes from **`output_json.guardrails.overall_pass`** (boolean), not `result_code`.

After `methyl-qc`, scope also receives **`qcDisposition`**, **`trimFront2`**, **`qcAttemptReason`**, and **`remediateR2Trim`** (boolean) for the remediation branch.

## FASTQ retention

**Do not delete FASTQs before final QC.** `sample.delete-fastqs` runs only after QC pass or final fail (including post-trim retry). Trimming (`sample.trim-fastq`) requires original `*_1.fastq.gz` / `*_2.fastq.gz` still present.

## Audit trail

- QC export: append-only **`qc_history`** on each `{sampleId}.json` in alignment QC output.
- Sample dir: append-only **`{sampleId}.sample_prep_log.jsonl`** for every prep action (download, align, trim, QC, delete).

## Idempotency

| Capability | Safe to retry when |
|------------|-------------------|
| `sample.download-fastq` | Destination FASTQs missing, or remote size/mtime differ from local |
| `sample.delete-fastqs` | FASTQs already absent (no-op success) |
| `sample.delete-bam` | BAM already absent (no-op success) |
| `parabricks.fq2bam` | Only when BAM missing or QC artifact missing (`{sampleId}.json` or `{sampleId}.qc-metrics.tar`); pass **`forceRealign: true`** after trim to clear stale outputs |
| `sample.trim-fastq` | When trimmed FASTQs missing or `trimFront2` changed |
| `methyl-extract` | When HDF5 outputs missing for `project.chromosomes × extract_contexts` |
| `sample.upload-h5` | Remote object missing or size/ETag differs from local `{chr}-{ctx}.h5` |

## Lease / retry

- Default lease: **3600 s** for Parabricks and MethylExtractor; **600 s** for download/delete/QC.
- Transient failures (network, GPU OOM): worker returns lease via heartbeat extension or explicit fail; middle-tier may re-queue if policy allows.
- Permanent failures (`result_code < 0`): instance **FAILED**; operator fixes inputs and starts a new instance.

---

## `sample.download-fastq`

**action_name:** `sample.download_fastq`

### input_json

```json
{
  "tool": "SampleDownloadFastq",
  "sampleId": "DPLST-051425-111148",
  "sampleDir": "/work/samples/DPLST-051425-111148",
  "fastqSource": {
    "type": "s3",
    "bucket": "methyl-cohort",
    "prefix": "plasma/DPLST-051425-111148/",
    "region": "us-east-1",
    "credentials": { "authMode": "instance_profile" }
  }
}
```

`fastqSource.prefix` points at a **folder prefix** (or single `.fastq.gz` object). All `*.fastq.gz` / `*.fq.gz` objects under that prefix are downloaded into `sampleDir`. Typical layout: `<sample>_1.fastq.gz`, `<sample>_2.fastq.gz`, but any matching extension in the folder is included.

**Idempotency:** for each file, download is skipped when the local copy already exists with the same **size** and **mtime** (±1 s) as the remote object.

### Authentication (typed JSON only)

Credentials are supplied in `fastqSource.credentials` — there is **no** env-var fallback on the worker.

| `type` | `credentials.authMode` | Notes |
|--------|------------------------|-------|
| `s3` | `explicit_keys` | `accessKeyId`, `secretAccessKey`, optional `sessionToken` |
| `s3` | `instance_profile` | boto3 default chain (IAM role on worker node) |
| `azure_blob` | `account_key` | `accountKey` (write-only in Portal schema) |
| `azure_blob` | `connection_string` | `connectionString` (write-only) |
| `azure_blob` | `default_credential` | `DefaultAzureCredential` (managed identity, Azure CLI dev) |
| `file` | — | `basePath` + `prefix` on shared NFS/local storage |

Portal / planner JSON: instance-level `fastqStorage` plus per-sample `fastqPrefix` (materialized into `samples[].fastqSource`). See `schemas/domain/fastq_storage.schema.json`.

### output_json

```json
{
  "sampleId": "DPLST-051425-111148",
  "fastqFiles": ["R1.fastq.gz", "R2.fastq.gz"]
}
```

---

## `parabricks.fq2bam`

**action_name:** `sample.parabricks_fq2bam`  
**Runtime:** Docker GPU container running `pbrun fq2bam_meth` (WGBS/bisulfite alignment).

### Worker environment (fallback)

Production settings should live in `project.step_config.parabricks` and task `input_json` overrides. Environment variables are used only when project/task values are absent:

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `METHYL_PARABRICKS_IMAGE` | fallback | — | Clara Parabricks image (e.g. `nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1`) |
| `METHYL_PARABRICKS_GPU_FLAGS` | no | `--gpus all` | Passed to `docker run` |
| `METHYL_PARABRICKS_BWA_THREADS` | no | `16` | `--bwa-cpu-thread-pool` |
| `METHYL_PARABRICKS_EXTRA_DOCKER_ARGS` | no | — | Extra `docker run` flags (shell-split) |
| `METHYL_PARABRICKS_CLEANUP_TMP` | no | `1` | Remove `{sampleDir}/tmp` after success |

Operators pre-pull the image on GPU nodes; the worker does not auto-pull. Use `scripts/verify_parabricks.sh` for a smoke test.

### Storage contract (`/work/samples/{sampleId}/`)

| Artifact | Path |
|----------|------|
| BAM | `{sampleId}.bam` |
| QC metrics archive | `{sampleId}.qc-metrics.tar` (from `{sampleId}.qc-metrics/`) |
| Duplicate metrics | `{sampleId}.deduplicate_metrics.txt` |
| Alignment log | `{sampleId}.fq2bam_meth.log` |

FASTQ inputs: prefer `{sampleId}_1.fastq.gz` + `{sampleId}_2.fastq.gz`; otherwise exactly two `**/*.fastq.gz` under `sampleDir`.

### input_json

```json
{
  "tool": "ParabricksFq2Bam",
  "sampleId": "DPLST-051425-111148",
  "sampleDir": "/work/samples/DPLST-051425-111148",
  "referenceFasta": "/work/genomes/.../Homo_sapiens.GRCh38.dna.primary_assembly.fa",
  "referenceGtf": "/work/genomes/.../Homo_sapiens.GRCh38.114.gtf",
  "parabricksImage": null,
  "bwaThreads": null
}
```

### Project `step_config.parabricks` (shared storage)

```json
"parabricks": {
  "image": "nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1",
  "bwa_threads": 16,
  "gpu_flags": "--gpus all",
  "cleanup_tmp": true
}
```

Task `input_json` keys: `parabricksImage`, `bwaThreads`, `gpuFlags`, `extraDockerArgs`, `cleanupTmp`.

### output_json

```json
{
  "sampleId": "DPLST-051425-111148",
  "bamPath": "/work/samples/DPLST-051425-111148/DPLST-051425-111148.bam",
  "metricsJson": "/work/samples/DPLST-051425-111148/DPLST-051425-111148.json",
  "qcMetricsTar": "/work/samples/DPLST-051425-111148/DPLST-051425-111148.qc-metrics.tar"
}
```

---

## `sample.delete-fastqs`

**action_name:** `sample.delete_fastqs`

### input_json

```json
{
  "tool": "SampleDeleteFastqs",
  "sampleId": "DPLST-051425-111148",
  "sampleDir": "/work/samples/DPLST-051425-111148"
}
```

### output_json

```json
{
  "sampleId": "DPLST-051425-111148",
  "deleted": true
}
```

---

## `methyl-qc`

**action_name:** `sample.methyl_qc`  
**Owner:** In-repo — [`packages/methylalignmentqc`](../../packages/methylalignmentqc/)

### input_json

```json
{
  "tool": "MethylAlignmentQc",
  "project": "/work/prostate-cancer/configs/project_Plasma_healthy_vs_PCa.json",
  "sampleId": "DPLST-051425-111148",
  "sampleDir": "/work/samples/DPLST-051425-111148",
  "primaryAnalyte": "cfdna"
}
```

**Phase 1:** Shell wrapper invokes `methyl-qc --project ${project}` with sample dir override in step JSON if CLI lacks `--sample-id`.  
**Phase 2:** Add `--sample-id` to methyl-qc CLI for explicit scoping.

### output_json

V2 alignment QC document. Workflow binds:

```json
{
  "guardrails": {
    "overall_pass": true
  }
}
```

Path binding: `$.guardrails.overall_pass` → scope variable **`qcPass`**.

Hard QC failure: `result_code < 0` fails the instance; soft fail uses `overall_pass: false` and **IF** routes to `sample.qc_failed`.

---

## `methyl-fragmentomics`

**action_name:** `sample.fragmentomics`  
**Owner:** In-repo — [`packages/methylfragmentomics`](../../packages/methylfragmentomics/)  
**When:** Only when `isCfdna` is true (workflow **IF** node).

### input_json

```json
{
  "tool": "MethylFragmentomics",
  "project": "/work/prostate-cancer/configs/project_Plasma_healthy_vs_PCa.json",
  "sampleId": "DPLST-051425-111148",
  "sampleDir": "/work/samples/DPLST-051425-111148"
}
```

### output_json

```json
{
  "sampleId": "DPLST-051425-111148",
  "outputDir": "/work/prostate-cancer/Plasma_healthy_vs_PCa/fragmentomics/DPLST-051425-111148"
}
```

---

## `methyl-extract`

**action_name:** `sample.methyl_extract`  
**Owner:** External [MethylExtractor](file:///home/ubuntu/MethylExtractor) (native CLI on worker PATH after `make install`)

Production remote workers are **self-contained per task**: config comes from **`input_json`** plus **`project.json` on shared storage**. Environment variables are **not** required (dev/CLI only).

### Required input_json

| Field | Description |
|-------|-------------|
| `sampleId` | Sample identifier |
| `sampleDir` | Shared storage path (`/work/samples/{id}`) |
| `project` | Absolute path to project JSON on shared storage |
| `referenceFasta` | Reference FASTA (workflow instance context; fallback: `step_config.alignment_qc.genome_fasta`) |

Optional per-task overrides: `extractContexts`, `threads`, `minMapq`, `chromMapping`, …

### Project `step_config.methyl_extract` (shared storage)

Production defaults (not env vars):

```json
"methyl_extract": {
  "extract_contexts": ["CG", "CHG", "CHH"],
  "contig_naming": "ensembl",
  "threads": 10,
  "min_mapq": 20,
  "min_phred": 20,
  "split": true,
  "output_format": "hdf5"
}
```

**`chrom_mapping`** is optional. When omitted, the worker derives `{reference, chromosomes: [{name, bam, fasta, extract}]}` from `project.chromosomes` and `contig_naming` (`ensembl` | `ucsc_chr` | `custom` with `chromosome_overrides`). Inline objects and file paths remain supported.

**`extract_contexts`** is independent of root-level `project.contexts` (which controls downstream centroid/detector). Production typically extracts all three contexts so `sample.delete_bam` can run without losing CHG/CHH.

`chromosomes` for idempotency come from `project.chromosomes`.

### Storage contract (`/work/samples/{sampleId}/`)

| Artifact | Path |
|----------|------|
| Input BAM | `{sampleId}.bam` |
| Per-chrom HDF5 | `{chrom}-{ctx}.h5` (e.g. `1-CG.h5`, `1-CHG.h5`, `1-CHH.h5`) |
| Log | `{sampleId}.methyl_extract.log` |

### input_json example

```json
{
  "tool": "MethylExtract",
  "sampleId": "DPLST-051425-111148",
  "sampleDir": "/work/samples/DPLST-051425-111148",
  "project": "/work/prostate-cancer/configs/project_Plasma_healthy_vs_PCa.json",
  "referenceFasta": "/work/genomes/.../Homo_sapiens.GRCh38.dna.primary_assembly.fa"
}
```

### output_json

```json
{
  "sampleId": "DPLST-051425-111148",
  "h5Files": ["1-CG.h5", "1-CHG.h5", "1-CHH.h5", "2-CG.h5", "..."]
}
```

---

## `sample.upload-h5`

**action_name:** `sample.upload_h5`  
**Runs after:** `sample.methyl_extract`, **before** `sample.delete_bam`

Archive-copies per-chromosome HDF5 files to durable object storage. **Local files on `/work/samples/{id}/` are retained** for downstream validation and BAM deletion.

### input_json

Instance-level `h5Storage` (planner) merges with per-sample `fastqPrefix` / `h5Destination.prefix`:

```json
{
  "tool": "SampleUploadH5",
  "sampleId": "DPLST-051425-111148",
  "sampleDir": "/work/samples/DPLST-051425-111148",
  "h5Destination": {
    "type": "s3",
    "bucket": "methyl-archive",
    "prefix": "plasma/DPLST-051425-111148/",
    "region": "us-east-1",
    "credentials": { "authMode": "instance_profile" }
  },
  "h5Files": ["1-CG.h5", "1-CHG.h5", "1-CHH.h5"]
}
```

Optional `h5Files` defaults to all `*.h5` in `sampleDir`. Credential modes mirror [`sample.download-fastq`](#sampledownload-fastq) (`s3`, `azure_blob`, `file`).

**Idempotency:** skip upload when remote size (and ETag/md5 when available) matches local.

### output_json

```json
{
  "sampleId": "DPLST-051425-111148",
  "uploadedFiles": ["1-CG.h5"],
  "skippedFiles": ["1-CHG.h5", "1-CHH.h5"],
  "remotePrefix": "plasma/DPLST-051425-111148/",
  "uploadedCount": 1,
  "skippedCount": 2
}
```

---

## `sample.delete-bam`

**action_name:** `sample.delete_bam`

### input_json

```json
{
  "tool": "SampleDeleteBam",
  "sampleId": "DPLST-051425-111148",
  "sampleDir": "/work/samples/DPLST-051425-111148"
}
```

### output_json

```json
{
  "sampleId": "DPLST-051425-111148",
  "deleted": true
}
```

---

## `sample.mark-failed`

**action_name:** `sample.qc_failed`  
**Owner:** Optional portal/DB worker

### input_json

```json
{
  "tool": "SampleMarkFailed",
  "sampleId": "DPLST-051425-111148",
  "sampleDir": "/work/samples/DPLST-051425-111148",
  "reason": "alignment_qc_failed"
}
```

### output_json

```json
{
  "sampleId": "DPLST-051425-111148",
  "status": "QC_FAILED"
}
```

Use `result_code = 0` even when marking failed — the sample is intentionally skipped; instance continues other FOREACH iterations.

---

## Registered actions (catalog)

| action_name | capability |
|-------------|------------|
| `sample.download_fastq` | `sample.download-fastq` |
| `sample.parabricks_fq2bam` | `parabricks.fq2bam` |
| `sample.delete_fastqs` | `sample.delete-fastqs` |
| `sample.methyl_qc` | `methyl-qc` |
| `sample.fragmentomics` | `methyl-fragmentomics` |
| `sample.methyl_extract` | `methyl-extract` |
| `sample.delete_bam` | `sample.delete-bam` |
| `sample.qc_failed` | `sample.mark-failed` |

Seed: [`../sql/wf_sample_prep_pipeline_seed.sql`](../sql/wf_sample_prep_pipeline_seed.sql)
