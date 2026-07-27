---
name: Fix tabular ALR routing
overview: Fix MonteCarloConfig so covariate composition / ALR settings resolve from the active backend (tabular/generative/ecdf), not always from ecdf.params — the bug that left RF/LR cell fractions as raw simplex columns.

> **Status: IMPLEMENTED.** Composition/ALR keys resolve from the active backend; regression tests pass; prostate tabular RF+ALR archived at `tabular_sklearn_RF`, LR+ALR re-run in progress (`/tmp/model_mc_tabular_lr_alr_20260726.log`) with `alr_*_vs_Neu` confirmed on `run_0001`.

azure_devops:
  type: Feature
  title: "Fix tabular ALR routing"
  work_item_id: null
  epic_id: 413
todos:
  - id: fix-resolve-attr
    content: Route covariate_composition_* via active model_backend in MonteCarloConfig._resolve_runtime_backend_attr
    status: completed
  - id: add-regression-test
    content: "Add tests: tabular/generative composition groups resolve; ecdf path unchanged"
    status: completed
  - id: run-pytest
    content: Run methylvalidation composition/backend profile tests in .venv
    status: completed
  - id: promo-plan
    content: Promote approved plan to docs/plans/fix-tabular-alr-routing.plan.md
    status: completed
  - id: operator-rerun
    content: "After fix: archive + force-rerun prostate tabular RF and LR; confirm alr_* features in metadata"
    status: completed
---

# Fix ALR routing for tabular (and generative) backends

## Problem

[`MonteCarloConfig._resolve_runtime_backend_attr`](../../packages/methylvalidation/methyl_validation/config.py) hardwires all `covariate_composition_*` keys to **`backend_profiles.ecdf.params`**.

[`trainer_api.py`](../../packages/methylvalidation/methyl_validation/trainer_api.py) passes `config.covariate_composition_groups` into `train_tabular_model`. For tabular RF/LR runs, ecdf params omit those groups → empty composition → raw `CD8T`…`Neu` (sum-to-1), even when ALR is correctly declared under `tabular_sklearn.params`.

Docs already require ALR for all covariate-consuming backends ([`USAGE.md`](../../packages/methylvalidation/docs/USAGE.md) § composition groups).

```mermaid
flowchart LR
  ctx["Context tabular_sklearn.params.covariate_composition_groups"]
  getattr["config.covariate_composition_groups"]
  ecdf["ecdf.params empty"]
  tab["tabular params ALR groups"]
  train["train_tabular_model"]
  ctx --> tab
  getattr -->|"bug: always ecdf"| ecdf
  ecdf --> train
  tab -.->|"should"| getattr
```

## Fix (code)

In [`packages/methylvalidation/methyl_validation/config.py`](../../packages/methylvalidation/methyl_validation/config.py) `_resolve_runtime_backend_attr`:

- Keep **ECDF-only** keys on the ecdf branch: `ecdf_second_stage_*`, `ecdf_aggregated_*`.
- **Remove** from that branch: `covariate_composition_transform`, `covariate_composition_columns`, `covariate_composition_reference`, `covariate_composition_pseudocount`, `covariate_composition_groups`.
- Those five then fall through to `get_backend_params(self.model_backend)` (same path as `covariates_path`).

No change needed in `tabular_backend` / preprocessor ALR math — they already work when groups are passed.

ECDF second stage stays correct: with `model_backend="ecdf"` (via `with_backend_selection`), composition groups still resolve from ecdf params.

## Tests

Add a focused regression in [`packages/methylvalidation/tests/test_backend_profiles_strict.py`](../../packages/methylvalidation/tests/test_backend_profiles_strict.py):

1. Build `MonteCarloConfig` with composition groups **only** on `tabular_sklearn.params` (ecdf groups `null`/absent).
2. `cfg.with_backend_selection("tabular_sklearn").covariate_composition_groups` returns the tabular groups (non-empty; columns/reference match).
3. Same pattern for `generative_hybrid`.
4. `with_backend_selection("ecdf")` still reads ecdf’s groups when set (no regression for second stage).

Run: `source .venv/bin/activate && pytest packages/methylvalidation/tests/test_backend_profiles_strict.py packages/methylvalidation/tests/test_composition_groups.py -q`

## Operator follow-up (after code lands)

Re-run prostate tabular with existing LR/RF contexts (ALR already declared) so artifacts show `alr_*_vs_Neu` (5 cov features + 4 gene_scored). Archive current `model_mc/tabular_sklearn` / `tabular_sklearn_RF` first; use stock `validation_model_mc_rebuild.program.json` + `--force-rerun`.
