---
marp: true
theme: epimethyl-sales
paginate: true
size: 16:9
html: true
header: "MethylPipeline · Regulatory-Ready Platform"
footer: "Confidential · Sales briefing"
---

<!-- _class: lead -->

# Regulatory-Ready Platform
## for Multiomics Diagnostics

<p class="kicker">Commercial briefing</p>
<p class="big">From discovery scripts to auditor-ready evidence — without rebuilding your stack for every assay.</p>

---

<!-- _class: invert -->

## The problem buyers already feel

| Failure mode | What happens today |
|--------------|-------------------|
| Slow path to market | Biomarker → **510(k)** / **De Novo** / **PMA** (+ **CLIA**) stalls on process, not only science |
| Quiet validation failure | Train/holdout **leakage**, notebooks, unreproducible “final” runs |
| Audit bottleneck | Documentation debt — not missing compute |
| Modality sprawl | Each omics or indication becomes a **new product stack** |

> MethylPipeline shrinks those modes with config-first science, partition discipline, and submission scaffolds.

---

## Claim boundary

> The platform **enforces process and configuration controls** and **assembles evidence packages**. Architecture and SaMD profiles are **not** FDA clearance or approval.

| We do | We do not |
|-------|-----------|
| Shorten the software + validation process path | Choose or guarantee the regulatory pathway |
| Lock partitions, configs, and provenance | Replace clinical judgment or predicate strategy |
| Stage clinical-performance claim gates | Imply every assay is a simple 510(k) |

---

<!-- _class: lead -->

# Positioning

## Control plane + process packs + application packs

Bridges **bioinformatics R&D engineering** and **regulatory / quality readiness**.

---

## Three pillars of value

<div class="cards">
  <div class="card">
    <h3>1. R&amp;D agility</h3>
    <p>Cohorts, ECDF / tabular models, covariates, Houseman / HiTIMED — via <strong>configuration</strong>, not ad hoc scripts.</p>
  </div>
  <div class="card sky">
    <h3>2. Cloud efficiency</h3>
    <p>Capability-matched workers + <strong>CAAS</strong> skip alignment when only downstream science changes.</p>
  </div>
  <div class="card amber">
    <h3>3. SaMD controls</h3>
    <p>Partition discipline, staged clinical-performance claims, and auto-assembled <strong>evidence scaffolds</strong>.</p>
  </div>
</div>

---

<!-- _class: invert -->

## What buyers actually purchase

| Layer | What it is |
|-------|------------|
| **1. Execution platform** | DomainProgram IR, typed actions, cfg/wf registry, portal, gateway, CAAS, fleet control |
| **2. Process packs** | Modality science — methylation WGBS, RNA-Seq, proteomics |
| **3. Application packs** | Indication / trait overlays as **config** on an existing process |

<span class="pill">Disease-agnostic</span>
<span class="pill">Analyte-extensible</span>
<span class="pill">Operator-configurable</span>
<span class="pill">Config not code</span>

---

## DomainProgram: declare the science once

```mermaid
%% mp:interactive
flowchart LR
  DP["DomainProgram<br/>versioned typed IR"] --> COMP["Compiler"]
  COMP --> LOCAL["Local engine"]
  COMP --> DB["wf.workflow_def<br/>Azure SQL / PostgreSQL"]
  DB --> GW["Gateway"]
  GW --> W["Workers claim tasks"]
  CFG["Site · Profile · Instance<br/>actionConfig"] --> BAKE["resolvedConfig<br/>baked at start"]
  BAKE --> W
```

| Strength | Detail |
|----------|--------|
| One language | SamplePrep, MC stability, freeze, model selection, holdouts |
| Config layers | Operators tune parameters without editing Python |
| Worker contract | Tasks carry baked `resolvedConfig` — no profile re-read on the node |

---

## Methylation process pack (production path)

```mermaid
%% mp:interactive
flowchart TB
  subgraph prep["SamplePrep · per sample · parallel workers"]
    DL["download_fastq"] --> MODE{"alignmentMode"}
    MODE -->|linear| PB["Parabricks<br/>fq2bam_meth"]
    MODE -->|pangenome_wgbs| MG["Mojo Giraffe<br/>dual C2T∥G2A GAF"]
    PB --> AQC["alignment QC"]
    MG --> AQC
    AQC -->|pass| EXT["extract H5"]
    AQC -->|remediate| REM["trim → realign → QC"]
    REM --> EXT
    EXT --> ARC["archive curated bundle"]
  end
  subgraph study["Study lifecycle · cohort"]
    MC["MC centroid + detector"] --> STAB["stability / readiness"]
    STAB --> FRZ["freeze panel + mapper"]
    FRZ --> COV["deconv + info measures"]
    COV --> MOD["select_best_model"]
    MOD --> VAL["locked / pivotal holdouts"]
  end
  ARC --> MC
```

---

## GPU pangenome WGBS (current engineering)

| Capability | Production contract |
|------------|---------------------|
| Dual-graph Align | C2T ∥ G2A → science **GAF** for MethylCall |
| Engine knobs | `actionConfig.methylgrapher_wgbs` → task `resolvedConfig` |
| Backends | `gpu_giraffe` / `mojo_giraffe` / `cpu_vg` (operator-set) |
| Image | `epimethyl/methylgrapher:1.70-mojo` on GH200-class fleet |
| QC path | Mojo QC BAM + conversion-rate sidecars when enabled |

> Linear `fq2bam_meth` remains the comparator; **pangenome_wgbs** is the graph science path — not a separate product.

---

## Same language, RNA-Seq process pack

```mermaid
flowchart LR
  FQ["FASTQ"] --> Q["Parabricks RNA quant<br/>STAR rna_fq2bam OR kallisto"]
  Q --> RQC["RNA QC"]
  RQC --> EXP["expression<br/>samples × features"]
  EXP --> DE["rna_de_select"]
  DE --> TAB["tabular classifier<br/>+ covariates + MC"]
```

| Shared | Pack-specific |
|--------|---------------|
| Scheduler, cfg/wf, CAAS, feature seam | `actionConfig.rna_align.quant_mode` |
| Portal / gateway / workers | RNA QC thresholds |
| Tabular model MC | STAR vs kallisto branch |

---

## Distributed execution

```mermaid
%% mp:interactive
flowchart TB
  subgraph control["Control plane"]
    UI["EpiPortal"] --> CFG["cfg registry"]
    CFG --> WF["DomainProgram → workflow_def"]
    WF --> INST["instance + actionConfig"]
    INST --> GW["methyl-gateway"]
  end
  subgraph compute["Site compute"]
    W1["GPU SamplePrep"]
    W2["CPU science"]
    W3["Enricher / models"]
  end
  STORE[("/work<br/>samples · projects · caches")]
  GW -->|"claim · heartbeat · submit"| W1 & W2 & W3
  W1 & W2 & W3 --> STORE
  CFG -->|"materialize non-secrets"| STORE
```

Workers are **stateless claimants**. Credentials stay in `cfg.credential` — never plain files under `/work`.

---

## Config layers — tune without redeploying science code

```mermaid
flowchart LR
  SITE["Site"] --> PROF["Profile"]
  PROF --> PROG["DomainProgram"]
  PROG --> INST["Instance"]
  INST --> RES["resolvedConfig<br/>on each task"]
```

| Layer | Who edits | Examples |
|-------|-----------|----------|
| Site | Operators / cluster | genomes, caches, Align image, fleet caps |
| Profile | Release / procedure | `samd_research`, MC knobs, gene FeatureCuts |
| DomainProgram | Pack authors | topology, typed actions |
| Study / instance | Study team | cohorts, partitions, claim gates |

**Merge:** site → profile → program/instance overlay → analyte fill-missing → *(no Python fallback for tunable knobs)*.

---

## Process packs vs application packs

```mermaid
flowchart LR
  P[Execution platform] --> PP[Process packs]
  P --> AP[Application packs]
  PP --> M[Methylation WGBS]
  PP --> R[RNA-Seq]
  PP --> PR[Proteomics]
  AP --> A[Alzheimer cfDNA]
  AP --> PL[Plant abiotic stress]
  M -.-> A
  M -.-> PL
```

<div class="columns">
<div>

**Process pack** = new modality  
DomainPrograms, typed actions, QC, profiles on the shared control plane.

</div>
<div>

**Application pack** = config overlay  
Study manifest, cohorts, partitions, disease/trait — **no new aligner**.

</div>
</div>

---

## Analyte & disease-process roadmap

| Process / analyte | Status | What ships |
|-------------------|--------|------------|
| Methylation — buffy / cfDNA | **Production** | SamplePrep → MC → freeze → model; SaMD ladder; Mojo pangenome_wgbs |
| RNA-Seq | **Research pack** | STAR/kallisto, RNA QC, DE panel → tabular classifier |
| Proteomics | **Research pack** | GPU DIA-NN, Sage DDA, panel ingest; Prosit / Casanovo |
| Alzheimer cfDNA | **Research app pack** | Methylation + `neuro-core` overlay — config only |
| Plant abiotic stress | **Research app pack** | Control vs Drought WGBS; multi-crop sites |

---

## Multiomics on one plane

```mermaid
%% mp:interactive
flowchart TB
  subgraph shared["Shared control plane"]
    DP["DomainProgram + typed actions"]
    SCH["Scheduler / gateway / CAAS"]
    CTL["Fleet desired_state<br/>catalog control"]
    FEAT["samples × features seam"]
  end
  METH["Methylation<br/>centroid / DMP"] --> FEAT
  RNA["RNA-Seq<br/>DE genes"] --> FEAT
  PROT["Proteomics<br/>DIA-NN / Sage"] --> FEAT
  FEAT --> CLF["Tabular classifier + covariates + MC"]
  DP --- SCH
  SCH --- CTL
  SCH --> METH & RNA & PROT
```

---

## Fleet control without SSH

Operators set worker state from the portal / SQL — workers honor it on claim and heartbeat.

```mermaid
flowchart LR
  OP["Operator"] --> SP["portal.sp_set_worker_desired_state"]
  SP --> ROW["wf.worker.desired_state"]
  ROW --> HB["claim / heartbeat ACK"]
  HB --> RUN["WorkerRunner"]
  CAT["Action catalog<br/>control.can_stop"] --> RUN
  RUN -->|DRAIN| IDLE["No new claims"]
  RUN -->|STOP + can_stop| ABORT["Abort in-flight"]
  RUN -->|ACTIVE| WORK["Claim & execute"]
```

| `desired_state` | Idle | In-flight |
|-----------------|------|-----------|
| **ACTIVE** | Claim | Continue |
| **DRAINING** | Skip claims | Finish current (pause only if `can_pause`) |
| **STOPPING** | Skip claims | Abort if catalog `can_stop` |

Science knobs stay on `actionConfig`. Fleet control stays on worker state + catalog `control`.

---

## Application pack pattern

<div class="cards two">
  <div class="card">
    <h3>Alzheimer cfDNA</h3>
    <p><code>primary_analyte: cfdna</code></p>
    <p>Patient-disjoint partitions; Alzheimer's disease term; <code>neuro-core</code>; Control → MCI → AD.</p>
    <p><strong>No new actions or aligners.</strong></p>
  </div>
  <div class="card amber">
    <h3>Plant abiotic stress</h3>
    <p><code>primary_analyte: plant_tissue</code></p>
    <p>Control vs Drought across CG/CHG/CHH; Ensembl Plants sites; offline trait priors.</p>
    <p>epi-GBS isolated via separate SamplePrep program.</p>
  </div>
</div>

---

## SaMD profile ladder

```mermaid
flowchart LR
  INIT["methyl-study-init"] --> R["samd_research"]
  R -->|"lock HPs + locked_test"| H["samd_holdout_enrichment"]
  H -->|"freeze + pivotal cohort"| P["samd_pivotal"]
  R -.-> HP["hyperparam search<br/>+ early-stop"]
```

| Profile | Intent |
|---------|--------|
| **samd_research** | Discover stable panels under partition discipline |
| **samd_holdout_enrichment** | Locked hyperparameters + locked test patients |
| **samd_pivotal** | Claim-gated clinical-performance evidence packaging |

---

## CAAS: change the classifier, keep the alignment

```mermaid
flowchart LR
  A["Align + extract<br/>content-addressed"] --> B["Centroid / detector"]
  B --> C["Classifier / model MC"]
  C -->|"edit downstream only"| C2["New model config"]
  A -.->|"CAAS hit · skip"| C2
  B -.->|"reuse artifacts"| C2
```

| Mechanism | Why it matters |
|-----------|----------------|
| Input / output signatures | Skip recomputation when science is unchanged |
| CLI + environment binding | Provenance for quality review |
| FOREACH bundle keys | Whole MC iteration short-circuit when safe |

---

<!-- _class: lead -->

# Packaging & GTM

## Open core that captures R&D — Enterprise that closes the FDA chasm

---

## Open-core packaging

```mermaid
%% mp:interactive
graph TD
    A[MethylPipeline Core] -->|AGPL-3.0| B[Community Edition]
    A -->|Commercial license + support| C[Enterprise SaMD Edition]
    B --> D[Academia · consortia · developers]
    C --> E[Biotech · pharma · reference labs]
    C --> F[EpiPortal · vault secrets · evidence index]
```

---

## Community vs Enterprise

<div class="cards two">
  <div class="card">
    <h3>Community Edition</h3>
    <p><span class="pill">AGPL-3.0</span></p>
    <ul>
      <li>LocalWorkflowEngine</li>
      <li>DNA methylation process pack</li>
      <li>CLI tools + <code>samd_research</code></li>
      <li>Goal: citations, adoption, contributions</li>
    </ul>
  </div>
  <div class="card amber">
    <h3>Enterprise / SaMD Edition</h3>
    <p><span class="pill">Annual subscription</span></p>
    <ul>
      <li>Evidence index + traceability packaging</li>
      <li>Pivotal ladder unlocks</li>
      <li>EpiPortal multi-tenant ops + fleet control</li>
      <li>Zero-trust credentials + GPU SamplePrep support</li>
    </ul>
  </div>
</div>

---

## Hybrid cloud (BYOC)

<div class="columns">
<div>

**We host / operate**
- EpiPortal control plane
- DB metadata + scheduler
- Non-secret materialization

</div>
<div>

**Customer keeps**
- Stateless workers (AWS / Azure / on-prem)
- `/work` + samples in their boundary
- HIPAA / GDPR data residency

</div>
</div>

> Regulated data never has to leave the customer’s estate.

---

## Who buys — and why

| Buyer | Why MethylPipeline |
|-------|-------------------|
| **Biotech / diagnostic startups** | Liquid biopsy & multiomics without building a platform |
| **Pharma / trial sponsors** | Locked, reproducible workflows as trial endpoints |
| **Reference labs / CROs** | FASTQs → curated classification + evidence packages |

---

## Customer journey: the “FDA chasm”

```mermaid
flowchart LR
  CE["Community / samd_research<br/>discover stable panels"] --> CHASM["FDA chasm<br/>locked pipeline + holdouts + evidence"]
  CHASM --> ENT["Enterprise SaMD<br/>portal · pivotal · packaging"]
```

| Stage | Motion |
|-------|--------|
| **Hook** | Research feasibility at low friction |
| **Trigger** | Marker must survive locked + pivotal validation under audit |
| **Upgrade** | Portal ops, pivotal ladder, regulatory packaging |

---

<!-- _class: invert -->

## Why technical buyers say yes

| Capability | Outcome |
|------------|---------|
| Audit trails with low overhead | Hashes, versions, environment signatures in action results |
| CAAS economics | Skip alignment across large cohorts when iterating models |
| Multiomics extensibility | Process packs add programs; application packs are config-only |
| Partition discipline | Development vs locked holdout enforced by profiles |
| Fleet control | Drain / stop workers from portal — no SSH to GPU nodes |
| Config not code | Science knobs in site/profile/instance — never magic numbers in Python |

---

<!-- _class: lead -->

# Close

## Regulatory-Ready Platform for Multiomics Diagnostics

**Control plane + packs** — not a single hard-coded assay.

**Next step:** live DomainProgram demo · SaMD ladder walkthrough · evidence-scaffold review
