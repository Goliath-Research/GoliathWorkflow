# MethylTrainer

**Advanced Bayesian Classifier Training with Flexible Validation**

## Overview

MethylTrainer is an advanced alternative to MethylDetector for training Bayesian classifiers from methylation centroids. It provides more flexibility in validation sample selection and direct control over the training workflow.

### What is MethylTrainer?

MethylTrainer offers:

- **DMP Detection**: Direct statistical comparison of centroids  
- **Flexible Validation**: Real samples from config, centroid metadata, or synthetic
- **Balanced Accuracy Optimization**: Robust binary search for optimal DMPs
- **Model Packaging**: Creates `.pkl` files for MethylClassifier
- **Lightweight**: Focused on training without extensive reporting

## Key Features

- 🎯 **Flexible Validation**: Multiple sources for real validation samples
- 📊 **Balanced Accuracy**: Unbiased metric robust to class imbalance
- 🔍 **Binary Search**: Optimizes DMP count for target accuracy
- 🚀 **GPU Accelerated**: Leverages MethylUtils for performance
- 📦 **Model Packaging**: Complete metadata for reproducibility
- ⚡ **Lightweight**: Faster execution than MethylDetector

## Installation

```bash
# Install from source
cd packages/methyltrainer
pip install -e .

# Or as part of MethylPipeline
pip install methylpipeline
```

## Quick Start

```python
from methyl_trainer import train_model, TrainingConfig

# Configure training
config = TrainingConfig(
    centroid1_path='/centroids/healthy.h5',
    centroid2_path='/centroids/cancer.h5',
    class1_name='Healthy',
    class2_name='Cancer',
    
    target_balanced_accuracy=0.95,
    
    validation_mode='real',
    centroid1_validation_samples=['/val/h1', '/val/h2', '/val/h3'],
    centroid2_validation_samples=['/val/c1', '/val/c2'],
    
    output_path='/output/model.pkl'
)

# Train model
model = train_model(config)
print(f"Model trained with {len(model.positions)} DMPs")
```

## Configuration Parameters

### Centroid Specification

- **`centroid1_path`**: Path to first centroid (e.g., Healthy)
- **`centroid2_path`**: Path to second centroid (e.g., Cancer)
- **`class1_name`**: Name for class 1
- **`class2_name`**: Name for class 2

### Training Parameters

- **`target_balanced_accuracy`**: Target for binary search (default: 0.95)
- **`min_dmps`**: Minimum DMPs (default: 10)
- **`max_dmps`**: Maximum DMPs (default: 10000)
- **`optimize_for_validation_accuracy`**: Optimize on validation set (default: true)

### Validation (Multiple Options)

**Option 1: Specify in Config**
```python
validation_mode='real'
centroid1_validation_samples=['/val/h1', '/val/h2']
centroid2_validation_samples=['/val/c1', '/val/c2']
```

**Option 2: Use Centroid Metadata**
```python
validation_mode='real'
# Falls back to centroid1.samples and centroid2.samples from metadata
```

**Option 3: Synthetic Samples**
```python
validation_mode='synthetic'
n_synthetic_samples_per_class=100
```

### Output

- **`output_path`**: Path for model package (`.pkl`)

## MethylTrainer vs MethylDetector

| Feature | MethylTrainer | MethylDetector |
|---------|---------------|----------------|
| DMP Detection | ✅ Direct | ✅ Via MethylCentroidPair |
| Binary Search | ✅ Yes | ✅ Yes |
| Balanced Accuracy | ✅ Yes | ✅ Yes |
| Validation Flexibility | ✅✅ High | ✅ Medium |
| Gene Mapping | ❌ No | ✅ Yes |
| Visualizations | ❌ Minimal | ✅ Extensive |
| Execution Speed | ✅✅ Faster | ✅ Fast |
| Use Case | Training only | Complete analysis |

**When to Use MethylTrainer:**
- Need flexible validation sample selection
- Want faster training without visualizations
- Programmatic model training workflows
- Have validation samples stored with centroid metadata

**When to Use MethylDetector:**
- Need complete DMP analysis and reporting
- Want gene-level feature importance
- Need visualization outputs (volcano plots, heatmaps)
- Prefer comprehensive documentation of analysis

## Documentation

📚 **[Comprehensive Documentation](docs/METHYLTRAINER_COMPREHENSIVE_DOCUMENTATION.md)** - Complete guide covering:
- Training workflow and algorithms
- Validation strategies
- API reference
- Examples and best practices
- Integration with MethylPipeline

## Examples

### Example 1: Train with Config Validation Samples

```python
from methyl_trainer import train_model, TrainingConfig

config = TrainingConfig(
    centroid1_path='/centroids/healthy.h5',
    centroid2_path='/centroids/cancer.h5',
    class1_name='Healthy',
    class2_name='Cancer',
    
    target_balanced_accuracy=0.95,
    
    validation_mode='real',
    centroid1_validation_samples=[
        '/data/healthy_val1', '/data/healthy_val2'
    ],
    centroid2_validation_samples=[
        '/data/cancer_val1', '/data/cancer_val2'
    ],
    
    output_path='/models/healthy_vs_cancer.pkl'
)

model = train_model(config)
```

### Example 2: Train with Centroid Metadata Samples

```python
# Centroids have samples listed in metadata
# MethylTrainer will automatically use them

config = TrainingConfig(
    centroid1_path='/centroids/healthy.h5',  # Has samples in metadata
    centroid2_path='/centroids/cancer.h5',   # Has samples in metadata
    class1_name='Healthy',
    class2_name='Cancer',
    
    validation_mode='real',  # Will use metadata samples
    
    output_path='/models/model.pkl'
)

model = train_model(config)
```

### Example 3: Train with Synthetic Validation

```python
config = TrainingConfig(
    centroid1_path='/centroids/healthy.h5',
    centroid2_path='/centroids/cancer.h5',
    class1_name='Healthy',
    class2_name='Cancer',
    
    validation_mode='synthetic',
    n_synthetic_samples_per_class=100,
    
    output_path='/models/model.pkl'
)

model = train_model(config)
```

## API Reference

### Main Function

```python
train_model(config: TrainingConfig) -> ProbabilisticBetaClassifier
```

Trains Bayesian classifier from two centroids.

**Returns**: `ProbabilisticBetaClassifier` model

### Configuration Class

```python
class TrainingConfig(BaseModel):
    centroid1_path: str
    centroid2_path: str
    class1_name: str
    class2_name: str
    
    target_balanced_accuracy: float = 0.95
    min_dmps: int = 10
    max_dmps: int = 10000
    
    validation_mode: str = "synthetic"
    centroid1_validation_samples: Optional[List[str]] = None
    centroid2_validation_samples: Optional[List[str]] = None
    n_synthetic_samples_per_class: int = 100
    
    output_path: str
    use_gpu: bool = True
```

See [Comprehensive Documentation](docs/METHYLTRAINER_COMPREHENSIVE_DOCUMENTATION.md) for complete API details.

## Integration with MethylPipeline

```
MethylCentroid → MethylTrainer → MethylClassifier
    (Generate)     (Train)         (Predict)
```

**Alternative to MethylDetector** in the pipeline.

## License

MIT License - see [LICENSE](../../LICENSE) file for details.

---

For more information, see:
- [MethylTrainer Comprehensive Documentation](docs/METHYLTRAINER_COMPREHENSIVE_DOCUMENTATION.md)
- [MethylPipeline Documentation](../../docs/METHYLPIPELINE_COMPREHENSIVE_DOCUMENTATION.md)
