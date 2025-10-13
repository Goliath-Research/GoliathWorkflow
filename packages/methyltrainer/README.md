# MethylTrainer

A command-line tool for training Bayesian classifiers from methylation centroid pairs. MethylTrainer uses `MethylCentroidPair` to detect differentially methylated positions (DMPs) and creates `ProbabilisticBetaClassifier` models for sample classification.

## Features

- **Automated DMP Detection**: Uses MethylCentroidPair for robust statistical comparison
- **Biological Filtering**: Multiple criteria for selecting informative DMPs
- **Bayesian Classification**: Creates probabilistic Beta distribution classifiers
- **Model Validation**: Automatic validation with synthetic test samples
- **Flexible Configuration**: JSON config files or command-line arguments
- **Rich Metadata**: Models include full context (chromosome, context, DMPs, validation metrics)

## Installation

### Prerequisites

MethylTrainer requires MethylUtils to be installed:

```bash
cd /home/ubuntu/MethylUtils
pip install -e .
```

### Install MethylTrainer

```bash
cd /home/ubuntu/MethylTrainer
pip install -e .
```

## Usage

### Basic Training

```bash
# Train from two centroid files
methyltrainer --centroid1 group1_chr1-CG.h5 --centroid2 group2_chr1-CG.h5 --output model.pkl
```

### Advanced Training

```bash
# Custom filtering parameters
methyltrainer --centroid1 healthy.h5 --centroid2 disease.h5 --output model.pkl \
              --max-dmps 500 \
              --max-q-value 0.01 \
              --min-jeffreys 0.5 \
              --min-auc 0.7
```

### Using Configuration File

```bash
# Create a config file (training_config.json)
{
  "centroid1_path": "healthy_chr1-CG.h5",
  "centroid2_path": "disease_chr1-CG.h5",
  "output_path": "model_chr1-CG.pkl",
  "chromosome": "chr1",
  "context": "CG",
  "min_coverage": 10,
  "max_q_value": 0.01,
  "min_delta_mean": 0.1,
  "max_dmps": 500,
  "min_jeffreys_divergence": 0.5
}

# Train using config
methyltrainer --config training_config.json
```

### With Metadata

```bash
methyltrainer --centroid1 c1.h5 --centroid2 c2.h5 --output model.pkl \
              --chromosome chr1 --context CG \
              --centroid1-name "healthy" --centroid2-name "disease"
```

## Command-Line Options

### Input/Output
- `--centroid1, -c1`: Path to first centroid HDF5 file (required)
- `--centroid2, -c2`: Path to second centroid HDF5 file (required)
- `--output, -o`: Output path for trained model (required)
- `--config`: Path to JSON configuration file (overrides other arguments)

### Metadata
- `--centroid1-name`: Name/label for centroid 1
- `--centroid2-name`: Name/label for centroid 2
- `--chromosome`: Chromosome identifier (e.g., chr1)
- `--context`: Methylation context (e.g., CG, CHG, CHH)

### Comparison Configuration
- `--min-coverage`: Minimum coverage threshold (default: 10)

### Filter Configuration
- `--max-q-value`: Maximum q-value for DMPs (default: 0.05)
- `--min-delta-mean`: Minimum absolute difference in means (default: 0.1)
- `--max-overlap`: Maximum distribution overlap (default: 0.6)
- `--min-jeffreys`: Minimum Jeffreys divergence (default: 0.3)
- `--min-auc`: Minimum AUC score (default: 0.6)
- `--max-dmps`: Maximum number of DMPs to use (default: 1000)
- `--sort-by`: Metric to sort DMPs by (default: jeffreys_divergence)

### Other Options
- `--verbose, -v`: Enable verbose output
- `--version`: Show version information

## Model Format

MethylTrainer creates enhanced PKL files containing:

```python
{
    'classifier': ProbabilisticBetaClassifier,
    'metadata': {
        'chromosome': str,
        'context': str,
        'centroid1_name': str,
        'centroid2_name': str,
        'n_dmps': int,
        'training_date': str,
        'dmp_positions': np.ndarray,
        'validation': {
            'overall_accuracy': float,
            'centroid1_accuracy': float,
            'centroid2_accuracy': float
        },
        'filter_config': {
            'max_q_value': float,
            'min_delta_mean': float,
            'max_overlap': float,
            'max_dmps': int
        }
    }
}
```

## Workflow Integration

MethylTrainer is part of a three-tool workflow:

1. **MethylDetector**: Detect and export DMPs for analysis
2. **MethylTrainer**: Train classifier from centroid pairs (this tool)
3. **MethylClassifier**: Classify new samples using trained models

```bash
# Full workflow
methyldetector --centroid1 c1.h5 --centroid2 c2.h5 --output dmps/
methyltrainer --centroid1 c1.h5 --centroid2 c2.h5 --output model.pkl
methylclassifier --model model.pkl --input samples/ --output results.csv
```

## Requirements

- Python 3.8+
- MethylUtils (core library)
- NumPy >= 1.20.0
- SciPy >= 1.7.0
- h5py >= 3.0.0

## Input Format

Centroid files must be:
- HDF5 format (`.h5`)
- Extended centroid type (with alpha/beta parameters)
- Created using MethylUtils MethylSample format

## License

MIT License - see LICENSE file for details.

## Citation

If you use MethylTrainer in your research, please cite:

```
MethylTrainer: Bayesian Classifier Training for Methylation Analysis
[Your citation information here]
```
