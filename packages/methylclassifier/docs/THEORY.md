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

- **Principled**: binary ECDF log-likelihood scoring with optional calibration.
- **Approximate**: chromosome fusion inherits the assumptions of its component binary models.
- **Heuristic**: OvR fusion, geometric-mean control aggregation, and some multiclass reductions.

## Key Point

The binary head is the cleanest part of the model. Multiclass and multi-chromosome behavior is an engineered ensemble on top of that binary core, not one unified generative model.

## Key Code Paths

- `methyl_classifier/core/classifier.py`
- `methyl_classifier/core/multiclass_ovr.py`
- `methyl_utils/ecdf_classifier.py`
