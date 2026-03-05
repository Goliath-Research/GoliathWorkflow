# MethylUtils Implementation

This document describes the MethylUtils package layout and how downstream pipeline packages use it.

## Package layout

The installable package is **methylutils**; the Python package name is **methyl_utils**. Top-level structure:

- **methyl_utils/__init__.py** — Public API: project config, sample/centroid types, metrics, classifiers, GPU/memory helpers. Downstream packages import from `methyl_utils` (e.g. `from methyl_utils import load_project`, `MethylSample`, `MethylCentroidBuilder`).
- **methyl_utils/core/** — Core data and building blocks:
  - **methyl_frame.py** — MethylSample, MethylExtendedCentroid (single centroid type), MethylFrame.
  - **centroid_builder.py** — MethylCentroidBuilder, build_centroid.
  - **io.py** — load_from_h5, save_to_h5 (and related I/O).
  - **distribution_views.py** — CountsView, BetaView, log_probability_sample_given_centroid, overlap_between_centroids.
  - **methyl_mixture_centroid.py** — MethylBetaMixtureCentroid.
  - **methyl_distribution_utils.py** — Distribution utilities used by metrics and tests.
- **methyl_utils/pipeline_config.py** — ProjectConfig, GroupConfig, ControlDiseaseSide, ComparisonSpec, DerivedPaths, **load_project**.
- **methyl_utils/methyl_centroid_pair.py** — MethylCentroidPair (two-centroid comparison, distances, effect size).
- **methyl_utils/beta_classifier.py** — BetaClassifier (and related).
- **methyl_utils/beta_mixture.py** — Beta mixture and multi-class mixture classifier support.
- **methyl_utils/beta_binomial_classifier.py** — BetaBinomialClassifier.
- **methyl_utils/bayesian_classifier_trainer.py** — Training helpers for classifiers.
- **methyl_utils/metrics_core.py** — Core distance/effect-size implementations (KL, Jeffreys, Bhattacharyya, Hellinger, JSD, Wasserstein).
- **methyl_utils/metrics_factory.py** — get_metric_factory, create_metric_computer, backend-agnostic dispatch.
- **methyl_utils/statistical_tests.py** — storey_qvalues, likelihood_ratio_test_beta, aggregate_pvalues_*, beta_mle_estimation, etc.
- **methyl_utils/gpu_detection.py** — is_gpu_available, get_cupy, cleanup_gpu_memory, get_gpu_memory_gb, etc.
- **methyl_utils/gpu_utils.py** — Backend-agnostic array handling.
- **methyl_utils/memory_manager.py** — get_memory_manager, get_memory_usage.
- **methyl_utils/chunked_processor.py** — ChunkedGenomicProcessor, process_genome_file_chunked.
- **methyl_utils/logging_utils.py** — setup_logging, setup_module_logging.
- **methyl_utils/transformations.py** — EAT (e.g. compute_eat_T, apply_eat_transform).

Other modules (beta_analytics, chrom_mapping, health_discovery, enricher, performance_profiler, models, classifier_factory, etc.) support the above or specialized workflows.

## How downstream packages use MethylUtils

| Package | Main MethylUtils usage |
|---------|------------------------|
| **MethylCentroid** | load_project, MethylCentroidBuilder, build_centroid, MethylSample, load_from_h5, get_memory_usage, is_gpu_available, get_methyl_dtype. See [METHYLCENTROID_IMPLEMENTATION.md](../../methylcentroid/docs/METHYLCENTROID_IMPLEMENTATION.md). |
| **MethylDetector** | load_project, MethylSample, MethylCentroidPair, BetaClassifier, BetaBinomialClassifier, compute_eat_T, setup_module_logging. See [METHYLDETECTOR_IMPLEMENTATION.md](../../methyldetector/docs/METHYLDETECTOR_IMPLEMENTATION.md). |
| **MethylClassifier** | load_project, BetaClassifier, load_from_h5, MethylSample, MultiClassBetaMixtureClassifier, MethylBetaMixtureCentroid. See [METHYLCLASSIFIER_IMPLEMENTATION.md](../../methylclassifier/docs/METHYLCLASSIFIER_IMPLEMENTATION.md). |
| **MethylPredictor** | load_project (for step_config.predictor: test_control_paths, test_disease_paths, model_dir, output_dir). See [METHYLPREDICTOR_IMPLEMENTATION.md](../../methylpredictor/docs/METHYLPREDICTOR_IMPLEMENTATION.md). |
| **MethylValidation** | load_project (for Monte Carlo validation runner). |

Details of how each package calls MethylUtils (config resolution, centroid building, classification flow) are in the implementation docs of those packages; this table is the index.

## Installation

MethylUtils is installed first; then any of MethylCentroid, MethylDetector, MethylClassifier, MethylPredictor. From the MethylPipeline repo root:

```bash
pip install -e packages/methylutils
```

Or from the package directory:

```bash
cd packages/methylutils && pip install -e .
```

For Docker and venv setups, see [USAGE.md](USAGE.md).
