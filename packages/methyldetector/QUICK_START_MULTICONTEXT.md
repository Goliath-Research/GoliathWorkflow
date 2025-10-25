# Multi-Context MethylDetector - Quick Start Guide

## Overview

Process all methylation contexts (CG, CHG, CHH) for a chromosome in one run with unified Beta-Binomial classification.

## 5-Minute Quick Start

### 1. Prepare Your Data

Organize centroid files by cohort:

```
centroids/
├── healthy/
│   ├── 1-CG.h5
│   ├── 1-CHG.h5
│   └── 1-CHH.h5
└── cancer/
    ├── 1-CG.h5
    ├── 1-CHG.h5
    └── 1-CHH.h5
```

### 2. Create Configuration

`config-chr1.json`:
```json
{
  "chromosome": "1",
  "contexts": ["CG", "CHG", "CHH"],
  "centroid1_dir": "centroids/healthy",
  "centroid2_dir": "centroids/cancer",
  "output_dir": "results/chr1",
  "alpha": 0.01,
  "min_delta_mean": 0.2,
  "max_bc": 0.5,
  "use_context_weights": true,
  "trimmed_percentile": 0.10
}
```

### 3. Run Analysis

```bash
python -m methyl_detector.cli.main --config config-chr1.json
```

### 4. Get Results

**Output files:**
- `results/chr1/dmps-1.csv` - All DMPs with context weights
- `results/chr1/classifier-1.pkl` - Unified Beta-Binomial model

## Python API

### Run Analysis

```python
from methyl_detector.models.config import MethylDetectorConfig
from methyl_detector.core.methyldetector import MethylDetector

config = MethylDetectorConfig.model_validate_json(
    open("config-chr1.json").read()
)

detector = MethylDetector(config)
result = detector.run()

print(f"DMPs: {result.total_biological_dmps}")
print(result.biologically_significant_dmps_df.head())
```

### Load Model and Predict

```python
import pickle
from methyl_utils import MethylSample

# Load model
with open("results/chr1/classifier-1.pkl", "rb") as f:
    pkg = pickle.load(f)

classifier = pkg['classifier']
print(f"Weights: {pkg['context_weights_summary']}")

# Predict on new sample
sample = MethylSample.load_from_h5("new_sample.h5")
pred = classifier.predict_proba(sample)

print(f"Cancer probability: {pred['probability']:.3f}")
print(f"Per-context LLR: {pred['per_context_llr']}")
```

## Key Concepts

### Context Weights

Computed using trimmed-mean (10-90 percentile) of effect sizes:

```python
# Example output
{
    'CG':  0.65,  # Most important
    'CHG': 0.25,
    'CHH': 0.10   # Least important
}
```

### Beta-Binomial Probability

For each site:
```
LLR_i = log P(counts | Cancer) - log P(counts | Healthy)
```

Chromosome score:
```
Δ_k = Σ w_i * LLR_i  (weighted sum across all DMPs)
P(Cancer) = sigmoid(Δ_k)
```

## CSV Output Format

`dmps-{chromosome}.csv`:

| Column | Description |
|--------|-------------|
| chromosome | Chromosome ID (e.g., "1") |
| context | Methylation context (CG, CHG, CHH) |
| position | Genomic position |
| p_value | Statistical significance |
| q_value | FDR-corrected p-value |
| delta_mean | Mean methylation difference |
| delta_sign | Direction of change (+1 or -1) |
| overlap | Bhattacharyya coefficient (0-1) |
| effect_size | Biological importance score |
| context_weight | γ_c for this context |
| alpha1, beta1 | Beta params (centroid 1) |
| alpha2, beta2 | Beta params (centroid 2) |

## Configuration Options

### Required
- `chromosome`: Chromosome to process ("1" to "22", "X", "Y", "M")
- `centroid1_dir`: Directory with centroid1 files
- `centroid2_dir`: Directory with centroid2 files
- `output_dir`: Where to save results

### Optional
- `contexts`: List of contexts (default: ["CG", "CHG", "CHH"])
- `alpha`: Significance threshold (default: 0.05)
- `min_delta_mean`: Min methylation difference (default: 0.2)
- `max_bc`: Max overlap allowed (default: 0.6)
- `use_context_weights`: Enable weighting (default: true)
- `trimmed_percentile`: Trim amount (default: 0.10)
- `use_gpu`: GPU acceleration (default: true)

## Common Tasks

### Process Single Context

Just specify one context:

```json
{
  "contexts": ["CG"]
}
```

### Disable Context Weighting

Use equal weights:

```json
{
  "use_context_weights": false
}
```

### More Aggressive Filtering

```json
{
  "alpha": 0.001,
  "min_delta_mean": 0.3,
  "max_bc": 0.3
}
```

## Troubleshooting

### Missing context file
**Error**: "Centroid1 file not found: .../1-CHH.h5"
**Solution**: Context will be skipped automatically. Ensure at least one context succeeds.

### Memory error
**Solution**: Reduce number of contexts or process chromosomes separately.

### Low context weight
**Warning**: "Context weight is zero"
**Solution**: Automatic fallback to equal weights. Check if DMPs have valid effect_size values.

## Next Steps

1. **Multiple chromosomes**: Run for each chromosome separately
2. **MethylClassifier**: Aggregate all chromosome models for final prediction
3. **Cross-validation**: Test model accuracy on held-out samples
4. **Visualization**: Plot context weights and DMP distributions

## Documentation

- **Full usage guide**: `MULTI_CONTEXT_USAGE.md`
- **Implementation details**: `IMPLEMENTATION_SUMMARY.md`
- **Completion report**: `IMPLEMENTATION_COMPLETE.md`
- **Example config**: `configs/multi-context-example.json`
- **Validation**: Run `python validate_multicontext.py`

## Formula Quick Reference

**Context weight:**
```
γ_c = trimmed_mean(effect_sizes) / Σ trimmed_means
```

**Per-site LLR:**
```
LLR_i = [log B(m+α^C, u+β^C) - log B(α^C, β^C)]
      - [log B(m+α^H, u+β^H) - log B(α^H, β^H)]
```

**Chromosome score:**
```
Δ_k = Σ_i w_i * LLR_i
```

**Probability:**
```
P(Cancer) = 1 / (1 + exp(-Δ_k))
```

## Support

For questions or issues:
1. Check the documentation files
2. Run validation: `python validate_multicontext.py`
3. Review example config: `configs/multi-context-example.json`

---

**Status**: ✅ Implemented and Validated
**Version**: 2.0.0-multi-context

