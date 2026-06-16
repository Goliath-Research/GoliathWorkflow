# Sample prep worker capabilities

Contract for **SamplePrepPipeline** remote workers. All workers use the standard poll/submit protocol ([`../workers/WORKER_PROTOCOL.md`](../../workers/WORKER_PROTOCOL.md)).

## Result codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `> 0` | Success with optional semantic payload (avoid for gate variables) |
| `< 0` | Permanent failure — instance marks **FAILED** |

QC gate variable `qcPass` comes from **`output_json.guardrails.overall_pass`** (boolean), not `result_code`.

## Idempotency

| Capability | Safe to retry when |
|------------|-------------------|
| `sample.download-fastq` | Destination FASTQs missing, or remote size/mtime differ from local |
| `sample.delete-fastqs` | FASTQs already absent (no-op success) |
| `sample.delete-bam` | BAM already absent (no-op success) |
| `parabricks.fq2bam` | Only when BAM missing or QC artifact missing (`{sampleId}.json` or `{sampleId}.qc-metrics.tar`) |
| `methyl-extract` | When HDF5 outputs missing for required chromosomes |

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
  "fastqSourceUri": "s3://bucket/prefix/ or az://container/prefix/ or file://..."
}
```

`fastqSourceUri` points at a **folder prefix** (or single `.fastq.gz` object). All `*.fastq.gz` / `*.fq.gz` objects under that prefix are downloaded into `sampleDir`. Typical layout: `<sample>_1.fastq.gz`, `<sample>_2.fastq.gz`, but any matching extension in the folder is included.

**Idempotency:** for each file, download is skipped when the local copy already exists with the same **size** and **mtime** (±1 s) as the remote object.

### Authentication

| Scheme | Configuration |
|--------|----------------|
| `s3://` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN` (or `METHYL_S3_*` aliases). S3-compatible: set `METHYL_S3_ENDPOINT_URL` and optional `METHYL_S3_REGION`. Without explicit keys, boto3 uses the instance credential chain (IAM role, etc.). |
| `az://` | `DefaultAzureCredential` (managed identity on registered HPC nodes, workload identity, Azure CLI for dev). URI forms: `az://container/prefix/` with `AZURE_STORAGE_ACCOUNT`, or `az://account@container/prefix/`. |
| `file://` | Local path or NFS mount under `/work/...` (no auth). |

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

### Worker environment

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `METHYL_PARABRICKS_IMAGE` | yes | — | Clara Parabricks image (e.g. `nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1`) |
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
**Owner:** External MethylDackel / MethylExtractor fork

### input_json

```json
{
  "tool": "MethylExtract",
  "sampleId": "DPLST-051425-111148",
  "sampleDir": "/work/samples/DPLST-051425-111148",
  "project": "/work/prostate-cancer/configs/project_Plasma_healthy_vs_PCa.json",
  "referenceFasta": "/work/genomes/.../Homo_sapiens.GRCh38.dna.primary_assembly.fa"
}
```

Chromosome list comes from worker reading `project.json` `chromosomes`.

### output_json

```json
{
  "sampleId": "DPLST-051425-111148",
  "h5Files": ["1-CG.h5", "2-CG.h5"]
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
