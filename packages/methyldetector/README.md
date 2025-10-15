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

## Installation

```bash
poetry install
```

## Usage

### Command Line

```bash
python run_methyl_detector.py path/to/config.json --verbose
```

### Python API

```python
from methyl_detector.core.methyl_detector import MethylDetector, MethylDetectorConfig

config = MethylDetectorConfig.from_json("config.json")
detector = MethylDetector(config)
selected_df, classifier = detector.run_analysis()
```

## Configuration

See example config.json in the original content.

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