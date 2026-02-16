# Proposal: Explicit comparisons (pairs) and implications for the pipeline

This document extends the **control / disease** config format with:

1. **Centroid layout**: Centroids for **all** groups, with folders that identify **control** vs **disease**.
2. **Comparisons**: A new top-level element that **explicitly lists which centroid pairs** to compare in detection, mapper, enricher, and classifier.
3. **Implications** for each package and for `methyl_utils`.

---

## 1. Unified config changes

### 1.1 Control / disease (recap)

- **control**: `{ "label": "caucasians", "groups": [ { "label": "healthy", "sample_paths": [...] } ] }`
- **disease**: `{ "label": "prostate cancer", "groups": [ { "label": "pca1-1", ... }, { "label": "pca1-2", ... }, ... ] }`

Group labels (e.g. `healthy`, `pca1-1`) are unique across control and disease and identify each cohort.

### 1.2 New element: `comparisons`

**Purpose:** Define exactly which **pairs** of groups (control group vs disease group) are run through detection, mapper, enricher, and classifier. Each pair is one “comparison”.

**Schema:**

```json
"comparisons": [
  { "control_group": "healthy", "disease_group": "pca1-1" },
  { "control_group": "healthy", "disease_group": "pca1-2" },
  { "control_group": "healthy", "disease_group": "pca1-3" },
  { "control_group": "healthy", "disease_group": "pca1-4" }
]
```

- **comparisons** (array, required when `control` and `disease` are used): List of objects.
- Each object:
  - **control_group** (string): Must match a `label` in `control.groups`.
  - **disease_group** (string): Must match a `label` in `disease.groups`.
  - **comparison_label** (string, optional): Name used for output folders (detection, mapper, enricher, classifier). If omitted, default = `disease_group` (current behaviour) or `"{control_group}_vs_{disease_group}"` (configurable in project or step_config).

**Shorthand (optional):**

- If `comparisons` is the string `"control_vs_each_disease"`, it expands to: for the **first** control group, one comparison per disease group. So `[ (control.groups[0].label, d.label) for d in disease.groups ]`.
- Alternative: `"all_pairs"` = all control × disease pairs (every control group vs every disease group). Useful when you have multiple control groups.

**Validation:**

- When `control` and `disease` are present, `comparisons` must be present (or the shorthand).
- Every `control_group` must be in `control.groups[*].label`; every `disease_group` in `disease.groups[*].label`.

---

## 2. Centroid layout (MethylCentroid)

**Rule:** MethylCentroid builds a centroid for **every** group in `control.groups` and `disease.groups`. No pairing at this step.

**Folder structure:** Use two top-level folders so centroids are clearly “control” vs “disease”:

```
{project_root}/centroids/
├── control/                    ← or use control.label (e.g. caucasians) if safe as path
│   ├── healthy/
│   │   ├── 1-CG.h5
│   │   └── ...
│   └── (other control groups if any)
└── disease/                   ← or use disease.label (e.g. prostate_cancer) if safe as path
    ├── pca1-1/
    ├── pca1-2/
    ├── pca1-3/
    └── pca1-4/
```

**Path convention:**

- Use literal `control` and `disease` for folder names (safe, no spaces), **or**
- Use slugified top-level labels (e.g. `caucasians`, `prostate_cancer`) from `control.label` / `disease.label` for readability. Recommend a `centroid_side_subdir` (or reuse `disease_subdir` only for disease) and default `control` / `disease` so paths are predictable.

**Implementation (methyl_utils):**

- Add e.g. `get_centroid_dir(side: "control" | "disease", group_label: str) -> str` → `{project_root}/centroids/{side}/{group_label}`.
- MethylCentroid, when using `--project` with control/disease: for each group in `control.groups` and `disease.groups`, resolve `output_dir` from this API and run centroid build (same as today per group, with `--group` or batch).

---

## 3. Downstream steps: one run per comparison

All of **MethylDetector**, **MethylMapper**, **MethylEnricher**, and **MethylClassifier** consume or produce data **per comparison**. Each comparison has:

- **Centroid 1:** `centroids/control/{control_group}` (or equivalent).
- **Centroid 2:** `centroids/disease/{disease_group}`.
- **Comparison label:** From `comparison_label` or default (e.g. `disease_group`).
- **Output dirs:** `detection/cancer/{comparison_label}`, `mapper/cancer/{comparison_label}`, `enricher/cancer/{comparison_label}`, `classifier/cancer/{comparison_label}`.

So the pipeline no longer infers “control vs each disease” from group order; it reads the explicit **comparisons** list.

---

## 4. Package-by-package implications

### 4.1 methyl_utils (pipeline_config.py)

**New or updated:**

- **ControlDiseaseSide**: already proposed (`label`, `groups`).
- **ComparisonSpec**: Pydantic model with `control_group: str`, `disease_group: str`, `comparison_label: Optional[str] = None`.
- **ProjectConfig**:
  - `comparisons: Optional[Union[List[ComparisonSpec], str]] = None`. When string, support `"control_vs_each_disease"` (and optionally `"all_pairs"`).
  - Method **get_comparisons()** → `List[ComparisonSpec]`: resolve shorthand to explicit list; validate group labels; fill default `comparison_label` (e.g. `disease_group`).
  - **get_centroid_dir(side, group_label)** → path for a single group’s centroid dir.
  - **get_resolved_groups()**: when control/disease present, return flat list of (label, paths) for **all** control and disease groups (for MethylCentroid and for any code that still expects a flat list). Optionally attach metadata (control vs disease) per group.
  - **DerivedPaths** or helpers: for a given comparison, return `centroid1_dir`, `centroid2_dir`, `comparison_label`, `detection_output_dir`, `mapper_output_dir`, etc., so packages don’t re-derive paths.

**Backward compatibility:**

- If only flat `groups` (or group1/group2) is set: no `comparisons`; existing behaviour (first group = control, rest = disease; “control vs each disease” implied). Resolved groups and derived paths stay as today.

### 4.2 MethylCentroid

- With **control/disease** config: build centroids for **all** groups in `control.groups` and `disease.groups`.
- **Output dir** for each group = `get_centroid_dir("control", label)` or `get_centroid_dir("disease", label)`.
- CLI: e.g. `--project ... --group all` (or “control_all” / “disease_all”) to build all; or by side and/or by group label. No change to per-group build logic; only how the list of groups and their output dirs are derived.

### 4.3 MethylDetector

- With **control/disease + comparisons**: for each entry in **get_comparisons()**:
  - `centroid1_dir` = centroid dir for `control_group` (e.g. `centroids/control/healthy`).
  - `centroid2_dir` = centroid dir for `disease_group` (e.g. `centroids/disease/pca1-1`).
  - `output_dir` = `detection/cancer/{comparison_label}` (e.g. `detection/cancer/pca1-1`).
- Run detection once per comparison (same as current “per-cancer-group” mode, but driven by `comparisons` instead of “first group vs each other group”).
- **Multi-class model:** Can still merge DMPs from a subset of comparisons (e.g. all disease groups vs one control) and build one multiclass model; the set of detection dirs comes from the comparison labels.

### 4.4 MethylMapper

- With **control/disease + comparisons**: for each comparison:
  - **Input:** DMP CSVs from `detection/cancer/{comparison_label}/`.
  - **Output:** `mapper/cancer/{comparison_label}/`.
- Same as current per-group behaviour; the list of “groups” is replaced by the list of **comparison_label**s from **get_comparisons()**.

### 4.5 MethylEnricher

- With **control/disease + comparisons**: for each comparison:
  - **Input:** e.g. `mapper/cancer/{comparison_label}/all-gene_name-combined.csv`.
  - **Output:** `enricher/cancer/{comparison_label}/`.
- Again, iteration is over comparisons, not over a flat “disease group” list.

### 4.6 MethylClassifier

- With **control/disease + comparisons**: for each comparison:
  - **Model / DMPs:** from `detection/cancer/{comparison_label}/`.
  - **Centroid dirs:** `centroids/control/{control_group}`, `centroids/disease/{disease_group}` (for validation/reporting).
  - **Output:** e.g. `classifier/cancer/{comparison_label}/classification_results.csv`.
- Same pattern: one run per comparison, paths derived from **get_comparisons()** and **get_centroid_dir()**.

---

## 5. Example configs

- **project_PCa1_4levels_vs_Healthy_with_comparisons.json** — Full example with control (caucasians, one group `healthy`), disease (prostate cancer, four groups `pca1-1` … `pca1-4`), and explicit **comparisons** listing the four pairs healthy–pca1-1, healthy–pca1-2, healthy–pca1-3, healthy–pca1-4.

Fragment:

```json
{
  "project_name": "PCa1_4levels_vs_Healthy",
  "output_base": "/work/data",
  "control": {
    "label": "caucasians",
    "groups": [
      { "label": "healthy", "sample_paths": ["configs/healthy.csv"] }
    ]
  },
  "disease": {
    "label": "prostate cancer",
    "groups": [
      { "label": "pca1-1", "sample_paths": ["configs/pca1-1.csv"] },
      { "label": "pca1-2", "sample_paths": ["configs/pca1-2.csv"] },
      { "label": "pca1-3", "sample_paths": ["configs/pca1-3.csv"] },
      { "label": "pca1-4", "sample_paths": ["configs/pca1-4.csv"] }
    ]
  },
  "comparisons": [
    { "control_group": "healthy", "disease_group": "pca1-1" },
    { "control_group": "healthy", "disease_group": "pca1-2" },
    { "control_group": "healthy", "disease_group": "pca1-3" },
    { "control_group": "healthy", "disease_group": "pca1-4" }
  ],
  "chromosomes": ["1", "2", "..."],
  "contexts": ["CG"],
  "step_config": { ... }
}
```

With shorthand (optional):

```json
"comparisons": "control_vs_each_disease"
```

expands to the same four pairs when there is one control group and four disease groups.

---

## 6. Summary

| Topic | Proposal |
|-------|----------|
| **Config** | Add **comparisons**: list of `{ control_group, disease_group, comparison_label? }` or shorthand `"control_vs_each_disease"` / `"all_pairs"`. |
| **Centroids** | One centroid per group; folders **centroids/control/{label}** and **centroids/disease/{label}** (or top-level labels as subdirs). |
| **Detection / Mapper / Enricher / Classifier** | One run **per comparison**; paths derived from **get_comparisons()** and **get_centroid_dir()**; output under **detection/cancer/{comparison_label}**, etc. |
| **Backward compatibility** | Flat **groups** (or group1/group2) without **comparisons** keeps current behaviour (first = control, rest = disease; implied “control vs each disease”). |

This keeps centroid creation independent of comparisons and makes downstream behaviour driven entirely by the explicit **comparisons** list.
