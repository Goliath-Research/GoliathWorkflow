---
name: Model MC Train Test
overview: Correct model-MC so each iteration fits on its training partition and evaluates only on its disjoint test partition, while introducing unambiguous train/test artifact names with compatibility aliases.

> **Status: IMPLEMENTED for ECDF.** Tabular/generative holdout parity is completed in [`unified-model-mc-partitions.plan.md`](unified-model-mc-partitions.plan.md).

azure_devops:
  type: Feature
  title: "Model MC Train Test"
  work_item_id: null
  epic_id: 413
todos:
  - id: bind-test-partition
    content: Create canonical test split artifacts, propagate explicit test groups, and enforce disjoint fail-closed evaluation.
    status: completed
    work_item_id: null
  - id: separate-ecdf-phases
    content: Separate ECDF and covariate-stack training from test application and emit clear train/test artifacts.
    status: completed
    work_item_id: null
  - id: aggregate-test-only
    content: Migrate model-MC metric consumers and ranking to test metrics with compatibility fallbacks.
    status: completed
    work_item_id: null
  - id: verify-document
    content: Add regression coverage, verify contracts, document semantics, and promote the plan.
    status: completed
    work_item_id: null
---

# Model-MC Train/Test Evaluation

## Correct the evaluation boundary
- In [`project_gen.py`](../../packages/methylvalidation/methyl_validation/project_gen.py), make `test_control.csv`, `test_disease.csv`, and `test_groups.json` the canonical per-run holdout artifacts; continue writing `val_control.csv`, `val_disease.csv`, and `val_test_groups.json` as compatibility aliases.
- Propagate the explicit test-group manifest through backend preparation and prediction. Model-MC evaluation must fail closed when test groups are absent instead of falling back to project training groups.
- Enforce non-empty, disjoint train/test sets and exact test prediction membership. Counts remain data-driven, never hardcoded.

## Separate ECDF training from test scoring
- Fit raw-gene or aggregated ECDF models and the covariate stacker on training samples, then apply frozen models and preprocessors to test samples only.
- Emit `train_predictions.csv`, `train_metrics.json`, `test_predictions.csv`, and `test_metrics.json`, including partition and sample-count provenance.
- Preserve `predictions.csv` and `validation_metrics.json` as deprecated aliases to the test artifacts.

## Aggregate only test performance
- Prefer `test_metrics.json` and `test_predictions.csv`, retaining legacy fallback only for older completed runs.
- Source `all_metrics.csv`, `metrics_summary.json`, backend ranking, and reported model-MC accuracy exclusively from test metrics.
- Carry canonical `test*` fields through typed domain and worker contracts while retaining deprecated `val*` aliases.

## Regression tests and operator contract
- Cover disjoint partition bindings, separated ECDF/covariate phases, fail-closed missing test bindings, canonical and compatibility artifacts, and test-only metric aggregation.
- Regenerate committed schemas and document the artifact layout and metric semantics.
