# MethylUtils Theoretical Foundation

## Role

MethylUtils is the **foundational library** of MethylPipeline. It provides data structures, project configuration, **ECDF-based** comparison and metrics, centroid building, and classifier primitives. **No pipeline step runs without it**: MethylCentroid, MethylDetector, MethylClassifier, MethylPredictor, and MethylValidation all depend on MethylUtils. Centroid comparison and DMP detection use **ECDF only** (no Beta, Normal, Beta-Binomial, or Beta-Mixture).

## Project configuration

A single **project JSON** defines the whole workflow: sample groups, comparisons, and output layout. MethylUtils parses and validates this so downstream packages do not repeat sample paths and output structure.

- **ProjectConfig**: `project_name`, `output_base`, groups (e.g. control/disease with sub-groups), `comparisons`, optional `level_labels_path`, `subcluster`, `samples_base_path`, `step_config`.
- **load_project(path)**: Loads and validates the JSON; returns a `ProjectConfig`.
- **get_derived_paths()**: Yields paths under `{output_base}/{project_name}/` for centroids, detection, classifier, predictor, etc. Used by MethylCentroid, MethylDetector, MethylClassifier, MethylPredictor to resolve inputs and outputs from one project file.

So the “theory” of project config is: one source of truth for groups and comparisons; derived paths are computed from that, not hard-coded in each package.

## Sample and centroid types

- **MethylSample**: Per-position methylation data (methylated counts `mC`, unmethylated `uC`, context bits `tnc`). Supports HDF5 serialization and position-indexed access. Used everywhere a single sample is loaded or compared.
- **Centroid types**: A single centroid type, **MethylExtendedCentroid**, with N, mC, uC, Sx, Sx2 and optional **binned_stats** (bin_edges, bin_counts) for ECDF. Mean/variance can be derived from N, Sx, Sx2 (method-of-moments); **only ECDF is used** for centroid comparison and classifier likelihoods.
- **MethylCentroidPair**: Wraps two centroids (or samples); used for distance, effect-size, and DMP-style comparison (e.g. in MethylDetector) using **ECDF only**.

## ECDF model and metrics

Methylation level at a position is a fraction in [0, 1]. For **centroid comparison and DMP detection**, MethylUtils uses **only the empirical distribution (ECDF)** from centroid binned_stats. No parametric distribution (Beta, Normal, Beta-Binomial, Beta-Mixture) is used in the pipeline.

**Distance and effect-size metrics** (centroid comparison and DMP detection use **ECDF only**, with optional GPU):

- Overlap and distance from ECDF (e.g. Bhattacharyya coefficient/distance from binned distributions), and an effect-size formula combining mean separation and overlap (used for DMP ranking). Means/variances come from N, Sx, Sx2 where available.

Formulas and details are in [METHYLUTILS_COMPREHENSIVE_DOCUMENTATION.md](METHYLUTILS_COMPREHENSIVE_DOCUMENTATION.md); MethylUtils provides a backend-agnostic (CPU/GPU) API used by MethylCentroid, MethylDetector (ECDF-based comparison, DMPs), and classifiers (ECDF-based likelihoods).

## Classifiers and centroid building

MethylUtils provides the building blocks; downstream packages orchestrate them:

- **MethylCentroidBuilder** / **build_centroid**: Build centroids from a list of sample paths (used by MethylCentroid); centroids include binned_stats for ECDF.
- **ECDF-based classifier**: Used by MethylDetector (training) and MethylClassifier (loading and prediction); likelihoods from centroid ECDF PDFs.
- **MethylCentroidPair**: Comparison and metrics between two centroids (MethylDetector) using ECDF only.

So the “theory” is: one implementation of centroid building, ECDF-based metrics and classifiers in MethylUtils; pipeline packages call these instead of reimplementing.

## Summary

| Aspect | Role |
|--------|------|
| Project config | Single JSON → ProjectConfig; get_derived_paths() for all step outputs. |
| Data types | MethylSample, MethylExtendedCentroid (with binned_stats for ECDF), MethylCentroidPair. |
| Distribution | **ECDF only** for comparison and DMP detection; distance/effect-size from ECDF. |
| Building blocks | MethylCentroidBuilder, build_centroid, ECDF-based classifier, MethylCentroidPair. |

For implementation (package layout, how each package uses MethylUtils), see [METHYLUTILS_IMPLEMENTATION.md](METHYLUTILS_IMPLEMENTATION.md). For setup (Docker, venv), see [USAGE.md](USAGE.md).
