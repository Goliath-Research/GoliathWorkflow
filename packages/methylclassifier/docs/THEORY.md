# MethylClassifier Theoretical Foundation

The canonical mathematical and statistical reference for this package is the Quarto chapter [`docs/theory/chapters/04-methylclassifier.qmd`](../../../docs/theory/chapters/04-methylclassifier.qmd).

## Scope

`methylclassifier` applies one or more binary ECDF classifiers to new samples and supports:

- binary classification,
- chromosome-weighted multi-chromosome classification,
- one-vs-rest multiclass fusion,
- pairwise control aggregation and bipartite aggregation,
- optional probability calibration.

## Method Status

- **Principled**: binary ECDF density scoring with explicit class priors (`p(X|c) * p(c)`), optional dependence-aware block aggregation, and optional calibration.
- **Approximate**: chromosome fusion inherits the assumptions of its component binary models.
- **Heuristic / Versioned**: OvR fusion and geometric-mean control aggregation remain engineered reductions, but are now versioned via `ovr_inference_version` + `ovr_fuse_mode` metadata for reproducible interpretation.

## Key Point

The binary head is the cleanest part of the model and now has an explicit posterior contract:

- feature densities from ECDF/PCHIP per class,
- weighted log-likelihood aggregation,
- explicit class priors,
- optional post-hoc calibration.

Multiclass and multi-chromosome behavior remain an engineered ensemble on top of that core; inference semantics are explicitly versioned in package metadata.

## Key Code Paths

- `methyl_classifier/core/classifier.py`
- `methyl_classifier/core/multiclass_ovr.py`
- `methyl_utils/ecdf_classifier.py`
