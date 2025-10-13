# MethylDetector Simplification Refactoring Summary

## Overview
Successfully simplified MethylDetector pipeline to focus on essential filters and binary search selection algorithm. The refactoring maintains DataFrame-centric architecture throughout and removes unused complexity.

## Changes Completed

### Phase 1: Configuration Model Simplification ✅
**File:** `methyl_detector/models/config.py`

**Removed Parameters (~30 parameters):**
- All divergence-related fields (min_divergence, divergence_method)
- Cohen's d filter (min_cohen_d)
- AUC filter (min_auc)
- Concentration filter (min_concentration)
- Overlap filters (min_overlap, max_overlap, min_bhattacharyya)
- Complex weight modes (weight_mode, weight_lambda, weight_I0, kappa_precision, use_precision_weight)
- MLE/MoM parameters (mle_max_iter, mle_tol, mom_var_eps, mom_tau_min, mom_tau_max, mom_only_hard, mom_res_tol)
- Importance mode (importance_mode, bd_cap)
- Data-aware delta mean (use_data_aware_delta_mean, delta_mean_effect_size)
- Multiple selection algorithms (selection_algorithm, selection_metric, target_youden)
- Unused sorting/selection flags (sort_dmps_by_biological_importance, skip_dmp_selection)
- Unused FDR fields (pvalue_aggregation_method, global_significance_threshold)
- gamma (for AUC weighting)

**Retained Essential Parameters (~20 parameters):**
- **Input/Output:** centroid1_path, centroid2_path, output_dir
- **Statistical Filter:** alpha, apply_fdr_correction, fdr_method
- **Coverage:** min_N_pct, min_N_abs
- **Biological Filters:** min_delta_mean, max_bc, biological_filters (simplified to ["delta_mean", "bhattacharyya"])
- **Selection:** min_selected_dmps, target_auc
- **System:** random_state, use_gpu, eps, verbose, generate_histograms

**Result:** Config reduced from ~50 parameters to ~20 essential ones (60% reduction)

### Phase 2: Core Pipeline Simplification ✅
**File:** `methyl_detector/core/methyldetector.py`

**Removed Components:**
- `DMPFilterResult` dataclass (replaced with direct DataFrame usage)
- `DMPData` dataclass (unused, removed)
- Unused metric computations: divergence, Cohen's d, signed_auc, direction, AUC score
- `_compute_biological_significance()` method (replaced with simpler `_compute_biological_importance()`)
- `_compute_weights()` method (gamma transformation removed)
- `_select_top_dmps()` method (replaced with binary search)

**Simplified Methods:**
- `_compute_chunk_metrics_df()`: Now only ensures Bhattacharyya distance is present (already computed by MethylUtils)
- `_apply_biological_filters()`: Only checks delta_mean and bhattacharyya filters
- `_filter_and_select_dmps()`: Streamlined to filter → compute importance → binary search → save
- `_create_final_result()`: Uses biological_importance instead of biological_significance
- `_save_results()`: Updated key_parameters to only include relevant config

**New Methods:**
- `_compute_biological_importance()`: Simple formula `|delta_mean| / (BC + eps)`, no normalization
- `_compute_subset_performance()`: AUC calculation using LLR moments (based on oldselection.py)
- `_select_dmps_binary_search()`: Binary search to find optimal k DMPs (based on oldselection.py)

**DataFrame Columns Maintained:**
- position, chromosome, context
- p_value, q_value
- alpha1, beta1, alpha2, beta2
- mean1, mean2
- delta_mean
- bhattacharyya
- biological_importance (delta_mean / (BC + eps))
- weight (optional, from MethylUtils)

### Phase 3: Binary Search Selection Implementation ✅

**Based on `oldselection.py` approach:**
1. Sort DMPs by biological_importance (descending)
2. Binary search to find minimum k where classifier performance >= target_auc
3. Use `compute_subset_performance()` with LLR moments from MethylUtils
4. Return DataFrame with top k DMPs selected

**Key Features:**
- Efficient O(log n) search complexity
- LLR moment-based performance evaluation
- Automatic orientation detection (direction flipping)
- GPU acceleration support
- Respects min_selected_dmps constraint

### Phase 4: Classifier Training Update ✅

**Updated to match `probabilistic_beta_classifier.py` interface:**
- Builds classifier data directly from DataFrame
- Computes directions using LLR moments (consistent with binary search)
- Creates `ProbabilisticBetaClassifier` instance
- Packages model with metadata (chromosome, context, config)
- Validates on training centroids

**Model Package Contents:**
- classifier: ProbabilisticBetaClassifier instance
- data: Dictionary with positions, alpha/beta parameters, weights, directions
- chromosome: Chromosome identifier
- context: Context identifier
- n_dmps: Number of DMPs
- config: Simplified configuration parameters

### Phase 5: Output Updates ✅

**CSV Output:**
- Saves ALL DataFrame columns for comprehensive analysis
- File: `biological_dmps-{chromosome}-{context}.csv`

**JSON Outputs:**
1. `result-{chromosome}-{context}.json`: Full result object
2. `analysis_summary-{chromosome}-{context}.json`: Summary with key parameters

**Text Summary:**
- Updated to reflect simplified configuration
- Shows alpha, min_delta_mean, max_bc, target_auc
- Reports statistical and biological DMP counts

**Pickle Output:**
- `classifier-{chromosome}-{context}.pkl`: Trained classifier model

## Simplified Pipeline Flow

```
1. Detect Statistical DMPs
   └─ Filter by q_value <= alpha via MethylCentroidPair
   
2. Apply Biological Filters
   ├─ delta_mean >= min_delta_mean
   └─ bhattacharyya >= max_bc
   
3. Compute Biological Importance
   └─ biological_importance = |delta_mean| / (BC + eps)
   
4. Binary Search Selection
   ├─ Sort by biological_importance (descending)
   ├─ Binary search for optimal k (target AUC)
   └─ Return top k DMPs
   
5. Train Classifier
   ├─ Compute directions via LLR moments
   ├─ Create ProbabilisticBetaClassifier
   └─ Save model package (.pkl)
   
6. Save Results
   ├─ CSV: All DataFrame columns
   ├─ JSON: Summary and full results
   └─ TXT: Human-readable summary
```

## Critical Correction: Bhattacharyya Distance vs Coefficient

**Issue Identified:** MethylUtils computes **Bhattacharyya Distance (BD)**, not the Bhattacharyya Coefficient (BC).

**Mathematical Relationship:**
- **BC (Coefficient)**: Overlap measure, range [0,1], where 1 = complete overlap, 0 = no overlap
- **BD (Distance)**: Separation measure, range [0,∞], where 0 = complete overlap, ∞ = complete separation
- **Conversion**: `BC = exp(-BD)` or equivalently `BD = -ln(BC)`

**Corrected Formula:**
```python
# Step 1: Convert BD to BC
bc = np.exp(-bhattacharyya)  # bhattacharyya is actually BD from MethylUtils

# Step 2: Compute biological importance
biological_importance = |delta_mean| / (bc + eps)

# Mathematically equivalent to:
biological_importance = |delta_mean| * exp(BD)
```

**Why This Matters:**
- **Before correction**: Would have incorrectly treated BD as overlap, giving LOW importance to well-separated distributions
- **After correction**: Correctly gives HIGH importance to well-separated distributions (high BD → low BC → high importance)

## Key Improvements

1. **Simplicity**: Reduced from 50+ config parameters to ~20 essential ones
2. **Clarity**: Single biological importance formula: `|delta_mean| / (BC + eps)` where `BC = exp(-BD)`
3. **Efficiency**: Binary search O(log n) vs linear O(n) selection
4. **Consistency**: Same LLR moment calculation in selection and classifier
5. **Maintainability**: Removed unused code paths and complex transformations
6. **DataFrame-centric**: No costly conversions to/from dataclasses or dictionaries
7. **Correctness**: Binary search and classifier based on proven `oldselection.py` approach
8. **Mathematical Accuracy**: Proper handling of Bhattacharyya Distance vs Coefficient

## Backward Compatibility

- Field `top_dmp_significance` in summary JSON now contains biological_importance value
- All essential functionality preserved
- Output file names unchanged
- API compatibility maintained for core methods

## Next Steps

The codebase is now ready for the next phase: updating MethylUtils calculations according to the correct implementation in `oldselection.py`.

## Testing Recommendations

1. Test with sample centroid files
2. Verify binary search convergence
3. Validate classifier training and predictions
4. Check output file formats
5. Confirm GPU acceleration works correctly

