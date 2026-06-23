# SamplePrepPipeline — per-sample upstream workflow

**SamplePrepPipeline** orchestrates ingest, alignment, QC gating (with cycle screening and optional R2 trim remediation), optional cfDNA fragmentomics, methylation extraction, and cleanup **per sample** before **DataDrivenPipeline** runs on `{chrom}-CG.h5` files.

## Architecture

```text
Engine (generic)                    Workflow definition
─────────────────                   ─────────────────────
SEQUENCE / IF / FOREACH             SamplePrepPipeline seed
scope_variable / placeholders       FOREACH samples (parallel)
worker_action + capabilities        ACTION nodes + QC gate IF

Instance (project-specific)         Workers
─────────────────────────           ───────
context_json: samples[],            download / Parabricks / methyl-qc /
  projectPath, reference paths         trim / realign / fragmentomics / extract / cleanup
```

## Workflow tree

```text
SEQUENCE root
└─ FOREACH samples (parallel, foreach_parallel=1)
   └─ SEQUENCE one_sample
      ├─ ACTION download_fastq
      ├─ ACTION parabricks_fq2bam
      ├─ ACTION methyl_qc          → binds qcPass, qcDisposition, remediateR2Trim
      └─ IF if_qc_passed (qcPass)
         ├─ THEN delete_fastqs → [IF is_cfdna → fragmentomics] → extract → delete_bam
         └─ ELSE IF remediateR2Trim
            └─ trim_fastq → parabricks (forceRealign) → methyl_qc retry → pass/fail paths
         └─ ELSE delete_fastqs → qc_failed
```

**FASTQ retention:** `sample.delete-fastqs` runs only after **final** QC (pass or fail after any trim/realign retry). Trimming requires original `*_1.fastq.gz` / `*_2.fastq.gz` still on disk.

**Ordering:** methyl-qc runs **before** methyl-fragmentomics so failed samples do not scan BAMs. Fragmentomics still runs before extraction and BAM deletion (both need the aligned BAM).

## Instance `context_json`

Top-level keys become scope-0 variables via `wf_init_instance_scope_from_context`. FOREACH object elements flatten into scope (`${var.sampleId}`, `${var.sampleDir}`, …).

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `projectPath` | string | yes | Absolute path to `project.json` (chromosomes, analyte profile, output paths) |
| `primaryAnalyte` | string | yes | `cfdna`, `buffy_coat`, etc. — passed to methyl-qc worker |
| `isCfdna` | boolean | yes | Drives **IF** `if_is_cfdna`; set `true` when `primaryAnalyte` is `cfdna` |
| `referenceFasta` | string | yes | Reference FASTA for Parabricks and MethylExtractor |
| `referenceGtf` | string | no | GTF for Parabricks (empty string if unused) |
| `fastqStorage` | object | yes | **Laboratory-owned** ingress storage (file/s3/azure_blob); never inferred from platform archive |
| `h5Storage` | object | no | Internal archive defaults from `wf.platform_sample_storage` when omitted |
| `samples` | array of objects | yes | Per-sample fan-out; each object needs `sampleId`, `sampleDir`, materialized `fastqSource` |

Examples:

- Hand-built: [`instance_context_examples/sample_prep_plasma.json`](instance_context_examples/sample_prep_plasma.json)
- Planner output: [`instance_context_examples/sample_prep_from_planner.json`](instance_context_examples/sample_prep_from_planner.json)

**Planner:** `POST /v1/studies/sample-prep/start` or `methyl_validation.sample_prep_planner.plan_sample_prep_context()` merges `fastqStorage` + per-sample `fastqPrefix` into `samples[].fastqSource`. See [`../docs/sample_prep_test_bed.md`](../docs/sample_prep_test_bed.md).

## Storage contract

Per sample under `/work/samples/{sample_id}/`:

```text
*.fastq.gz              (transient; deleted after final QC)
{sample_id}.bam         (transient; deleted after extract)
{sample_id}.json        (Parabricks metrics; retained)
*.qc-metrics.tar        (optional; retained)
bisulfite_conversion.json  (optional sidecar)
{sample_id}.sample_prep_log.jsonl  (append-only audit)
1-CG.h5 … Y-CG.h5       (retained; consumed by methyl-centroid)
```

## Deploy & run

PostgreSQL (REST):

```bash
bash scripts/deploy_workflow_definitions.sh
curl -X POST http://localhost:8080/v1/studies/sample-prep/start -H 'Content-Type: application/json' -d '{ ... }'
```

SQL Server seed (legacy):

```sql
:r wf_sample_prep_pipeline_seed.sql
```

Workers poll by capability; task count scales with `len(samples) × (actions per sample)` including remediation branch when triggered.

## Portal handoff

1. Start **SamplePrepPipeline** when FASTQs are ready.
2. On instance **COMPLETED**, start **StudyValidationLifecycle** or **DataDrivenPipeline** with the same `projectPath`.

See [pipeline architecture §0](../docs/pipeline_architecture.md) for end-to-end diagram.

## Worker capability matrix

| action_name | capability | Owner |
|-------------|------------|-------|
| `sample.download_fastq` | `sample.download-fastq` | External ingest worker |
| `sample.parabricks_fq2bam` | `parabricks.fq2bam` | External GPU worker |
| `sample.trim_fastq` | `sample.trim-fastq` | External / in-process (fastp) |
| `sample.delete_fastqs` | `sample.delete-fastqs` | External cleanup worker |
| `sample.methyl_qc` | `methyl-qc` | In-repo CLI wrapper |
| `sample.fragmentomics` | `methyl-fragmentomics` | In-repo CLI (cfDNA only) |
| `sample.methyl_extract` | `methyl-extract` | External MethylExtractor |
| `sample.delete_bam` | `sample.delete-bam` | External cleanup worker |
| `sample.qc_failed` | `sample.mark-failed` | Optional portal/DB update worker |

Contract details: [`../contract/sample_prep_capabilities.md`](../contract/sample_prep_capabilities.md)

## Related

- Test bed: [`../docs/sample_prep_test_bed.md`](../docs/sample_prep_test_bed.md)
- Seed SQL: [`wf_sample_prep_pipeline_seed.sql`](wf_sample_prep_pipeline_seed.sql)
- DomainProgram: [`../domain/fixtures/sample_prep.program.json`](../domain/fixtures/sample_prep.program.json)
- Downstream analysis: [`DataDrivenPipeline.md`](DataDrivenPipeline.md)
- Capability check: [`../CAPABILITY_CHECK.md`](../CAPABILITY_CHECK.md)
- Analyte profiles: [`../../docs/ANALYTE_PROFILES.md`](../../docs/ANALYTE_PROFILES.md)
