# Analysis of pb-hc1-1_config.json

## Summary
The config is mostly complete but is missing several important fields for optimal multi-context analysis.

## ✅ Present and Correct Fields
- All required fields: `chromosome`, `contexts`, `centroid1_dir`, `centroid2_dir`
- Core analysis parameters: `alpha`, `min_delta_mean`, `max_bc`, `gamma`, `temperature`
- Validation setup: `validation_mode: "real"`, validation samples for both centroids
- Calibration: `enable_platt_calibration: true`
- DMP selection: `target_balanced_accuracy`, `min_dmps_for_export`, `n_validation_samples`

## ⚠️ Missing Important Fields

### 1. **Context Weighting (Critical for Multi-Context Analysis)**
```json
"use_context_weights": true,
"trimmed_percentile_low": 0.10,
"trimmed_percentile_high": 0.01
```
**Impact**: Without these, multi-context analysis (CG, CHG, CHH) won't use weighted trimming. These are essential when processing multiple contexts.

**Why it matters**: Context weighting uses trimmed means to weight DMPs across contexts, with low percentile removing bottom 10% (low effect_size DMPs) and high percentile removing top 1% (extreme outliers). This improves multi-context classifier performance.

### 2. **Classifier Configuration**
```json
"classifier_type": "ecdf"
```
**Impact**: The detector uses ECDF-based comparison only. Set explicitly for clarity.

### 3. **DMP Optimization (Optional but Recommended)**
```json
"optimize_dmps": true,
"optimization_method": "featurecuts"  // or "bayesian_optimization"
```
**Impact**: The config has `optimize_for_validation_accuracy: true` which may be deprecated. The modern equivalent is `optimize_dmps: true`. This uses real validation samples to optimize DMP count beyond the binary search.

**Note**: `pc-hc_config.json` has this set to `true` with `optimization_method: "featurecuts"`.

### 4. **Biological Filters (Optional)**
```json
"biological_filters": ["delta_mean", "bhattacharyya"]
```
**Impact**: Defaults to this anyway, but explicit is clearer. These filters ensure DMPs have both minimum effect size (`delta_mean`) and distribution separation (`bhattacharyya`).

### 5. **Coverage Settings (Optional)**
```json
"min_N_pct": 0.10,
"min_sample_coverage": 10
```
**Impact**: Defaults are fine, but explicit values help document expectations. `min_N_pct` controls minimum fraction of samples covering a position (10% default).

### 6. **System Settings (Optional)**
```json
"classifier_coverage_weighting": true,
"eps": 1e-6
```
**Impact**: Defaults are fine for most cases.

## 🔍 Potentially Deprecated Field

### `optimize_for_validation_accuracy: true`
This field is present in the config but **not in the current MethylModelerConfig schema**. It may be deprecated in favor of `optimize_dmps: true`. The field exists in MethylTrainer but appears to be legacy.

**Recommendation**: Replace with `optimize_dmps: true` and `optimization_method: "featurecuts"`.

## 📋 Recommended Complete Config

Here are the fields that should be added to make it fully complete:

```json
{
  "use_context_weights": true,
  "trimmed_percentile_low": 0.10,
  "trimmed_percentile_high": 0.01,
  "classifier_type": "ecdf",
  "optimize_dmps": true,
  "optimization_method": "featurecuts",
  "biological_filters": ["delta_mean", "bhattacharyya"],
  "min_N_pct": 0.10
}
```

And consider replacing:
- `"optimize_for_validation_accuracy": true` → `"optimize_dmps": true`

## Comparison with pc-hc_config.json

`pc-hc_config.json` has these additional fields that `pb-hc1-1_config.json` is missing:
- ✅ `use_context_weights: true`
- ✅ `trimmed_percentile_low: 0.1`
- ✅ `trimmed_percentile_high: 0.01`
- ✅ `classifier_type: "ecdf"`
- ✅ `optimize_dmps: true`
- ✅ `optimization_method: "featurecuts"`

These are the key differences that make `pc-hc_config.json` more complete for multi-context analysis.

