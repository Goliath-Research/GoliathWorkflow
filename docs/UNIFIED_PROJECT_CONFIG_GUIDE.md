# Unified Project Config: Full Guide

This document is the **single reference** for the **unified project config** (project JSON) used as the main parameter across all MethylPipeline packages. One JSON file defines the project, sample groups, comparisons, output layout, and per-step defaults so every tool can be run with `--project path/to/project.json` without duplicating paths or sample lists.

**Example used throughout:** `configs/project_PCa1_3levels_vs_Healthy_Hardik.json` — one healthy control group and three disease groups (pca1-1, pca1-2, pca1-3) with explicit comparisons.

---

## 1. What is the unified project config?

- **One JSON file** that all pipeline tools accept via `--project path/to/project.json`.
- **Single source of truth** for:
  - Project name and output root
  - Control and disease groups and their sample lists
  - Which comparisons to run (e.g. healthy vs pca1-1, healthy vs pca1-2, …)
  - Shared options (chromosomes, contexts, path remapping)
  - Per-step defaults (centroid, detection, mapper, enricher, classifier, validator)

Tools that support `--project`:

- **methyl-centroid** — builds centroids per group
- **methyl-detector** — DMP detection (per comparison when using control/disease)
- **methyl-mapper** — maps DMPs to genes (per comparison)
- **methyl-enricher** — enrichment (per comparison)
- **methyl-classifier** — classification (per comparison)
- **methyl-validator** — validation metrics (per comparison)
- **methyl-qc** — alignment QC (optional)

Optional **step overrides**: `--step-override path/to/overrides.json` merges over the project’s `step_config` for that run.

---

## 2. Config format: controls, diseases, comparisons

The **recommended format** uses three top-level blocks: **controls**, **diseases**, and **comparisons**. The loader also accepts **controls** / **diseases** (plural); they are normalized to **control** / **disease** internally.

### 2.1 Top-level fields

| Field | Required | Description |
|-------|----------|-------------|
| `project_name` | Yes | Project identifier; used in paths and naming (e.g. `PCa1_3levels_vs_Healthy_Hardik`). |
| `output_base` | Yes | Global output directory. All step outputs live under `{output_base}/{project_name}`. |
| `controls` | Yes* | Control side: `label` (e.g. `"healthy"`) and `groups` (list of `{ label, sample_paths }`). |
| `diseases` | Yes* | Disease side: `label` (e.g. `"cancer"`) and `groups` (list of `{ label, sample_paths }`). |
| `comparisons` | Yes* | List of pairs: `{ "control_group": "...", "disease_group": "..." }`. Defines which control/disease pairs to run through detection, mapper, enricher, classifier, validator. |
| `samples_base_path` | No | Base directory to resolve relative sample paths or names in CSVs. |
| `chromosomes` | No | Shared chromosome list (e.g. `["1","2",...,"22","X","Y"]`). |
| `contexts` | No | Methylation contexts (e.g. `["CG"]`). |
| `path_remap` | No | Map old path prefixes to new ones when data moves (e.g. `{ "/old/path": "/new/path" }`). Longest match is applied. |
| `step_config` | No | Per-step defaults; see §5. |

\*When using control/disease layout, `controls`, `diseases`, and `comparisons` are required. Alternative: legacy `group1` / `group2` or flat `groups` (see package docs).

### 2.2 Example: project_PCa1_3levels_vs_Healthy_Hardik.json (structure)

```json
{
  "project_name": "PCa1_3levels_vs_Healthy_Hardik",
  "output_base": "/work/david-gladys/all-prostate",
  "samples_base_path": "/work/david-gladys/all-prostate",

  "controls": {
    "label": "healthy",
    "groups": [
      { "label": "healthy", "sample_paths": ["configs/healthy-hardik.csv"] }
    ]
  },
  "diseases": {
    "label": "cancer",
    "groups": [
      { "label": "pca1-1", "sample_paths": ["configs/pca1-1.csv"] },
      { "label": "pca1-2", "sample_paths": ["configs/pca1-2.csv"] },
      { "label": "pca1-3", "sample_paths": ["configs/pca1-3.csv"] }
    ]
  },
  "comparisons": [
    { "control_group": "healthy", "disease_group": "pca1-1" },
    { "control_group": "healthy", "disease_group": "pca1-2" },
    { "control_group": "healthy", "disease_group": "pca1-3" }
  ],

  "chromosomes": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "X", "Y"],
  "contexts": ["CG"],
  "path_remap": { "/home/dizada/data": "/work/david-gladys/all-prostate/samples" },

  "step_config": {
    "centroid": { ... },
    "detection": { ... },
    "mapper": { ... },
    "enricher": { ... },
    "classifier": { ... },
    "validator": { ... }
  }
}
```

- **controls.label** / **diseases.label** are used in paths as the “side” name (e.g. disease side → `cancer`).
- **comparisons** define one run per pair: e.g. healthy vs pca1-1, healthy vs pca1-2, healthy vs pca1-3. Each comparison gets its own detection, mapper, enricher, classifier, and validator outputs.

---

## 3. Path convention: project root and step directories

- **Project root:** `{output_base}/{project_name}`  
  Example: `/work/david-gladys/all-prostate/PCa1_3levels_vs_Healthy_Hardik`

- **Step directories** follow one of two patterns:
  - **Control (centroids only):** `centroids/controls/<controls.label>/<group.label>`  
    Example: `centroids/controls/healthy/healthy`
  - **Disease / comparisons:** `<step>/<diseases.label>/<disease_group.label>`  
    Example: `detection/cancer/pca1-1`, `mapper/cancer/pca1-2`, `classifier/cancer/pca1-3`, `validator/cancer/pca1-1`

So the pattern is **`<pipeline_step>/<disease_label>/<disease_group>`** for detection, mapper, enricher, classifier, and validator. The **disease_label** comes from `diseases.label` (e.g. `"cancer"`); the **disease_group** is the comparison’s disease group (e.g. `pca1-1`).

### 3.1 Full directory tree (example project)

With `output_base = /work/david-gladys/all-prostate` and `project_name = PCa1_3levels_vs_Healthy_Hardik`:

```
/work/david-gladys/all-prostate/PCa1_3levels_vs_Healthy_Hardik/
├── centroids/
│   ├── controls/
│   │   └── healthy/
│   │       └── healthy/              ← control centroid (e.g. 1-CG.h5, 2-CG.h5, …)
│   └── diseases/
│       └── cancer/
│           ├── pca1-1/
│           ├── pca1-2/
│           └── pca1-3/
│
├── detection/
│   └── cancer/
│       ├── pca1-1/                   ← DMPs, classifier-*.pkl (per chrom), etc.
│       ├── pca1-2/
│       └── pca1-3/
│
├── mapper/
│   └── cancer/
│       ├── pca1-1/                   ← all-gene_name-combined.csv, feature CSVs
│       ├── pca1-2/
│       └── pca1-3/
│
├── enricher/
│   └── cancer/
│       ├── pca1-1/
│       ├── pca1-2/
│       └── pca1-3/
│
├── classifier/
│   └── cancer/
│       ├── pca1-1/                   ← classification_results.csv, optional *-classifier.pkl
│       ├── pca1-2/
│       └── pca1-3/
│
├── validator/
│   └── cancer/
│       ├── pca1-1/                   ← validation_metrics.json, predictions.csv
│       ├── pca1-2/
│       └── pca1-3/
│
└── alignment_qc/                     ← optional; one JSON per sample
```

### 3.2 How each step uses these paths

| Step | Reads from | Writes to |
|------|------------|-----------|
| **Centroid** | — | `centroids/controls/<control.label>/<group>` and `centroids/diseases/<disease.label>/<group>` |
| **Detection** | Centroid dirs for control + disease group | `detection/<disease.label>/<group>` (e.g. `detection/cancer/pca1-1`) |
| **Mapper** | `detection/<disease.label>/<group>` (DMP CSVs) | `mapper/<disease.label>/<group>` |
| **Enricher** | `mapper/<disease.label>/<group>/all-gene_name-combined.csv` | `enricher/<disease.label>/<group>` |
| **Classifier** | `detection/<disease.label>/<group>` (classifier-*.pkl) or full pkl under `classifier/...` | `classifier/<disease.label>/<group>/classification_results.csv` (and optional saved pkl) |
| **Validator** | Full classifier pkl in `classifier/<disease.label>/<group>/` or fallback `detection/<disease.label>/<group>/` | `validator/<disease.label>/<group>/` |

---

## 4. Sample lists and path resolution

- **sample_paths** in each group can be:
  - Directories (sample dirs containing e.g. `*-CG.h5`).
  - Paths to **files** that list samples: one path per line, or a CSV with a path/sample column, or a JSON array. Paths can be absolute or relative.
- **samples_base_path**: when set, entries in those files can be **sample names or relative paths**; they are resolved against `samples_base_path` (e.g. each line is `samples_base_path + "/" + line`).
- **path_remap**: after resolving paths, any prefix that matches a key in `path_remap` is replaced by the corresponding value (longest match wins). Use this when data has moved (e.g. from a local disk to a NAS).

Example: `sample_paths`: `["configs/healthy-hardik.csv"]` with `samples_base_path`: `"/work/david-gladys/all-prostate"` and a CSV that lists sample folder names. Each name is resolved to `{samples_base_path}/{name}`; then `path_remap` is applied if applicable.

---

## 5. Per-step configuration: `step_config`

The project can define **defaults per pipeline step** under `step_config`. Keys are step names: `centroid`, `detection`, `mapper`, `enricher`, `classifier`, `validator`, `alignment_qc`. Each value is a JSON object merged into that step’s config when running with `--project`.

**Resolution order:** project-derived paths + `step_config[step]` → `--step-override` file → CLI arguments (later overrides earlier).

### 5.1 Example from project_PCa1_3levels_vs_Healthy_Hardik.json

- **centroid:** `base_config` (min_coverage, use_gpu, …), `parallel_combinations`, `continue_on_error`, `save_batch_summary`.
- **detection:** `alpha`, `optimize_dmps`, `validation_mode`, `target_balanced_accuracy`, `min_delta_mean`, `max_overlap`, `min_effect_size`, `optimization_method`, `export_sample_size_estimate`, `random_state`, `min_N_pct`.
- **mapper:** `csv_pattern`, `gtf`, `disease_term`, `enrich_disease`, `enrich_source`, `enrich_profile`, `optimize_dmps`, and optionally API keys (or via env / step-override).
- **enricher:** `gene_column`, `disease_only`, `disease_association_type`, `min_disease_evidence_level`, `min_disease_score`, `min_dmp_count`, `max_gene_q_value`, `sort_by`, `top`, `cutoff`, `organism`, `libraries`.
- **classifier:** `weight_method`, `weight_fit_*`, `temperature`, `enable_platt_calibration`, `trimmed_percentile_*`, `chromosome_weights`, `project_name`, `save_classifier_path`, `debug`, `log_level`.
- **validator:** e.g. `debug`.

Step-specific options (e.g. mapper’s `gtf`, classifier’s `save_classifier_path`) are documented in each package. When using `--project`, these come from `step_config` unless overridden by `--step-override` or CLI.

---

## 6. Running the pipeline with the unified config

All commands use the **same project file**. With control/disease + comparisons, detection, mapper, enricher, classifier, and validator run **once per comparison** (no need to pass `--per-cancer-group` for classifier/validator; it is implied).

### 6.1 Typical workflow

```bash
# 1) Centroids for all groups (control + disease groups)
methyl-centroid --project configs/project_PCa1_3levels_vs_Healthy_Hardik.json --group all

# 2) Detection: one run per comparison (healthy vs pca1-1, healthy vs pca1-2, healthy vs pca1-3)
methyl-detector --project configs/project_PCa1_3levels_vs_Healthy_Hardik.json --per-cancer-group

# 3) Mapper: one run per comparison
methyl-mapper --project configs/project_PCa1_3levels_vs_Healthy_Hardik.json

# 4) Enricher: one run per comparison
methyl-enricher --project configs/project_PCa1_3levels_vs_Healthy_Hardik.json

# 5) Classifier: one run per comparison (reads from detection/cancer/<group>, writes to classifier/cancer/<group>)
methyl-classifier --project configs/project_PCa1_3levels_vs_Healthy_Hardik.json

# 6) Validator: one run per comparison (reads full classifier from classifier/... or detection/...)
methyl-validator --project configs/project_PCa1_3levels_vs_Healthy_Hardik.json
```

### 6.2 Overriding without editing the project file

- **Step override file:**  
  `--step-override path/to/overrides.json` — merged over `step_config` for that step (e.g. different `gtf` or `save_classifier_path` for one run).
- **CLI flags** — tool-specific options (e.g. `--gtf`, `--output-dir`) override project and step-override when provided.

---

## 7. Comparisons in detail

- **comparisons** is a list of objects: `{ "control_group": "<label>", "disease_group": "<label>" }`. Optional: `"comparison_label": "<label>"` (defaults to `disease_group` for output dirs).
- Each comparison is one **control group** vs one **disease group**. Labels must exist in `controls.groups` and `diseases.groups`.
- Shorthand (if supported by loader): set `comparisons` to the string `"control_vs_each_disease"` to auto-generate one comparison per disease group with the first control group; or `"all_pairs"` for every control × disease pair.

Example with three disease groups and one control group:

```json
"comparisons": [
  { "control_group": "healthy", "disease_group": "pca1-1" },
  { "control_group": "healthy", "disease_group": "pca1-2" },
  { "control_group": "healthy", "disease_group": "pca1-3" }
]
```

Outputs are then under `detection/cancer/pca1-1`, `detection/cancer/pca1-2`, `detection/cancer/pca1-3`, and similarly for mapper, enricher, classifier, and validator.

---

## 8. References

- **Schema and path helpers:** `methyl_utils.pipeline_config.ProjectConfig`, `DerivedPaths`, `get_project_root()`, `get_detection_output_dir(comparison_label)`, `get_classifier_output_dir(comparison_label)`, etc. Load with `methyl_utils.load_project(project_path)`.
- **Config examples:** `configs/README.md`, `configs/project_PCa1_3levels_vs_Healthy_Hardik.json`.
- **Workflow and operations:** `docs/OPERATIONS_MANUAL.md`, `docs/UNIFIED_PROJECT_CONFIG.md`.
- **Architecture:** `docs/ARCHITECTURE.md`.
