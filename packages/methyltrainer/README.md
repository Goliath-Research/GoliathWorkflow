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

## Training Workflow Explained

### Step-by-Step Process

1. **Load Centroids**: Read two centroid HDF5 files (e.g., healthy vs. disease)
2. **Compare Centroids**: Use `MethylCentroidPair` to detect DMPs with statistical significance
3. **Filter DMPs**: Apply biological filtering criteria:
   - Statistical significance (q-value)
   - Effect size (delta mean methylation)
   - Distribution separation (overlap, Jeffreys divergence, AUC)
4. **Select Top DMPs**: Rank and select most informative positions
5. **Train Classifier**: Fit Beta distributions to selected DMPs
6. **Validate Model**: Test on synthetic samples from the learned distributions
7. **Save Model**: Export classifier with full metadata for downstream use

### Statistical Methods

**Jeffreys Divergence**: Information-theoretic measure of distribution dissimilarity
```
D_J(P||Q) = ∫ [P(x)log(P(x)/Q(x)) + Q(x)log(Q(x)/P(x))] dx
```

**AUC (Area Under Curve)**: Discrimination power of a single DMP
- AUC = 1.0: Perfect separation
- AUC = 0.5: No discrimination power
- Threshold: default 0.6

**Beta Distributions**: Models methylation levels as Beta(α, β) where:
- α, β are fitted from centroid statistics (Sx, Sx2, N)
- Enables probabilistic classification

## Output Format Details

### Classifier Object Structure

The trained model (`.pkl` file) contains:

```python
{
    'classifier': ProbabilisticBetaClassifier(
        positions=np.array([...]),  # DMP genomic positions
        centroid1_params={          # Beta(α,β) for each DMP in centroid 1
            'alpha': np.array([...]),
            'beta': np.array([...])
        },
        centroid2_params={          # Beta(α,β) for each DMP in centroid 2
            'alpha': np.array([...]),
            'beta': np.array([...])
        }
    ),
    'metadata': {
        'chromosome': 'chr1',
        'context': 'CG',
        'centroid1_name': 'healthy',
        'centroid2_name': 'disease',
        'n_dmps': 500,
        'dmp_positions': np.array([...]),
        'training_date': '2024-01-15T10:30:00',
        'validation': {
            'overall_accuracy': 0.95,
            'centroid1_accuracy': 0.94,
            'centroid2_accuracy': 0.96,
            'n_samples_tested': 200
        },
        'filter_config': {
            'max_q_value': 0.01,
            'min_delta_mean': 0.1,
            'max_overlap': 0.6,
            'min_jeffreys_divergence': 0.5,
            'min_auc': 0.7,
            'max_dmps': 500,
            'sort_by': 'jeffreys_divergence'
        }
    }
}
```

### Model Metadata Fields

- **chromosome/context**: Genomic region for which model is valid
- **centroid names**: Labels for the two classes
- **n_dmps**: Number of discriminative positions used
- **training_date**: ISO timestamp of model creation
- **validation metrics**: Synthetic sample test results
- **filter_config**: Exact parameters used for DMP selection

This rich metadata enables:
- Model provenance tracking
- Reproducibility
- Quality assessment
- Integration with downstream tools

## Common Use Cases

### 1. Disease vs. Healthy Classification

```bash
# Train classifier from disease and healthy centroids
methyltrainer \
  --centroid1 centroids/healthy_chr1-CG.h5 \
  --centroid2 centroids/disease_chr1-CG.h5 \
  --output models/disease_classifier_chr1-CG.pkl \
  --centroid1-name "Healthy" \
  --centroid2-name "Disease" \
  --max-dmps 1000 \
  --max-q-value 0.001  # Very stringent
```

### 2. Treatment Response Prediction

```bash
# Compare responders vs. non-responders
methyltrainer \
  --centroid1 centroids/responders_chr1-CG.h5 \
  --centroid2 centroids/non_responders_chr1-CG.h5 \
  --output models/response_predictor_chr1-CG.pkl \
  --min-delta-mean 0.2 \  # Larger effect size
  --min-auc 0.75          # Better discrimination
```

### 3. Tissue Type Identification

```bash
# Distinguish tissue types
methyltrainer \
  --centroid1 centroids/liver_chr1-CG.h5 \
  --centroid2 centroids/kidney_chr1-CG.h5 \
  --output models/tissue_classifier_chr1-CG.pkl \
  --max-dmps 300 \        # Fewer DMPs for simpler model
  --min-jeffreys 0.8      # High information content
```

### 4. Batch Training for Multiple Chromosomes

```bash
# Train models for all chromosomes (automation script)
for chrom in chr1 chr2 chr3 chr4 chr5 chr6 chr7 chr8 chr9 chr10 \
             chr11 chr12 chr13 chr14 chr15 chr16 chr17 chr18 chr19 \
             chr20 chr21 chr22 chrX chrY; do
    for context in CG CHG CHH; do
        echo "Training ${chrom}-${context}..."
        methyltrainer \
          --centroid1 centroids/healthy_${chrom}-${context}.h5 \
          --centroid2 centroids/disease_${chrom}-${context}.h5 \
          --output models/classifier_${chrom}-${context}.pkl \
          --chromosome ${chrom} \
          --context ${context} \
          --config default_config.json
    done
done
```

## Configuration File Example

Complete configuration file (`training_config.json`):

```json
{
  "centroid1_path": "centroids/healthy_chr1-CG.h5",
  "centroid2_path": "centroids/disease_chr1-CG.h5",
  "output_path": "models/classifier_chr1-CG.pkl",
  "centroid1_name": "Healthy Control",
  "centroid2_name": "Cancer Patient",
  "chromosome": "chr1",
  "context": "CG",
  "comparison_config": {
    "min_coverage": 10
  },
  "filter_config": {
    "max_q_value": 0.01,
    "min_delta_mean": 0.15,
    "max_overlap": 0.5,
    "min_jeffreys_divergence": 0.6,
    "min_auc": 0.75,
    "max_dmps": 500,
    "sort_by": "jeffreys_divergence"
  },
  "validation_config": {
    "n_samples_per_class": 100
  }
}
```

Run with: `methyltrainer --config training_config.json --verbose`

## Performance Considerations

### Centroid Quality

- **Minimum samples**: Use centroids with ≥5 samples each
- **Outlier removal**: Ensure centroids have undergone outlier detection
- **Coverage**: Higher coverage (≥10x) yields more reliable DMPs

### DMP Selection Strategies

**Conservative (High Precision)**:
```bash
--max-q-value 0.001 --min-jeffreys 0.8 --min-auc 0.8 --max-dmps 100
```

**Balanced (Default)**:
```bash
--max-q-value 0.01 --min-jeffreys 0.5 --min-auc 0.7 --max-dmps 500
```

**Exploratory (High Sensitivity)**:
```bash
--max-q-value 0.05 --min-jeffreys 0.3 --min-auc 0.6 --max-dmps 1000
```

### Model Validation

- **Synthetic validation**: Automatic, tests learned distributions
- **Real sample validation**: Use independent test set with MethylClassifier
- **Cross-validation**: Train on chr1-22, test on chrX/chrY or vice versa

## Troubleshooting

### Issue: "No DMPs pass filtering criteria"

**Solution**: Relax filtering parameters
```bash
methyltrainer --centroid1 c1.h5 --centroid2 c2.h5 --output model.pkl \
  --max-q-value 0.1 \      # Less stringent
  --min-delta-mean 0.05 \  # Smaller effect size
  --min-auc 0.55           # Lower threshold
```

### Issue: "Validation accuracy too low"

**Possible causes**:
1. Centroids are too similar (biological signal weak)
2. DMPs selected are not discriminative enough
3. Insufficient DMP count

**Solutions**:
- Increase `--max-dmps` to include more positions
- Check centroid quality and sample composition
- Try different `--sort-by` metric (e.g., 'auc' instead of 'jeffreys_divergence')

### Issue: "Model too large / slow inference"

**Solution**: Reduce DMP count
```bash
methyltrainer --centroid1 c1.h5 --centroid2 c2.h5 --output model.pkl \
  --max-dmps 200  # Smaller model, faster prediction
```

## Integration Examples

### With MethylDetector

```bash
# 1. Detect DMPs (for exploratory analysis)
methyldetector --centroid1 c1.h5 --centroid2 c2.h5 --output dmps/

# 2. Train classifier (for prediction)
methyltrainer --centroid1 c1.h5 --centroid2 c2.h5 --output model.pkl

# 3. Classify new samples
methylclassifier --model model.pkl --input new_samples/ --output predictions.csv
```

### With MethylMapper

```bash
# 1. Train classifier
methyltrainer --centroid1 c1.h5 --centroid2 c2.h5 --output model.pkl

# 2. Extract DMP positions from model metadata
python -c "
import pickle
with open('model.pkl', 'rb') as f:
    data = pickle.load(f)
positions = data['metadata']['dmp_positions']
print('\\n'.join(map(str, positions)))
" > dmp_positions.txt

# 3. Map to genes
methylmapper --positions dmp_positions.txt --chromosome chr1 --output gene_mapping.csv
```

## Advanced Topics

### Custom Filtering Logic

For advanced users, the filtering logic can be extended by modifying the filter configuration:

```python
# In custom_training.py
from methyltrainer import MethylTrainerConfig, train_classifier

config = MethylTrainerConfig(
    centroid1_path="c1.h5",
    centroid2_path="c2.h5",
    output_path="model.pkl",
    filter_config={
        "max_q_value": 0.01,
        "min_delta_mean": 0.1,
        "max_overlap": 0.6,
        "min_jeffreys_divergence": 0.5,
        "min_auc": 0.7,
        "max_dmps": 500,
        "sort_by": "combined_score"  # Custom metric
    }
)

model = train_classifier(config)
```

### Ensemble Models

Train multiple models and combine predictions:

```bash
# Train with different DMP sets
methyltrainer --centroid1 c1.h5 --centroid2 c2.h5 --output model_top500.pkl --max-dmps 500 --sort-by jeffreys
methyltrainer --centroid1 c1.h5 --centroid2 c2.h5 --output model_top300.pkl --max-dmps 300 --sort-by auc
methyltrainer --centroid1 c1.h5 --centroid2 c2.h5 --output model_top200.pkl --max-dmps 200 --sort-by delta_mean

# Use MethylClassifier to combine predictions (voting or averaging)
```

## Citation

If you use MethylTrainer in your research, please cite:

```
MethylTrainer: Bayesian Classifier Training for Methylation Analysis
[Your citation information here]
```
