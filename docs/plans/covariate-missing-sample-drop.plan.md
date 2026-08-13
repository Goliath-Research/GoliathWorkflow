---
name: Covariate missing sample drop
overview: When some samples lack covariate rows, warn and continue the covariate-using stage on the intersection instead of skipping second-stage or failing the whole run. Keep fail-fast as an explicit operator choice.

> **Status: IMPLEMENTED.** `covariates_missing_samples: drop` excludes missing IDs, warns, and continues; enabled ECDF second-stage errors now fail the step.

azure_devops:
  type: Feature
  title: "Covariate missing-sample drop + warn"
  work_item_id: null
  epic_id: 413
todos:
  - id: join-helper
    content: Add covariates_missing_samples fail|drop resolver and kept/dropped ID helper in covariate_preprocessor.py
    status: completed
    work_item_id: null
  - id: ecdf-subset
    content: Subset ECDF second-stage train/test to kept IDs; persist drop warning + counts in reports/metrics
    status: completed
    work_item_id: null
  - id: tabular-gen
    content: Apply the same drop+warn helper in tabular_backend and generative_backend
    status: completed
    work_item_id: null
  - id: no-swallow
    content: Stop swallowing enabled second-stage exceptions in trainer_api.py
    status: completed
    work_item_id: null
  - id: schema-tests-docs
    content: Export schemas, add drop/fail/trainer tests, document the key; set drop on Exp_6_vs_7 contexts
    status: completed
    work_item_id: null
---

# Drop missing-covariate samples and warn

> **Status: IMPLEMENTED.**

Operator-enabled ECDF second-stage used to skip the whole stacker when any sample ID was missing from the covariates sidecar. `covariates_missing_samples: "drop"` now excludes those IDs, warns, and continues on the intersection. `fail` / unset + `covariates_strict_join` still raise. Enabled second-stage exceptions fail the step (no silent first-stage-only success).
