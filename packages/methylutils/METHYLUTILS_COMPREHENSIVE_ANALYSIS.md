# MethylUtils Comprehensive Analysis

## Overview

MethylUtils is a comprehensive Python package for methylation data analysis, providing efficient data structures and statistical methods for genomic methylation analysis. The package centers around the `MethylSample` class, which represents methylation data at genomic positions, and provides sophisticated probability calculations for sample classification using Beta distributions.

## Core Components

### 1. MethylSample Class

#### Data Structure

The `MethylSample` class is the fundamental data structure in MethylUtils, representing methylation data for a single sample across genomic positions.

**Core Data Fields (always present):**
- `pos`: `np.ndarray` of `uint32` - Genomic positions (sorted)
- `mC`: `np.ndarray` of `uint32` - Methylated cytosine counts
- `uC`: `np.ndarray` of `uint32` - Unmethylated cytosine counts
- `tnc`: `np.ndarray` of `uint8` - Trinucleotide context + strand information

**Centroid-Specific Fields (optional):**
- `N`: `np.ndarray` of `uint32` - Sample counts contributing to each position
- `Sx`: `np.ndarray` of `float32` - Sum of methylation levels
- `Sx2`: `np.ndarray` of `float32` - Sum of squared methylation levels

**Extended Centroid Fields (optional):**
- `log_x_sum`: `np.ndarray` of `float32` - Sum of log(methylation_level)
- `log_1_minus_x_sum`: `np.ndarray` of `float32` - Sum of log(1 - methylation_level)

#### Sample Types

The class supports three distinct types of methylation data:

1. **Sample**: Basic methylation data with raw counts (`pos`, `mC`, `uC`, `tnc`)
2. **Basic Centroid**: Aggregated data from multiple samples (`N`, `Sx`, `Sx2` fields)
3. **Extended Centroid**: Enhanced centroids with log-space statistics for Beta distribution parameter estimation

#### Key Properties

- `sample_type`: Returns "sample", "basic_centroid", or "extended_centroid"
- `is_centroid`: Boolean indicating if the sample represents aggregated data
- `is_extended_centroid`: Boolean indicating if the sample has extended statistics
- `position_count`: Number of genomic positions
- `memory_usage_mb`: Total memory footprint in megabytes

### 2. Centroid Implementation

#### Basic Centroids

Basic centroids aggregate methylation data from multiple samples using method-of-moments (MoM) estimation:

```python
# Beta parameters estimated from aggregated statistics
alpha, beta = beta_mom_estimation(N, Sx, Sx2)
```

Where:
- `N`: Number of samples contributing to each position
- `Sx`: Sum of methylation levels across samples
- `Sx2`: Sum of squared methylation levels

#### Extended Centroids

Extended centroids use maximum likelihood estimation (MLE) with log-space statistics for superior parameter estimation:

```python
# MLE estimation using log-space sums
alpha, beta = beta_mle_estimation(N, log_x_sum, log_1_minus_x_sum)
```

**Advantages of Extended Centroids:**
- More accurate parameter estimation, especially with small sample sizes
- Better handling of extreme methylation values (0.0 or 1.0)
- Improved numerical stability through log-space computations

#### Beta Distribution Parameters

All centroids provide Beta distribution parameters (`α`, `β`) that characterize the methylation distribution at each position:

- **Mean**: `μ = α/(α+β)`
- **Variance**: `σ² = αβ/((α+β)²(α+β+1))`
- **Precision**: `τ = α + β` (total concentration)

### 3. Probability Calculation Methods

#### 3.1 Statistical Test Properties

**Purpose**: Test if a sample belongs to a centroid using statistical hypothesis testing.

**Algorithm**: Adaptive approach based on centroid sample size:
- **Large centroids (N > 30)**: Z-score test using Central Limit Theorem (CLT)
- **Small centroids (N ≤ 30)**: Exact Beta distribution likelihood ratio test

**Large Centroid Approach (CLT):**
```python
# Normal approximation for large sample sizes
centroid_mean = alpha / (alpha + beta)
centroid_var = alpha * beta / ((alpha + beta)**2 * (alpha + beta + 1))
z_score = (sum(sample_meth) - sum(centroid_mean)) / sqrt(sum(centroid_var))
p_value = 2 * (1 - norm.cdf(abs(z_score)))
```

**Small Centroid Approach (Beta exact):**
```python
# Direct Beta distribution evaluation for small sample sizes
log_likelihood = beta.logpdf(sample_meth, alpha, beta)
log_like_diff = log_likelihood - expected_log_likelihood
z_score = mean(log_like_diff) / (std(log_like_diff) / sqrt(n_positions))
p_value = 2 * (1 - norm.cdf(abs(z_score)))
```

**Available Properties:**
- `centroid.z_score(sample)` - Returns the Z-statistic (adaptive method)
- `centroid.p_value(sample)` - Returns the two-tailed p-value (adaptive method)
- `centroid.statistical_test(sample)` - Returns (z_score, p_value) tuple
- `centroid.prob_belongs(sample)` - Legacy method, equivalent to p_value

**Interpretation:**
- p > 0.05: Sample likely belongs to centroid
- p < 0.05: Sample likely does not belong (outlier)
- |z_score| > 1.96: Significant deviation at p < 0.05 level
- **Method automatically chosen** based on centroid size for optimal accuracy

#### 3.2 BetaClassifier.predict_proba() Method

**Purpose**: Classify samples using Bayesian inference with Beta distributions.

**Algorithm**: GPU-accelerated log-likelihood summation with temperature-scaled softmax

```python
# For each class (centroid):
log_likelihood = sum(beta.logpdf(sample_methylation, alpha_class, beta_class))

# Temperature scaling for probability softening
scaled_log_likes = log_likelihoods / temperature

# Numerically stable softmax
max_log_like = max(scaled_log_likes)
likelihood_ratios = exp(scaled_log_likes - max_log_like)
probabilities = likelihood_ratios / sum(likelihood_ratios)
```

**Key Features:**
- Handles missing data through masking
- Uses log-space operations for numerical stability
- Temperature parameter controls probability extremeness
- Supports calibration with Platt scaling

#### 3.3 Extreme Probability Values Issue

**Problem**: Current implementation can return probabilities very close to 0 or 1.

**Root Cause**: Mathematically correct behavior when strong evidence exists from many independent positions.

**Analysis**:
- With 1000+ DMPs, log-likelihood differences can exceed 5000
- `exp(5000)` → ∞, `exp(-5000)` → 0
- This reflects true classification confidence

**Solutions**:
1. **Increase Temperature**: Default 1.0 → 2.0+ for softer probabilities
2. **Alternative Aggregation**: Consider averaging normalized likelihoods
3. **Confidence Intervals**: Provide probability intervals instead of point estimates

**Recommended Fix**: Increase default temperature to 2.0 for more moderate probabilities:

```python
self.temperature = 2.0  # Increased from 1.0 for less extreme probabilities
```

## Usage Examples

### Loading Samples

```python
from methyl_utils import MethylSample

# Load from HDF5 file
sample = MethylSample.load_from_h5("sample.h5")

# Load with position filtering (for DMP-only analysis)
dmp_positions = np.array([100, 200, 300], dtype=np.uint32)
filtered_sample = MethylSample.load_from_h5("sample.h5", positions=dmp_positions)
```

### Working with Centroids

```python
# Check centroid type
if centroid.is_extended_centroid:
    print("Extended centroid with MLE parameters")
    alpha, beta = centroid.get_beta_parameters()

# Get statistical properties
mean_methylation = centroid.mean
variance = centroid.variance
precision = centroid.precision  # tau = alpha + beta

# Statistical testing against samples
z_score = centroid.z_score(test_sample)
p_value = centroid.p_value(test_sample)
z_score, p_value = centroid.statistical_test(test_sample)

# Legacy method (equivalent to p_value)
legacy_p_value = centroid.prob_belongs(test_sample)
```

### Probability Calculations

```python
# Test sample belonging (Z-test approach)
p_value = centroid.prob_belongs(test_sample)
if p_value > 0.05:
    print("Sample belongs to centroid")
else:
    print("Sample is an outlier")

# Bayesian classification (Beta likelihood approach)
classifier = BetaClassifier.from_dataframe(dmp_dataframe)
probabilities = classifier.predict_proba(sample_methylation_matrix)
predicted_class = np.argmax(probabilities, axis=1)
```

## Performance Optimizations

### Memory Efficiency
- Uses compact NumPy dtypes (`uint32`, `uint8`, `float32`)
- Categorical data types for chromosome information
- Optional fields minimize memory footprint

### GPU Acceleration
- CuPy integration for GPU computations
- Automatic CPU/GPU backend selection
- Memory management and cleanup utilities

### HDF5 Optimizations
- Z-standard compression for storage efficiency
- Hyperslice loading for position-filtered access
- Structured array support for fast I/O

## File Structure

```
methylutils/
├── methyl_sample.py          # Core MethylSample class
├── beta_classifier.py        # Bayesian classification
├── beta_analytics.py         # Beta distribution analytics
├── methyl_centroid_pair.py   # Centroid comparison utilities
├── gpu_utils.py              # GPU acceleration utilities
├── statistical_tests.py      # Statistical testing functions
├── metrics_core.py           # Distance and similarity metrics
└── tests/                    # Comprehensive test suite
```

## API Reference

### MethylSample Class

#### Core Methods
- `load_from_h5(file_path, positions=None)` - Load from HDF5 with optional filtering
- `save_to_h5(file_path)` - Save to compressed HDF5 format
- `prob_belongs(sample)` - Test sample membership (Z-test)
- `z_score(sample)` - Calculate Z-score for statistical test
- `p_value(sample)` - Calculate p-value for statistical test
- `statistical_test(sample)` - Get (z_score, p_value) tuple
- `get_beta_parameters()` - Get Beta distribution parameters
- `create_aligned_sample(mask)` - Filter to specific positions

#### Centroid Modification Methods
- `add_sample(sample, use_gpu=True)` - Add a sample to this centroid, returning new centroid
- `remove_sample(sample, use_gpu=True)` - Remove a sample from this centroid, returning new centroid
- `create_centroid_from_samples(samples, use_gpu=True)` - Class method to create centroid from sample list

#### Properties
- `sample_type` - Data type classification
- `is_centroid` - Boolean centroid indicator
- `position_count` - Number of genomic positions
- `memory_usage_mb` - Memory footprint
- `mean` - Beta distribution mean at each position
- `variance` - Beta distribution variance at each position
- `z_score(sample)` - Z-score for statistical test against a sample
- `p_value(sample)` - P-value for statistical test against a sample
- `statistical_test(sample)` - Tuple of (z_score, p_value) for statistical test

### BetaClassifier Class

#### Core Methods
- `predict_proba(X, availability_mask=None, use_gpu=True)` - Predict posterior probabilities (GPU accelerated)
- `predict_log_proba(X, availability_mask=None, use_gpu=True)` - Predict log-probabilities (GPU accelerated)
- `predict(X, availability_mask=None, use_gpu=True)` - Predict class labels (GPU accelerated)
- `predict_proba_calibrated(X, availability_mask=None, use_gpu=True)` - Predict calibrated probabilities (GPU accelerated)
- `set_temperature(temperature)` - Control probability sharpness
- `calibrate_platt(X_val, y_val)` - Platt scaling calibration

#### Class Methods
- `from_dataframe(dmpDF)` - Create from DMP DataFrame
- `from_data_dict(data)` - Create from data dictionary

## Recent Improvements

### 1. Adaptive Statistical Testing

**Issue**: Statistical tests for sample-centroid belonging used only CLT approximation, which is suboptimal for small sample sizes.

**Solution**: Implemented adaptive statistical testing that automatically chooses the appropriate method:
- **Large centroids (N > 30)**: CLT with Normal approximation (fast, good for large N)
- **Small centroids (N ≤ 30)**: Exact Beta distribution likelihood ratio test (accurate for small N)

**Benefits**:
- More accurate p-values for small training sets
- Automatic method selection based on data characteristics
- Maintains backward compatibility

### 2. GPU Acceleration for BetaClassifier

**Issue**: BetaClassifier used CPU-only scipy functions, unlike other MethylUtils components.

**Solution**: Added comprehensive GPU support using CuPy acceleration:
- `predict_proba()`, `predict()`, `predict_log_proba()` all support `use_gpu=True`
- Automatic GPU detection and fallback to CPU
- Consistent with MethylUtils GPU acceleration patterns

**Benefits**:
- Significant performance improvements for large-scale classification
- Consistent API with other MethylUtils components
- Automatic hardware detection

## Usage Examples

### Adaptive Statistical Testing

```python
# Small centroid (N=10) - uses Beta exact method
small_centroid = load_centroid_with_n_samples(10)
p_value = small_centroid.prob_belongs(test_sample)  # Uses Beta distribution

# Large centroid (N=100) - uses CLT method
large_centroid = load_centroid_with_n_samples(100)
p_value = large_centroid.prob_belongs(test_sample)  # Uses Normal approximation

# Method automatically chosen - no code changes needed!
```

### GPU-Accelerated Classification

```python
classifier = BetaClassifier.from_dataframe(dmp_df)

# GPU acceleration automatically enabled
probabilities = classifier.predict_proba(methylation_matrix)  # Uses GPU if available
predictions = classifier.predict(methylation_matrix)          # Uses GPU if available

# Explicit GPU control
probabilities = classifier.predict_proba(methylation_matrix, use_gpu=True)   # Force GPU
probabilities = classifier.predict_proba(methylation_matrix, use_gpu=False)  # Force CPU
```

### Centroid Modification

```python
# Create centroid from multiple samples
samples = [MethylSample.load_from_h5(f"sample_{i}.h5") for i in range(10)]
centroid = MethylSample.create_centroid_from_samples(samples, use_gpu=True)

# Add individual samples to existing centroid
new_sample = MethylSample.load_from_h5("additional_sample.h5")
updated_centroid = centroid.add_sample(new_sample, use_gpu=True)

# Remove outlier sample from centroid
outlier_sample = MethylSample.load_from_h5("outlier.h5")
cleaned_centroid = centroid.remove_sample(outlier_sample, use_gpu=True)

# Save modified centroids
updated_centroid.save_to_h5("expanded_centroid.h5")
cleaned_centroid.save_to_h5("cleaned_centroid.h5")

# GPU control
centroid = MethylSample.create_centroid_from_samples(samples, use_gpu=False)  # Force CPU
```

## Conclusion

MethylUtils provides a robust, efficient framework for methylation data analysis with sophisticated statistical methods. The package now features adaptive statistical testing that chooses the optimal method based on data characteristics and comprehensive GPU acceleration throughout all components. These improvements ensure both accuracy and performance across different use cases while maintaining backward compatibility.
