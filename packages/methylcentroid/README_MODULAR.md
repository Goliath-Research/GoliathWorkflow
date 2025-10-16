# MethylCentroid - Modular Architecture

## Overview

This document describes the refactored modular architecture of MethylCentroid, which transforms the original 3420-line monolithic file into a clean, maintainable, and extensible codebase following SOLID principles.

## Architecture Overview

The modular architecture is organized into focused packages, each responsible for specific functionality:

```
methylcentroid/
├── config.py                    # Configuration management
├── cli.py                       # Command-line interface
├── core/                        # Core processing logic
│   ├── methyl_centroid.py       # Main orchestration class
│   └── sample_manager.py        # Sample loading and caching
├── outlier_detection/           # Outlier detection algorithms
│   ├── base_detector.py         # Abstract base classes
│   ├── probabilistic_detector.py # Probabilistic Beta classifier
│   ├── multi_metric_detector.py # Multi-metric consensus
│   ├── single_metric_detector.py # Traditional statistical
│   └── detector_factory.py      # Factory pattern for detectors
├── output/                      # Output and reporting (future)
├── validation/                  # Validation components (future)
└── tests/                       # Test suite
    └── ...                      # Unit and integration tests
```

## SOLID Principles Implementation

### 1. **Single Responsibility Principle (SRP)**
Each module has one clear, focused responsibility:

- `config.py`: Configuration validation and management
- `sample_manager.py`: Sample loading, caching, and memory management
- `probabilistic_detector.py`: Advanced probabilistic outlier detection
- `cli.py`: Command-line interface and user interaction

**Logging and Performance**: MethylCentroid leverages MethylUtils logging and performance profiling infrastructure, eliminating code duplication and ensuring consistency across the genomics toolkit.

### 2. **Open/Closed Principle (OCP)**
The architecture is designed for extension without modification:

- **Outlier Detection**: New algorithms can be added by implementing `BaseOutlierDetector`
- **Configuration**: New parameters can be added to `MethylCentroidConfig` without breaking existing code
- **Output Formats**: New exporters can be added to the output package

### 3. **Liskov Substitution Principle (LSP)**
All outlier detectors implement the same interface, allowing them to be used interchangeably:

```python
# Any detector can be used in place of another
detectors = [
    ProbabilisticOutlierDetector(metrics, config),
    MultiMetricOutlierDetector(metrics, config),
    SingleMetricOutlierDetector(metrics, config)
]

for detector in detectors:
    result = detector.detect_outlier(samples, indices)  # Same interface
```

### 4. **Interface Segregation Principle (ISP)**
Clean, focused interfaces:

- `BaseOutlierDetector` defines only essential methods for outlier detection
- `SampleManager` provides specific methods for sample management
- Configuration classes have minimal, relevant methods

### 5. **Dependency Inversion Principle (DIP)**
High-level modules depend on abstractions, not concretions:

- `MethylCentroid` depends on `BaseOutlierDetector` interface, not specific implementations
- `SampleManager` uses abstract memory management interfaces
- Factory pattern provides appropriate implementations based on context

## Key Components

### Configuration Management (`config.py`)

```python
from methyl_centroid.config import MethylCentroidConfig

# Create configuration
config = MethylCentroidConfig(
    chrom="1",
    ctx="CG",
    output_dir="./output",
    samples=["sample1_dir", "sample2_dir"],
    distance_metrics=["jensen_shannon", "wasserstein"]
)

# Save/load configuration
config.to_file("config.json")
config = MethylCentroidConfig.from_file("config.json")
```

### Sample Management (`core/sample_manager.py`)

Intelligent caching with memory management:

```python
from methyl_centroid.core.sample_manager import SampleManager, SmartSampleCache

sample_manager = SampleManager(processing_config, chrom, ctx)
samples = sample_manager.load_samples_parallel(sample_paths)

# Automatic memory management and LRU eviction
cache_stats = sample_manager.get_cache_stats()
```

### Outlier Detection (`outlier_detection/`)

Factory pattern for algorithm selection:

```python
from methyl_centroid.outlier_detection import OutlierDetectorFactory

# Automatically selects best algorithm based on sample size
detector = OutlierDetectorFactory.create_detector(
    distance_metrics=["jensen_shannon", "wasserstein"],
    num_samples=50  # Will use ProbabilisticBetaClassifier
)

# Or specify explicitly
detector = OutlierDetectorFactory.create_specific_detector(
    "probabilistic",
    distance_metrics=["jensen_shannon"],
    config={"min_samples_for_classifier": 20}
)

result = detector.detect_outlier(sample_paths, sample_indices)
```

### Command-Line Interface (`cli.py`)

Clean, organized CLI with grouped options:

```bash
# Single processing
python -m methylcentroid.cli -C 1 -x CG -s samples.csv -o ./output

# Configuration file
python -m methylcentroid.cli --config config.json

# Batch processing
python -m methylcentroid.cli --batch-config batch.json
```

## Integration with MethylUtils

MethylCentroid is designed as a focused application that leverages the comprehensive MethylUtils library for shared functionality:

### Shared Infrastructure
- **Logging**: Uses `methyl_utils.logging_utils` for consistent logging across genomics tools
- **Performance Profiling**: Leverages `methyl_utils.PerformanceProfiler` with context manager support
- **GPU Detection**: Inherits GPU capabilities and memory management from MethylUtils
- **Memory Management**: Uses MethylUtils memory monitoring and optimization features

### Benefits of Integration
- **Zero Code Duplication**: Eliminates redundant logging and utility code
- **Consistent Behavior**: Unified logging and performance monitoring across tools
- **Shared Improvements**: Enhancements to MethylUtils automatically benefit MethylCentroid
- **Maintainability**: Single source of truth for shared functionality

## Performance Improvements

### Memory Management
- **Dynamic Chunk Sizing**: Chunk sizes adapt to available memory and context density
- **Intelligent Caching**: LRU eviction prevents memory exhaustion
- **Parallel Loading**: Memory-aware worker allocation

### Algorithm Selection
- **Adaptive Detection**: Automatically chooses appropriate algorithm based on sample size
- **Probabilistic Methods**: Advanced statistical modeling for large datasets (≥20 samples)
- **Multi-Metric Consensus**: Robust detection combining multiple distance metrics

### Processing Optimization
- **GPU Acceleration**: Intelligent GPU detection and fallback
- **Memory Monitoring**: Continuous memory usage tracking and corrective actions
- **Performance Profiling**: Comprehensive timing and resource monitoring

## Benefits of Modular Architecture

### 1. **Maintainability**
- Each module is focused and easy to understand
- Changes in one area don't affect others
- Clear interfaces prevent coupling

### 2. **Testability**
- Each module can be unit tested independently
- Mock implementations for testing
- Focused test cases per responsibility

### 3. **Extensibility**
- New outlier detection algorithms can be added easily
- New output formats without modifying core logic
- Plugin architecture for custom components

### 4. **Reusability**
- Sample manager can be used independently
- Outlier detectors are interchangeable
- Configuration system is reusable across contexts

### 5. **Debugging**
- Problems are isolated to specific modules
- Logging is centralized and configurable
- Performance profiling per component

## Migration from Monolithic Version

The modular version maintains API compatibility while providing enhanced capabilities:

```python
# Old monolithic usage
from methyl_centroid import MethylCentroid

mc = MethylCentroid(
    samples=sample_list,
    chrom="1",
    ctx="CG",
    output_dir="./output"
)
results = mc.build_centroid()

# New modular usage (same API)
from methyl_centroid import MethylCentroid

mc = MethylCentroid.from_config(config, processing_config)
results = mc.build_centroid()
```

## Development Guidelines

### Adding New Components

1. **New Outlier Detector**:
   ```python
   from methyl_centroid.outlier_detection.base_detector import BaseOutlierDetector

   class MyDetector(BaseOutlierDetector):
       def detect_outlier(self, samples, indices):
           # Implementation
           pass
   ```

2. **New Configuration Parameter**:
   ```python
   # Add to MethylCentroidConfig in config.py
   new_param: str = Field(default="value", description="Description")
   ```

3. **New CLI Option**:
   ```python
   # Add to cli.py argument parser
   parser.add_argument('--new-option', help='Description')
   ```

### Testing Strategy

- **Unit Tests**: Test individual modules in isolation
- **Integration Tests**: Test module interactions
- **End-to-End Tests**: Test complete workflows
- **Performance Tests**: Validate memory and speed improvements

## Future Enhancements

The modular architecture enables easy addition of:

- **New Output Formats**: CSV, JSON, HDF5, database storage
- **Advanced Validation**: Statistical validation, cross-validation
- **Visualization**: Interactive plots, dashboards
- **Distributed Processing**: Multi-node processing capabilities
- **Machine Learning**: ML-based outlier detection algorithms

## Conclusion

The modular architecture transforms MethylCentroid from a monolithic script into a professional, maintainable codebase that follows industry best practices. Each module has clear responsibilities, clean interfaces, and can be developed, tested, and maintained independently while working seamlessly together to provide advanced methylation centroid calculation capabilities.
