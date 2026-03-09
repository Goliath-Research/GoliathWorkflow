---
name: ECDF-only centroid comparison
overview: Remove all non-ECDF distribution paths (Beta, Normal, Beta-Mixture) from MethylCentroidPair and MethylDetector, leaving a single unconditional ECDF-based comparison pipeline. Alpha/beta parameters must remain in the output because BetaClassifier and EAT consume them downstream.
todos: []
isProject: false
---

# ECDF-Only Centroid Comparison

## What is kept

- `alpha1/beta1/alpha2/beta2` in `