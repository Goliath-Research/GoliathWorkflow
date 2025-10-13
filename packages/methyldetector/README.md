# MethylDetector: Advanced DMP Detection Pipeline

> **Note:** MethylDetector now focuses exclusively on DMP detection. For classifier training, use [MethylTrainer](../MethylTrainer/). For sample classification, use [MethylClassifier](../MethylClassifier/).

## Overview

MethylDetector is a production-ready pipeline for detecting differentially methylated positions (DMPs) between two methylation centroids. It leverages the MethylSample class and MethylUtils ecosystem for efficient, GPU-optimized computations.

## Key Features

- **MethylSample-based API** for cleaner, more maintainable code
- **GPU-optimized computations** using MethylUtils GPU detection
- **Biological importance ranking** for gene discovery
- **Support for centroids and extended centroids**
- **Gene-level feature importance analysis**
- **Production-ready CLI interface**

## Workflow Integration

MethylDetector is part of a three-tool workflow:

1. **MethylDetector** (this tool): Detect DMPs between centroid pairs
2. **[MethylTrainer](../MethylTrainer/)**: Train Bayesian classifiers from centroids
3. **[MethylClassifier](../MethylClassifier/)**: Classify samples using trained models

### 🚀 Quick Start: Complete Pipeline

For convenience, we provide scripts that run the complete workflow (DMP detection + classifier training):

```bash
# Simple: Auto-detect everything
./quick_pipeline.sh healthy.h5 disease.h5 output/

# Advanced: Full control
./run_full_pipeline.sh \
    --centroid1 healthy.h5 \
    --centroid2 disease.h5 \
    --output-dir results/ \
    --max-dmps 500 \
    --verbose
```

See [PIPELINE_USAGE.md](PIPELINE_USAGE.md) for complete documentation.

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Install MethylUtils (if not already installed)
pip install methyl-utils

# Optional: Install RAPIDS for GPU data frames (recommended for large datasets)
# Note: RAPIDS requires specific CUDA versions and may not be available in all environments
# The pipeline requires cuDF for GPU mode and pandas for CPU mode
```

## GPU Requirements

The pipeline supports both GPU and CPU execution:

- **GPU Mode**: Requires CUDA, CuPy, and cuDF (RAPIDS) - all computations on GPU
- **CPU Mode**: Uses NumPy and pandas - all computations on CPU
- **No mixing**: GPU mode uses cuDF, CPU mode uses pandas

## Quick Start

### 1. Easy Execution Methods

MethylDetector provides several convenient ways to run the pipeline:

#### Using Make (Recommended)
```bash
# Run with configuration file
make run CONFIG=path/to/config.json

# Run with verbose logging
make run-verbose CONFIG=path/to/config.json
```

#### Using the Runner Script
```bash
# Direct execution with automatic path setup
python run_methyl_detector.py path/to/config.json --verbose
```

#### Using Poetry (if installed)
```bash
poetry run methyl-detector path/to/config.json
```

#### Using Python Module
```bash
python -m methyl_detector.cli.main path/to/config.json
```

#### Inside Docker Container
```bash
docker exec -w /home/ubuntu/MethylDetector epimethyl python run_methyl_detector.py path/to/config.json
```

### 2. Generate Example Configuration

```bash
python run_methyl_detector.py --help  # Shows available options
```

### 2. Edit Configuration

Edit the generated `config.json` file with your specific parameters:

```json
{
  "centroid1_path": "path/to/your/centroid1.h5",
  "centroid2_path": "path/to/your/centroid2.h5",
  "output_dir": "./output",
  "min_q_value": 0.05,
  "min_delta_mean": 0.1,
  "max_bhattacharyya": 0.8,
  "min_importance": 0.5,
  "max_dmps": 1000
}
```

### 3. Run Analysis

```bash
# Basic run
python methyl_detector/core/methyl_detector.py --config config.json

# With verbose logging
python methyl_detector/core/methyl_detector.py --config config.json --verbose
```

## Configuration Parameters

### Input/Output
- `centroid1_path`: Path to first centroid file
- `centroid2_path`: Path to second centroid file  
- `output_dir`: Output directory for results

### Analysis Parameters
- `min_q_value`: Maximum q-value for statistical significance (default: 0.05)
- `min_delta_mean`: Minimum delta mean for biological significance (default: 0.1)
- `max_bhattacharyya`: Maximum Bhattacharyya coefficient (default: 0.8)
- `min_importance`: Minimum biological importance score (default: 0.5)
- `max_dmps`: Maximum number of DMPs to select (default: None = no limit)

### GPU/CPU Selection
- `prefer_gpu`: Use GPU acceleration if available (default: true)

### Estimation Parameters
- `mle_max_iter`: Newton iterations for MLE (default: 10)
- `mle_tol`: Gradient tolerance for Newton stop (default: 1e-8)

### Weight Squashing
- `weight_mode`: Bounded weight transform ("none", "rational", "exp")
- `weight_lambda`: λ for rational weight I/(I+λ) (auto-calibrated if None)
- `weight_I0`: I0 for exp weight 1-exp(-I/I0) (auto-calibrated if None)

## Output Files

The pipeline generates several output files:

- `methyl_detector_selected_dmps.csv`: Selected DMPs with all metrics
- `methyl_detector_classifier.pkl`: Trained classifier for sample classification
- `methyl_detector_gene_weights.csv`: Gene weights for feature discovery
- `methyl_detector_summary.json`: Analysis summary and metadata

## Usage Examples

### Basic Analysis

```bash
python methyl_detector/core/methyl_detector.py --config config.json
```

### With Debug Logging

```bash
python methyl_detector/core/methyl_detector.py --config config.json --verbose
```

### Generate Example Config

```bash
python methyl_detector/core/methyl_detector.py --generate-config example.json
```

## Programmatic Usage

```python
from methyl_detector.core.methyl_detector import MethylDetector, MethylDetectorConfig

# Load configuration
config = MethylDetectorConfig.from_json("config.json")

# Create detector
detector = MethylDetector(config)

# Run analysis
selected_df, classifier = detector.run_analysis()

# Classify a new sample
from methyl_utils import MethylSample
new_sample = MethylSample.load_from_h5("new_sample.h5")
predictions, probabilities = detector.classify_sample(classifier, new_sample)
```

## Advanced Features

### Biological Importance Ranking

The pipeline computes biological importance using the formula:
```
I = |Δμ| / (BC + ε) * w_prec
```

Where:
- Δμ = |mean1 - mean2| (difference in means)
- BC = Bhattacharyya coefficient (overlap measure)
- w_prec = precision weight (down-weights low-precision sites)

### Weight Squashing

Converts unbounded importance scores to bounded weights [0,1] for gene mapping:

- **Rational**: `I / (I + λ)`
- **Exponential**: `1 - exp(-I / I0)`

### GPU Optimization

- **70-80% reduction** in GPU↔CPU transfers
- **GPU-resident computations** for biological importance
- **Automatic GPU/CPU fallback** with MethylUtils detection
- **Proper memory management** with cleanup

## Performance

### GPU Acceleration
- Automatic GPU detection using MethylUtils
- GPU-resident computations for large datasets
- Fallback to CPU if GPU unavailable

### Memory Efficiency
- MethylSample objects for better memory locality
- Optimized array operations
- Automatic cleanup

## Troubleshooting

### Common Issues

1. **GPU not detected**: Check CUDA installation and MethylUtils GPU detection
2. **Memory errors**: Reduce `max_dmps` or use CPU mode
3. **File not found**: Check centroid file paths in configuration

### Debug Mode

Use `--verbose` flag for detailed logging:

```bash
python methyl_detector/core/methyl_detector.py --config config.json --verbose
```

## Dependencies

- **MethylUtils**: Core methylation analysis toolkit
- **cuDF**: GPU data frames (RAPIDS)
- **CuPy**: GPU array operations
- **scikit-learn**: Statistical functions
- **pandas**: Data manipulation
- **numpy**: Numerical computing

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Citation

If you use MethylDetector in your research, please cite:

```bibtex
@software{methyldetector2024,
  title={MethylDetector: Advanced DMP Detection and Classification Pipeline},
  author={MethylDetector Team},
  year={2024},
  url={https://github.com/your-org/MethylDetector}
}
```

## Support

For questions and support:
- Create an issue on GitHub
- Check the documentation
- Review the example configurations

## Changelog

### Version 2.0.0
- Complete rewrite with MethylSample-based API
- GPU optimization with MethylUtils integration
- Production-ready CLI interface
- Enhanced biological importance ranking
- Gene-level feature discovery
- Comprehensive configuration system