---
name: Independent LR Stack Features
overview: Replace redundant ECDF probability and cell-composition inputs with one clipped class-1 logit and five Neu-referenced ALR coordinates, fitted on training data and applied unchanged to test data.

> **Status: IMPLEMENTED.** The independent six-feature LR contract, persisted design matrices, schemas, tests, and documentation are complete.

azure_devops:
  type: Feature
  title: "Independent LR Stack Features"
  work_item_id: null
  epic_id: 413
todos:
  - id: typed-transform-contract
    content: Add typed probability-logit and Neu-referenced ALR configuration, including explicit zero handling.
    status: completed
    work_item_id: null
  - id: fit-apply-independent-features
    content: Fit five ALR coordinates and scaling on training data, then apply frozen transforms to test data alongside one ECDF logit.
    status: completed
    work_item_id: null
  - id: persist-exact-design-matrices
    content: Export exact six-feature train/test LR datasets and a disjointness/provenance manifest.
    status: completed
    work_item_id: null
  - id: verify-document-contract
    content: Add regression coverage, regenerate schemas, document semantics, and promote the approved plan.
    status: completed
    work_item_id: null
---

# Independent LR Stack Features

## Typed transformation contract
- Configure a clipped class-1 logit for the binary ECDF score.
- Configure additive log-ratios for `CD8T`, `CD4T`, `NK`, `Bcell`, and `Mono` relative to `Neu`, including explicit zero replacement.

## Train-only fit and frozen test application
- Learn ALR scaling parameters from training rows only.
- Persist the preprocessor and apply it unchanged to test and external samples.
- Reject invalid probability complements, non-finite values, and incomplete composition contracts.

## Exact model-input artifacts
- Save `model_bundle/second_stage/train_dataset.csv` and `test_dataset.csv` with the exact ordered six-feature LR matrix.
- Save `dataset_manifest.json` with feature order, transform parameters, sample counts, and overlap QC.
- Keep source probabilities and raw cell fractions in their existing provenance artifacts.

## Verification
- Cover zero-valued fractions, serialization, train-only fitting, frozen test transformation, feature order, and disjointness.
- Regenerate committed schemas and document the mathematical contract.
