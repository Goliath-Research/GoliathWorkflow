# MethylModeler: Comprehensive Documentation

## Table of Contents

1. [Overview](#overview)
2. [Mathematical Theory](#mathematical-theory)
3. [Core Concepts](#core-concepts)
4. [DMP Detection Algorithm](#dmp-detection-algorithm)
5. [DMP Filtering and Selection](#dmp-filtering-and-selection)
6. [Classifier Training](#classifier-training)
7. [API Reference](#api-reference)
8. [Configuration](#configuration)
9. [Advanced Features](#advanced-features)
10. [Usage Examples](#usage-examples)
11. [Troubleshooting](#troubleshooting)
12. [Integration with MethylPipeline](#integration-with-methylpipeline)
13. [Performance](#performance)
14. [License](#license)

---

## Overview

**MethylModeler** is a production-ready pipeline for detecting differentially methylated positions (DMPs) between two methylation centroids. It combines statistical rigor with biological relevance to identify positions that truly discriminate between experimental groups.

### What is MethylModeler?

MethylModeler compares two centroids (representing different biological conditions) to identify positions where methylation significantly differs:

- **Statistical DMP Detection**: Likelihood ratio tests with FDR correction (Storey's q-value method)
- **Biological Filtering**: Multi-factor importance ranking (effect size, variance reliability, statistical significance, context weighting)
- **Classifier Training**: Automatic training of hybrid Beta/Normal Bayesian classifiers on selected DMPs
- **Validation**: Real or synthetic sample validation with Balanced Accuracy
- **Model Packaging**: Complete model serialization with metadata for deployment

### Key Features

- **Robust Statistics**: Likelihood ratio tests for Beta distributions with Storey's FDR correction
- **Biological Relevance**: Multi-criteria filtering (effect size, overlap, divergence)
- **Balanced Accuracy**: Class-imbalance robust metric for DMP selection
- **GPU Accelerated**: Leverages MethylUtils for 10-50x speedup
- **Flexible Validation**: Real samples from config or centroid metadata, or synthetic samples
- **Gene-Level Analysis**: Feature importance aggregation by gene
- **Production Ready**: Complete model packaging for deployment

---

## Mathematical Theory

### DMP Detection: Likelihood Ratio Test

For each genomic position, test the hypothesis:

$$
H_0: \text{Beta}(\alpha_1, \beta_1) = \text{Beta}(\alpha_2, \beta_2)
$$

**Test Statistic**:

$$
\Lambda = -2\log\frac{\mathcal{L}(H_0)}{\mathcal{L}(H_1)}
$$

where:
- $\mathcal{L}(H_0)$: Likelihood under null (pooled parameters)
- $\mathcal{L}(H_1)$: Likelihood under alternative (separate parameters)

Under $H_0$, $\Lambda \sim \chi^2_2$ with 2 degrees of freedom.

**P-value**:

$$
p = P(\chi^2_2 \geq \Lambda) = 1 - F_{\chi^2_2}(\Lambda)
$$

### FDR Correction: Storey's q-value Method

Given $m$ positions with p-values $p_1, \ldots, p_m$:

**Step 1: Estimate $\pi_0$ (proportion of true nulls)**

$$
\hat{\pi}_0(\lambda) = \frac{\#\{p_i > \lambda\}}{m(1-\lambda)}
$$

**Step 2: Compute q-values** (sorted p-values):

$$
q_{(i)} = \min_{j \geq i} \left\{\hat{\pi}_0 \cdot \frac{m \cdot p_{(j)}}{j}\right\}
$$

**Advantage**: More powerful than Benjamini-Hochberg for genomics data with many true nulls.

### Effect Size Metrics

#### Delta Mean

Absolute difference in mean methylation:

$$
\Delta\mu = |\mu_1 - \mu_2| = \left|\frac{\alpha_1}{\alpha_1 + \beta_1} - \frac{\alpha_2}{\alpha_2 + \beta_2}\right|
$$

#### Bhattacharyya Coefficient

Distribution overlap measure:

$$
BC(\alpha_1, \beta_1, \alpha_2, \beta_2) = \frac{B\left(\frac{\alpha_1 + \alpha_2}{2}, \frac{\beta_1 + \beta_2}{2}\right)}{\sqrt{B(\alpha_1, \beta_1) \cdot B(\alpha_2, \beta_2)}}
$$

Where $B(\alpha, \beta)$ is the Beta function.

**Interpretation**:
- $BC \approx 1$: High overlap (poor discrimination)
- $BC \approx 0$: Low overlap (good discrimination)

#### Jeffreys Divergence

Symmetric information-theoretic distance:

$$
D_{\text{Jeffreys}} = D_{\text{KL}}(P_1 \| P_2) + D_{\text{KL}}(P_2 \| P_1)
$$

where for Beta distributions:

$$
D_{\text{KL}}(P_1 \| P_2) = \log\frac{B(\alpha_2, \beta_2)}{B(\alpha_1, \beta_1)} + (\alpha_1 - \alpha_2)[\psi(\alpha_1) - \psi(\alpha_1 + \beta_1)]
$$
$$
+ (\beta_1 - \beta_2)[\psi(\beta_1) - \psi(\alpha_1 + \beta_1)]
$$

$\psi$ is the digamma function.

#### Cohen's d

Standardized effect size:

$$
d = \frac{\mu_1 - \mu_2}{\sqrt{\frac{\sigma_1^2 + \sigma_2^2}{2}}}
$$

For Beta distributions:

$$
\sigma^2 = \frac{\alpha\beta}{(\alpha + \beta)^2(\alpha + \beta + 1)}
$$

### Biological Importance

**Biological importance** combines multiple factors to prioritize DMPs that are both statistically significant and biologically meaningful:

#### Importance Formula

$$
\text{Importance} = \text{effect_size} \times \text{variance_reliability} \times \text{significance_factor} \times \text{context_weight}
$$

#### 1. Effect Size (Foundation)

Effect size includes statistical corrections already:
- **Between-centroid variance**: $\text{effect_size} = |\Delta\mu| / \sqrt{\text{var}_1 + \text{var}_2}$
- **Distribution overlap**: $\text{effect_size} = \text{effect_size} \times (1 - BC)^\gamma$

Where $BC$ is the Bhattacharyya coefficient (0=no overlap, 1=complete overlap).

#### 2. Variance Reliability Factor

Within-centroid measurement quality:
- **Beta distribution variance**: $\text{var} = \frac{\alpha\beta}{(\alpha + \beta)^2(\alpha + \beta + 1)}$
- **Reliability factor**: $\text{variance_reliability} = \frac{1}{1 + \max(\text{var}_1, \text{var}_2) / 0.05}$
- **Effect**: Positions with high variance (noisy measurements) get lower importance

#### 3. Statistical Significance Factor

Extra weighting for more significant DMPs:
- **Significance strength**: $\text{significance_factor} = -\log_{10}(q\text{-value})$
- **Normalized range**: Scaled to [0.5, 2.0] across all DMPs
- **Effect**: More significant DMPs get higher importance

#### 4. Context Weight

Cytosine context reliability:
- **CG contexts**: Weight = 1.0 (most reliable)
- **CHG contexts**: Weight = 0.7
- **CHH contexts**: Weight = 0.5 (least reliable)

#### Complete Importance Interpretation

- **High importance**: Large effect size + low measurement noise + high statistical significance + reliable context
- **Low importance**: Small effect size + noisy measurements + low significance + unreliable context

**Why not double-count corrections?**
- effect_size already includes variance and overlap corrections
- importance adds complementary biological factors without redundancy

### Balanced Accuracy

Robust metric for imbalanced classes:

$$
\text{Balanced Accuracy} = \frac{\text{Sensitivity} + \text{Specificity}}{2}
$$

where:

$$
\text{Sensitivity} = \frac{TP}{TP + FN}, \quad \text{Specificity} = \frac{TN}{TN + FP}
$$

**Why Balanced Accuracy?**
- Robust to class imbalance (common in healthy vs cancer)
- Treats both classes equally
- Better than AUC for imbalanced data

### Theoretical AUC Computation

From likelihood ratio distribution moments:

$$
\text{AUC} = \Phi\left(\frac{\mu_{\text{LLR}}}{\sqrt{2\sigma^2_{\text{LLR}}}}\right)
$$

where $\Phi$ is the standard normal CDF, and $\mu_{\text{LLR}}, \sigma^2_{\text{LLR}}$ are computed from Beta distribution parameters.

---

## Core Concepts

### 1. Differentially Methylated Positions (DMPs)

**Definition**: Genomic positions where methylation significantly differs between two groups.

**Criteria**:
1. **Statistical Significance**: $q$-value < $\alpha$ (typically 0.05)
2. **Biological Relevance**: Sufficient effect size, low overlap
3. **Discriminative Power**: High Balanced Accuracy or AUC

### 2. Centroid Comparison Workflow

```
1. Load Centroids
   ├─ Centroid 1 (e.g., Healthy)
   └─ Centroid 2 (e.g., Cancer)

2. Find Common Positions
   └─ Intersection of genomic positions

3. Statistical Testing
   ├─ Estimate Beta parameters (MLE)
   ├─ Likelihood ratio tests
   └─ FDR correction (Storey's method)

4. Effect Size Computation
   ├─ Delta mean
   ├─ Bhattacharyya coefficient
   ├─ Jeffreys divergence
   └─ Cohen's d

5. DMP Filtering
   ├─ Coverage threshold (min_N_pct)
   ├─ Effect size threshold (min_delta_mean)
   ├─ Overlap threshold (max_bc)
   └─ Biological importance ranking

6. Binary Search for Optimal DMPs
   ├─ Target: Balanced Accuracy ≥ 0.95
   ├─ Start: All significant DMPs
   ├─ Iterate: Remove least important DMPs
   └─ Stop: Target achieved or minimum reached

7. Classifier Training
   ├─ Train ProbabilisticBetaClassifier
   ├─ Validate on real or synthetic samples
   └─ Package model with metadata
```

### 3. Validation Modes

#### Real Sample Validation

Uses actual samples from:
1. **Config explicit**: `centroid1_validation_samples` and `centroid2_validation_samples`
2. **Centroid metadata fallback**: `centroid1.samples` and `centroid2.samples`

#### Synthetic Sample Validation

Generates samples from Beta distributions when real samples unavailable:

$$
x_i \sim \text{Beta}(\alpha_{k,i}, \beta_{k,i}) \quad \text{for class } k
$$

### 4. Binary Search for DMP Selection

**Goal**: Find minimum DMP subset achieving target Balanced Accuracy.

**Algorithm**:
```
low = min_dmps (e.g., 10)
high = total_dmps

while low < high:
    mid = (low + high) // 2
    
    # Select top mid DMPs by importance
    selected_dmps = top_k_dmps(mid)
    
    # Train classifier on selected DMPs
    classifier = train(selected_dmps)
    
    # Validate
    balanced_acc = validate(classifier, validation_samples)
    
    if balanced_acc >= target_balanced_accuracy:
        high = mid  # Try fewer DMPs
    else:
        low = mid + 1  # Need more DMPs

return selected_dmps
```

**Biological Importance Ranking**:

$$
\text{Importance}_i = w_1 \cdot \Delta\mu_i + w_2 \cdot (1 - BC_i) + w_3 \cdot D_{\text{Jeffreys}, i}
$$

Default weights: $w_1 = w_2 = w_3 = 1/3$ (equal weighting).

---

## DMP Detection Algorithm

### Step-by-Step Process

#### Step 1: Load and Validate Centroids

```python
from methyl_utils import MethylSample

centroid1 = MethylSample.load_from_h5(centroid1_path)
centroid2 = MethylSample.load_from_h5(centroid2_path)

# Validate centroids
assert centroid1.is_centroid, "Centroid 1 must have N field"
assert centroid2.is_centroid, "Centroid 2 must have N field"
```

#### Step 2: Find Common Positions

```python
import numpy as np

# Intersection of positions
common_pos = np.intersect1d(centroid1.pos, centroid2.pos)

# Align centroids to common positions
c1_aligned = centroid1.align_to_positions(common_pos)
c2_aligned = centroid2.align_to_positions(common_pos)
```

#### Step 3: Statistical Comparison

```python
from methyl_utils import MethylCentroidPair

pair = MethylCentroidPair(
    centroid1=centroid1,
    centroid2=centroid2,
    alpha=0.05,
    use_gpu=True
)

# Detect DMPs with statistical testing and FDR correction
dmps = pair.find_dmps(
    min_delta_mean=0.0,  # Apply later in filtering
    min_N_pct=0.10       # Minimum 10% sample coverage
)

# dmps DataFrame contains:
# - position, p_value, q_value
# - alpha1, beta1, alpha2, beta2 (Beta parameters)
# - mean1, mean2, delta_mean
# - bhattacharyya distance
```

#### Step 4: Apply Biological Filtering

```python
# Filter by significance
significant_dmps = dmps[dmps['q_value'] < alpha]

# Filter by effect size
filtered_dmps = significant_dmps[
    (significant_dmps['delta_mean'].abs() >= min_delta_mean) &
    (significant_dmps['bhattacharyya'] <= max_bc)  # Low overlap
]

print(f"Significant DMPs: {len(significant_dmps)}")
print(f"After filtering: {len(filtered_dmps)}")
```

#### Step 5: Compute Biological Importance

```python
def compute_biological_importance(dmps_df):
    """
    Compute biological importance score.

    Importance = effect_size × variance_reliability × significance_factor × context_weight

    effect_size already includes:
    - Between-centroid variance correction: |Δμ| / √(var₁ + var₂)
    - Distribution overlap correction: × (1 - BC)^γ

    importance adds biological factors:
    - Within-centroid variance reliability: reduces weight for noisy measurements
    - Statistical significance: higher weight for more significant DMPs (-log10(q_value))
    - Context reliability: CG > CHG > CHH prioritization
    """

    # Start with effect_size (already includes statistical corrections)
    importance = dmps_df['effect_size'].copy()

    # Add within-centroid variance reliability
    if all(col in dmps_df.columns for col in ['alpha1', 'beta1', 'alpha2', 'beta2']):
        # Compute variance for each centroid
        tau1 = dmps_df['alpha1'] + dmps_df['beta1']
        tau2 = dmps_df['alpha2'] + dmps_df['beta2']
        var1 = (dmps_df['alpha1'] * dmps_df['beta1']) / (tau1**2 * (tau1 + 1))
        var2 = (dmps_df['alpha2'] * dmps_df['beta2']) / (tau2**2 * (tau2 + 1))

        # Variance reliability factor
        max_var = np.maximum(var1, var2)
        var_factor = 1.0 / (1.0 + max_var / 0.05)
        importance = importance * var_factor

    # Add statistical significance
    if 'q_value' in dmps_df.columns:
        eps = 1e-20
        q_value_safe = np.maximum(dmps_df['q_value'], eps)
        significance_factor = -np.log10(q_value_safe)
        sig_min, sig_max = significance_factor.min(), significance_factor.max()
        if sig_max > sig_min:
            sig_normalized = 0.5 + 1.5 * (significance_factor - sig_min) / (sig_max - sig_min)
        else:
            sig_normalized = np.ones(len(dmps_df))
        importance = importance * sig_normalized

    # Apply context weighting
    if 'context_weight' in dmps_df.columns:
        importance = importance * dmps_df['context_weight']

    return importance

dmps_df['importance'] = compute_biological_importance(dmps_df)
dmps_df = dmps_df.sort_values('importance', ascending=False)
```

#### Step 6: Binary Search for Optimal DMP Count

```python
from methyl_utils import ProbabilisticBetaClassifier

def select_dmps_binary_search(dmps_df, target_balanced_accuracy=0.95):
    """Binary search for optimal DMP count."""
    
    min_dmps = 10
    max_dmps = len(dmps_df)
    best_dmps = None
    best_balanced_acc = 0.0
    
    while min_dmps <= max_dmps:
        mid = (min_dmps + max_dmps) // 2
        
        # Select top mid DMPs
        selected = dmps_df.head(mid)
        
        # Train classifier
        classifier = train_classifier(selected)
        
        # Validate
        balanced_acc = validate_classifier(classifier, validation_samples)
        
        if balanced_acc >= target_balanced_accuracy:
            # Target achieved, try fewer DMPs
            best_dmps = selected
            best_balanced_acc = balanced_acc
            max_dmps = mid - 1
        else:
            # Need more DMPs
            min_dmps = mid + 1
    
    return best_dmps, best_balanced_acc
```

#### Step 7: Train Final Classifier

```python
# Prepare training data
training_data = {
    'positions': selected_dmps['position'].values,
    'alpha1': selected_dmps['alpha1'].values,
    'beta1': selected_dmps['beta1'].values,
    'alpha2': selected_dmps['alpha2'].values,
    'beta2': selected_dmps['beta2'].values,
    'weights': selected_dmps['importance'].values,
    'directions': np.sign(selected_dmps['delta_mean']).values
}

# Create classifier
classifier = ProbabilisticBetaClassifier(training_data)

# Validate
validation_accuracy = validate(classifier, validation_samples)
```

#### Step 8: Package and Save Model

```python
import pickle

model_package = {
    'classifier': classifier,
    'dmps': selected_dmps,
    'metadata': {
        'centroid1_path': centroid1_path,
        'centroid2_path': centroid2_path,
        'n_dmps': len(selected_dmps),
        'balanced_accuracy': validation_accuracy,
        'creation_date': datetime.now().isoformat(),
        'version': '1.0.0'
    }
}

with open('model.pkl', 'wb') as f:
    pickle.dump(model_package, f)
```

---

## DMP Filtering and Selection

### Filtering Criteria

#### 1. Coverage Threshold (`min_N_pct`)

Minimum fraction of samples with coverage at a position:

$$
\frac{\min(N_1, N_2)}{\max(\text{total_samples}_1, \text{total_samples}_2)} \geq \text{min_N_pct}
$$

**Purpose**: Ensure sufficient sample support.

#### 2. Effect Size (`min_delta_mean`)

Minimum absolute mean difference:

$$
|\mu_1 - \mu_2| \geq \text{min_delta_mean}
$$

**Typical value**: 0.2 (20% methylation difference)

#### 3. Distribution Overlap (`max_bc`)

Maximum Bhattacharyya coefficient:

$$
BC(\alpha_1, \beta_1, \alpha_2, \beta_2) \leq \text{max_bc}
$$

**Typical value**: 0.6 (40% separation)

#### 4. Statistical Significance

FDR-corrected q-value:

$$
q \leq \alpha
$$

**Typical value**: $\alpha = 0.05$ (5% FDR)

### Biological Importance Ranking

**Multi-Metric Score**:

$$
\text{Importance} = w_1 \cdot \text{norm}(\Delta\mu) + w_2 \cdot \text{norm}(1 - BC) + w_3 \cdot \text{norm}(D_{\text{Jeffreys}})
$$

where $\text{norm}(x) = \frac{x - \min(x)}{\max(x) - \min(x)}$ scales to [0, 1].

**Default Weights**:
- $w_1 = 1/3$: Effect size
- $w_2 = 1/3$: Distribution separation
- $w_3 = 1/3$: Information divergence

### Gene-Level Aggregation

For positions mapped to genes:

$$
\text{Gene Importance} = \sum_{i \in \text{gene}} \text{Importance}_i
$$

**Use Case**: Identify most discriminative genes for biological interpretation.

---

## Classifier Training

### Training Data Format

```python
training_data = {
    'positions': np.array([pos1, pos2, ...]),        # Genomic positions
    'alpha1': np.array([α1_1, α1_2, ...]),          # Beta params class 1
    'beta1': np.array([β1_1, β1_2, ...]),
    'alpha2': np.array([α2_1, α2_2, ...]),          # Beta params class 2
    'beta2': np.array([β2_1, β2_2, ...]),
    'weights': np.array([w1, w2, ...]),             # DMP importance weights
    'directions': np.array([d1, d2, ...])            # Direction indicators
}
```

### Validation Strategies

#### Strategy 1: Real Samples from Config

```json
{
  "validation_mode": "real",
  "centroid1_validation_samples": [
    "/data/healthy/sample1",
    "/data/healthy/sample2"
  ],
  "centroid2_validation_samples": [
    "/data/cancer/sample1",
    "/data/cancer/sample2"
  ]
}
```

#### Strategy 2: Real Samples from Centroid Metadata

```python
# Fallback if not in config
centroid1_samples = centroid1.metadata['samples']
centroid2_samples = centroid2.metadata['samples']
```

#### Strategy 3: Synthetic Samples

```python
# Generate synthetic samples from Beta distributions
def generate_synthetic_samples(alpha, beta, n_samples=100):
    samples = []
    for _ in range(n_samples):
        methylation = np.random.beta(alpha, beta, size=len(alpha))
        samples.append(methylation)
    return np.array(samples)

synthetic_class1 = generate_synthetic_samples(alpha1, beta1)
synthetic_class2 = generate_synthetic_samples(alpha2, beta2)
```

### Performance Metrics

- **Balanced Accuracy**: Primary metric for DMP selection
- **Sensitivity**: True positive rate for each class
- **Specificity**: True negative rate for each class
- **Precision**: Positive predictive value
- **F1 Score**: Harmonic mean of precision and recall

---

## API Reference

### MethylModeler Class

Main class for DMP detection and classifier training:

```python
class MethylModeler:
    def __init__(self, config: MethylModelerConfig):
        """Initialize MethylModeler with configuration."""
    
    def run(self) -> MethylModelerResult:
        """Run complete DMP detection and classifier training pipeline."""
    
    def find_dmps(self) -> pd.DataFrame:
        """Find DMPs using statistical testing."""
    
    def filter_dmps(self, dmps: pd.DataFrame) -> pd.DataFrame:
        """Apply biological filtering to DMPs."""
    
    def train_classifier(self, dmps: pd.DataFrame) -> ProbabilisticBetaClassifier:
        """Train classifier on selected DMPs."""
    
    def validate_classifier(
        self,
        classifier: ProbabilisticBetaClassifier
    ) -> Dict[str, float]:
        """Validate classifier and return metrics."""
```

### MethylModelerConfig Class

Pydantic configuration model:

```python
class MethylModelerConfig(BaseModel):
    # Input files
    centroid1_path: str
    centroid2_path: str
    output_dir: str
    
    # Statistical parameters
    alpha: float = 0.05                           # FDR threshold
    min_N_pct: float = 0.10                       # Coverage threshold
    
    # Biological filtering
    apply_dmp_filtering: bool = True
    min_delta_mean: float = 0.2                   # Effect size threshold
    max_bc: float = 0.6                           # Overlap threshold
    
    # DMP selection
    target_balanced_accuracy: float = 0.95        # Target for binary search
    min_dmps: int = 10                            # Minimum DMPs
    max_dmps: int = 1000                          # Maximum DMPs
    
    # Validation
    validation_mode: str = "real"                 # "real" or "synthetic"
    centroid1_validation_samples: List[str] = []
    centroid2_validation_samples: List[str] = []
    
    # Performance
    use_gpu: bool = True
```

### MethylModelerResult Class

Result container:

```python
class MethylModelerResult(BaseModel):
    # DMPs
    all_dmps: pd.DataFrame                        # All significant DMPs
    filtered_dmps: pd.DataFrame                   # After biological filtering
    selected_dmps: pd.DataFrame                   # Final selected DMPs
    
    # Classifier
    classifier: ProbabilisticBetaClassifier
    classifier_path: str                          # Saved model path
    
    # Validation metrics
    balanced_accuracy: float
    sensitivity: float
    specificity: float
    
    # Gene-level analysis
    gene_importance: Optional[pd.DataFrame]
    
    # Summary
    summary: Dict[str, Any]
```

---

## Configuration

### JSON Configuration Example

```json
{
  "centroid1_path": "/data/healthy_centroid_chr1-CG.h5",
  "centroid2_path": "/data/cancer_centroid_chr1-CG.h5",
  "output_dir": "/output/detector_results",
  
  "alpha": 0.05,
  "min_N_pct": 0.10,
  
  "apply_dmp_filtering": true,
  "min_delta_mean": 0.2,
  "max_bc": 0.6,
  
  "target_balanced_accuracy": 0.95,
  "min_dmps": 10,
  "max_dmps": 500,
  
  "validation_mode": "real",
  "centroid1_validation_samples": [
    "/data/healthy/sample1",
    "/data/healthy/sample2",
    "/data/healthy/sample3"
  ],
  "centroid2_validation_samples": [
    "/data/cancer/sample1",
    "/data/cancer/sample2"
  ],
  
  "use_gpu": true,
  "enable_gene_mapping": true
}
```

### Key Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `alpha` | float | 0.05 | FDR threshold for statistical significance |
| `min_N_pct` | float | 0.10 | Minimum coverage percentage |
| `min_delta_mean` | float | 0.2 | Minimum effect size (20% methylation difference) |
| `max_bc` | float | 0.6 | Maximum Bhattacharyya coefficient (overlap threshold) |
| `target_balanced_accuracy` | float | 0.95 | Target Balanced Accuracy for DMP selection |
| `validation_mode` | str | "real" | Validation mode: "real" or "synthetic" |
| `use_gpu` | bool | True | Enable GPU acceleration |

---

## Advanced Features

### 1. GPU-Optimized Computations

Automatic GPU acceleration via MethylUtils:

```python
# All distance and statistical computations automatically use GPU
pair = MethylCentroidPair(centroid1, centroid2, use_gpu=True)
dmps = pair.find_dmps()  # GPU-accelerated
```

**Performance**: 20-50x speedup for statistical testing and distance calculations.

### 2. Gene-Level Feature Importance

Aggregate DMP importance by gene:

```python
config = MethylModelerConfig(
    ...,
    enable_gene_mapping=True,
    gene_annotation_file="/data/genes.bed"
)

result = detector.run()
gene_importance = result.gene_importance

# Top discriminative genes
top_genes = gene_importance.nlargest(20, 'importance')
print(top_genes[['gene_name', 'importance', 'n_dmps']])
```

### 3. Model Versioning and Metadata

Complete model packaging:

```python
model_package = {
    'classifier': classifier,
    'dmps': selected_dmps,
    'metadata': {
        'version': '1.0.0',
        'creation_date': '2024-10-24',
        'centroid1': {
            'path': centroid1_path,
            'samples': centroid1_samples,
            'group': 'Healthy'
        },
        'centroid2': {
            'path': centroid2_path,
            'samples': centroid2_samples,
            'group': 'Cancer'
        },
        'n_dmps': 150,
        'balanced_accuracy': 0.96,
        'validation_mode': 'real'
    }
}
```

### 4. Incremental Model Updates

Update existing models with new data:

```python
# Load existing model
with open('existing_model.pkl', 'rb') as f:
    old_model = pickle.load(f)

# Detect new DMPs with updated centroids
new_dmps = detector.find_dmps()

# Merge with existing DMPs
merged_dmps = merge_dmp_sets(old_model['dmps'], new_dmps)

# Retrain classifier
updated_classifier = train_classifier(merged_dmps)
```

### 5. Batch Processing Multiple Chromosome/Context Combinations

```python
chromosomes = [str(i) for i in range(1, 23)] + ['X', 'Y']
contexts = ['CG', 'CHG', 'CHH']

for chrom in chromosomes:
    for ctx in contexts:
        config = MethylModelerConfig(
            centroid1_path=f'/data/healthy_chr{chrom}-{ctx}.h5',
            centroid2_path=f'/data/cancer_chr{chrom}-{ctx}.h5',
            output_dir=f'/output/chr{chrom}_{ctx}',
            ...
        )
        
        detector = MethylModeler(config)
        result = detector.run()
        
        print(f"{chrom}-{ctx}: {result.balanced_accuracy:.3f} "
              f"with {len(result.selected_dmps)} DMPs")
```

---

## Usage Examples

### Example 1: Basic DMP Detection

```python
from methyl_modeler import MethylModeler, MethylModelerConfig

# Configure detector
config = MethylModelerConfig(
    centroid1_path='/data/healthy_chr1-CG.h5',
    centroid2_path='/data/cancer_chr1-CG.h5',
    output_dir='/output/dmps',
    alpha=0.05,
    min_delta_mean=0.2,
    target_balanced_accuracy=0.95
)

# Run detection
detector = MethylModeler(config)
result = detector.run()

print(f"Detected {len(result.all_dmps)} significant DMPs")
print(f"Selected {len(result.selected_dmps)} DMPs for classifier")
print(f"Balanced Accuracy: {result.balanced_accuracy:.3f}")

# Save results
result.selected_dmps.to_csv('/output/selected_dmps.csv', index=False)
```

### Example 2: Custom Filtering Thresholds

```python
config = MethylModelerConfig(
    centroid1_path='/data/healthy_chr1-CG.h5',
    centroid2_path='/data/cancer_chr1-CG.h5',
    output_dir='/output/dmps',
    
    # Stricter filtering for highly discriminative DMPs
    min_delta_mean=0.3,      # 30% methylation difference
    max_bc=0.4,              # 60% separation
    target_balanced_accuracy=0.98,  # Very high accuracy
    
    alpha=0.01               # Stricter FDR threshold
)

detector = MethylModeler(config)
result = detector.run()
```

### Example 3: Real Sample Validation

```python
config = MethylModelerConfig(
    centroid1_path='/data/healthy_chr1-CG.h5',
    centroid2_path='/data/cancer_chr1-CG.h5',
    output_dir='/output/dmps',
    
    # Specify validation samples explicitly
    validation_mode='real',
    centroid1_validation_samples=[
        '/data/healthy/val1',
        '/data/healthy/val2',
        '/data/healthy/val3'
    ],
    centroid2_validation_samples=[
        '/data/cancer/val1',
        '/data/cancer/val2'
    ]
)

detector = MethylModeler(config)
result = detector.run()

print(f"Validation Metrics:")
print(f"  Balanced Accuracy: {result.balanced_accuracy:.3f}")
print(f"  Sensitivity: {result.sensitivity:.3f}")
print(f"  Specificity: {result.specificity:.3f}")
```

### Example 4: Gene-Level Analysis

```python
config = MethylModelerConfig(
    centroid1_path='/data/healthy_chr1-CG.h5',
    centroid2_path='/data/cancer_chr1-CG.h5',
    output_dir='/output/dmps',
    
    # Enable gene mapping
    enable_gene_mapping=True,
    gene_annotation_file='/data/hg38_genes.bed'
)

detector = MethylModeler(config)
result = detector.run()

# Analyze gene-level importance
gene_importance = result.gene_importance
top_genes = gene_importance.nlargest(20, 'importance')

print("Top 20 Discriminative Genes:")
for _, row in top_genes.iterrows():
    print(f"  {row['gene_name']}: {row['importance']:.3f} "
          f"({row['n_dmps']} DMPs)")

# Save gene results
gene_importance.to_csv('/output/gene_importance.csv', index=False)
```

### Example 5: Batch Processing

```python
from pathlib import Path
import pandas as pd

# Process all chromosome/context combinations
results_summary = []

chromosomes = ['1', '2', '3', 'X']
contexts = ['CG', 'CHG', 'CHH']

for chrom in chromosomes:
    for ctx in contexts:
        print(f"Processing {chrom}-{ctx}...")
        
        config = MethylModelerConfig(
            centroid1_path=f'/data/healthy_chr{chrom}-{ctx}.h5',
            centroid2_path=f'/data/cancer_chr{chrom}-{ctx}.h5',
            output_dir=f'/output/chr{chrom}_{ctx}',
            alpha=0.05,
            min_delta_mean=0.2,
            target_balanced_accuracy=0.95
        )
        
        try:
            detector = MethylModeler(config)
            result = detector.run()
            
            results_summary.append({
                'chromosome': chrom,
                'context': ctx,
                'n_dmps': len(result.selected_dmps),
                'balanced_accuracy': result.balanced_accuracy,
                'status': 'success'
            })
        except Exception as e:
            print(f"Error processing {chrom}-{ctx}: {e}")
            results_summary.append({
                'chromosome': chrom,
                'context': ctx,
                'status': 'failed',
                'error': str(e)
            })

# Save summary
summary_df = pd.DataFrame(results_summary)
summary_df.to_csv('/output/batch_summary.csv', index=False)
print(summary_df)
```

### Example 6: Model Deployment Pipeline

```python
# Complete pipeline from detection to deployment

# Step 1: Detect DMPs
config = MethylModelerConfig(
    centroid1_path='/data/healthy_chr1-CG.h5',
    centroid2_path='/data/cancer_chr1-CG.h5',
    output_dir='/models/production',
    target_balanced_accuracy=0.95
)

detector = MethylModeler(config)
result = detector.run()

# Step 2: Package model with metadata
model_package = {
    'classifier': result.classifier,
    'dmps': result.selected_dmps,
    'metadata': {
        'model_id': 'cancer_classifier_v1.0',
        'creation_date': datetime.now().isoformat(),
        'balanced_accuracy': result.balanced_accuracy,
        'n_dmps': len(result.selected_dmps),
        'validation_samples': {
            'class1': config.centroid1_validation_samples,
            'class2': config.centroid2_validation_samples
        }
    }
}

# Step 3: Save for deployment
import pickle
with open('/models/production/cancer_classifier_v1.pkl', 'wb') as f:
    pickle.dump(model_package, f)

# Step 4: Create deployment manifest
manifest = {
    'model_path': '/models/production/cancer_classifier_v1.pkl',
    'model_version': '1.0',
    'requires_gpu': True,
    'input_format': 'methylation_levels',
    'output_format': 'class_probabilities',
    'performance': {
        'balanced_accuracy': result.balanced_accuracy,
        'sensitivity': result.sensitivity,
        'specificity': result.specificity
    }
}

with open('/models/production/manifest.json', 'w') as f:
    json.dump(manifest, f, indent=2)

print("Model deployed successfully!")
```

---

## Troubleshooting

### Common Issues and Solutions

#### 1. No DMPs Detected

**Problem**: `find_dmps()` returns empty DataFrame

**Diagnosis**:
```python
pair = MethylCentroidPair(centroid1, centroid2)
stats = pair.compute_statistics()

print(f"Positions tested: {len(stats)}")
print(f"Significant (q < 0.05): {(stats['q_value'] < 0.05).sum()}")
print(f"Mean delta: {stats['delta_mean'].abs().mean():.3f}")
```

**Solutions**:
```python
# Relax filtering thresholds
config = MethylModelerConfig(
    ...,
    alpha=0.10,              # More lenient FDR
    min_delta_mean=0.1,      # Lower effect size threshold
    max_bc=0.8,              # Allow more overlap
    min_N_pct=0.05           # Lower coverage requirement
)

# Check centroid quality
print(f"Centroid 1 positions: {len(centroid1.pos)}")
print(f"Centroid 2 positions: {len(centroid2.pos)}")
print(f"Common positions: {len(np.intersect1d(centroid1.pos, centroid2.pos))}")
```

#### 2. Low Balanced Accuracy

**Problem**: Classifier achieves < target Balanced Accuracy

**Solutions**:
```python
# Lower target
config = MethylModelerConfig(
    ...,
    target_balanced_accuracy=0.90  # More realistic target
)

# Use more DMPs
config = MethylModelerConfig(
    ...,
    max_dmps=2000  # Allow more DMPs
)

# Check validation samples
print(f"Class 1 validation: {len(config.centroid1_validation_samples)}")
print(f"Class 2 validation: {len(config.centroid2_validation_samples)}")

# Try synthetic validation if real samples problematic
config = MethylModelerConfig(
    ...,
    validation_mode='synthetic'
)
```

#### 3. GPU Out of Memory

**Problem**: CUDA out of memory errors

**Solutions**:
```python
# Disable GPU for large datasets
config = MethylModelerConfig(
    ...,
    use_gpu=False
)

# Or process in batches
from methyl_utils import cleanup_gpu_memory

for batch in batches:
    process_batch(batch)
    cleanup_gpu_memory()  # Free GPU memory between batches
```

#### 4. Slow Performance

**Problem**: DMP detection taking too long

**Diagnosis**:
```python
from methyl_utils import start_performance_monitoring, get_performance_profiler

monitor = start_performance_monitoring()
result = detector.run()
profiler = get_performance_profiler()

report = profiler.get_report()
print(f"Total time: {report['total_time']:.2f}s")
print(f"Statistical testing: {report['stat_test_time']:.2f}s")
print(f"Filtering: {report['filter_time']:.2f}s")
```

**Solutions**:
```python
# Enable GPU
config = MethylModelerConfig(..., use_gpu=True)

# Reduce DMP search space
config = MethylModelerConfig(
    ...,
    min_delta_mean=0.3,  # Stricter initial filter
    max_dmps=500         # Limit search space
)

# Use synthetic validation (faster)
config = MethylModelerConfig(..., validation_mode='synthetic')
```

#### 5. Model File Size Too Large

**Problem**: Saved model file is very large

**Solutions**:
```python
# Save only essential data
model_package = {
    'classifier': result.classifier,
    'dmps': result.selected_dmps[['position', 'alpha1', 'beta1', 
                                   'alpha2', 'beta2']],  # Essential columns only
    'metadata': essential_metadata_only
}

# Use compression
import pickle
import gzip

with gzip.open('model.pkl.gz', 'wb') as f:
    pickle.dump(model_package, f)
```

---

## Integration with MethylPipeline

MethylModeler is a central component connecting centroids to classifiers:

### Pipeline Position

```
MethylCentroid (Creates centroids with outlier removal)
        ↓
MethylModeler (Detects DMPs, trains classifier)
        ↓
MethylClassifier (Classifies new samples)
```

### Complete Workflow Example

```python
from methyl_centroid import MethylCentroid, MethylCentroidConfig
from methyl_modeler import MethylModeler, MethylModelerConfig
from methyl_classifier import MethylClassifier

# Step 1: Create centroids
centroid1_config = MethylCentroidConfig(
    laboratory="UCSF",
    disease="Breast Cancer",
    group="Healthy",
    batch="2024-01",
    chrom='1',
    ctx='CG',
    output_dir='./centroids',
    add_samples=healthy_samples,
    α=0.05
)

mc1 = MethylCentroid(**centroid1_config.model_dump())
result1 = mc1.build_centroid()

centroid2_config = MethylCentroidConfig(
    laboratory="UCSF",
    disease="Breast Cancer",
    group="Cancer",
    batch="2024-01",
    chrom='1',
    ctx='CG',
    output_dir='./centroids',
    add_samples=cancer_samples,
    α=0.05
)

mc2 = MethylCentroid(**centroid2_config.model_dump())
result2 = mc2.build_centroid()

# Step 2: Detect DMPs and train classifier
detector_config = MethylModelerConfig(
    centroid1_path=result1.final_centroid_path,
    centroid2_path=result2.final_centroid_path,
    output_dir='./models',
    target_balanced_accuracy=0.95,
    validation_mode='real'
)

detector = MethylModeler(detector_config)
detector_result = detector.run()

# Step 3: Classify new samples
classifier = MethylClassifier(model_path=detector_result.classifier_path)

for new_sample_path in new_samples:
    prediction = classifier.predict(new_sample_path)
    print(f"{new_sample_path}: {prediction.class_name} "
          f"(probability: {prediction.probability:.3f})")
```

---

## Performance

### Computational Complexity

| Operation | Time Complexity | Space Complexity |
|-----------|----------------|------------------|
| Load Centroids | O(P) | O(P) |
| Position Alignment | O(P) | O(P) |
| Statistical Testing | O(P) | O(P) |
| FDR Correction | O(P log P) | O(P) |
| Effect Size Computation | O(P) | O(P) |
| DMP Filtering | O(P) | O(P) |
| Binary Search | O(log D × V) | O(D) |
| Classifier Training | O(D) | O(D) |
| **Total** | **O(P log P + log D × V)** | **O(P)** |

Where:
- P = total genomic positions
- D = number of DMPs
- V = validation samples

### Benchmarks

#### DMP Detection Performance

| Positions | DMPs Found | CPU Time | GPU Time | Speedup |
|-----------|------------|----------|----------|---------|
| 1M | 5K | 30s | 1.5s | 20x |
| 10M | 50K | 300s | 12s | 25x |
| 28M | 150K | 850s | 30s | 28x |

#### Classifier Training Performance

| DMPs | Validation Samples | Training Time | Validation Time |
|------|-------------------|---------------|-----------------|
| 50 | 10 | 0.5s | 0.1s |
| 200 | 50 | 2s | 0.5s |
| 500 | 100 | 5s | 1.2s |

#### Memory Usage

| Dataset Size | Centroids | DMPs | Total Memory |
|--------------|-----------|------|--------------|
| Small (1M pos) | 100 MB | 20 MB | 150 MB |
| Medium (10M pos) | 1 GB | 200 MB | 1.5 GB |
| Large (28M pos) | 2.8 GB | 600 MB | 4 GB |

---

## License

MethylModeler is licensed under the MIT License.

---

## Citation

```bibtex
@software{methylmodeler2024,
  title={MethylModeler: Statistical Detection of Differentially Methylated Positions with Biological Filtering},
  author={MethylPipeline Contributors},
  year={2024},
  url={https://github.com/yourusername/MethylPipeline}
}
```

---

*End of MethylModeler Comprehensive Documentation*

**Last Updated**: October 2024  
**Version**: 1.0.0

