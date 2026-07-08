# SamplePrepPipeline — per-sample upstream workflow

**SamplePrepPipeline** is the **universal entry point** for every sample entering MethylPipeline: cfDNA or buffy-coat, from any structured laboratory `fastqSource` (file / S3 / Azure Blob). It orchestrates ingest, GPU alignment, **alignment QC** (with optional fastp remediation), optional cfDNA fragmentomics, GPU methylation extraction, **extraction QC**, optional HDF5 archive, and cleanup **per sample** — in parallel — before **DataDrivenPipeline** consumes `{chrom}-CG.h5` files.

**Source of truth (workflow graph):** [`../domain/fixtures/sample_prep.program.json`](../domain/fixtures/sample_prep.program.json)

**Implementation detail:** [`docs/implementation/sample-preparation-flow.md`](../../docs/implementation/sample-preparation-flow.md) — guardrail boundaries, focused FASTP remediation, extraction filtering, cfDNA fragmentomics.

**Deploy:** `bash scripts/deploy_workflow_definitions.sh` → `POST /v1/workflows/definitions`

**Legacy SQL seed** [`deprecated/wf_sample_prep_pipeline_seed.sql`](deprecated/wf_sample_prep_pipeline_seed.sql) is **deprecated**; use DomainProgram deploy above.

## Architecture

```text
Engine (generic)                    Workflow definition
─────────────────                   ─────────────────────
SEQUENCE / IF / FOREACH             SamplePrepPipeline (DomainProgram)
scope_variable / placeholders       FOREACH samples (parallel=true)
worker_action + capabilities        ACTION nodes + two QC gates

Instance (project-specific)         Performance stack
─────────────────────────           ─────────────────
context_json: samples[],            Clara Parabricks (GPU align)
  fastqStorage, projectPath           fastp (R2 trim remediation)
                                    MethylExtractor (GPU extract)
```

## Workflow tree

```text
SEQUENCE root
└─ FOREACH samples (parallel)
   └─ SEQUENCE one_sample
      ├─ ACTION download_fastq       ← laboratory fastqSource → local sampleDir
      ├─ IF usePangenome
      │    ├─ THEN parabricks_giraffe   ← GPU vg Giraffe (HPRC pangenome → GRCh38 surjection)
      │    └─ ELSE parabricks_fq2bam    ← GPU linear WGBS align (fq2bam_meth)
      ├─ ACTION methyl_qc            ← alignment guardrail #1
      │     binds: qcPass, qcDisposition, trimFront1/2, trimTail1/2, remediateAlignment
      └─ IF qcPass
         ├─ THEN (pass path)
         │    ├─ [IF isCfdna → fragmentomics]
         │    ├─ methyl_extract
         │    ├─ extraction_qc       ← extraction guardrail #2
         │    └─ IF extractionQcPass
         │         ├─ [IF sampleDestination → archive_sample mode=full]
         │         ├─ delete_fastqs
         │         └─ delete_bam
         │       ELSE → archive_sample mode=qc_only → delete_fastqs → delete_bam → qc_failed
         └─ ELSE (alignment fail)
            └─ IF remediateAlignment
               ├─ trim_fastq (fastp, read-end trim from screening)
               ├─ IF usePangenome → parabricks_giraffe else parabricks_fq2bam (forceRealign)
               ├─ methyl_qc retry (attempt 2)
               └─ IF qcPass → same pass path as above
                  ELSE → archive_sample mode=qc_only → delete_fastqs → delete_bam → qc_failed
            ELSE → archive_sample mode=qc_only → delete_fastqs → delete_bam → qc_failed
```

### Two guardrails

| Gate | Action | Scope variable | When | Blocks |
|------|--------|----------------|------|--------|
| **Alignment** | `sample.methyl_qc` | `qcPass` | After Parabricks, before extract | Extract path (unless fastp remediation) |
| **Extraction** | `sample.extraction_qc` | `extractionQcPass` | After `sample.methyl_extract` | Full archive + BAM delete |

Alignment QC may recommend **REALIGN_TRIM** (cycle screening in methylalignmentqc). When `remediateAlignment` is true, fastp trims Read 1/2 start or end bases per `trimFront1`/`trimTail1`/`trimFront2`/`trimTail2`, Parabricks realigns, and methyl_qc runs again — **FASTQs must remain on disk** until archive (pass or reject).

Extraction QC reads MethylExtractor `{sampleId}.extraction_manifest.json` and writes `{sampleId}.extraction_qc.json`. Failures are **terminal** (no retry loop today).

**Ordering:** methyl-qc runs **before** fragmentomics so failed samples skip BAM scanning. Fragmentomics runs before extraction (needs aligned BAM).

## Analytes and sources

| Dimension | Behavior |
|-----------|----------|
| **Analyte** | Set `primaryAnalyte` (`cfdna`, `buffy_coat`, …) and `isCfdna` in instance context. Fragmentomics runs only when `isCfdna` is true. Alignment and extraction QC apply to **all** analytes. |
| **FASTQ ingress** | **Required** `fastqStorage` on study start (laboratory-owned). Planner materializes `samples[].fastqSource` from storage + per-sample prefix. |
| **Sample archive** | Optional `sampleStorage` / `sampleDestination` from portal profile when omitted. **Full** archive (FASTQs + QC + H5) after **extractionQcPass**; **qc_only** archive on any final reject. Legacy keys `h5Storage` / `h5Destination` accepted. |

See [`../../docs/ANALYTE_PROFILES.md`](../../docs/ANALYTE_PROFILES.md) for downstream step profiles.

## Instance `context_json`

Top-level keys become scope-0 variables. FOREACH object elements flatten into per-sample scope (`${var.sampleId}`, `${var.sampleDir}`, …).

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `projectPath` | string | yes | Absolute path to `project.json` |
| `primaryAnalyte` | string | yes | `cfdna`, `buffy_coat`, etc. |
| `isCfdna` | boolean | yes | Drives fragmentomics **IF** |
| `referenceFasta` | string | yes | Reference FASTA for linear Parabricks fq2bam and MethylExtractor |
| `referenceGtf` | string | no | GTF for Parabricks |
| `alignmentMode` | string | no | `linear` (default) or `pangenome` — binds `usePangenome` for Giraffe vs fq2bam |
| `fastqStorage` | object | yes | Laboratory-owned ingress (never inferred from archive profile) |
| `sampleStorage` | object | no | Internal archive defaults from `portal.resource_profile` when omitted (`h5Storage` alias) |
| `samples` | array | yes | Each object: `sampleId`, `sampleDir`, materialized `fastqSource`, optional `sampleDestination` |

After `sample.methyl_qc`: `qcPass`, `qcDisposition`, `trimFront1`, `trimTail1`, `trimFront2`, `trimTail2`, `qcAttemptReason`, `remediateAlignment`.

After `sample.archive_sample`: `sampleArchived`.

After `sample.extraction_qc`: `extractionQcPass` ← `guardrails.overall_pass`.

Examples:

- [`instance_context_examples/sample_prep_plasma.json`](instance_context_examples/sample_prep_plasma.json)
- [`instance_context_examples/sample_prep_from_planner.json`](instance_context_examples/sample_prep_from_planner.json)

**Planner:** `POST /v1/studies/sample-prep/start` or `methyl_validation.sample_prep_planner.plan_sample_prep_context()`. See [`../docs/sample_prep_test_bed.md`](../docs/sample_prep_test_bed.md).

## Storage contract

Per sample under `/work/samples/{sample_id}/`:

```text
*.fastq.gz                          retained until archive_sample, then deleted
{sample_id}.bam                     deleted after archive (pass or reject)
{sample_id}.json                    Parabricks metrics (retained)
*.qc-metrics.tar                    optional Parabricks tar (retained)
{sample_id}.sample_prep_log.jsonl   append-only audit (retained)
{sample_id}.extraction_manifest.json   MethylExtractor export (retained)
{sample_id}.extraction_qc.json      post-extract guardrails (retained)
{chr}-{ctx}.json                    optional per-context QC sidecars (retained)
{chr}-{ctx}.h5                      methylation matrices (retained; optional remote copy)
bisulfite_conversion.json           optional alignment QC sidecar
```

Alignment QC export path when project-scoped: `{output_base}/{project}/alignment_qc/{sampleId}.json`.

## Downstream handoff (`MethylSampleRef`)

Workers enrich scope with a tagged **`MethylSampleRef`** (`$type: MethylSampleRef`) accumulating:

- `alignmentQc` — pass/fail + QC JSON path
- `extractionQc` — pass/fail + extraction QC JSON path
- `methylation` — `MethylationMatrixRef` (`sampleDir`, `chromosomes`, `contexts`, `h5Pattern`)
- optional `h5Archive`, `fragmentomics`

Downstream analysis loads HDF5 via **`methyl_domain.helpers.resolve_methylation_h5_path()`** and **`MethylSample.load_from_h5()`** (GPU-capable in methylutils). Do not hard-code `{chr}-CG.h5` paths.

## Deploy & run

PostgreSQL (REST) — **preferred**:

```bash
bash scripts/deploy_workflow_definitions.sh
curl -X POST http://localhost:8080/v1/studies/sample-prep/start -H 'Content-Type: application/json' -d '{ ... }'
```

Workers poll by capability; task count scales with `len(samples) × actions per sample` including remediation when triggered.

## Portal handoff

1. Start **SamplePrepPipeline** when laboratory FASTQs are ready.
2. On instance **COMPLETED**, start **StudyValidationLifecycle** or **DataDrivenPipeline** with the same `projectPath`.

See [pipeline architecture §0](../docs/pipeline_architecture.md).

## Worker capability matrix

| action_name | capability | Owner |
|-------------|------------|-------|
| `sample.download_fastq` | `sample.download-fastq` | In-process worker |
| `sample.parabricks_fq2bam` | `parabricks.fq2bam` | External GPU (Docker Parabricks) |
| `sample.trim_fastq` | `sample.trim-fastq` | In-process (fastp) |
| `sample.delete_fastqs` | `sample.delete-fastqs` | In-process |
| `sample.methyl_qc` | `methyl-qc` | In-repo methylalignmentqc |
| `sample.fragmentomics` | `methyl-fragmentomics` | In-repo (cfDNA only) |
| `sample.methyl_extract` | `methyl-extract` | External MethylExtractor |
| `sample.extraction_qc` | `methyl-extraction-qc` | In-repo methylextractionqc |
| `sample.archive_sample` | `sample.archive-sample` | In-process |
| `sample.upload_h5` | `sample.upload-h5` | In-process (deprecated alias) |
| `sample.delete_bam` | `sample.delete-bam` | In-process |
| `sample.qc_failed` | `sample.mark-failed` | In-process |

Contract details: [`../contract/sample_prep_capabilities.md`](../contract/sample_prep_capabilities.md)

## Related

- DomainProgram fixture: [`../domain/fixtures/sample_prep.program.json`](../domain/fixtures/sample_prep.program.json)
- Remediation cohort: [`../domain/fixtures/sample_prep_remediate.program.json`](../domain/fixtures/sample_prep_remediate.program.json)
- Test bed: [`../docs/sample_prep_test_bed.md`](../docs/sample_prep_test_bed.md)
- Extraction QC contract (upstream): MethylExtractor `docs/extraction_qc_contract.md`
- Downstream analysis: [`DataDrivenPipeline.md`](DataDrivenPipeline.md)
