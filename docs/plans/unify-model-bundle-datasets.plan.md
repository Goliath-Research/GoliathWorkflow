---
name: Unify Model Bundle Datasets
overview: Always write flat Parquet train/test design matrices under each run’s isolated `model_bundle/` (`train_dataset.parquet`, `test_dataset.parquet`, plus a small manifest) for tabular, ECDF second-stage, and generative backends—replacing the current CSV/Parquet split and tabular-prefixed filenames.

> **Status: IMPLEMENTED (Parquet era).** Flat train/test design matrices + `dataset_manifest.json` under each backend run’s `model_bundle/`; shared helper in `packages/methylvalidation/methyl_validation/model_datasets.py`. **Superseded for on-disk format:** [`ecdf-h5-binary-p.plan.md`](ecdf-h5-binary-p.plan.md) moves canonical artifacts to `train_dataset.h5` / `test_dataset.h5` (float32) and binary raw \(p\) (ALR only for \(K>2\)). Legacy `.parquet` remains readable for migration.

azure_devops:
  type: Feature
  title: "Unify model_bundle train/test datasets (Parquet)"
  work_item_id: null
  epic_id: 413
todos:
  - id: shared-writer
    content: "Add model_datasets.py: Parquet I/O, flat paths, identity schema, dataset_manifest.json"
    status: completed
    work_item_id: null
  - id: tabular-rename
    content: Point tabular defaults/cache at train_dataset.parquet / test_dataset.parquet; update meta + error strings
    status: completed
    work_item_id: null
  - id: ecdf-parquet
    content: "ECDF second stage: flat Parquet + aligned identity columns; auto-set model_bundle_dir for ecdf in model-MC CLI"
    status: completed
    work_item_id: null
  - id: generative-export
    content: Export generative train/test Parquet + manifest from fitted/eval matrices
    status: completed
    work_item_id: null
  - id: tests-docs
    content: Update ECDF/tabular/generative tests and docs citing old CSV/tabular_* paths; run targeted pytest
    status: completed
    work_item_id: null
---

# Unify model_bundle train/test datasets (Option A + Parquet)

## Locked decisions

- **Layout (Option A):** flat under the run’s already-isolated bundle:
  - `model_bundle/train_dataset.parquet`
  - `model_bundle/test_dataset.parquet` (omit only when no test split exists)
  - `model_bundle/dataset_manifest.json`
- **Format:** Parquet only (shared writer in [`model_datasets.py`](../../packages/methylvalidation/methyl_validation/model_datasets.py)).
- **Legacy paths:** replace only — no `tabular_train_dataset.parquet` / `second_stage/*.csv`.
- **Always save** for research; tabular reuse/cache keys off the new filenames.

## Shared contract

Identity columns: `sample_id`, `class_index`, `class_label`, then backend-specific features.

## Backend wiring

- Tabular: defaults to `train_dataset.parquet` / `test_dataset.parquet`; writes `dataset_manifest.json`.
- ECDF second stage: flat Parquet under `model_bundle/`; model-MC CLI auto-sets `model_bundle_dir` for `ecdf`.
- Generative: exports train (and test on predict) Parquet + manifest.

## Tests / docs

- Updated ECDF, tabular, and generative tests; docs in `IMPLEMENTATION.md` and `docs/usage/07-stage-model.qmd`.
