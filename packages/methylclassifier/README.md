# MethylClassifier

A command-line tool for Bayesian classification of methylation samples using probabilistic beta classifiers. This tool can classify methylation samples against multiple centroids and supports various methylation data formats.

## Features

- **Bayesian Classification**: Uses probabilistic beta classifiers for robust methylation-based classification
- **Multi-Centroid Support**: Classify samples against multiple reference centroids
- **Flexible Input**: Supports both single .h5 files and directories containing multiple samples
- **Comprehensive Output**: Detailed classification results with statistical information
- **Debug Mode**: Enhanced debugging capabilities for troubleshooting classification issues
- **Batch Processing**: Efficiently process large numbers of samples

## Installation

### From Source
```bash
git clone https://github.com/your-org/methylclassifier.git
cd methylclassifier
pip install -e .
```

### Requirements
- Python 3.7+
- numpy
- scipy
- pandas
- h5py
- matplotlib
- seaborn

## Usage

### Basic Classification
```bash
# Classify a single sample
methylclassifier --model classifier.pkl --input sample.h5

# Classify all samples in a directory
methylclassifier --model classifier.pkl --input samples/ --output results.csv
```

### Advanced Options
```bash
# Enable debug output
methylclassifier --model classifier.pkl --input sample.h5 --debug

# Process without chromosome/context filtering
methylclassifier --model classifier.pkl --input samples/ --no-filter --output results.csv

# Specify custom output location
methylclassifier --model classifier.pkl --input sample.h5 --output /path/to/results.csv
```

## Command Line Arguments

- `--model, -m`: Path to trained classifier model (.pkl file) [required]
- `--input, -i`: Path to input .h5 file or directory containing .h5 files [required]
- `--output, -o`: Optional output CSV file for classification results
- `--debug, -d`: Enable debug output for detailed analysis
- `--no-filter`: Process all .h5 files without chromosome/context filtering

## Output Format

The tool generates detailed classification results including:

- Sample name and type
- Predicted class and probabilities
- Coverage statistics
- DMP (Differentially Methylated Position) usage
- Statistical properties for centroid samples

Results can be saved to CSV format for further analysis.

## Development

### Setup Development Environment
```bash
pip install -e ".[dev]"
```

### Run Tests
```bash
pytest
```

### Code Formatting
```bash
black methylclassifier/
flake8 methylclassifier/
```

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Classification Workflow

### Step-by-Step Process

1. **Load Model**: Read trained classifier (`.pkl` file) with embedded metadata
2. **Load Sample**: Read methylation sample HDF5 file
3. **Extract DMPs**: Get methylation values at discriminative positions
4. **Calculate Probabilities**: Compute Beta distribution likelihoods for each class
5. **Classify**: Assign sample to class with higher probability
6. **Report Results**: Output class label, probabilities, and confidence metrics

### Probabilistic Classification

MethylClassifier uses **Bayesian probabilistic classification** based on Beta distributions:

For each DMP position *i* and sample *s*:
- Methylation level: x_i ∈ [0, 1]
- Class 0 model: Beta(α₀ᵢ, β₀ᵢ)
- Class 1 model: Beta(α₁ᵢ, β₁ᵢ)

**Likelihood calculation**:
```
P(x_i | Class 0) = Beta_PDF(x_i; α₀ᵢ, β₀ᵢ)
P(x_i | Class 1) = Beta_PDF(x_i; α₁ᵢ, β₁ᵢ)
```

**Log-likelihood aggregation**:
```
L₀ = Σᵢ log P(x_i | Class 0)
L₁ = Σᵢ log P(x_i | Class 1)
```

**Classification decision**:
```
Predicted Class = argmax(L₀, L₁)
Probability = exp(L_k) / (exp(L₀) + exp(L₁))
```

This approach naturally handles:
- Varying methylation levels across positions
- Different discrimination power of each DMP
- Uncertainty quantification via probabilities

## Configuration Details

### Model File Requirements

A valid classifier model must contain:
- **Classifier object**: `ProbabilisticBetaClassifier` with fitted parameters
- **Metadata**: chromosome, context, DMP positions, class names
- **Validation metrics**: accuracy on synthetic test samples

### Sample File Requirements

Input HDF5 files must:
- Follow MethylSample format (from MethylUtils)
- Match model's chromosome and context
- Contain methylation data at DMP positions
- Have minimum coverage (positions with low coverage are excluded)

### Output Format

#### CSV Output Columns

| Column | Description | Example |
|--------|-------------|---------|
| `sample_name` | Sample identifier | `patient_001` |
| `sample_type` | File vs. directory | `file` |
| `predicted_class` | Assigned class | `disease` |
| `class_0_prob` | Probability for class 0 | `0.15` |
| `class_1_prob` | Probability for class 1 | `0.85` |
| `confidence` | max(P₀, P₁) | `0.85` |
| `log_likelihood_0` | Log-likelihood for class 0 | `-145.3` |
| `log_likelihood_1` | Log-likelihood for class 1 | `-89.7` |
| `n_dmps_used` | DMPs with valid data | `487` |
| `n_dmps_total` | Total DMPs in model | `500` |
| `coverage_fraction` | Used/Total DMPs | `0.974` |
| `chromosome` | Genomic region | `chr1` |
| `context` | Methylation context | `CG` |

#### Console Output Example

```
Classifying sample: patient_001_chr1-CG.h5
  DMPs available: 487/500 (97.4%)
  Class 0 (healthy): P = 0.15, LL = -145.3
  Class 1 (disease): P = 0.85, LL = -89.7
  → Predicted: disease (confidence: 85.0%)
```

## Performance Metrics

### Classification Confidence

- **High confidence**: P > 0.9 (90%+)
  - Strong evidence for classification
  - Reliable prediction
  
- **Medium confidence**: 0.7 < P < 0.9
  - Moderate evidence
  - Consider additional validation
  
- **Low confidence**: 0.5 < P < 0.7
  - Weak evidence
  - Borderline case, manual review recommended
  
- **Ambiguous**: P ≈ 0.5
  - No clear preference
  - Sample may not fit either class

### Coverage Requirements

- **Excellent**: >95% DMP coverage
- **Good**: 85-95% DMP coverage
- **Acceptable**: 70-85% DMP coverage
- **Poor**: <70% DMP coverage (classification may be unreliable)

Low coverage can result from:
- Low sequencing depth
- Different genomic regions covered
- Quality filtering removing positions

## Integration with MethylPipeline

### Complete Workflow Example

```bash
# 1. Generate centroids (MethylCentroid)
methylcentroid --config healthy_config.json --output centroids/
methylcentroid --config disease_config.json --output centroids/

# 2. Train classifier (MethylTrainer)
methyltrainer \
  --centroid1 centroids/healthy_chr1-CG.h5 \
  --centroid2 centroids/disease_chr1-CG.h5 \
  --output models/classifier_chr1-CG.pkl

# 3. Classify new samples (MethylClassifier)
methylclassifier \
  --model models/classifier_chr1-CG.pkl \
  --input new_samples/ \
  --output predictions.csv

# 4. Analyze results
python analyze_predictions.py predictions.csv
```

### Multi-Chromosome Classification

```bash
# Classify using all chromosomes
for chrom in chr1 chr2 chr3 chr4 chr5 chr6 chr7 chr8 chr9 chr10 \
             chr11 chr12 chr13 chr14 chr15 chr16 chr17 chr18 chr19 \
             chr20 chr21 chr22 chrX chrY; do
    for context in CG CHG CHH; do
        if [ -f "models/classifier_${chrom}-${context}.pkl" ]; then
            echo "Classifying with ${chrom}-${context}..."
            methylclassifier \
              --model models/classifier_${chrom}-${context}.pkl \
              --input samples/ \
              --output results/predictions_${chrom}-${context}.csv
        fi
    done
done

# Aggregate results
python aggregate_predictions.py results/predictions_*.csv > final_classification.csv
```

## Common Use Cases

### 1. Clinical Sample Classification

```bash
# Classify patient samples for disease prediction
methylclassifier \
  --model models/disease_classifier_chr1-CG.pkl \
  --input patient_samples/ \
  --output clinical_predictions.csv \
  --debug  # Enable detailed output for review
```

### 2. Quality Control

```bash
# Verify sample identity/quality
methylclassifier \
  --model models/tissue_classifier_chr1-CG.pkl \
  --input unknown_sample.h5 \
  --debug

# Check if sample matches expected tissue type
```

### 3. Batch Processing Large Cohorts

```bash
# Process hundreds of samples efficiently
# Input: directory with 1000+ .h5 files
methylclassifier \
  --model models/classifier_chr1-CG.pkl \
  --input large_cohort/ \
  --output cohort_predictions.csv \
  --no-filter  # Process all files regardless of chromosome/context
```

### 4. Research Study Classification

```bash
# Classify experimental samples
for sample_group in control treatment_day1 treatment_day7 treatment_day14; do
    methylclassifier \
      --model models/response_classifier_chr1-CG.pkl \
      --input ${sample_group}/ \
      --output results/${sample_group}_predictions.csv
done
```

## Advanced Features

### Debug Mode

Enable with `--debug` flag for detailed diagnostic output:

```bash
methylclassifier --model model.pkl --input sample.h5 --debug
```

**Debug output includes**:
- Model metadata (DMPs, class names, validation metrics)
- Sample loading details
- DMP-by-DMP probability calculations
- Coverage statistics
- Intermediate likelihood values
- Classification decision reasoning

### Filtering Options

#### Default Behavior (Recommended)
```bash
# Only processes files matching model's chromosome/context
methylclassifier --model classifier_chr1-CG.pkl --input samples/
# Will only process files named *chr1-CG.h5 or chr1-CG.h5
```

#### No Filtering (Process All)
```bash
# Process all .h5 files, attempt classification regardless of chromosome/context
methylclassifier --model classifier_chr1-CG.pkl --input samples/ --no-filter
# Warning: May produce unreliable results if chromosome/context don't match
```

### Handling Missing DMPs

When sample doesn't have data at all DMP positions:
- **Strategy**: Use available DMPs only
- **Minimum**: Require ≥50% DMP coverage for classification
- **Warning**: Log samples with low coverage
- **Output**: Include coverage metrics in results

## Troubleshooting

### Issue: "Chromosome/context mismatch"

**Problem**: Sample file doesn't match model's chromosome/context

**Solutions**:
```bash
# Option 1: Use correct model
methylclassifier --model classifier_chr2-CG.pkl --input sample_chr2-CG.h5

# Option 2: Force classification (use with caution)
methylclassifier --model classifier_chr1-CG.pkl --input sample_chr2-CG.h5 --no-filter
```

### Issue: "Low DMP coverage"

**Problem**: Sample has data at <70% of DMP positions

**Possible causes**:
1. Low sequencing depth
2. Different genomic coverage
3. Quality filtering removed positions

**Solutions**:
- Increase sequencing depth for future samples
- Use model trained with fewer DMPs (more robust)
- Check sample quality metrics

### Issue: "All probabilities near 0.5"

**Problem**: Classifier cannot confidently assign class

**Possible causes**:
1. Sample is genuinely intermediate/mixed
2. Model not well-trained for this sample type
3. Batch effects or technical artifacts

**Solutions**:
- Review model validation metrics
- Check if sample is from expected population
- Consider retraining model with more samples
- Use ensemble of multiple models

### Issue: "Model file not found"

**Solution**:
```bash
# Check file path
ls -lh models/classifier_chr1-CG.pkl

# Use absolute path if needed
methylclassifier --model /full/path/to/model.pkl --input samples/
```

## Python API Usage

For programmatic classification:

```python
from methylclassifier import classify_sample
import pickle

# Load model
with open('model.pkl', 'rb') as f:
    model_data = pickle.load(f)

classifier = model_data['classifier']
metadata = model_data['metadata']

# Classify single sample
result = classify_sample(
    classifier=classifier,
    sample_path='patient_001_chr1-CG.h5',
    metadata=metadata
)

print(f"Predicted class: {result['predicted_class']}")
print(f"Confidence: {result['confidence']:.2%}")
print(f"Probabilities: {result['class_probabilities']}")
```

### Batch Classification API

```python
from methylclassifier import batch_classify
import pandas as pd

# Classify multiple samples
results = batch_classify(
    model_path='model.pkl',
    sample_dir='samples/',
    output_csv='results.csv'
)

# Results as DataFrame
df = pd.DataFrame(results)
print(df[['sample_name', 'predicted_class', 'confidence']].head())
```

## Model Compatibility

### Version Compatibility

- **Model format**: Python pickle (`.pkl`)
- **Python version**: 3.7+
- **Required packages**: numpy, scipy, h5py
- **MethylUtils**: Any version (for sample loading)

### Cross-Platform Support

Models trained on Linux can be used on:
- ✓ Linux
- ✓ macOS
- ✓ Windows (with Python 3.7+)

**Note**: HDF5 file paths in config must be adjusted for platform

## Performance Optimization

### Speed Considerations

- **Single sample**: <1 second
- **Batch (100 samples)**: ~30 seconds
- **Large cohort (1000 samples)**: ~5 minutes

**Factors affecting speed**:
- Number of DMPs in model (500 DMPs: fast, 5000 DMPs: slower)
- HDF5 file size and compression
- Disk I/O speed

### Memory Usage

- **Model size**: 1-10 MB (typically ~5 MB for 500 DMPs)
- **Per-sample processing**: <50 MB RAM
- **Batch processing**: Scales linearly with sample count

## Citation

If you use MethylClassifier in your research, please cite:

```
MethylClassifier: A Command Line Tool for Methylation-Based Sample Classification
[Your citation information here]
```
