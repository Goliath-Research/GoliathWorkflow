---
name: Unified Model-MC Partitions
overview: Make every model-MC backend (ECDF, tabular_sklearn, generative_hybrid) train and score on the same shared-run partitions via one resolver contract, so holdout validation and cross-backend ranking stay comparable.

> **Status: IMPLEMENTED.** All model-MC backends score `test_groups.json` via `evaluation_partition` and fail closed without `test_metrics.json`.

azure_devops:
  type: Feature
  title: "Unified Model-MC Partitions"
  work_item_id: null
  epic_id: 413
todos:
  - id: predict-partition-api
    content: Add evaluation_partition to tabular + generative predict; write train_/test_ metrics like gene ECDF
    status: completed
    work_item_id: null
  - id: trainer-orchestration
    content: Dual train+test predict for tabular/generative; route classic ECDF through shared resolver; clean second-stage duplicate resolver
    status: completed
    work_item_id: null
  - id: fail-closed-all-backends
    content: Require test_metrics.json / model_test for all model-MC backends in cli (+ pipeline_runner parity)
    status: completed
    work_item_id: null
  - id: train-membership-assert
    content: "Fail-closed check: fit samples == shared train CSVs and disjoint from test_groups.json"
    status: completed
    work_item_id: null
  - id: tests-docs-plan
    content: Regression tests, IMPLEMENTATION/usage notes, promote plan under AB#413
    status: completed
    work_item_id: null
---

# Unified Model-MC Train/Test Partitions

## Problem

[`model-mc-train-test.plan.md`](model-mc-train-test.plan.md) marked ECDF holdout scoring done, but **tabular** and **generative** never adopted it. Shared splits exist under `model_mc/shared/run_XXXX/` and are copied into each backend tree; only gene/aggregated ECDF scored them via `evaluation_partition="test"` → `test_groups.json`. Tabular/generative called predict once with no partition, so `resolve_predictor_config` filled misnamed `test_*` with **train** cohorts while the real holdout sat unused in `test_groups.json`. Model-MC fail-closed guards were `backend == "ecdf"` only.

## Canonical contract

| Role | Source of truth | Used for |
|------|-----------------|----------|
| Train | `project.get_resolved_groups()` ← `train_control.csv` / `train_disease.csv` | Fit + optional train diagnostics |
| Test / holdout | `test_groups.json` | Reported model-MC metrics |

Every backend predict goes through `resolve_eval_paths_and_labels(..., evaluation_partition in {train,test})`. Artifacts: `train_metrics.json` / `test_metrics.json` (aliases `validation_metrics.json` / `predictions.csv` → test only).

## Implementation summary

- Tabular + generative: `evaluation_partition` API, dual score in `trainer_api`, train membership assert.
- Classic ECDF: partition paths from shared resolver (`test_groups.json`), not a separate CSV-only codepath.
- CLI: require `test_metrics.json` / `metrics_source=model_test` for **all** backends.
- Docs: IMPLEMENTATION.md, usage ch.07; follow-up from model-mc-train-test.
