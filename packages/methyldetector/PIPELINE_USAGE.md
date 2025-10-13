# Pipeline Usage Guide

## Overview

MethylDetector now works as part of an integrated pipeline with MethylTrainer to provide complete DMP detection and classifier training functionality.

## Quick Start

### Option 1: Quick Pipeline (Recommended for Testing)

```bash
./quick_pipeline.sh healthy.h5 disease.h5 output/
```

This automatically:
1. Runs MethylDetector to find DMPs
2. Runs MethylTrainer to create a classifier
3. Saves everything to `output/` directory

### Option 2: Full Pipeline (Recommended for Production)

```bash
./run_full_pipeline.sh \
    --centroid1 healthy_chr1-CG.h5 \
    --centroid2 disease_chr1-CG.h5 \
    --output-dir results/ \
    --max-dmps 500 \
    --max-q-value 0.01 \
    --min-jeffreys 0.5 \
    --verbose
```

### Option 3: Manual Step-by-Step

```bash
# Step 1: Detect DMPs
methyldetector --centroid1 healthy.h5 --centroid2 disease.h5 --output dmps/

# Step 2: Train classifier
methyltrainer --centroid1 healthy.h5 --centroid2 disease.h5 --output model.pkl

# Step 3: Classify samples
methylclassifier --model model.pkl --input samples/ --output results.csv
```

## Full Pipeline Options

### Required Arguments
- `--centroid1 PATH` - Path to first centroid HDF5 file
- `--centroid2 PATH` - Path to second centroid HDF5 file

### Optional Arguments

**Output:**
- `--output-dir DIR` - Output directory (default: ./output)

**Metadata:**
- `--chromosome CHR` - Chromosome identifier (e.g., chr1)
- `--context CTX` - Methylation context (e.g., CG, CHG, CHH)

**Training Parameters:**
- `--max-dmps N` - Maximum DMPs for classifier (default: 1000)
- `--max-q-value Q` - Maximum q-value threshold (default: 0.05)
- `--min-jeffreys J` - Minimum Jeffreys divergence (default: 0.3)
- `--min-auc A` - Minimum AUC score (default: 0.6)
- `--alpha A` - Significance level for DMP detection (default: 0.05)

**Execution:**
- `--verbose, -v` - Enable verbose output
- `--skip-detector` - Skip DMP detection (use existing DMPs)
- `--skip-trainer` - Skip classifier training

## Examples

### Basic Usage

```bash
# Simple analysis with defaults
./run_full_pipeline.sh \
    --centroid1 group1.h5 \
    --centroid2 group2.h5 \
    --output-dir my_results/
```

### Advanced: High-Quality Classifier

```bash
# Strict filtering for high-quality DMPs
./run_full_pipeline.sh \
    --centroid1 healthy.h5 \
    --centroid2 disease.h5 \
    --output-dir high_quality/ \
    --max-dmps 500 \
    --max-q-value 0.001 \
    --min-jeffreys 0.8 \
    --min-auc 0.8 \
    --verbose
```

### Chromosome-Specific Analysis

```bash
# Analysis for specific chromosome and context
./run_full_pipeline.sh \
    --centroid1 healthy_chr1-CG.h5 \
    --centroid2 disease_chr1-CG.h5 \
    --chromosome chr1 \
    --context CG \
    --output-dir chr1_results/
```

### Re-train Classifier Only

```bash
# Skip DMP detection, just re-train with different parameters
./run_full_pipeline.sh \
    --centroid1 healthy.h5 \
    --centroid2 disease.h5 \
    --skip-detector \
    --max-dmps 300 \
    --min-jeffreys 0.7
```

### Batch Processing

```bash
# Process multiple chromosomes
for chr in chr{1..22} chrX chrY; do
    for ctx in CG CHG CHH; do
        if [ -f "healthy_${chr}-${ctx}.h5" ]; then
            ./run_full_pipeline.sh \
                --centroid1 "healthy_${chr}-${ctx}.h5" \
                --centroid2 "disease_${chr}-${ctx}.h5" \
                --output-dir "results/${chr}-${ctx}/" \
                --chromosome "$chr" \
                --context "$ctx"
        fi
    done
done
```

## Output Structure

After running the pipeline, you'll have:

```
output/
├── dmps/                                      # DMP Detection Results
│   ├── biological_dmps.csv                    # Filtered DMPs
│   ├── biological_dmps_summary.json           # Statistics
│   └── biological_dmps_analysis_summary.json  # Detailed analysis
└── classifier_chr1-CG.pkl                     # Trained classifier
```

## Using the Classifier

Once you have a trained classifier, use MethylClassifier to classify new samples:

```bash
# Classify samples
methylclassifier --model output/classifier.pkl \
                 --input test_samples/ \
                 --output classification_results.csv
```

## Inspecting Results

### View DMP Summary

```bash
# Summary statistics
cat output/dmps/biological_dmps_analysis_summary.json | python -m json.tool

# Count DMPs
wc -l output/dmps/biological_dmps.csv
```

### Inspect Classifier Model

```python
import pickle

# Load and inspect model
with open('output/classifier.pkl', 'rb') as f:
    model_package = pickle.load(f)

# View metadata
metadata = model_package.get('metadata', {})
print(f"Chromosome: {metadata.get('chromosome')}")
print(f"Context: {metadata.get('context')}")
print(f"Number of DMPs: {metadata.get('n_dmps')}")
print(f"Training date: {metadata.get('training_date')}")
print(f"Validation accuracy: {metadata.get('validation', {}).get('overall_accuracy', 'N/A')}")
```

## Troubleshooting

### No DMPs Found

If you get "No DMPs found after filtering":
1. Relax q-value threshold: `--max-q-value 0.1`
2. Reduce minimum Jeffreys: `--min-jeffreys 0.1`
3. Lower AUC threshold: `--min-auc 0.55`

```bash
./run_full_pipeline.sh \
    --centroid1 c1.h5 \
    --centroid2 c2.h5 \
    --max-q-value 0.1 \
    --min-jeffreys 0.1 \
    --min-auc 0.55
```

### Low Classifier Accuracy

If validation accuracy is low:
1. Increase DMPs: `--max-dmps 2000`
2. Stricter filtering: `--max-q-value 0.01 --min-jeffreys 0.5`
3. Check centroid quality (ensure they're extended_centroid type)

### File Not Found Errors

Ensure:
- Centroid files are in HDF5 format (`.h5`)
- Files are of type `extended_centroid`
- MethylUtils, MethylDetector, and MethylTrainer are installed

```bash
# Verify installations
methyldetector --version
methyltrainer --version
```

## Performance Tips

### For Large Datasets

- Use `--max-dmps 500` to limit classifier size
- Process per-chromosome rather than genome-wide
- Run in parallel for multiple chromosomes

### For Quick Tests

- Use quick_pipeline.sh for rapid iteration
- Start with `--max-dmps 100` for fast training
- Use `--skip-detector` when testing training parameters

## Workflow Diagram

```
┌─────────────────┐
│ Centroid Files  │ (healthy.h5, disease.h5)
└────────┬────────┘
         │
         ▼
┌──────────────────┐
│ run_full_pipeline│.sh
└────────┬─────────┘
         │
         ├─► Step 1: MethylDetector
         │   └─► DMPs (CSV/JSON)
         │
         └─► Step 2: MethylTrainer
             └─► Classifier (PKL)
```

## Integration with Other Tools

### Use with MethylClassifier

```bash
# Complete workflow
./run_full_pipeline.sh --centroid1 c1.h5 --centroid2 c2.h5 --output-dir results/
methylclassifier --model results/classifier.pkl --input samples/ --output predictions.csv
```

### Export for External Tools

DMPs are saved as CSV and can be used with any analysis tool:

```bash
# Load in R
library(data.table)
dmps <- fread("output/dmps/biological_dmps.csv")

# Load in Python
import pandas as pd
dmps = pd.read_csv("output/dmps/biological_dmps.csv")
```

## FAQ

**Q: Do I need to run MethylDetector separately?**  
A: No, `run_full_pipeline.sh` runs it automatically.

**Q: Can I use the same centroids for different parameters?**  
A: Yes, use `--skip-detector` to reuse DMP results.

**Q: How do I know if my classifier is good?**  
A: Check the validation accuracy in the output. >80% is typically good.

**Q: Can I train on one chromosome and classify on another?**  
A: No, the classifier is chromosome/context-specific. Train separate models.

**Q: What if my files don't have chromosome/context in the name?**  
A: Use `--chromosome` and `--context` arguments explicitly.

## See Also

- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture overview
- [INTEGRATION_TESTS.md](../INTEGRATION_TESTS.md) - Testing procedures
- [MethylTrainer README](../MethylTrainer/README.md) - Training tool documentation
- [MethylClassifier README](../MethylClassifier/README.md) - Classification tool documentation

