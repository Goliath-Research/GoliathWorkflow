# MethylPipeline end-to-end workflow

**Audience:** operators, statisticians, and engineers who need one clear picture from external sample ingest through Monte Carlo stability, cell deconvolution, information-theoretic covariates, model training, and holdout validation.

**Sources of truth (programs):**

| Phase | DomainProgram |
|-------|----------------|
| Per-sample prep | [`workflow_engine/domain/fixtures/sample_prep.program.json`](../../workflow_engine/domain/fixtures/sample_prep.program.json) |
| Study MC → freeze → model | [`full_lifecycle.program.json`](../../workflow_engine/domain/fixtures/full_lifecycle.program.json) / [`study_validation_lifecycle.program.json`](../../workflow_engine/domain/fixtures/study_validation_lifecycle.program.json) |
| SaMD profile ladder | [`docs/usage/18-samd-study-lifecycle.qmd`](../usage/18-samd-study-lifecycle.qmd) |

Related stage chapters: [ch.03 Sample prep](../usage/03-sample-prep-and-qc.qmd) · [ch.05 Stability](../usage/05-stage-stability.qmd) · [ch.06 Freeze](../usage/06-stage-freeze.qmd) · [ch.07 Model](../usage/07-stage-model.qmd) · [ch.08 Post-model](../usage/08-stage-post-model-validation.qmd).

---

## 1. Big picture

Two DomainPrograms run in sequence for a typical study:

1. **SamplePrepPipeline** — one sample at a time (parallel across samples): download → align → QC → optional trim/realign → extract → archive.
2. **Study validation lifecycle** — cohort-level: Monte Carlo centroid/detector iterations → stability → freeze panel → mapper / derived measures / **CellDeconv** / **info measures** → enricher → model selection → holdout / post-model validation.

```mermaid
flowchart TB
  subgraph ingest["0 · External storage"]
    EXT["Cloud / QNAP / portal object store<br/>FASTQ or sequenced library IDs"]
  end

  subgraph prep["1 · SamplePrepPipeline (per sample)"]
    DL["download_fastq"]
    ALN["Parabricks align<br/>fq2bam_meth or giraffe"]
    AQC["methyl_qc"]
    REM["trim_fastq → realign → methyl_qc retry"]
    EXT2["methyl_extract<br/>*.h5 + *.patterns.h5"]
    EQC["extraction_qc"]
    ARC["archive + delete FASTQ/BAM"]
  end

  subgraph study["2 · Study validation lifecycle (cohort)"]
    MC["MC iterations<br/>centroid + detector"]
    STAB["stability + freeze readiness"]
    FRZ["freeze centroid/detector + mapper"]
    COV["derived_measures<br/>cell_deconvolution<br/>info_measures"]
    ENR["enricher ± progression"]
    MOD["select_best_model<br/>ECDF ± covariates"]
    VAL["post_model_validation<br/>locked_test / pivotal holdouts"]
  end

  EXT --> DL --> ALN --> AQC
  AQC -->|pass| EXT2
  AQC -->|remediate| REM --> EXT2
  EXT2 --> EQC --> ARC
  ARC --> MC --> STAB --> FRZ --> COV --> ENR --> MOD --> VAL
```

```mermaid
flowchart LR
  subgraph layers["Configuration layers (highest wins on the right)"]
    SITE["Site<br/>/work/site"] --> PROF["Profile<br/>samd_*"]
    PROF --> PROG["DomainProgram"]
    PROG --> INST["Instance context"]
  end
```

Study science lives under `/work/projects/<study>/`; sample archives under `/work/samples/{sample_id}/`. Credentials stay in the `cfg` registry — never under project trees.

---

## 2. Where data lives

```mermaid
flowchart TB
  subgraph external["External / portal"]
    OBJ["Object storage endpoint<br/>cfg.storage + credentials"]
  end

  subgraph work["Shared /work"]
    SAMP["/work/samples/{sample_id}/<br/>BAM → then *.h5 + *.patterns.h5"]
    PROJ["/work/projects/{study}/<br/>configs/, data/, outputs/"]
    SITE["/work/site/methyl_site.json<br/>genomes, caches"]
    EPI["/work/epimethyl/current/<br/>runtime-bundle, venv"]
  end

  OBJ -->|"sample.download_fastq"| SAMP
  SAMP -->|"paths in project groups"| PROJ
  SITE -.->|"METHYL_SITE_CONFIG"| EPI
  PROJ -->|"projectPath in --context"| EPI
```

| Path | Role |
|------|------|
| `/work/samples/{id}/` | Per-sample BAM (transient), `{chrom}-{ctx}.h5`, `{chrom}-{ctx}.patterns.h5`, QC JSON |
| `/work/projects/{study}/configs/project_*.json` | Cohorts, comparisons, `validation_partitions` |
| `/work/projects/{study}/{project_name}/` | MC runs, freeze, cell_fractions, info_measures, models |
| `/work/site/` | Genomes, site `actionConfig` defaults |

---

## 3. Sample prep — arrival to extract

### 3.1 Happy path

```mermaid
flowchart TD
  A["sample.download_fastq<br/>from storage endpoint"] --> B{"usePangenome?"}
  B -->|no| C["sample.parabricks_fq2bam<br/>pbrun fq2bam_meth"]
  B -->|yes| D["sample.parabricks_giraffe<br/>vg giraffe → GRCh38"]
  C --> E["sample.methyl_qc"]
  D --> E
  E --> F{"qcPass?"}
  F -->|yes| G{"isCfdna?"}
  G -->|yes| H["sample.fragmentomics"]
  G -->|no| I["sample.methyl_extract"]
  H --> I
  I --> J["sample.extraction_qc"]
  J --> K{"extractionQcPass?"}
  K -->|yes| L["archive_sample full"]
  L --> M["delete_fastqs"]
  M --> N["delete_bam"]
  K -->|no| O["archive qc_only + qc_failed"]
```

**Extract outputs** (read-level enabled by default on SaMD/research profiles):

| File | Content |
|------|---------|
| `{chrom}-{ctx}.h5` | Marginal per-CpG counts (`mC`, `uC`, coverage) |
| `{chrom}-{ctx}.patterns.h5` | Read-level co-methylation tile histograms (MethylInfoTheory input) |

If patterns are missing, extract warns and continues; later `pipeline.info_measures` skips without failing the study.

### 3.2 Alignment QC fail → trim → realign → retry

FASTQs are **kept** until QC is fully resolved so remediation can trim and realign.

```mermaid
flowchart TD
  QC1["methyl_qc attempt 1"] --> P{"qcPass?"}
  P -->|yes| OK["extract path"]
  P -->|no| R{"remediateAlignment?"}
  R -->|no| FAIL["archive qc_only → qc_failed"]
  R -->|yes| T["sample.trim_fastq<br/>fastp front/tail from QC disposition"]
  T --> RA["parabricks_* forceRealign<br/>alignmentPass=post_trim_realign"]
  RA --> QC2["methyl_qc attempt 2"]
  QC2 --> P2{"qcPass?"}
  P2 -->|yes| OK2["fragmentomics? → methyl_extract → extraction_qc → archive"]
  P2 -->|no| FAIL2["archive qc_only → qc_failed"]
```

Typical remediation trigger: Read-2 start low quality (`READ2_START_LOW_QUALITY`) → `trimFront2` / related trim knobs from the QC screening report.

### 3.3 Per-sample artifact timeline

```mermaid
sequenceDiagram
  participant Ext as External storage
  participant W as Worker
  participant S as /work/samples/id
  participant Q as QC reports

  Ext->>W: download_fastq
  W->>S: *.fastq.gz
  W->>S: align → *.bam + metrics
  W->>Q: methyl_qc JSON / disposition
  alt remediate
    W->>S: trim FASTQ in place / sidecar
    W->>S: forceRealign BAM
    W->>Q: methyl_qc retry
  end
  W->>S: methyl_extract → *.h5 + *.patterns.h5
  W->>Q: extraction_qc
  W->>S: archive; delete FASTQ + BAM
  Note over S: Durable inputs for MC: HDF5 + patterns
```

---

## 4. Study lifecycle — Monte Carlo to freeze

After enough samples pass prep, start the study program with `projectPath` pointing at the study manifest (groups, chromosomes, contexts, comparisons, holdout partitions).

```mermaid
flowchart TD
  PLAN["validation.plan_iterations<br/>build iteration + seed plans"] --> SEED["Optional centroid seeds<br/>foreach seedGroup × chrom × ctx"]
  SEED --> ITER["foreach iteration parallel"]
  ITER --> CEN["pipeline.centroid<br/>per group × chrom"]
  CEN --> DET["pipeline.detector<br/>per comparison × chrom"]
  DET --> ST["validation.stability<br/>DMP/gene recurrence, BA gates"]
  ST --> RD["stability_freeze_readiness"]
  RD --> PREP["prepare_freeze_project<br/>fixed panels"]
  PREP --> FC["freeze centroid + detector<br/>fixedDmpPanel"]
  FC --> MAP["pipeline.mapper"]
```

```mermaid
flowchart LR
  subgraph mc["Each MC iteration"]
    direction TB
    T["Train split<br/>holdout excluded"] --> C["Centroids per group"]
    C --> D["ECDF / detector DMPs"]
    D --> M["Metrics + selected panels"]
  end
  mc --> AGG["stability aggregates<br/>freq ≥ threshold<br/>FeatureCuts optional"]
```

Holdouts configured in the study manifest (`validation_partitions.locked_test`, later `pivotal_validation`) are **excluded from training** when the profile sets `holdout_exclude_from_training: true` (SaMD profiles).

---

## 5. Cohort covariates after freeze

These nodes run **after** freeze mapper work and **before** final model selection. They enrich each sample with biology that ECDF alone does not see.

```mermaid
flowchart TD
  MAP["pipeline.mapper"] --> DM["pipeline.derived_measures<br/>chromosome / genome surrogates"]
  DM --> CD["pipeline.cell_deconvolution<br/>Houseman / FlowSorted IDOL"]
  CD --> IM["pipeline.info_measures<br/>MethylInfoTheory / Ising"]
  IM --> EN["pipeline.enricher"]
  EN --> PR["pipeline.progression optional"]
  PR --> SEL["validation.select_best_model"]
```

### 5.1 Cell deconvolution (Ω)

```mermaid
flowchart LR
  H5["Sample *.h5 β at IDOL markers"] --> QP["Houseman QP"]
  REF["FlowSorted.Blood.EPIC IDOL<br/>6 cell types"] --> QP
  QP --> CSV["cell_fractions.csv<br/>CD8T CD4T NK Bcell Mono Neu"]
```

- Written under `{output_base}/cell_fractions/cell_fractions.csv`.
- Listed on profile `covariates_path` for tabular / ECDF second-stage.
- Auto-infer **excludes** `group` / `qp_status` (label leakage guard).

### 5.2 Information measures (read-level)

```mermaid
flowchart LR
  PAT["*.patterns.h5 per sample"] --> V1["Entropy / epipolymorphism / PDR"]
  PAT --> V2["Ising MML NME ESI MSI<br/>ising_enabled"]
  V1 --> RL["readlevel_measures.csv"]
  V2 --> RL
  V2 --> CONF["confirmation_report.json<br/>JSD/dNME vs DMPs"]
  PAT -.->|none present| SKIP["status skipped<br/>no hard fail"]
```

### 5.3 How covariates reach the model

```mermaid
flowchart TB
  ECDF1["First-stage ECDF<br/>methylation only<br/>raw_gene / raw_dmp"] --> PROBS["Class probabilities"]
  OMEGA["cell_fractions.csv<br/>6 Ω"] --> STACK["ECDF second-stage<br/>logistic stacker"]
  RL["readlevel_measures.csv<br/>NME / MML / …"] --> STACK
  DM2["derived_measures.csv"] --> STACK
  PROBS --> STACK
  STACK --> SCORE["Refined scores / BA"]
```

Profiles such as `samd_research` merge those CSV paths under `backend_profiles.ecdf.params.covariates_path`. Missing files in the list are skipped with a warning so studies can proceed before full re-extract.

---

## 6. Model selection and holdout validation

```mermaid
flowchart TD
  SEL["validation.select_best_model<br/>train on non-holdout; backends from profile"] --> PMV["validation.post_model_validation"]
  PMV --> LT{"Partition"}
  LT -->|locked_test| LTE["Internal holdout metrics<br/>samd_holdout_enrichment+"]
  LT -->|pivotal_validation| PV["Pivotal cohort<br/>samd_pivotal only"]
  LT -->|MC folds| DIST["post_model_validation/<br/>metrics distributions"]
```

### SaMD ladder (claim-oriented studies)

```mermaid
flowchart LR
  R["samd_research<br/>explore HPs / early-stop"] -->|"lock caps + BA"| H["samd_holdout_enrichment<br/>require locked_test"]
  H -->|"freeze HPs + open cohort"| P["samd_pivotal<br/>require pivotal_validation"]
```

| Partition | When | Rule |
|-----------|------|------|
| `locked_test` | Research recommended; enrichment required | Never trained; evaluate after lock |
| `pivotal_validation` | Pivotal only | Never used in research/enrichment training |
| Independence keys | Always | Same `patient_id` cannot sit in train and holdout |

Clinical performance claims are blocked until `regulatory.stage = pivotal_validation`.

---

## 7. Operator run order (canonical)

```mermaid
flowchart TD
  S0["methyl-study-init / fill CSVs + partitions"] --> S1["SamplePrepPipeline<br/>foreach sample"]
  S1 --> S2["methyl-workflow-run<br/>study_validation_lifecycle<br/>profile samd_research"]
  S2 --> S3["Review stability + covariate CSVs<br/>Ω + readlevel"]
  S3 --> S4["Lock HPs → samd_holdout_enrichment<br/>eval locked_test"]
  S4 --> S5["Optional samd_pivotal<br/>pivotal_validation cohort"]
```

Example (production-style paths):

```bash
# 1) Sample prep (gateway or local engine)
methyl-workflow-run \
  --program /work/epimethyl/current/runtime-bundle/domain/fixtures/sample_prep.program.json \
  --context '{"projectPath":"/work/projects/my-study/configs/project_Healthy_vs_Disease.json"}'

# 2) Study lifecycle
methyl-workflow-run \
  --program /work/epimethyl/current/runtime-bundle/domain/fixtures/study_validation_lifecycle.program.json \
  --context '{"projectPath":"/work/projects/my-study/configs/project_Healthy_vs_Disease.json","pipelineProfile":"samd_research"}' \
  --parallel-workers 1 -v
```

---

## 8. End-to-end swimlane (systems)

```mermaid
sequenceDiagram
  participant Portal as Portal / cfg
  participant GW as Gateway
  participant W as GPU workers
  participant Stor as Shared /work
  participant Ext as External object store

  Portal->>GW: Start SamplePrep instance
  GW->>W: Claim download_fastq
  W->>Ext: Fetch FASTQ
  W->>Stor: /work/samples/id/*.fastq.gz
  W->>Stor: Align BAM
  W->>Stor: QC + extract h5/patterns
  W->>GW: Complete sample
  Portal->>GW: Start study lifecycle
  GW->>W: MC centroid/detector tasks
  W->>Stor: Iteration artifacts
  W->>Stor: stability / freeze / mapper
  W->>Stor: cell_fractions + readlevel_measures
  W->>Stor: model + post_model_validation
  GW->>Portal: Instance succeeded
```

---

## 9. Checklist — “ready for holdout validation”

| Gate | Evidence |
|------|----------|
| Samples archived | `/work/samples/{id}/*-CG.h5` present; BAM optional after delete |
| Patterns (preferred) | `*.patterns.h5` or info_measures skipped cleanly |
| Study groups | Manifest groups match sample IDs |
| Holdouts | `locked_test` non-empty before enrichment claims |
| MC stability | Freeze readiness passed for profile BA/freq gates |
| Ω CSV | `cell_fractions/cell_fractions.csv` with six columns |
| Info CSV | `info_measures/readlevel_measures.csv` when patterns exist |
| Model | `select_best_model` artifacts; ECDF ± second-stage covariates |
| Holdout metrics | `post_model_validation/` (and partition-specific eval as configured) |

---

## 10. What this document is not

- Not an FDA submission or SaMD evidence package — see [`docs/regulatory/`](../regulatory/README.md).
- Not a substitute for package THEORY/USAGE docs (centroid math, ECDF details, Ising formulas).
- Not the storage-credential runbook — see [config registry](config-registry.md) and [Usage ch.19](../usage/19-config-registry.qmd).

For a shorter stage DAG only, see [pipeline-stages.md](pipeline-stages.md). For SamplePrep QC dispositions, see [Usage ch.03](../usage/03-sample-prep-and-qc.qmd).
