# MethylTrainer: Comprehensive Documentation

## Table of Contents

1. [Overview](#overview)
2. [Mathematical Theory](#mathematical-theory)
3. [Core Concepts](#core-concepts)
4. [Training Algorithm](#training-algorithm)
5. [API Reference](#api-reference)
6. [Configuration](#configuration)
7. [Advanced Features](#advanced-features)
8. [Usage Examples](#usage-examples)
9. [Troubleshooting](#troubleshooting)
10. [Integration with MethylPipeline](#integration-with-methylpipeline)
11. [Performance](#performance)
12. [License](#license)

---

## Overview

**MethylTrainer** is a command-line tool for training Bayesian classifiers from methylation centroid pairs. It provides a streamlined workflow for creating `ProbabilisticBetaClassifier` models that can classify samples based on their methylation patterns.

### What is MethylTrainer?

MethylTrainer focuses on the training aspect of the methylation analysis pipeline:

- **DMP Detection**: Uses `MethylCentroidPair` for robust statistical comparison
- **Biological Filtering**: Multiple criteria for selecting informative DMPs
- **Classifier Training**: Creates probabilistic Beta distribution classifiers
- **Model Validation**: Automatic validation with real or synthetic samples
- **Model Packaging**: Serialization with complete metadata

### Key Features

- **Automated DMP Detection**: Statistical testing with Storey's FDR correction
- **Balanced Accuracy Optimization**: Robust to class imbalance
- **Flexible Validation**: Real samples from config/metadata or synthetic generation
- **Binary Search**: Optimal DMP selection targeting performance metrics
- **Rich Metadata**: Models include training context, validation metrics, and provenance
- **GPU Accelerated**: Leverages MethylUtils for high performance

### MethylTrainer vs MethylDetector

| Aspect | MethylTrainer | MethylDetector |
|--------|---------------|----------------|
| **Focus** | Training classifiers | Complete DMP detection + training |
| **Flexibility** | Command-line focused | Full pipeline with extensive config |
| **Output** | Trained model (.pkl) | DMPs + model + analysis |
| **Use Case** | Quick classifier training | Comprehensive DMP analysis |
| **Gene Analysis** | No | Yes |
| **Visualizations** | No | Optional |

---

## Mathematical Theory

### Bayesian Classification with Beta Distributions

MethylTrainer creates classifiers based on exact Beta distribution likelihoods:

#### Posterior Probability Computation

For a sample with methylation vector $\mathbf{x} = (x_1, \ldots, x_n)$ at $n$ DMPs:

$$
P(\text{Class } k | \mathbf{x}) = \frac{P(\mathbf{x} | \text{Class } k) \cdot P(\text{Class } k)}{\sum_{j=1}^{2} P(\mathbf{x} | \text{Class } j) \cdot P(\text{Class } j)}
$$

#### Likelihood Computation

Assuming independence across DMPs (Naive Bayes):

$$
P(\mathbf{x} | \text{Class } k) = \prod_{i=1}^{n} \text{Beta}(x_i; \alpha_{k,i}, \beta_{k,i})
$$

where:

$$
\text{Beta}(x; \alpha, \beta) = \frac{x^{\alpha-1}(1-x)^{\beta-1}}{B(\alpha, \beta)}
$$

#### Log-Space Computation

For numerical stability:

$$
\log P(\text{Class } k | \mathbf{x}) = \log P(\text{Class } k) + \sum_{i=1}^{n} \log \text{Beta}(x_i; \alpha_{k,i}, \beta_{k,i}) - \log Z
$$

where $Z$ is the normalization constant.

### Balanced Accuracy

Primary metric for model evaluation:

$$
\text{Balanced Accuracy} = \frac{\text{Sensitivity} + \text{Specificity}}{2}
$$

where:

$$
\text{Sensitivity} = \frac{TP}{TP + FN}, \quad \text{Specificity} = \frac{TN}{TN + FP}
$$

**Why Balanced Accuracy?**
- Robust to class imbalance (e.g., 35 healthy vs 12 cancer)
- Treats both classes equally
- More reliable than overall accuracy for imbalanced data

### Log-Likelihood Ratio (LLR)

For discrimination analysis:

$$
LLR(\mathbf{x}) = \log\frac{P(\mathbf{x} | \text{Class 1})}{P(\mathbf{x} | \text{Class 2})} = \sum_{i=1}^{n} \left[\log \text{Beta}(x_i; \alpha_{1,i}, \beta_{1,i}) - \log \text{Beta}(x_i; \alpha_{2,i}, \beta_{2,i})\right]
$$

Used for theoretical performance evaluation.

---

## Core Concepts

### 1. Training Workflow

```
1. Load Centroids
   ├─ Centroid 1 (e.g., Healthy)
   └─ Centroid 2 (e.g., Cancer)

2. Detect DMPs
   ├─ Statistical testing (MethylCentroidPair)
   ├─ FDR correction (Storey's method)
   └─ Initial filtering (coverage, significance)

3. Apply Biological Filters
   ├─ Effect size (min_delta_mean)
   ├─ Distribution overlap (max_bc)
   └─ Importance ranking

4. Binary Search for Optimal DMPs
   ├─ Target: Balanced Accuracy ≥ target
   ├─ Strategy: Minimize DMP count
   └─ Validation: Real or synthetic samples

5. Train Classifier
   ├─ Create ProbabilisticBetaClassifier
   ├─ Set Beta parameters from centroids
   └─ Configure weights and priors

6. Validate Model
   ├─ Load validation samples
   ├─ Predict classes
   ├─ Compute metrics
   └─ Store validation results

7. Package and Save
   ├─ Serialize classifier
   ├─ Include metadata
   ├─ Add validation metrics
   └─ Save as .pkl file
```

### 2. Validation Modes

#### Real Sample Validation

**Priority 1**: Explicit config specification
```json
{
  "centroid1_validation_samples": ["/data/healthy/sample1", ...],
  "centroid2_validation_samples": ["/data/cancer/sample1", ...]
}
```

**Priority 2**: Centroid metadata fallback
```python
# From centroid HDF5 metadata
centroid1.metadata['samples']
centroid2.metadata['samples']
```

#### Synthetic Sample Validation

Generate samples from Beta distributions:

$$
x_i \sim \text{Beta}(\alpha_{k,i}, \beta_{k,i}) \quad \text{for class } k, \text{ position } i
$$

**When to Use**:
- No real validation samples available
- Quick model prototyping
- Theoretical performance bounds

### 3. Binary Search Strategy

**Objective**: Find minimum DMP count achieving target Balanced Accuracy.

**Algorithm**:
```python
def binary_search_dmps(dmps, target_ba=0.95):
    low, high = min_dmps, len(dmps)
    best_result = None
    
    while low <= high:
        mid = (low + high) // 2
        selected = dmps[:mid]  # Top mid DMPs by importance
        
        classifier = train_classifier(selected)
        ba = validate_classifier(classifier)
        
        if ba >= target_ba:
            best_result = (selected, ba)
            high = mid - 1  # Try fewer DMPs
        else:
            low = mid + 1  # Need more DMPs
    
    return best_result
```

**Termination**:
- Target achieved with minimum DMPs
- All DMPs used and target not achieved
- Maximum iterations reached

### 4. Model Structure

Saved model package:

```python
{
    'classifier': ProbabilisticBetaClassifier,
    'metadata': {
        'version': '1.0.0',
        'creation_date': '2024-10-24T10:30:00',
        'centroid1_path': '/data/healthy.h5',
        'centroid2_path': '/data/cancer.h5',
        'n_dmps': 150,
        'balanced_accuracy': 0.96,
        'validation_mode': 'real',
        'target_balanced_accuracy': 0.95,
        'chromosome': '1',
        'context': 'CG'
    },
    'dmps': pd.DataFrame(...),  # Selected DMPs
    'validation_results': {
        'balanced_accuracy': 0.96,
        'sensitivity': 0.95,
        'specificity': 0.97,
        'predictions': [...]
    }
}
```

---

## Training Algorithm

### Step-by-Step Process

#### Step 1: Initialize and Load

```python
from methyl_trainer import MethylTrainer, TrainingConfig

config = TrainingConfig(
    centroid1_path='/data/healthy_chr1-CG.h5',
    centroid2_path='/data/cancer_chr1-CG.h5',
    output_path='/models/classifier.pkl',
    target_balanced_accuracy=0.95
)

trainer = MethylTrainer(config)
```

#### Step 2: Detect DMPs

```python
# Uses MethylCentroidPair internally
dmps_df = trainer._detect_dmps()

# Returns DataFrame with:
# - position, p_value, q_value
# - alpha1, beta1, alpha2, beta2
# - mean1, mean2, delta_mean
# - bhattacharyya
```

#### Step 3: Filter DMPs

```python
# Apply significance filter
significant = dmps_df[dmps_df['q_value'] < config.alpha]

# Apply biological filters
filtered = significant[
    (significant['delta_mean'].abs() >= config.min_delta_mean) &
    (significant['bhattacharyya'] <= config.max_bc)
]

# Compute importance ranking
filtered['importance'] = compute_importance(filtered)
filtered = filtered.sort_values('importance', ascending=False)
```

#### Step 4: Binary Search

```python
selected_dmps, final_ba = trainer._select_dmps_binary_search(
    filtered_dmps,
    target_balanced_accuracy=config.target_balanced_accuracy
)

print(f"Selected {len(selected_dmps)} DMPs")
print(f"Balanced Accuracy: {final_ba:.3f}")
```

#### Step 5: Train Final Classifier

```python
training_data = {
    'positions': selected_dmps['position'].values,
    'alpha1': selected_dmps['alpha1'].values,
    'beta1': selected_dmps['beta1'].values,
    'alpha2': selected_dmps['alpha2'].values,
    'beta2': selected_dmps['beta2'].values,
    'weights': selected_dmps['importance'].values,
    'directions': np.sign(selected_dmps['delta_mean']).values
}

classifier = ProbabilisticBetaClassifier(training_data)
```

#### Step 6: Validate

```python
# Load validation samples
val_samples_1 = load_validation_samples(config.centroid1_validation_samples)
val_samples_2 = load_validation_samples(config.centroid2_validation_samples)

# Extract methylation at DMP positions
X_val = extract_dmp_methylation(val_samples_1 + val_samples_2, selected_dmps)
y_val = create_labels(len(val_samples_1), len(val_samples_2))

# Predict
predictions = classifier.predict(X_val)
probs = classifier.predict_proba(X_val)

# Compute metrics
from sklearn.metrics import confusion_matrix
cm = confusion_matrix(y_val, predictions)

tn, fp, fn, tp = cm.ravel()
sensitivity = tp / (tp + fn)
specificity = tn / (tn + fp)
balanced_accuracy = (sensitivity + specificity) / 2
```

#### Step 7: Package and Save

```python
model_package = {
    'classifier': classifier,
    'metadata': {
        'version': '1.0.0',
        'creation_date': datetime.now().isoformat(),
        'n_dmps': len(selected_dmps),
        'balanced_accuracy': balanced_accuracy,
        # ... more metadata
    },
    'dmps': selected_dmps,
    'validation_results': {
        'balanced_accuracy': balanced_accuracy,
        'sensitivity': sensitivity,
        'specificity': specificity
    }
}

with open(config.output_path, 'wb') as f:
    pickle.dump(model_package, f)
```

---

## API Reference

### MethylTrainer Class

Main training class:

```python
class MethylTrainer:
    def __init__(self, config: TrainingConfig):
        """Initialize trainer with configuration."""
    
    def train(self) -> Dict[str, Any]:
        """
        Execute complete training pipeline.
        
        Returns:
            Dictionary with classifier, metrics, and metadata
        """
    
    def _detect_dmps(self) -> pd.DataFrame:
        """Detect DMPs using MethylCentroidPair."""
    
    def _filter_dmps(self, dmps: pd.DataFrame) -> pd.DataFrame:
        """Apply biological filtering."""
    
    def _select_dmps_binary_search(
        self,
        dmps: pd.DataFrame,
        target_balanced_accuracy: float
    ) -> Tuple[pd.DataFrame, float]:
        """Binary search for optimal DMP subset."""
    
    def _train_classifier(
        self,
        dmps: pd.DataFrame
    ) -> ProbabilisticBetaClassifier:
        """Train classifier on selected DMPs."""
    
    def _validate_classifier(
        self,
        classifier: ProbabilisticBetaClassifier
    ) -> Dict[str, float]:
        """Validate classifier and return metrics."""
```

### TrainingConfig Class

Pydantic configuration model:

```python
class TrainingConfig(BaseModel):
    # Input files
    centroid1_path: str = Field(..., description="Path to centroid 1")
    centroid2_path: str = Field(..., description="Path to centroid 2")
    output_path: str = Field(..., description="Output model path (.pkl)")
    
    # Statistical parameters
    alpha: float = Field(default=0.05, description="FDR threshold")
    min_N_pct: float = Field(default=0.10, description="Min coverage percentage")
    
    # Biological filtering
    min_delta_mean: float = Field(default=0.2, description="Min effect size")
    max_bc: float = Field(default=0.6, description="Max Bhattacharyya coefficient")
    
    # DMP selection
    target_balanced_accuracy: float = Field(default=0.95, description="Target BA")
    min_dmps: int = Field(default=10, description="Minimum DMPs")
    max_dmps: int = Field(default=1000, description="Maximum DMPs")
    
    # Validation
    validation_mode: str = Field(default="real", description="'real' or 'synthetic'")
    centroid1_validation_samples: List[str] = Field(default_factory=list)
    centroid2_validation_samples: List[str] = Field(default_factory=list)
    
    # Performance
    use_gpu: bool = Field(default=True, description="Enable GPU acceleration")
```

### train_from_centroids Function

Convenience function for training:

```python
def train_from_centroids(
    centroid1_path: str,
    centroid2_path: str,
    output_path: str,
    target_balanced_accuracy: float = 0.95,
    **kwargs
) -> Dict[str, Any]:
    """
    Train classifier from centroid pair.
    
    Args:
        centroid1_path: Path to first centroid
        centroid2_path: Path to second centroid
        output_path: Where to save trained model
        target_balanced_accuracy: Target performance metric
        **kwargs: Additional configuration parameters
    
    Returns:
        Dictionary with training results
    """
    config = TrainingConfig(
        centroid1_path=centroid1_path,
        centroid2_path=centroid2_path,
        output_path=output_path,
        target_balanced_accuracy=target_balanced_accuracy,
        **kwargs
    )
    
    trainer = MethylTrainer(config)
    return trainer.train()
```

---

## Configuration

### JSON Configuration Example

```json
{
  "centroid1_path": "/data/healthy_chr1-CG.h5",
  "centroid2_path": "/data/cancer_chr1-CG.h5",
  "output_path": "/models/classifier_chr1-CG.pkl",
  
  "alpha": 0.05,
  "min_N_pct": 0.10,
  
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
  
  "use_gpu": true
}
```

### Command-Line Usage

```bash
# Using config file
methyl_trainer --config training_config.json

# Direct parameters
methyl_trainer \
  --centroid1 /data/healthy_chr1-CG.h5 \
  --centroid2 /data/cancer_chr1-CG.h5 \
  --output /models/classifier.pkl \
  --target-balanced-accuracy 0.95 \
  --min-delta-mean 0.2 \
  --use-gpu
```

### Python API Usage

```python
from methyl_trainer import train_from_centroids

result = train_from_centroids(
    centroid1_path='/data/healthy_chr1-CG.h5',
    centroid2_path='/data/cancer_chr1-CG.h5',
    output_path='/models/classifier.pkl',
    target_balanced_accuracy=0.95,
    min_delta_mean=0.2,
    validation_mode='real'
)

print(f"Trained with {result['n_dmps']} DMPs")
print(f"Balanced Accuracy: {result['balanced_accuracy']:.3f}")
```

---

## Advanced Features

### 1. Flexible Validation Modes

#### Real Sample Validation

```python
config = TrainingConfig(
    ...,
    validation_mode='real',
    # Explicit samples (priority 1)
    centroid1_validation_samples=['/data/healthy/val1', ...],
    centroid2_validation_samples=['/data/cancer/val1', ...]
)

# Or rely on centroid metadata (priority 2)
# Automatically uses centroid1.metadata['samples']
```

#### Synthetic Sample Validation

```python
config = TrainingConfig(
    ...,
    validation_mode='synthetic',
    n_synthetic_samples=100  # Generate 100 samples per class
)
```

### 2. Optimize for Different Metrics

While Balanced Accuracy is default, you can optimize for other metrics:

```python
config = TrainingConfig(
    ...,
    optimize_for_validation_accuracy=True,  # Use overall accuracy instead
    # Or customize in trainer implementation
)
```

### 3. Model Versioning

```python
model_package = {
    'classifier': classifier,
    'metadata': {
        'version': '2.0.1',
        'model_id': 'breast_cancer_classifier',
        'git_commit': 'abc123',
        'training_date': datetime.now().isoformat(),
        'trained_by': 'researcher@institution.edu'
    },
    ...
}
```

### 4. Batch Training

Train multiple models:

```python
from methyl_trainer import train_from_centroids

chromosomes = [str(i) for i in range(1, 23)]
contexts = ['CG', 'CHG', 'CHH']

for chrom in chromosomes:
    for ctx in contexts:
        print(f"Training {chrom}-{ctx}...")
        
        result = train_from_centroids(
            centroid1_path=f'/data/healthy_chr{chrom}-{ctx}.h5',
            centroid2_path=f'/data/cancer_chr{chrom}-{ctx}.h5',
            output_path=f'/models/classifier_chr{chrom}-{ctx}.pkl',
            target_balanced_accuracy=0.95
        )
        
        print(f"  DMPs: {result['n_dmps']}, BA: {result['balanced_accuracy']:.3f}")
```

### 5. Integration with MethylDetector

MethylTrainer and MethylDetector can be used interchangeably:

```python
# MethylDetector: Full pipeline
from methyl_detector import MethylDetector, MethylDetectorConfig

detector_config = MethylDetectorConfig(...)
detector = MethylDetector(detector_config)
detector_result = detector.run()  # DMPs + model + analysis

# MethylTrainer: Focused training
from methyl_trainer import train_from_centroids

trainer_result = train_from_centroids(...)  # Just model

# Both create compatible classifiers for MethylClassifier
```

---

## Usage Examples

### Example 1: Basic Training

```python
from methyl_trainer import train_from_centroids

result = train_from_centroids(
    centroid1_path='/data/healthy_chr1-CG.h5',
    centroid2_path='/data/cancer_chr1-CG.h5',
    output_path='/models/classifier.pkl',
    target_balanced_accuracy=0.95
)

print(f"Training complete!")
print(f"  DMPs selected: {result['n_dmps']}")
print(f"  Balanced Accuracy: {result['balanced_accuracy']:.3f}")
print(f"  Sensitivity: {result['sensitivity']:.3f}")
print(f"  Specificity: {result['specificity']:.3f}")
print(f"  Model saved to: /models/classifier.pkl")
```

### Example 2: Custom Configuration

```python
from methyl_trainer import MethylTrainer, TrainingConfig

config = TrainingConfig(
    centroid1_path='/data/healthy_chr1-CG.h5',
    centroid2_path='/data/cancer_chr1-CG.h5',
    output_path='/models/classifier_strict.pkl',
    
    # Stricter filtering
    alpha=0.01,              # 1% FDR
    min_delta_mean=0.3,      # 30% methylation difference
    max_bc=0.4,              # 60% separation
    
    # Higher performance target
    target_balanced_accuracy=0.98,
    
    # Real sample validation
    validation_mode='real',
    centroid1_validation_samples=[
        '/data/healthy/val1',
        '/data/healthy/val2'
    ],
    centroid2_validation_samples=[
        '/data/cancer/val1',
        '/data/cancer/val2'
    ]
)

trainer = MethylTrainer(config)
result = trainer.train()

print(f"Strict model trained: BA = {result['balanced_accuracy']:.3f}")
```

### Example 3: Synthetic Validation

```python
from methyl_trainer import train_from_centroids

result = train_from_centroids(
    centroid1_path='/data/healthy_chr1-CG.h5',
    centroid2_path='/data/cancer_chr1-CG.h5',
    output_path='/models/classifier_synthetic.pkl',
    
    # Use synthetic validation
    validation_mode='synthetic',
    target_balanced_accuracy=0.95
)

print(f"Model trained with synthetic validation")
print(f"  Theoretical BA: {result['balanced_accuracy']:.3f}")
```

### Example 4: Batch Training Pipeline

```python
from methyl_trainer import train_from_centroids
import pandas as pd

# Train models for all chromosomes
results = []

for chrom in ['1', '2', '3', 'X']:
    for ctx in ['CG', 'CHG']:
        print(f"Training {chrom}-{ctx}...")
        
        try:
            result = train_from_centroids(
                centroid1_path=f'/data/healthy_chr{chrom}-{ctx}.h5',
                centroid2_path=f'/data/cancer_chr{chrom}-{ctx}.h5',
                output_path=f'/models/classifier_chr{chrom}-{ctx}.pkl',
                target_balanced_accuracy=0.95
            )
            
            results.append({
                'chromosome': chrom,
                'context': ctx,
                'n_dmps': result['n_dmps'],
                'balanced_accuracy': result['balanced_accuracy'],
                'status': 'success'
            })
            
        except Exception as e:
            print(f"  Error: {e}")
            results.append({
                'chromosome': chrom,
                'context': ctx,
                'status': 'failed',
                'error': str(e)
            })

# Save summary
summary_df = pd.DataFrame(results)
summary_df.to_csv('/models/training_summary.csv', index=False)
print(summary_df)
```

### Example 5: Model Inspection

```python
import pickle

# Load trained model
with open('/models/classifier.pkl', 'rb') as f:
    model_package = pickle.load(f)

# Inspect
print("Model Metadata:")
for key, value in model_package['metadata'].items():
    print(f"  {key}: {value}")

print(f"\nDMPs: {len(model_package['dmps'])}")
print(model_package['dmps'].head())

print(f"\nValidation Results:")
for metric, value in model_package['validation_results'].items():
    if isinstance(value, float):
        print(f"  {metric}: {value:.3f}")
```

### Example 6: Integration with MethylClassifier

```python
from methyl_trainer import train_from_centroids
from methyl_classifier import MethylClassifier

# Step 1: Train model
train_result = train_from_centroids(
    centroid1_path='/data/healthy_chr1-CG.h5',
    centroid2_path='/data/cancer_chr1-CG.h5',
    output_path='/models/classifier.pkl',
    target_balanced_accuracy=0.95
)

print(f"Model trained: BA = {train_result['balanced_accuracy']:.3f}")

# Step 2: Load and use classifier
classifier = MethylClassifier(model_path='/models/classifier.pkl')

# Step 3: Classify new samples
for sample_path in new_samples:
    prediction = classifier.predict(sample_path)
    print(f"{sample_path}: {prediction.class_name} "
          f"(prob={prediction.probability:.3f})")
```

---

## Troubleshooting

### Common Issues

#### 1. Low Balanced Accuracy

**Problem**: Cannot achieve target Balanced Accuracy

**Solutions**:
```python
# Lower the target
config = TrainingConfig(
    ...,
    target_balanced_accuracy=0.90  # More realistic
)

# Use more DMPs
config = TrainingConfig(
    ...,
    max_dmps=1000  # Allow more DMPs
)

# Relax filtering
config = TrainingConfig(
    ...,
    min_delta_mean=0.1,  # Lower threshold
    max_bc=0.8           # More lenient
)
```

#### 2. No DMPs Found

**Problem**: DMP detection returns empty set

**Solutions**:
```python
# Check centroids
from methyl_utils import MethylSample

c1 = MethylSample.load_from_h5(centroid1_path)
c2 = MethylSample.load_from_h5(centroid2_path)

print(f"Centroid 1: {len(c1.pos)} positions")
print(f"Centroid 2: {len(c2.pos)} positions")
print(f"Common: {len(np.intersect1d(c1.pos, c2.pos))}")

# Relax significance threshold
config = TrainingConfig(..., alpha=0.10)
```

#### 3. Validation Samples Not Found

**Problem**: Cannot load validation samples

**Solutions**:
```python
# Check paths
print(config.centroid1_validation_samples)

# Use synthetic validation
config = TrainingConfig(..., validation_mode='synthetic')

# Or check centroid metadata
c1 = MethylSample.load_from_h5(centroid1_path)
print(f"Centroid samples: {c1.metadata.get('samples', [])}")
```

#### 4. GPU Out of Memory

**Problem**: CUDA out of memory

**Solutions**:
```python
# Disable GPU
config = TrainingConfig(..., use_gpu=False)

# Or cleanup between operations
from methyl_utils import cleanup_gpu_memory
cleanup_gpu_memory()
```

---

## Integration with MethylPipeline

### Pipeline Position

```
MethylCentroid → MethylTrainer → MethylClassifier
                     ↓
              (Alternative to
               MethylDetector)
```

### Complete Workflow

```python
from methyl_centroid import MethylCentroid, MethylCentroidConfig
from methyl_trainer import train_from_centroids
from methyl_classifier import MethylClassifier

# Step 1: Create centroids
centroid1_result = MethylCentroid(...).build_centroid()
centroid2_result = MethylCentroid(...).build_centroid()

# Step 2: Train classifier
train_result = train_from_centroids(
    centroid1_path=centroid1_result.final_centroid_path,
    centroid2_path=centroid2_result.final_centroid_path,
    output_path='/models/classifier.pkl'
)

# Step 3: Classify new samples
classifier = MethylClassifier(model_path='/models/classifier.pkl')
predictions = classifier.predict_batch(new_sample_paths)
```

---

## Performance

### Benchmarks

| Operation | Time (CPU) | Time (GPU) | Speedup |
|-----------|------------|------------|---------|
| DMP Detection | 20s | 1s | 20x |
| Binary Search (100 iter) | 50s | 5s | 10x |
| Validation | 2s | 0.2s | 10x |
| **Total** | **72s** | **6.2s** | **12x** |

### Memory Usage

- Small model (50 DMPs): ~10 MB
- Medium model (200 DMPs): ~20 MB
- Large model (500 DMPs): ~40 MB

---

## License

MethylTrainer is licensed under the MIT License.

---

## Citation

```bibtex
@software{methyltrainer2024,
  title={MethylTrainer: Bayesian Classifier Training for Methylation Data},
  author={MethylPipeline Contributors},
  year={2024},
  url={https://github.com/yourusername/MethylPipeline}
}
```

---

*End of MethylTrainer Comprehensive Documentation*

**Last Updated**: October 2024  
**Version**: 1.0.0

