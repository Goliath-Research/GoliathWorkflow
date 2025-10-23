# MethylTrainer Usage Guide

## Overview

MethylTrainer trains Bayesian classifiers from pairs of methylation centroids. It performs DMP detection, biological filtering, and creates ProbabilisticBetaClassifier models for sample classification.

## Installation

```bash
cd packages/methyltrainer
poetry install
```

## Command-Line Usage

### Basic Training

Train a classifier from two centroids:

```bash
methyl-trainer --centroid1 healthy_chr1-CG.h5 \
               --centroid2 cancer_chr1-CG.h5 \
               --output classifier_chr1-CG.pkl
```

### Training with Custom Parameters

```bash
methyl-trainer --centroid1 healthy_chr1-CG.h5 \
               --centroid2 cancer_chr1-CG.h5 \
               --output classifier_chr1-CG.pkl \
               --max-dmps 500 \
               --max-q-value 0.01 \
               --target-auc 0.95
```

### Training from Configuration File

```bash
methyl-trainer --config example_training_config.json
```

See `configs/example_training_config.json` for a complete example.

## Python API

### Train from Centroids

```python
from methyl_trainer import train_from_centroids

result = train_from_centroids(
    centroid1_path="healthy_chr1-CG.h5",
    centroid2_path="cancer_chr1-CG.h5",
    output_path="classifier_chr1-CG.pkl",
    max_dmps=500,
    max_q_value=0.01,
    target_auc=0.95
)

print(f"Trained classifier with {result['n_dmps']} DMPs")
print(f"Validation accuracy: {result['validation_accuracy']:.2%}")
```

### Train with Configuration Object

```python
from methyl_trainer import MethylTrainer, TrainingConfig

config = TrainingConfig(
    centroid1_path="healthy_chr1-CG.h5",
    centroid2_path="cancer_chr1-CG.h5",
    output_path="classifier_chr1-CG.pkl",
    target_auc=0.95,
    validation_mode="real",
    centroid1_validation_samples=["healthy_sample1.h5", "healthy_sample2.h5"],
    centroid2_validation_samples=["cancer_sample1.h5", "cancer_sample2.h5"]
)

trainer = MethylTrainer(config)
model_package = trainer.train_from_dmps(
    dmp_df=dmp_dataframe,
    centroid1_path=Path(config.centroid1_path),
    centroid2_path=Path(config.centroid2_path),
    chromosome="1",
    context="CG"
)
```

## Configuration Parameters

### Input/Output
- `centroid1_path`: Path to first centroid HDF5 file
- `centroid2_path`: Path to second centroid HDF5 file
- `output_path`: Path for output classifier PKL file

### Statistical Filtering
- `alpha`: Significance level for DMP detection (default: 0.01)
- `min_delta_mean`: Minimum absolute mean difference (default: 0.2)
- `max_bc`: Maximum Bhattacharyya coefficient/overlap (default: 0.5)

### DMP Selection
- `target_auc`: Target AUC for binary search (default: 0.95)
- `min_selected_dmps`: Minimum number of DMPs to select (default: 50)
- `min_dmps_for_export`: Minimum DMPs required for export (default: 100)

### Validation
- `validation_mode`: "synthetic" or "real" validation
- `n_validation_samples`: Number of synthetic samples for validation
- `centroid1_validation_samples`: List of real sample paths for centroid 1
- `centroid2_validation_samples`: List of real sample paths for centroid 2
- `optimize_for_validation_accuracy`: Optimize selection for validation accuracy

### Calibration
- `temperature`: Temperature for softmax calibration (default: 1.0)
- `enable_platt_calibration`: Enable Platt scaling calibration (default: false)

### Performance
- `use_gpu`: Enable GPU acceleration (default: true)
- `random_state`: Random seed for reproducibility (default: 42)

## Output

The trained classifier is saved as a PKL file containing:

```python
{
    'classifier': ProbabilisticBetaClassifier,  # Trained model
    'metadata': {
        'chromosome': str,
        'context': str,
        'n_dmps': int,
        'training_date': str,
        'validation': {
            'overall_accuracy': float,
            'centroid1_accuracy': float,
            'centroid2_accuracy': float
        },
        'temperature': float,
        'enable_platt_calibration': bool
    },
    'selected_dmps_df': pd.DataFrame,  # Selected DMPs with statistics
    'package_version': str
}
```

## Examples

See `configs/` directory for complete configuration examples:
- `example_training_config.json` - Basic training with synthetic validation
- `example_real_validation_config.json` - Training with real sample validation

## Troubleshooting

### No DMPs Found
- Relax filtering parameters (`min_delta_mean`, `max_bc`)
- Lower `alpha` threshold
- Check centroid quality

### Low Validation Accuracy
- Increase `target_auc`
- Add more DMPs (`min_selected_dmps`)
- Use real validation samples
- Enable `optimize_for_validation_accuracy`

### Memory Errors
- Reduce `n_validation_samples`
- Disable GPU (`use_gpu: false`)
- Reduce number of validation samples

## Integration

MethylTrainer is part of the MethylPipeline ecosystem:
- Uses centroids from **MethylCentroid**
- Trains models for **MethylClassifier**
- Integrates with **MethylDetector** for DMP detection

