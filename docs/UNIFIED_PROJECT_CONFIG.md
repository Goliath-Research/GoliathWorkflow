# Unified project config: one healthy group + several disease groups

This document describes how to use the **unified project config** (single JSON) for a project with **one control group** (e.g. healthy) and **multiple disease groups** (e.g. cancer levels pca1, pca2, pca3). It shows the **hierarchical structure of results** and how each pipeline step reads and writes under that layout.

---

## 1. Project config overview

A single **project JSON** defines:

- **Project root:** `{output_base}/{project_name}` — all step outputs live under this folder.
- **Groups:** A list of cohorts. The **first group (index 0)** is the **control** (e.g. healthy). All other groups are **disease** groups (e.g. pca1, pca1-1, pca1-2, pca1-3).
- **Shared settings:** `chromosomes`, `contexts`, `path_remap`, and optional **per-step defaults** under `step_config` (e.g. `centroid`, `detection`, `mapper`, `enricher`, `classifier`).

Example (one healthy + three disease groups):

```json
{
  "project_name": "PCa1_3levels_vs_Healthy_Hardik",
  "output_base": "/work/david-gladys/all-prostate",
  "groups": [
    { "label": "healthy", "sample_paths": ["configs/healthy-hardik.csv"] },
    { "label": "pca1-1", "sample_paths": ["configs/pca1-1.csv"] },
    { "label": "pca1-2", "sample_paths": ["configs/pca1-2.csv"] },
    { "label": "pca1-3", "sample_paths": ["configs/pca1-3.csv"] }
  ],
  "chromosomes": ["1", "2", "3", "..."],
  "contexts": ["CG"],
  "step_config": { "centroid": {...}, "detection": {...}, "mapper": {...}, "enricher": {...}, "classifier": {...} }
}
```

All tools accept `--project path/to/project.json` (and optional `--step-override path/to/overrides.json`). Paths and sample lists are derived from the project so you do not duplicate paths in each step config.

---

## 2. Hierarchical structure of results

For a project with **one control** and **several disease groups**, the pipeline uses a **consistent convention**:

- **Control (group 0):** outputs use a single folder named by the group label (e.g. `centroids/healthy`).
- **Disease groups (index 1, 2, …):** outputs use a **`cancer`** subdirectory and then the group label, so each disease group has its own folder and results are **not overwritten** (e.g. `detection/cancer/pca1-1`, `mapper/cancer/pca1-2`).

The subdirectory name `cancer` is the default and can be overridden in step config (e.g. `disease_subdir`) where supported.

### Full directory tree (N-group project)

Assume `output_base = /work/data` and `project_name = PCa1_3levels_vs_Healthy_Hardik`, with groups: **healthy**, **pca1-1**, **pca1-2**, **pca1-3**.

```
/work/data/PCa1_3levels_vs_Healthy_Hardik/
├── centroids/
│   ├── healthy/                          ← control (group 0): one centroid dir
│   │   ├── 1-CG.h5
│   │   ├── 2-CG.h5
│   │   └── ...
│   └── cancer/                           ← disease groups: one dir per group
│       ├── pca1-1/
│       │   ├── 1-CG.h5
│       │   └── ...
│       ├── pca1-2/
│       └── pca1-3/
│
├── detection/
│   ├── cancer/                           ← one detection run per disease group (control vs that group)
│   │   ├── pca1-1/
│   │   │   ├── dmps-1-CG.csv
│   │   │   ├── result-1-CG.json
│   │   │   └── ...
│   │   ├── pca1-2/
│   │   └── pca1-3/
│   └── (optional: dmps-merged-multiclass.csv, multiclass model output)
│
├── mapper/
│   └── cancer/                           ← one mapping run per disease group
│       ├── pca1-1/
│       │   ├── all-gene_name-combined.csv
│       │   ├── *-features-gene_name.csv
│       │   └── ...
│       ├── pca1-2/
│       └── pca1-3/
│
├── enricher/
│   └── cancer/                           ← one enrichment run per disease group
│       ├── pca1-1/
│       │   ├── enrichment_merged.csv
│       │   └── ...
│       ├── pca1-2/
│       └── pca1-3/
│
├── classifier/
│   └── cancer/                           ← one classification output per disease group (binary)
│       ├── pca1-1/
│       │   └── classification_results.csv
│       ├── pca1-2/
│       └── pca1-3/
│   └── (optional: multiclass-classifier.pkl, multiclass results)
│
└── alignment_qc/                         ← optional; one JSON per sample
    └── ...
```

### Summary table (where each step reads and writes)

| Step            | Control (group 0)              | Disease groups (1, 2, …)                    |
|-----------------|--------------------------------|---------------------------------------------|
| **Centroids**   | Writes to `centroids/{label}`  | Writes to `centroids/cancer/{label}`        |
| **Detection**   | Reference (centroid1); no dir  | Writes to `detection/cancer/{label}`        |
| **Mapper**      | —                              | Reads `detection/cancer/{label}`, writes `mapper/cancer/{label}` |
| **Enricher**    | —                              | Reads `mapper/cancer/{label}/all-gene_name-combined.csv`, writes `enricher/cancer/{label}` |
| **Classifier**  | Reference (centroid1)          | Reads `detection/cancer/{label}`, writes `classifier/cancer/{label}/classification_results.csv` |

---

## 3. Workflow order and CLI commands (N-group)

Run steps in this order. With `--project`, each tool derives input/output paths from the project; for N-group projects, **MethylDetector**, **MethylMapper**, and **MethylEnricher** run **once per disease group** and write under `…/cancer/{label}`.

### 1) Centroids (one dir per group)

Build a centroid for **each** group (control + all disease groups). Control goes to `centroids/healthy`; each disease group goes to `centroids/cancer/{label}`.

```bash
# Build centroids for all groups (recommended)
methyl-centroid --project configs/project_PCa1_3levels_vs_Healthy_Hardik.json --group all

# Or one group at a time (group: group1, group2, or 0-based index 0, 1, 2, 3)
methyl-centroid --project configs/project_PCa1_3levels_vs_Healthy_Hardik.json --group 0   # healthy
methyl-centroid --project configs/project_PCa1_3levels_vs_Healthy_Hardik.json --group 1   # pca1-1
methyl-centroid --project configs/project_PCa1_3levels_vs_Healthy_Hardik.json --group 2   # pca1-2
methyl-centroid --project configs/project_PCa1_3levels_vs_Healthy_Hardik.json --group 3   # pca1-3
```

### 2) Detection (one run per disease group)

Each run compares **control (healthy)** vs **one disease group** and writes to `detection/cancer/{label}`. No overwriting between groups.

```bash
methyl-detector --project configs/project_PCa1_3levels_vs_Healthy_Hardik.json --per-cancer-group
```

This produces `detection/cancer/pca1-1/`, `detection/cancer/pca1-2/`, `detection/cancer/pca1-3/`.

Optional: merge DMPs and build a **multiclass** model in the same call:

```bash
methyl-detector --project configs/project_PCa1_3levels_vs_Healthy_Hardik.json --per-cancer-group --multi-class-model
```

### 3) Mapper (one run per disease group)

Reads DMP CSVs from `detection/cancer/{label}/` and writes gene/feature tables to `mapper/cancer/{label}/`. Requires a GTF path (e.g. in `step_config.mapper` or `--gtf`).

```bash
methyl-mapper --project configs/project_PCa1_3levels_vs_Healthy_Hardik.json
```

With a multi-group project, the mapper automatically runs once per disease group and writes under `mapper/cancer/<label>`. To force a **single** combined run (e.g. one output dir), pass explicit `--csv-pattern` and/or `--output-dir`.

### 4) Enricher (one run per disease group)

Reads the mapper combined CSV from `mapper/cancer/{label}/all-gene_name-combined.csv` and writes enrichment results to `enricher/cancer/{label}/`.

```bash
methyl-enricher --project configs/project_PCa1_3levels_vs_Healthy_Hardik.json
```

With a multi-group project, the enricher automatically runs once per disease group. To use a **single** input/output instead, pass explicit `--input` and/or `--outdir`.

### 5) Classifier (per disease group or multiclass)

**Per-cancer-group (binary classifier per group):**

```bash
methyl-classifier --project configs/project_PCa1_3levels_vs_Healthy_Hardik.json --per-cancer-group
```

Reads the model (and DMPs) from each `detection/cancer/{label}/` and writes to `classifier/cancer/{label}/classification_results.csv`.

**Multiclass:** If you built a multiclass model with `methyl-detector ... --multi-class-model`, use the classifier in multiclass mode (see MethylClassifier docs and project config).

### 6) Alignment QC (optional)

```bash
methyl-qc --project configs/project_PCa1_3levels_vs_Healthy_Hardik.json
```

Writes one JSON per sample under `{project_root}/alignment_qc/`.

---

## 4. Two-group projects (control vs one disease group)

If the project has **exactly two groups** (e.g. healthy and pca1):

- **Centroids:** `centroids/healthy` and `centroids/cancer/pca1`.
- **Detection:** A single run (no `--per-cancer-group` needed) can write to `detection/` or you can still use `--per-cancer-group` to get `detection/cancer/pca1`.
- **Mapper / Enricher:** With two groups, mapper and enricher still use the per-group layout when using `--project` (one disease group → `mapper/cancer/pca1`, `enricher/cancer/pca1`).

So the same hierarchy applies; for a single disease group you simply have one subdir under each `cancer/` folder.

---

## 5. Overriding paths and step options

- **Per-step defaults:** Set in the project JSON under `step_config.centroid`, `step_config.detection`, `step_config.mapper`, `step_config.enricher`, `step_config.classifier`. Keys match each tool’s config (e.g. `gtf`, `disease_term`, `enrich_disease` for mapper; `gene_column`, `libraries`, `top` for enricher).
- **Step override file:** `--step-override path/to/overrides.json` merges over the project’s `step_config` for that step. Use for one-off overrides without editing the project file.
- **CLI flags:** Tool-specific options (e.g. `--gtf`, `--outdir`) override project and step-override when provided.

Resolution order: **project derived paths + step_config → step_override file → CLI**.

---

## 6. References

- **Project and path types:** `methyl_utils.pipeline_config.ProjectConfig`, `DerivedPaths`, `load_project()`.
- **Config examples:** [configs/README.md](../configs/README.md).
- **Operations and workflow:** [OPERATIONS_MANUAL.md](OPERATIONS_MANUAL.md).
- **Architecture:** [ARCHITECTURE.md](ARCHITECTURE.md).
