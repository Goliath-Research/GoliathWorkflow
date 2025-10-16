# MethylClassifier Quick Start Guide

## Installation

Already installed as part of MethylPipeline. Use the `mc` wrapper script:

```bash
mc --help
```

## Basic Usage

### 1. Simplest Classification (Smart Defaults)

```bash
mc --model classifier.pkl --input samples/ --output results.csv
```

**What happens:**
- Automatically chooses best prediction method (sklearn for >10 DMPs, beta for ≤10)
- Classifies all samples
- Saves results to CSV

### 2. Using Config File (Recommended)

Create `config.json`:
```json
{
  "model_path": "classifier.pkl",
  "input_path": "samples/",
  "output_path": "results.csv",
  "prediction_method": null
}
```

Run:
```bash
mc --config config.json
```

### 3. Force Fast Method (sklearn)

```bash
mc --model classifier.pkl --input samples/ --use-sklearn
```

Use when:
- You have many DMPs (>10)
- Speed is critical
- 0.15% precision difference is acceptable

### 4. Force Exact Method (beta)

```bash
mc --model classifier.pkl --input samples/ --use-beta
```

Use when:
- You have few DMPs (≤10)
- You need exact Bayesian inference
- You have time to wait (can be slow for >100 DMPs)

## Python API

### Basic Usage

```python
from methyl_classifier import MethylClassifier
import numpy as np

# Load classifier
classifier = MethylClassifier()
classifier.load_classifier('model.pkl')

# Classify samples (smart default)
methylation_data = np.array([...])  # Shape: (n_samples, n_dmps)
probabilities = classifier.predict_proba(methylation_data)
predictions = classifier.predict(methylation_data)

print(f"Sample 1: Class {predictions[0]}, P={probabilities[0]}")
```

### Force Specific Method

```python
# Force sklearn (fast)
probs_fast = classifier.predict_proba(data, use_sklearn=True)

# Force beta (exact)
probs_exact = classifier.predict_proba(data, use_sklearn=False)

# Compare methods
diff = abs(probs_fast - probs_exact).mean() * 100
print(f"Difference: {diff:.3f}%")
```

### Using Config Files

```python
from methyl_classifier.config_schema import ClassificationConfig
from pathlib import Path

# Create config
config = ClassificationConfig(
    model_path="classifier.pkl",
    input_path="samples/",
    output_path="results.csv",
    prediction_method=None  # Smart default
)

# Save for later
config.to_json(Path("my_config.json"))

# Load and use
config = ClassificationConfig.from_json(Path("my_config.json"))
```

## Understanding Output

### Console Output

```
📋 Classifier trained on chromosome chr1, context CG
🧠 Using smart default (sklearn for >10 DMPs, beta for ≤10 DMPs)
🔍 Loading samples from: samples/
📊 Extracting features for 48 samples...
🤖 Classifying samples using sklearn (fast) method...

📋 Classification Results:
Sample                              Type         Predicted    Prob_Class0  Prob_Class1  Coverage  DMPs
------------------------------------------------------------------------------------------------
sample_001                          real_sample  Class_0      0.8234       0.1766       15.3      19543/20000
sample_002                          real_sample  Class_1      0.1234       0.8766       14.8      19432/20000
...

Total samples: 48
Class_0: 24 samples
Class_1: 24 samples
```

### CSV Output

```csv
sample,sample_type,prediction,predicted_class,prob_class0,prob_class1,avg_coverage,dmps_used,dmps_total,dmp_coverage_pct
sample_001,real_sample,0,Class_0,0.8234,0.1766,15.3,19543,20000,97.7
sample_002,real_sample,1,Class_1,0.1234,0.8766,14.8,19432,20000,97.2
```

## Smart Default Logic

| DMPs | Method | Rationale |
|------|--------|-----------|
| ≤10  | beta   | Fast enough (<5ms), exact Bayesian |
| >10  | sklearn| Much faster, excellent precision (0.15% diff) |

**Override:** Metadata in model always takes precedence

## Common Workflows

### Workflow 1: Production Classification

```bash
# Create reproducible config
cat > production_config.json << 'EOF'
{
  "model_path": "production/classifier-chr1-CG.pkl",
  "input_path": "production/samples/",
  "output_path": "production/results.csv",
  "prediction_method": "sklearn",
  "log_level": "INFO"
}
EOF

# Run classification
mc --config production_config.json
```

### Workflow 2: Validation Study

```bash
# Compare both methods
mc --model classifier.pkl --input validation_samples/ --use-sklearn --output results_sklearn.csv
mc --model classifier.pkl --input validation_samples/ --use-beta --output results_beta.csv

# Analyze differences
python compare_results.py results_sklearn.csv results_beta.csv
```

### Workflow 3: Debug Single Sample

```bash
mc --model classifier.pkl --input problem_sample.h5 --debug --log-level DEBUG
```

## Performance Tips

### For Speed (Production)
✅ Use sklearn: `--use-sklearn`
✅ Use config files to avoid repeated typing
✅ Smart default works well for most cases

### For Precision (Validation)
✅ Use beta for few DMPs: `--use-beta`
✅ Compare both methods to verify
✅ Smart default gives exact inference for ≤10 DMPs

### For Large Batches
✅ Use smart default (automatically optimal)
✅ Process by chromosome/context to parallelize
✅ Use config files for reproducibility

## Troubleshooting

### Issue: Classification is slow

**Solution:** Check prediction method
```bash
# If you see "beta (exact)" for >100 DMPs, force sklearn:
mc --model classifier.pkl --input samples/ --use-sklearn
```

### Issue: Low DMP coverage

**Solution:** Check chromosome/context matching
```bash
# Disable filtering to see all files:
mc --model classifier.pkl --input samples/ --no-filter --debug
```

### Issue: Config file not found

**Solution:** Use absolute paths
```json
{
  "model_path": "/full/path/to/classifier.pkl",
  "input_path": "/full/path/to/samples/"
}
```

## Next Steps

- Read [SMART_DEFAULTS.md](SMART_DEFAULTS.md) for detailed logic
- Read [CONFIG_FILE_GUIDE.md](CONFIG_FILE_GUIDE.md) for advanced config usage
- Read [PRECISION_ANALYSIS.md](../../PRECISION_ANALYSIS.md) for method comparison
- Check [example_config.json](example_config.json) for all options

## Summary

**For most users:**
```bash
mc --config config.json  # Smart defaults work great!
```

**For speed-critical:**
```bash
mc --config config.json --use-sklearn  # 28,000x faster
```

**For validation:**
```bash
mc --config config.json --use-beta  # Exact inference
```

That's it! 🎉

