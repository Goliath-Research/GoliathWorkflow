# Multi-Context MethylDetector Usage Guide

## Overview

MethylDetector now supports unified multi-context analysis, processing all methylation contexts (CG, CHG, CHH) for a chromosome in a single run. This produces:

1. **Unified DataFrame**: All contexts combined with context-specific weights
2. **Single CSV Export**: `dmps-{chromosome}.csv` with all contexts
3. **Unified Classifier**: `BetaBinomialClassifier` using Beta-Binomial probability model
4. **Context Weighting**: Trimmed-mean normalization for robust context importance

## Key Features

### Beta-Binomial Classification

The new classifier uses log-likelihood ratios (LLR) based on Beta-Binomial distribution:

```
For each site i with methylated counts m_i, unmethylated u_i:
  LLR_i = log P(m_i, u_i | Cancer) - log P(m_i, u_i | Healthy)

Chromosome score: Δ_k = Σ_i w_i * LLR_i
Probability: P(Cancer | sample) = sigmoid(Δ_k)
```

### Context Weighting

Context weights (γ_c) are computed using trimmed-mean normalization:

1. For each context, compute effect sizes for all DMPs
2. Trim bottom 10% and top 10% (configurable via `trimmed_percentile`)
3. Compute mean of trimmed values
4. Normalize across contexts to sum=1.0

Example weights for prostate cancer chr1:
- CG: 0.65 (most important)
- CHG: 0.25
- CHH: 0.10

## Configuration

### Multi-Context Config Example

```json
{
  "chromosome": "1",
  "contexts": ["CG", "CHG", "CHH"],
  "centroid1_dir": "/path/to/healthy/centroids",
  "centroid2_dir": "/path/to/cancer/centroids",
  "output_dir": "/path/to/output",
  
  "alpha": 0.01,
  "min_delta_mean": 0.2,
  "max_bc": 0.5,
  
  "use_context_weights": true,
  "trimmed_percentile": 0.10,
  "export_all_biological_dmps": true,
  
  "biological_filters": ["delta_mean", "bhattacharyya"],
  "gamma": 1.5,
  "use_gpu": true,
  "random_state": 42
}
```

### Required Directory Structure

Centroid files must follow naming convention: `{chromosome}-{context}.h5`

```
centroids/healthy/
  ├── 1-CG.h5
  ├── 1-CHG.h5
  └── 1-CHH.h5

centroids/cancer/
  ├── 1-CG.h5
  ├── 1-CHG.h5
  └── 1-CHH.h5
```

## Usage

### Python API

```python
from methyl_detector.models.config import MethylDetectorConfig
from methyl_detector.core.methyldetector import MethylDetector

# Load config
config = MethylDetectorConfig.model_validate_json(open("config.json").read())

# Run analysis
detector = MethylDetector(config)
result = detector.run()

# Access results
print(f"Total DMPs: {result.total_biological_dmps}")
print(f"Contexts: {result.biologically_significant_dmps_df['context'].unique()}")
```

### Command Line

```bash
python -m methyl_detector.cli.main --config multi-context-config.json
```

## Outputs

### 1. Unified CSV: `dmps-{chromosome}.csv`

Contains all contexts with columns:

- `chromosome`, `context`, `position`
- `p_value`, `q_value`
- `delta_mean`, `delta_sign`
- `overlap` (Bhattacharyya coefficient)
- `effect_size`
- `context_weight` (γ_c for this position)
- `alpha1`, `beta1`, `alpha2`, `beta2` (Beta parameters)
- `mean1`, `mean2`

Example:
```csv
chromosome,context,position,p_value,q_value,delta_mean,delta_sign,overlap,effect_size,context_weight,alpha1,beta1,alpha2,beta2
1,CG,100234,1.2e-10,5.3e-9,0.35,1.0,0.12,0.85,0.65,12.3,45.7,35.2,10.1
1,CG,100456,2.3e-12,1.1e-10,0.42,-1.0,0.08,0.92,0.65,8.5,50.2,42.1,15.3
1,CHG,100123,3.4e-8,1.2e-6,0.28,1.0,0.25,0.55,0.25,15.2,38.9,28.5,22.1
```

### 2. Classifier Model: `classifier-{chromosome}.pkl`

Pickle file containing:

```python
{
    'classifier': BetaBinomialClassifier(
        chromosome='1',
        positions=[...],
        contexts=[...],
        alpha1=[...], beta1=[...],
        alpha2=[...], beta2=[...],
        weights=[...]
    ),
    'context_weights_summary': {'CG': 0.65, 'CHG': 0.25, 'CHH': 0.10},
    'chromosome': '1',
    'n_dmps': 5432,
    'n_dmps_per_context': {'CG': 3500, 'CHG': 1200, 'CHH': 732},
    'metadata': {...}
}
```

### 3. Loading and Using Model

```python
import pickle
from methyl_utils import MethylSample

# Load model
with open('classifier-1.pkl', 'rb') as f:
    model_pkg = pickle.load(f)

classifier = model_pkg['classifier']
print(classifier)  # BetaBinomialClassifier(chromosome=1, n_dmps=5432, ...)

# Predict on new sample
sample = MethylSample.load_from_h5('new_sample_1-ALL.h5')
prediction = classifier.predict_proba(sample)

print(f"Cancer probability: {prediction['probability']:.3f}")
print(f"Chromosome LLR: {prediction['chromosome_llr']:.2f}")
print(f"Sites used: {prediction['n_sites_used']}")
print(f"Per-context LLR: {prediction['per_context_llr']}")
```

## Backward Compatibility

The old single-context mode still works using the legacy config:

```json
{
  "centroid1_path": "/path/to/centroid1-1-CG.h5",
  "centroid2_path": "/path/to/centroid2-1-CG.h5",
  "output_dir": "/path/to/output",
  "alpha": 0.01,
  ...
}
```

MethylDetector automatically detects which mode to use based on config parameters.

## Migration from Single-Context

To migrate from single-context to multi-context:

1. **Organize centroid files** into directories by cohort
2. **Update config**: Replace `centroid1_path/centroid2_path` with `centroid1_dir/centroid2_dir` and add `chromosome`
3. **Add contexts**: Specify which contexts to process (default: ["CG", "CHG", "CHH"])
4. **Enable weighting**: Set `use_context_weights: true`
5. **Run**: Single execution processes all contexts

## Performance Considerations

- **Memory**: Processes one context at a time, then combines (memory-efficient)
- **GPU**: Automatically uses GPU for statistical tests if available
- **Speed**: ~2-5 minutes per context for chr1 (depends on coverage)
- **Disk**: Unified CSV is larger but more convenient than separate files

## Next Steps: MethylClassifier

The unified chromosome models will be used by MethylClassifier:

1. Load models for all chromosomes
2. Compute per-chromosome LLR (Δ_k) using Beta-Binomial formula
3. Compute chromosome weights (trimmed mean of effect_sizes)
4. Final prediction: Δ_global = Σ_k w_k Δ_k
5. Multi-stage classification: P(Healthy/Early/Intermediate/Late)

## Formula Reference

### Per-site Log-Likelihood Ratio

```
log B(x, y) = log Γ(x) + log Γ(y) - log Γ(x + y)

LLR_i = [log B(m_i + α_i^C, u_i + β_i^C) - log B(α_i^C, β_i^C)]
      - [log B(m_i + α_i^H, u_i + β_i^H) - log B(α_i^H, β_i^H)]
```

### Per-context Chromosome Score

```
Δ_{k,c} = Σ_{i ∈ context c} LLR_i
```

### Weighted Chromosome Score

```
Δ_k = Σ_c γ_c * Δ_{k,c}

where γ_c = context weight (sum to 1.0)
```

### Classification Probability

```
P(Cancer | sample) = 1 / (1 + exp(-Δ_k))
```

## Troubleshooting

### Missing context files
If a context file doesn't exist, it will be skipped with a warning. At least one context must succeed.

### Context weight is zero
If all effect sizes are zero, equal weights (1/n_contexts) are used automatically.

### Memory issues
Reduce number of contexts or process chromosomes separately. GPU memory is monitored automatically.

### Model compatibility
Models trained with multi-context mode are NOT compatible with old single-context classifiers (different mathematical formulation).

## Examples

See `configs/multi-context-example.json` for a complete working example.

For questions, see the main MethylDetector documentation or contact the development team.

