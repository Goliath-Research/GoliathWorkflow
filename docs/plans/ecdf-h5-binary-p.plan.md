---
name: ECDF H5 binary-p
overview: Replace model_bundle design-matrix Parquet exports with float32 HDF5 across ECDF/tabular/generative, and encode 2-part simplices as the non-reference probability p (keep ALR only for K>2), so stacker features and exports are inspectable and dtype-consistent with the rest of the pipeline.

> **Status: IMPLEMENTED.** Canonical `train_dataset.h5` / `test_dataset.h5` (float32) via `model_datasets.py`; binary simplices use closed non-reference \(p\); ALR only for \(K>2\). Supersedes Parquet wording in [`unify-model-bundle-datasets.plan.md`](unify-model-bundle-datasets.plan.md).

azure_devops:
  type: Feature
  title: "ECDF design matrices HDF5 float32 + binary raw p"
  work_item_id: null
  epic_id: 413
todos:
  - id: h5-writer
    content: Implement float32 HDF5 write/read in model_datasets.py; rename train/test to .h5; parquet read-compat; update sidecars/manifest
    status: completed
    work_item_id: null
  - id: binary-p
    content: Add _simplex_encode (k=2 → raw p; k>2 → ALR); wire fit_covariates and ecdf _probability_design; drop binary epsilon requirement
    status: completed
    work_item_id: null
  - id: callers-dtypes
    content: Remove ECDF export float64 upcast; ensure tabular/generative paths emit .h5 float32 via shared writer
    status: completed
    work_item_id: null
  - id: tests
    content: Update/add tests for binary p, multi ALR, and .h5 datasets; run targeted pytest in .venv
    status: completed
    work_item_id: null
  - id: docs-plan
    content: Update usage/theory/IMPLEMENTATION; promote docs/plans/ecdf-h5-binary-p.plan.md + README row; note unify-model-bundle-datasets supersession
    status: completed
    work_item_id: null
---

# ECDF design matrices: HDF5 float32 + binary raw p

## Decisions (confirmed)

1. **Format:** All `model_bundle` design matrices (ECDF second-stage, tabular, generative) move from Parquet → **HDF5**, with continuous feature columns forced to **`float32`** (match `model_feature_bundle.h5` / sample H5).
2. **Binary simplex:** For any 2-part composition (ECDF `prob_class*` or declared covariate groups with exactly two columns), use the **non-reference closed probability \(p\)** in the design matrix and exports. **ALR remains only when \(K>2\)**.

## 1. Canonical dataset I/O (HDF5 float32)

Update [`packages/methylvalidation/methyl_validation/model_datasets.py`](../../packages/methylvalidation/methyl_validation/model_datasets.py):

- Rename constants: `train_dataset.h5` / `test_dataset.h5` (keep `dataset_manifest.json`).
- `write_dataset_frame`: write HDF5 via `h5py`:
  - identity: `sample_id` (utf-8/string), `class_index` (`int32`), `class_label` (string)
  - every numeric feature column: **`np.float32`**
  - store `feature_names` dataset for column order
- `read_dataset_frame`: read `.h5`; **compat**: still read legacy `.parquet` (and csv/tsv).
- `dataset_sidecar_meta_path`: `.h5.meta.json` (tabular cache fingerprint).

Callers already go through this helper (`ecdf_second_stage.py`, `tabular_backend.py`, `generative_backend.py`).

```mermaid
flowchart LR
  backends["ECDF / tabular / generative"] --> writer["write_dataset_frame"]
  writer --> h5["train_dataset.h5 / test_dataset.h5 float32"]
  writer --> man["dataset_manifest.json"]
  reader["read_dataset_frame"] --> h5
  reader -.->|"compat"| pq["legacy .parquet"]
```

## 2. Binary raw p; ALR only for K>2

### Shared transform helper

In [`covariate_preprocessor.py`](../../packages/methylvalidation/methyl_validation/covariate_preprocessor.py):

- `_simplex_encode`: \(K=2\) → `p_<nonref>`; \(K>2\) → ALR (`ε` required).
- `fit_covariates` / `transform_covariates` use `_simplex_encode`.

### ECDF class probabilities

In [`ecdf_second_stage._probability_design`](../../packages/methylvalidation/methyl_validation/ecdf_second_stage.py):

- Binary: stack/export `prob_class1` (closed \(p\)); epsilon not required.
- Multiclass: ALR + required epsilon.
- Legacy `logit_class1` means default simplex encode.

## 3. Tests

- Composition groups, ECDF second-stage covariates, model_datasets HDF5 + legacy parquet, tabular/generative path assertions.

## 4. Docs

- Usage ch.07, theory ch.15, methylvalidation USAGE/IMPLEMENTATION.
- Supersession note on [`unify-model-bundle-datasets.plan.md`](unify-model-bundle-datasets.plan.md).

## 5. Operator note

- Existing on-disk `train_dataset.parquet`: reader compat only; re-run Model-MC / `--force-rerun` for `.h5` + binary-\(p\) features.
- No change to `model_feature_bundle.h5` DMP schema.

## Key files

- `packages/methylvalidation/methyl_validation/model_datasets.py`
- `packages/methylvalidation/methyl_validation/covariate_preprocessor.py`
- `packages/methylvalidation/methyl_validation/ecdf_second_stage.py`
- Tabular/generative backends (path constants via shared helper)
