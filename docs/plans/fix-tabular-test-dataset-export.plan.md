---
name: Fix tabular test dataset export
overview: Confirm generative_hybrid already uses the correct holdout partition for test Parquet; fix tabular’s train-time export that still resolved “test” from misnamed predictor paths instead of test_groups.json.

> **Status: IMPLEMENTED.** Tabular train-time `test_dataset.parquet` uses `evaluation_partition="test"` → `test_groups.json` only; zero train/test sample overlap enforced; regression test covers misnamed predictor `test_*` paths.

azure_devops:
  type: Feature
  title: "Fix tabular test_dataset export (test_groups.json)"
  work_item_id: null
  epic_id: 413
todos:
  - id: fix-tabular-export
    content: Pass evaluation_partition="test" in tabular train-time test export; gate on test_groups.json; fail closed; assert no train/test ID overlap
    status: completed
    work_item_id: null
  - id: regression-test
    content: Add tabular fixture where predictor test_* == train paths but test_groups.json is holdout; assert Parquet uses holdout
    status: completed
    work_item_id: null
  - id: docs-promo
    content: Document partition contract; promote plan to docs/plans/ on implement
    status: completed
    work_item_id: null
  - id: operator-rerun
    content: Note operator force-rerun for existing bad tabular model_bundle Parquets
    status: completed
    work_item_id: null
---

# Fix tabular test_dataset export (generative already correct)

## Generative hybrid verification

**Verdict: generative_hybrid is not affected by this bug.** Train writes only `train_dataset.parquet`; test Parquet is written during predict with `evaluation_partition="test"` → `test_groups.json`.

## Root cause (tabular only)

Train-time export called `resolve_eval_paths_and_labels` without `evaluation_partition="test"`, gated by `_has_explicit_eval_split` on misnamed predictor `test_*` paths (often the train cohort). Scoring already used the correct partition; bundle Parquet did not.

## Fix delivered

1. [`tabular_backend.py`](../../packages/methylvalidation/methyl_validation/tabular_backend.py): `save_test_dataset` → `evaluation_partition="test"`; removed `_has_explicit_eval_split` gate; fail closed without `test_groups.json`; raise on train/test `sample_id` overlap.
2. Regression in [`test_model_bundle_tabular_backend.py`](../../packages/methylvalidation/tests/test_model_bundle_tabular_backend.py).
3. Docs: [`docs/usage/07-stage-model.qmd`](../usage/07-stage-model.md), [`IMPLEMENTATION.md`](../../packages/methylvalidation/docs/IMPLEMENTATION.md).

## Operator follow-up

Re-run tabular Model-MC with `--force-rerun` so existing bad `test_dataset.parquet` files are rewritten (e.g. prostate `Healthy_vs_PCa_low_ecdf_covariates` tabular runs). Example:

```bash
source .venv/bin/activate
methyl-workflow-run \
  --program workflow_engine/domain/fixtures/validation_model_mc_rebuild.program.json \
  --context-file /work/projects/prostate-cancer/configs/context_Healthy_vs_PCa_low_ecdf_covariates_model_mc_tabular.json \
  --parallel-workers 1 --force-rerun -v
```

After re-run, `model_bundle/test_dataset.parquet` row count must match holdout (`test_groups.json`), not train.
