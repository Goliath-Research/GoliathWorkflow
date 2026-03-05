# MethylUtils Theoretical Foundation

## Role

MethylUtils is the **foundational library** of MethylPipeline. It provides data structures, project configuration, statistical models (Beta, method-of-moments), distance and effect-size metrics, centroid building, and classifier primitives. **No pipeline step runs without it**: MethylCentroid, MethylDetector, MethylClassifier, MethylPredictor, and MethylValidation all depend on MethylUtils.

## Project configuration

A single **project JSON** defines the whole workflow: sample groups, comparisons, and output layout. MethylUtils parses and validates this so downstream packages do not repeat sample paths and output structure.

- **ProjectConfig**: `project_name`, `output_base`, groups (e.g. control/disease with sub-groups), `comparisons`, optional `level_labels_path`, `subcluster`, `samples_base_path`, `step_config`.
- **load_project(path)**: Loads and validates the JSON; returns a `ProjectConfig`.
- **get_derived_paths()**: Yields paths under `{output_base}/{project_name}/` for centroids, detection, classifier, predictor, etc. Used by MethylCentroid, MethylDetector, MethylClassifier, MethylPredictor to resolve inputs and outputs from one project file.

So the “theory” of project config is: one source of truth for groups and comparisons; derived paths are computed from that, not hard-coded in each package.

## Sample and centroid types

- **MethylSample**: Per-position methylation data (methylated counts `mC`, unmethylated `uC`, context bits `tnc`). Supports HDF5 serialization and position-indexed access. Used everywhere a single sample is loaded or compared.
- **Centroid types**: Aggregations over many samples with sufficient statistics for Beta (and related) models:
  - **MethylExtendedCentroid**: Counts and accumulators (N, mC, uC, Sx, Sx2); Beta via MoM.
  - **MethylExtendedCentroid**: Adds Sx, Sx2, log sums for method-of-moments and log-likelihood.
  - **MethylBetaMixtureCentroid**, **MethylBetaBinomialCentroid**: For mixture and beta-binomial modeling.
- **MethylCentroidPair**: Wraps two centroids (or samples); used for distance, effect-size, and DMP-style comparison (e.g. in MethylDetector).

## Beta model and metrics

Methylation level at a position is a fraction in [0, 1]. MethylUtils models it with a **Beta(α, β)** distribution. Parameters are derived from coverage and methylation fraction via a **method-of-moments** style mapping (effective size, clamped α/β; invalid/low-coverage falls back to a uniform Beta). This supports likelihoods and distances between positions.

**Distance and effect-size metrics** (all for Beta distributions, with optional GPU):

- KL divergence, Jeffreys (symmetric KL), Bhattacharyya coefficient/distance, Hellinger, Jensen–Shannon distance, Wasserstein (moment approximation), and an effect-size formula combining mean separation and overlap (used for DMP ranking).

Formulas and details are in [METHYLUTILS_COMPREHENSIVE_DOCUMENTATION.md](METHYLUTILS_COMPREHENSIVE_DOCUMENTATION.md); here we only state that MethylUtils provides a single, backend-agnostic (CPU/GPU) metrics API used by MethylCentroid (distances), MethylDetector (centroid comparison, DMPs), and classifiers (likelihoods).

## Classifiers and centroid building

MethylUtils provides the building blocks; downstream packages orchestrate them:

- **MethylCentroidBuilder** / **build_centroid**: Build centroids from a list of sample paths (used by MethylCentroid).
- **BetaClassifier**, **BetaBinomialClassifier**, **MultiClassBetaMixtureClassifier**: Bayesian classifiers used by MethylDetector (training) and MethylClassifier (loading and prediction).
- **MethylCentroidPair**: Comparison and metrics between two centroids (MethylDetector).

So the “theory” is: one implementation of centroid building, metrics, and classifiers in MethylUtils; pipeline packages call these instead of reimplementing.

## Summary

| Aspect | Role |
|--------|------|
| Project config | Single JSON → ProjectConfig; get_derived_paths() for all step outputs. |
| Data types | MethylSample, centroid hierarchy, MethylCentroidPair. |
| Beta & metrics | Beta(α, β) from coverage; seven distance/effect-size metrics. |
| Building blocks | MethylCentroidBuilder, build_centroid, BetaClassifier, MethylCentroidPair. |

For implementation (package layout, how each package uses MethylUtils), see [METHYLUTILS_IMPLEMENTATION.md](METHYLUTILS_IMPLEMENTATION.md). For setup (Docker, venv), see [USAGE.md](USAGE.md).
