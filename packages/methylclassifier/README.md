# MethylClassifier

## Overview

A command-line tool for Bayesian classification of methylation samples using probabilistic beta classifiers. This tool can classify methylation samples against multiple centroids and supports various methylation data formats.

## Features

- Bayesian Classification: Uses probabilistic beta classifiers for robust methylation-based classification
- Multi-Centroid Support: Classify samples against multiple reference centroids
- Flexible Input: Supports both single .h5 files and directories containing multiple samples
- Comprehensive Output: Detailed classification results with statistical information
- Debug Mode: Enhanced debugging capabilities for troubleshooting classification issues
- Batch Processing: Efficiently process large numbers of samples

## Installation

```bash
poetry install
```

## Usage

### Command Line

```bash
methylclassifier --model classifier.pkl --input sample.h5
```

### Python API

```python
from methylclassifier import classify_sample

result = classify_sample(classifier=classifier, sample_path='sample.h5', metadata=metadata)
```

## Configuration

No separate config file; parameters via CLI.

## Output

CSV with sample name, predicted class, probabilities, etc.

## Integration

Use with models trained by MethylTrainer in MethylPipeline.

## Troubleshooting

- Mismatch: Use --no-filter cautiously
- Low coverage: Check sample quality

## License

MIT License - see LICENSE file for details.
