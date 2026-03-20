# MethylUtils Theoretical Foundation

The canonical mathematical and statistical reference for this package is the Quarto chapter [`docs/theory/chapters/01-methylutils.qmd`](../../../docs/theory/chapters/01-methylutils.qmd).

## Scope

`methylutils` is the shared mathematical layer for:

- centroid sufficient statistics,
- ECDF reconstruction from histogram counts,
- KS and histogram-based Mann-Whitney testing,
- Storey q-values and p-value aggregation,
- ECDF overlap and canonical effect-size ranking,
- ECDF-based classification scores.

## Method Status

- **Principled**: centroid moment calculations, Storey q-values, standard asymptotic testing, weighted ECDF log-likelihood scoring.
- **Approximate**: grid-based KS, overlap integration, histogram-reconstructed Mann-Whitney.
- **Heuristic**: biological effect-size ranking and some numerical stabilizers.
- **Auxiliary**: beta-based metrics remain available for downstream consumers such as clustering, but they are not the canonical detector-classifier path.

## Key Code Paths

- `methyl_utils/core/distribution_views.py`
- `methyl_utils/core/centroid_builder.py`
- `methyl_utils/statistical_tests.py`
- `methyl_utils/methyl_centroid_pair.py`
- `methyl_utils/ecdf_classifier.py`
