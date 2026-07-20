# RNA-Seq — end-to-end workflow

> **Per-process docs.** This document covers the **RNA-Seq (transcriptomics)** process pack. For DNA methylation see [end-to-end workflow](end-to-end-workflow.md). Both packs share one control plane (DomainProgram, typed actions, scheduler, cfg/wf, CAAS); only the science layer differs.

**Audience:** operators, statisticians, and engineers who need one clear picture from external RNA-Seq FASTQ ingest through quantification, RNA QC, the per-sample expression contract, differential-expression gene selection, and tabular classification.

**Selected by** `regulatory.primary_modality: rnaseq` in the study manifest. Modality is independent of `primary_analyte` (which is the DNA-methylation sample matrix).

**Sources of truth (programs / profile):**

| Phase | Artifact |
|-------|----------|
| Per-sample prep | [`sample_prep_rnaseq.program.json`](../../workflow_engine/domain/fixtures/sample_prep_rnaseq.program.json) |
| Study modeling | [`rnaseq_study_lifecycle.program.json`](../../workflow_engine/domain/fixtures/rnaseq_study_lifecycle.program.json) |
| Profile | [`rnaseq_research.profile.json`](../../workflow_engine/domain/profiles/rnaseq_research.profile.json) |
| Operator guide | [Usage ch.20 RNA-Seq process pack](../usage/20-rnaseq-process-pack.qmd) |

Packages: `rna_alignment_qc` (RNA QC), `rna_express` (expression contract + DE selection). Quantifier runners: `workers/methyl_worker/rna_fq2bam_runner.py`, `kallisto_runner.py`.

---

## 1. Big picture

Two DomainPrograms run in sequence, mirroring the methylation pack but swapping the science:

1. **SamplePrepRnaSeqPipeline** — one sample at a time (parallel across samples): download → quantify (STAR `rna_fq2bam` **or** `kallisto`) → RNA QC → register expression → archive.
2. **RnaSeqStudyLifecycle** — cohort-level: per-comparison differential-expression gene-panel selection + tabular classification (`pipeline.rna_de_select`).

```mermaid
flowchart TB
  subgraph src["0a · FASTQ source storage<br/>fastqSource — lab cloud / QNAP / NFS"]
    FQSRC["file | s3 | azure_blob<br/>raw RNA-Seq FASTQs"]
  end

  subgraph prep["1 · SamplePrepRnaSeqPipeline (per sample on /work scratch)"]
    DL["download_fastq"]
    QUANT["Parabricks quantify<br/>rna_fq2bam (STAR) or kallisto"]
    RQC["rna_qc<br/>mapping/pseudoalign rate · genes detected"]
    REG["register_expression<br/>{sample}.expression.h5"]
    ARC["archive_sample<br/>pass → full · fail → qc_only"]
    DEL["delete_fastqs<br/>local scratch cleanup"]
  end

  subgraph dst["0b · Result archive storage<br/>sampleDestination"]
    ARCH["qc/ · fastq/ · expression.h5"]
  end

  subgraph study["2 · RnaSeqStudyLifecycle (cohort)"]
    DE["pipeline.rna_de_select<br/>per comparison"]
    PANEL["DE gene panel CSV<br/>+ balanced accuracy"]
  end

  FQSRC -->|"download"| DL --> QUANT --> RQC
  RQC -->|qcPass| REG --> ARC
  ARC -->|"upload curated bundle"| ARCH
  ARC --> DEL
  DEL --> DE --> PANEL
```

**What is reused vs replaced (relative to methylation):**

| Reused as-is | Replaced for RNA-Seq |
|--------------|----------------------|
| DomainProgram / scheduler / CAAS / cfg-wf | `fq2bam_meth` / giraffe → `rna_fq2bam` / `kallisto` |
| Storage split (`fastqSource` / `sampleDestination`) | `methyl_extract` (HDF5 β) → `register_expression` (gene counts/TPM) |
| QC-gate pattern (`${qcPass}`) | bisulfite / CpG-coverage QC → RNA mapping / genes-detected QC |
| Tabular sklearn + covariate stacking (`covariate_preprocessor`, `ecdf_second_stage`) | centroid / detector / ECDF-on-β → Welch DE gene selection |
| Monte Carlo orchestration in `methylvalidation` | Houseman / HiTIMED cell deconvolution, info measures (dropped) |

---

## 2. Where data lives

Same two-endpoint model as methylation, with an RNA-specific reference bundle.

```mermaid
flowchart LR
  subgraph src["fastqSource (ingress)"]
    S1["Lab / portal object store or NFS"]
  end
  subgraph scratch["/work scratch (GPU node shared FS)"]
    W["/work/samples/{sample_id}/<br/>FASTQ · BAM (STAR) · gene_counts / abundance · expression.h5"]
  end
  subgraph dst["sampleDestination (egress)"]
    D1["Durable archive<br/>qc/ · fastq/ · expression.h5"]
  end

  S1 -->|"sample.download_fastq"| W
  W -->|"sample.archive_sample"| D1
```

**Site reference bundle** (`rna_reference`, pinned once per cluster — see [`site_grch38.example.json`](../../workflow_engine/domain/profiles/site_grch38.example.json)):

| Key | Used by | Role |
|-----|---------|------|
| `star_index_dir` | `rna_fq2bam` | STAR genome index |
| `gtf` | `rna_fq2bam` | gene annotation for STAR counts |
| `kallisto_index` | `kallisto` | prebuilt transcriptome index (`.idx`) |
| `transcriptome_fasta` | index build | source for the kallisto index |
| `tx2gene` | `register_expression` | transcript→gene map to aggregate kallisto abundances |

Provision with [`scripts/download_rna_reference_grch38.sh`](../../scripts/download_rna_reference_grch38.sh). Reference resolution: `methyl_utils.action_config_resolver.resolve_rna_reference` + site slice for `rna_align` / `rna_qc`.

---

## 3. Sample prep — arrival to expression

### 3.1 Quantifier selection

The quantifier is chosen like the methylation linear/pangenome switch. Set `actionConfig.rna_align.quant_mode`; `pipeline_profiles.py` derives the `${useKallisto}` program flag (parallel to `${usePangenome}`).

```mermaid
flowchart TD
  A["sample.download_fastq<br/>fastqSource → /work/samples/id"] --> B{"useKallisto?<br/>(quant_mode)"}
  B -->|no · star| C["sample.parabricks_rna_fq2bam<br/>pbrun rna_fq2bam (STAR)<br/>→ {id}.rna.bam + {id}.gene_counts.tsv"]
  B -->|yes · kallisto| D["sample.kallisto<br/>pbrun kallisto<br/>→ {id}.kallisto/abundance.tsv"]
  C --> E["sample.rna_qc"]
  D --> E
  E --> F{"qcPass?"}
  F -->|yes| G["sample.register_expression<br/>→ {id}.expression.h5"]
  G --> H["archive_sample mode=full<br/>→ sampleDestination · no BAM"]
  H --> I{"deleteFastqs? default true"}
  I -->|yes| J["delete_fastqs"]
  I -->|no| K["retain FASTQs on /work"]
  F -->|no| L["archive_sample mode=qc_only<br/>reject rna_qc_failed"]
  L --> M["delete_fastqs? → sample.qc_failed"]
```

**Quantifier outputs:**

| Quantifier | Action | Files |
|------------|--------|-------|
| STAR | `sample.parabricks_rna_fq2bam` | `{id}.rna.bam`, `{id}.gene_counts.tsv` (gene_id, count) |
| kallisto | `sample.kallisto` | `{id}.kallisto/abundance.tsv` (transcript est_counts + TPM), `run_info.json` |

### 3.2 RNA QC (gate)

`sample.rna_qc` (package `rna_alignment_qc`) parses whichever quantifier output is present and gates on RNA-relevant metrics — **not** bisulfite conversion or CpG coverage. Thresholds are operator-set under `actionConfig.rna_qc`.

```mermaid
flowchart LR
  STAR["STAR Log.final.out"] --> M1["input reads · uniquely mapped % · mapping rate"]
  KAL["kallisto run_info.json"] --> M2["pseudoalignment rate"]
  CNT["gene_counts.tsv / abundance.tsv"] --> M3["genes detected (non-zero)"]
  M1 --> G["guardrails.overall_pass<br/>→ ${qcPass}"]
  M2 --> G
  M3 --> G
```

### 3.3 Expression contract

`sample.register_expression` (package `rna_express`) normalizes the quantifier output into a canonical per-sample HDF5 so downstream cohort code is quantifier-agnostic.

```mermaid
flowchart TD
  SRC{"quantifier output"}
  SRC -->|STAR| GC["gene_counts.tsv<br/>(gene_id, count)"]
  SRC -->|kallisto| AB["abundance.tsv (transcripts)"]
  AB -->|"aggregate via tx2gene"| GENE["per-gene est_counts + TPM"]
  GC --> H5["{id}.expression.h5<br/>datasets: gene_id · count · tpm<br/>attrs: quant_mode · n_genes"]
  GENE --> H5
```

Domain handle: [`expression_matrix_ref.schema.json`](../../schemas/domain/expression_matrix_ref.schema.json) (embedded in `rna_sample_ref.schema.json`), the RNA analogue of `methylation_matrix_ref`.

### 3.4 Per-sample artifact timeline

```mermaid
sequenceDiagram
  participant Src as fastqSource storage
  participant W as Worker
  participant S as /work/samples/id
  participant Dst as sampleDestination storage

  Src->>W: download_fastq
  W->>S: stage *.fastq.gz
  alt quant_mode=star
    W->>S: rna_fq2bam → *.rna.bam + gene_counts.tsv
  else quant_mode=kallisto
    W->>S: kallisto → abundance.tsv + run_info.json
  end
  W->>S: rna_qc → {id}.rna_qc.json
  W->>S: register_expression → {id}.expression.h5
  alt qcPass → mode=full
    W->>Dst: upload qc/ + fastq/ + expression.h5 + manifest
  else fail → mode=qc_only
    W->>Dst: upload qc/ + reject_reason + manifest
  end
  Note over Dst: BAM never uploaded
  W->>S: delete_fastqs
  Note over S: Keep expression.h5 for cohort modeling on /work
```

---

## 4. Study modeling — DE gene panel + classification

After enough samples pass prep, start `rnaseq_study_lifecycle` with `projectPath` pointing at the study manifest (groups, comparisons, holdout partitions) and `rnaDeOutputDir` in the instance context. It runs `pipeline.rna_de_select` per comparison.

```mermaid
flowchart TD
  START["foreach comparison in project.comparisons"] --> LOAD["load_expression_matrix<br/>cohort samples × genes (log-CPM)"]
  LOAD --> DE["Welch differential expression<br/>rank by |t| or signed log2FC"]
  DE --> PANEL["select top max_genes<br/>→ rna_de_panel.csv (gene_id · log2fc · t_stat · score · rank)"]
  PANEL --> CLF["tabular sklearn classifier<br/>StratifiedKFold balanced accuracy"]
  COV["covariates_csv (optional)"] -->|"covariate_preprocessor"| CLF
  CLF --> RES["rna_de_results.json<br/>balanced_accuracy · n_genes · feature_mode=rna_expression"]
```

```mermaid
flowchart LR
  subgraph reuse["Reused from methylvalidation"]
    MAT["samples × features matrix"] --> TAB["tabular sklearn backend"]
    CP["covariate_preprocessor + ALR"] --> ST["second-stage stacking"]
  end
  EXPR["expression.h5 (log-CPM)"] --> MAT
  NOTE["feature_mode = rna_expression<br/>(MonteCarloConfig accepts it)"] -.-> MAT
```

- The gene-panel CSV uses a recurrence-friendly schema (one row per selected `gene_id`) so `validation.stability` aggregation can count gene recurrence across Monte Carlo runs, exactly as it counts DMP recurrence for methylation.
- Cell-type deconvolution (Houseman / HiTIMED) and read-level information measures are **methylation-only** and do not run for RNA-Seq. Covariate stacking (e.g. an externally supplied `cell_fractions.csv` or clinical covariates) still works via `covariate_preprocessor`.

---

## 5. Operator run order (canonical)

```mermaid
flowchart TD
  S0["methyl-study-init --modality rnaseq<br/>fill CSVs + partitions"] --> S1["SamplePrepRnaSeqPipeline<br/>foreach sample"]
  S1 --> S2["methyl-workflow-run<br/>rnaseq_study_lifecycle<br/>profile rnaseq_research"]
  S2 --> S3["Review DE panels + balanced accuracy"]
```

Example (production-style paths):

```bash
# 1) Sample prep (STAR by default; set quant_mode=kallisto in the profile to switch)
methyl-workflow-run \
  --program /work/epimethyl/current/runtime-bundle/domain/fixtures/sample_prep_rnaseq.program.json \
  --context '{"projectPath":"/work/projects/my-rna-study/configs/project_Healthy_vs_Disease.json","pipelineProfile":"rnaseq_research"}'

# 2) Study modeling
methyl-workflow-run \
  --program /work/epimethyl/current/runtime-bundle/domain/fixtures/rnaseq_study_lifecycle.program.json \
  --context '{"projectPath":"/work/projects/my-rna-study/configs/project_Healthy_vs_Disease.json","pipelineProfile":"rnaseq_research","rnaDeOutputDir":"/work/projects/my-rna-study/RnaSeq/rna_de"}' \
  --parallel-workers 1 -v
```

---

## 6. End-to-end swimlane (systems)

```mermaid
sequenceDiagram
  participant Portal as Portal / cfg
  participant GW as Gateway
  participant W as GPU workers
  participant Stor as Shared /work
  participant Src as fastqSource
  participant Dst as sampleDestination

  Portal->>GW: Start SamplePrepRnaSeq instance
  GW->>W: Claim download_fastq
  W->>Src: Fetch FASTQ
  W->>Stor: Stage under /work/samples/id
  W->>Stor: Quantify (rna_fq2bam | kallisto)
  W->>Stor: rna_qc · register_expression (expression.h5)
  W->>Dst: archive_sample full or qc_only (no BAM)
  W->>Stor: delete_fastqs
  W->>GW: Complete sample
  Portal->>GW: Start rnaseq study lifecycle
  GW->>W: pipeline.rna_de_select per comparison
  W->>Stor: DE panel + classification results
  GW->>Portal: Instance succeeded
```

---

## 7. Checklist — “ready for modeling”

| Gate | Evidence |
|------|----------|
| Modality set | Study `regulatory.primary_modality: rnaseq` |
| Reference pinned | Site `rna_reference` (STAR index or kallisto index for the chosen `quant_mode`) |
| Samples registered | `/work/samples/{id}/{id}.expression.h5` present |
| RNA QC | `{id}.rna_qc.json` with `guardrails.overall_pass` |
| Study groups | Manifest comparisons match sample IDs |
| DE panels | `rna_de_panel.csv` + `rna_de_results.json` per comparison |

---

## 8. What this document is not

- Not an FDA submission or SaMD evidence package — see [`docs/regulatory/`](../regulatory/README.md).
- Not the methylation workflow — see [end-to-end workflow](end-to-end-workflow.md).
- Not the config-registry / credential runbook — see [config registry](config-registry.md) and [Usage ch.19](../usage/19-config-registry.qmd).

Operator detail: [Usage ch.20 RNA-Seq process pack](../usage/20-rnaseq-process-pack.qmd). Plan: [`docs/plans/rna-seq-process-pack.plan.md`](../plans/rna-seq-process-pack.plan.md).
