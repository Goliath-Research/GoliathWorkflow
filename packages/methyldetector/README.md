# MethylDetector

## Overview

A production-ready pipeline for detecting differentially methylated positions (DMPs) between two methylation centroids. It leverages the MethylSample class and MethylUtils ecosystem for efficient, GPU-optimized computations.

## Features

- MethylSample-based API for cleaner, more maintainable code
- GPU-optimized computations using MethylUtils GPU detection
- Biological importance ranking for gene discovery
- Support for centroids and extended centroids
- Gene-level feature importance analysis
- Production-ready CLI interface

## Quick Start

1. Install dependencies: `poetry install`
2. Run analysis: `poetry run methyl-detector path/to/config.json`

## Configuration

Key parameters in `MethylDetectorConfig`:

- `centroid1_path`, `centroid2_path`: Input centroid files
- `output_dir`: Results directory
- `alpha`: Significance level (default: 0.05)
- `min_N_pct`: Minimum coverage fraction (default: 0.10)
- `apply_dmp_filtering`: Enable biological filtering (default: true)
- `min_delta_mean`: Minimum effect size (default: 0.2)
- `max_bc`: Maximum overlap (default: 0.6)
- `target_balanced_accuracy`: Target Balanced Accuracy for DMP selection (default: 0.95). Balanced Accuracy = (Sensitivity + Specificity) / 2, robust to class imbalance.
- `use_gpu`: Enable GPU acceleration (default: true)

## Output

- methyl_detector_selected_dmps.csv
- methyl_detector_classifier.pkl
- methyl_detector_gene_weights.csv
- methyl_detector_summary.json

## Integration

Part of MethylPipeline: Use with MethylTrainer for classifier training and MethylClassifier for classification.

## Troubleshooting

- GPU not detected: Check CUDA installation
- Memory errors: Reduce max_dmps

## License

MIT License - see LICENSE file for details.