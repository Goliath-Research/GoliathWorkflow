# SamplePrepPipeline — per-sample upstream workflow

**SamplePrepPipeline** orchestrates ingest, alignment, QC gating, optional cfDNA fragmentomics, methylation extraction, and cleanup **per sample** before **DataDrivenPipeline** runs on `{chrom}-CG.h5` files.

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
  projectPath, reference paths         methyl-fragmentomics / extract / cleanup
```

## Workflow tree

```text
SEQUENCE root
└─ FOREACH samples (parallel, foreach_parallel=1)
   └─ SEQUENCE one_sample
      ├─ ACTION download_fastq
      ├─ ACTION parabricks_fq2bam
      ├─ ACTION delete_fastqs
      ├─ ACTION methyl_qc          → binds qcPass from guardrails.overall_pass
      └─ IF if_qc_passed (qcPass)
         ├─ THEN SEQUENCE on_pass
         │  ├─ IF if_is_cfdna (isCfdna)
         │  │  └─ THEN ACTION methyl_fragmentomics
         │  ├─ ACTION methyl_extract
         │  └─ ACTION delete_bam
         └─ ELSE ACTION qc_failed
```

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
| `samples` | array of objects | yes | Per-sample fan-out; each object needs `sampleId`, `sampleDir`, `fastqSourceUri` |

Example: [`instance_context_examples/sample_prep_plasma.json`](instance_context_examples/sample_prep_plasma.json)

A **planner service** (outside SQL) expands sample CSVs from `project.json` into `samples[]` and sets `isCfdna` from `primary_analyte`.

## Storage contract

Per sample under `/work/samples/{sample_id}/`:

```text
*.fastq.gz              (transient; deleted after align)
{sample_id}.bam         (transient; deleted after extract)
{sample_id}.json        (Parabricks metrics; retained)
*.qc-metrics.tar        (optional; retained)
bisulfite_conversion.json  (optional sidecar)
1-CG.h5 … Y-CG.h5       (retained; consumed by methyl-centroid)
```

## Deploy & run

```sql
-- once (after wf_sql_foreach_support.sql and wf_data_driven_pipeline_seed.sql optional order)
:r wf_sample_prep_pipeline_seed.sql

EXEC wf.sp_delete_workflow_def @workflow_name = N'SamplePrepPipeline';  -- rebuild only

INSERT INTO wf.workflow_instance (workflow_version_id, status, context_json)
SELECT TOP (1) wv.id, N'CREATED', CAST(<sample_prep_plasma.json contents> AS json)
FROM wf.workflow_version wv
JOIN wf.workflow_def wd ON wd.id = wv.workflow_def_id
WHERE wd.name = N'SamplePrepPipeline';

INSERT INTO wf.instance_cursor (workflow_instance_id) VALUES (SCOPE_IDENTITY());
EXEC wf.sp_start_workflow_instance @workflow_instance_id = SCOPE_IDENTITY();
```

Workers poll by capability; task count scales with `len(samples) × (7 or 8 actions per sample)` depending on cfDNA branch.

## Portal handoff

1. Start **SamplePrepPipeline** when FASTQs are ready.
2. On instance **COMPLETED**, start **DataDrivenPipeline** with the same `projectPath`, `comparisons`, and `chromosomes`.

See [pipeline architecture §0](../docs/pipeline_architecture.md) for end-to-end diagram.

## Worker capability matrix

| action_name | capability | Owner |
|-------------|------------|-------|
| `sample.download_fastq` | `sample.download-fastq` | External ingest worker |
| `sample.parabricks_fq2bam` | `parabricks.fq2bam` | External GPU worker |
| `sample.delete_fastqs` | `sample.delete-fastqs` | External cleanup worker |
| `sample.methyl_qc` | `methyl-qc` | In-repo CLI wrapper |
| `sample.fragmentomics` | `methyl-fragmentomics` | In-repo CLI (cfDNA only) |
| `sample.methyl_extract` | `methyl-extract` | External MethylExtractor |
| `sample.delete_bam` | `sample.delete-bam` | External cleanup worker |
| `sample.qc_failed` | `sample.mark-failed` | Optional portal/DB update worker |

Contract details: [`../contract/sample_prep_capabilities.md`](../contract/sample_prep_capabilities.md)

## Related

- Seed SQL: [`wf_sample_prep_pipeline_seed.sql`](wf_sample_prep_pipeline_seed.sql)
- Downstream analysis: [`DataDrivenPipeline.md`](DataDrivenPipeline.md)
- Capability check: [`../CAPABILITY_CHECK.md`](../CAPABILITY_CHECK.md)
- Analyte profiles: [`../../docs/ANALYTE_PROFILES.md`](../../docs/ANALYTE_PROFILES.md)
