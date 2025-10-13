# MethylCentroid

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/dependency%20management-poetry-blue.svg)](https://python-poetry.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)]()

A high-performance Python package for calculating methylation centroids from genomic data with GPU acceleration support, advanced outlier detection algorithms, and modular SOLID principles-based architecture.

## Overview

MethylCentroid calculates methylation centroids from groups of samples, representing the average methylation patterns across biological replicates or similar samples. The package processes methylation data stored in HDF5 format and provides both basic and extended centroid calculations with Jeffreys divergence-based outlier detection using accumulated methylation level statistics for statistically rigorous sample quality assessment.

### Key Features

- **Modular Architecture**: Clean, SOLID principles-based design with focused modules
- **High-Performance Processing**: Optimized for large genomic datasets with parallel processing
- **GPU Acceleration**: Automatic NVIDIA GPU detection and acceleration (10-50x speedup)
- **Advanced Outlier Detection**: Multiple algorithms including probabilistic Beta classification for ≥20 samples
- **Incremental Operations**: Add/remove samples from existing centroids without full recalculation
- **Flexible Input**: Support for multiple chromosome/context combinations (CG, CHG, CHH)
- **MethylUtils Integration**: Leverages shared utilities for logging, performance profiling, and GPU management
- **Memory Optimization**: Intelligent caching, dynamic chunking, and memory-aware processing
- **Command-Line Interface**: Easy-to-use CLI for batch processing

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Usage](#usage)
  - [Python API](#python-api)
  - [Command Line](#command-line)
  - [Configuration](#configuration)
  - [Configuration Management](#configuration-management)
- [Data Format](#data-format)
- [Features](#features)
  - [Basic vs Extended Centroids](#basic-vs-extended-centroids)
  - [Outlier Detection](#outlier-detection)
  - [GPU Acceleration](#gpu-acceleration)
  - [Incremental Operations](#incremental-operations)
- [Examples](#examples)
- [Performance](#performance)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)

## Architecture

MethylCentroid follows a modular, SOLID principles-based architecture designed for maintainability, extensibility, and performance.

### Modular Design

The codebase is organized into focused packages, each responsible for specific functionality:

```
methylcentroid/
├── config.py                    # Configuration management with Pydantic validation
├── cli.py                       # Command-line interface with organized argument groups
├── core/                        # Core processing logic
│   ├── methyl_centroid.py       # Main orchestration class
│   └── sample_manager.py        # Intelligent sample loading and caching
├── outlier_detection/           # Multiple outlier detection algorithms
│   ├── base_detector.py         # Abstract base classes and interfaces
│   ├── probabilistic_detector.py # Advanced Beta classification (≥20 samples)
│   ├── multi_metric_detector.py # Multi-metric consensus detection
│   ├── single_metric_detector.py # Traditional statistical detection
│   └── detector_factory.py      # Factory pattern for algorithm selection
├── output/                      # Output and reporting (future expansion)
├── validation/                  # Validation components (future expansion)
└── tests/                       # Comprehensive test suite
```

### SOLID Principles

MethylCentroid implements SOLID design principles for robust, maintainable code:

- **Single Responsibility**: Each module has one clear, focused responsibility
- **Open/Closed**: New algorithms can be added without modifying existing code
- **Liskov Substitution**: All outlier detectors implement the same interface
- **Interface Segregation**: Clean, minimal interfaces for each component
- **Dependency Inversion**: High-level modules depend on abstractions, not concretions

### MethylUtils Integration

MethylCentroid leverages the comprehensive MethylUtils library for shared functionality:

- **Logging**: Uses `methyl_utils.logging_utils` for consistent logging across genomics tools
- **Performance Profiling**: Leverages `methyl_utils.PerformanceProfiler` with context manager support
- **GPU Detection**: Inherits GPU capabilities and memory management from MethylUtils
- **Memory Management**: Uses MethylUtils monitoring and optimization features

This integration eliminates code duplication and ensures consistency across the genomics toolkit.

## Installation

MethylCentroid can be installed directly using Poetry or run via Docker container for easier deployment.

### Containerized Installation (Recommended)

The easiest way to use MethylCentroid is through the epimethyl Docker container:

```bash
# Execute directly in running container
docker exec -w /home/ubuntu/MethylCentroid epimethyl \
    python -m methylcentroid.centroid_cli --config methylcentroid/configs/example_config.json
```

See [Docker Container Usage](#docker-container-usage) for detailed instructions.

### Container-Only Setup (Recommended)

Since MethylCentroid requires GPU support and specialized libraries (CUDA, RAPIDS) that are only available in the container environment, the recommended approach is **container-only usage** with no heavy Python packages installed on the VM.

#### Prerequisites

- Docker installed and running
- Access to the epimethyl container image
- Git (for cloning the repository)

#### Container Setup

```bash
# Clone the repository
git clone <repository-url>
cd MethylCentroid

# Run the container setup script (creates wrapper, no VM installation)
./install.sh

# Use the wrapper script
./mc --help
./mc --config your_config.json
```

#### What the Container Setup Does

The container setup script:
- **Verifies Docker availability**
- **Checks container status** (warns if epimethyl container isn't running)
- **Creates a wrapper script** (`methylcentroid`) for easy command execution
- **No heavy packages installed on VM** - everything runs in the container

#### Direct Container Usage

You can also use Docker commands directly:

```bash
# Ensure container is running
docker ps | grep epimethyl

# Run MethylCentroid commands
docker exec -w /home/ubuntu/MethylCentroid epimethyl \
    python -m methylcentroid.centroid_cli --config your_config.json
```

### GPU Acceleration

MethylCentroid automatically detects and utilizes GPU acceleration when available. In containerized environments with CUDA and RAPIDS:

- **Automatic Detection**: GPU hardware is detected automatically
- **Transparent Acceleration**: No configuration required - operations automatically use GPU when available
- **Performance Gains**: 10-50x speedup for compute-intensive operations
- **Fallback Support**: Gracefully falls back to CPU if GPU is unavailable

The container environment provides optimized GPU libraries (CUDA, RAPIDS) that are automatically leveraged by MethylCentroid's integration with MethylUtils.

### VM Quick Start (Container-Only)

For users on virtual machines - **no Python packages installed on VM**:

```bash
# 1. Clone MethylCentroid
git clone <repository-url>
cd MethylCentroid

# 2. Run container setup (creates wrapper script)
./install.sh

# 3. Use the wrapper script
./mc --config your_config.json
```

The container setup automatically:
- Verifies Docker availability
- Checks epimethyl container status
- Creates `mc` wrapper script
- **Zero heavy packages installed on VM**

#### Troubleshooting Container Setup

**Container not running:**
```bash
# Check if container is running
docker ps | grep epimethyl

# If not running, start it
docker run -d --name epimethyl <your-epimethyl-image>

# Or if it exists but is stopped
docker start epimethyl
```

**Docker not available:**
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group (logout/login required)
sudo usermod -aG docker $USER
```

**Permission issues:**
```bash
# Fix script permissions
sudo chmod +x install.sh
sudo chmod +x mc
```

**Container connection issues:**
```bash
# Test container connectivity
docker exec epimethyl echo "Container is accessible"

# Check if MethylCentroid is available in container
docker exec epimethyl python -c "import methylcentroid; print('OK')"
```

**Wrapper script issues:**
```bash
# Recreate wrapper script
./install.sh

# Or manually create it
cat > mc << 'EOF'
#!/bin/bash
exec docker exec -w /home/ubuntu/MethylCentroid epimethyl python -m methylcentroid.centroid_cli "$@"
EOF
chmod +x mc
```

## Docker Container Usage

MethylCentroid is available as a Docker container for easy deployment and reproducible analysis.

### Prerequisites

- Docker installed and running
- Access to epimethyl container image

### Running with Docker

```bash
# Execute MethylCentroid using the epimethyl container
docker exec -w /home/ubuntu/MethylCentroid epimethyl python -m methylcentroid.centroid_cli --config methylcentroid/configs/bc-healthy_config.json
```

### Containerized Workflow

1. **Mount data volumes**: Mount your data directories when running the container
2. **Configuration files**: Place configuration JSON files in accessible paths
3. **Output directories**: Ensure output directories are writable from within the container

Example with volume mounting:
```bash
# Run container with data volume mounted
docker run -v /path/to/your/data:/data -v /path/to/output:/output epimethyl \
  python -m methylcentroid.centroid_cli --config /data/config.json
```

### Benefits of Containerized Deployment

- **Reproducible**: Same environment across different systems
- **Isolated**: No dependency conflicts with system packages
- **Portable**: Run on any system with Docker support
- **Versioned**: Pin specific versions of all dependencies

## Quick Start

```python
from methylcentroid.methyl_centroid import MethylCentroid

# Initialize with sample paths
mc = MethylCentroid(
    add_samples=["path/to/sample1", "path/to/sample2"],
    chrom="1",
    ctx="CG",
    output_dir="output",
    min_coverage=4
)

# Build centroid with outlier removal (automatically uses extended centroid)
results = mc.build_centroid()

print(f"Centroid saved: {results.final_centroid_path}")
print(f"Outliers removed: {results.total_samples_removed}")
```

## Usage

### Python API

#### Basic Usage

```python
from methylcentroid.methyl_centroid import MethylCentroid
from pathlib import Path

# Define sample directories containing HDF5 files
sample_paths = [
    "data/sample1",
    "data/sample2",
    "data/sample3"
]

# Create MethylCentroid instance
mc = MethylCentroid(
    add_samples=sample_paths,
    chrom="1",           # Chromosome
    ctx="CG",            # Context (CG, CHG, or CHH)
    output_dir="output", # Output directory
    min_coverage=4,      # Minimum coverage threshold
    max_iterations=10,   # Max outlier removal iterations
    α=0.05              # Significance level
)

# Build extended centroid with outlier removal
results = mc.build_centroid()

# Access results
print(f"Final centroid: {results.final_centroid_path}")
print(f"Samples removed: {results.total_samples_removed}")
```

#### Incremental Operations

```python
# Load existing centroid and add new samples
mc = MethylCentroid(
    samples=["data/sample1", "data/sample2"],  # Original samples in centroid
    chrom="1",
    ctx="CG",
    output_dir="output",
    add_samples=["data/sample3"]  # New samples to add
)

# Load existing centroid state
centroid_path = Path("output/1-CG.h5")
if mc._load_existing_centroid_state(centroid_path):
    # Add new samples
    for i, _ in enumerate(mc.new_samples):
        mc.add_sample(i, is_new_sample=True)

    # Re-run outlier detection
    results = mc.remove_outliers()
```

#### Extended Centroids with Statistics

```python
# Build extended centroid with methylation level statistics
results = mc.build_centroid()

# Extended centroid includes:
# - pos: Genomic positions
# - mC: Average methylated cytosines
# - uC: Average unmethylated cytosines
# - tnc: Trinucleotide context
# - N: Number of samples contributing
# - Sx: Sum of methylation levels (essential for accurate outlier detection)
# - Sx2: Sum of squared methylation levels (for variance calculations)
# - log_x_sum, log_1_minus_x_sum: For Beta distribution fitting

# Note: Extended centroids are automatically used by build_centroid() for proper outlier detection
```

### Command Line

#### Docker Container Usage

For containerized execution using the epimethyl Docker container:

```bash
# Basic processing with container
docker exec -w /home/ubuntu/MethylCentroid epimethyl \
    python -m methylcentroid.centroid_cli \
    --config methylcentroid/configs/bc-healthy_config.json

# Process specific chromosome/context with container
docker exec -w /home/ubuntu/MethylCentroid epimethyl \
    python -m methylcentroid.centroid_cli \
    -c 1 \
    -x CG \
    -s samples.csv \
    -o output/ \
    --verbose
```

#### Direct Python Execution

If running MethylCentroid directly (not in container):

#### Basic Processing

```bash
# Process chromosome 1, CG context
python -m methylcentroid.centroid_cli \
    -c 1 \
    -x CG \
    -s samples.csv \
    -o output/

# With custom parameters
python -m methylcentroid.centroid_cli \
    -c X \
    -x CHG \
    -s samples.csv \
    -o output/ \
    --min-coverage 5 \
    --max-iterations 15 \
    --alpha 0.01 \
    --verbose
```

#### Using Configuration File

**With Docker Container:**
```bash
# Run with configuration file using container
docker exec -w /home/ubuntu/MethylCentroid epimethyl \
    python -m methylcentroid.centroid_cli --config methylcentroid/configs/bc-healthy_config.json --verbose
```

**Direct Python Execution:**
```bash
# Create config.json
cat > config.json << EOF
{
  "samples": ["data/sample1", "data/sample2"],
  "chrom": "1",
  "ctx": "CG",
  "output_dir": "output",
  "min_coverage": 4,
  "max_iterations": 10,
  "α": 0.05,
  "min_samples": 3
}
EOF

# Run with configuration
python -m methylcentroid.centroid_cli --config config.json --verbose
```

### Configuration

#### Configuration File Format

```json
{
  "samples": ["path/to/sample1", "path/to/sample2"],
  "chrom": "1",
  "ctx": "CG",
  "output_dir": "output",
  "new_samples": [],
  "min_coverage": 4,
  "max_iterations": 10,
  "α": 0.05,
  "min_samples": 3
}
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `samples` | List[str] | Required | Sample directory paths |
| `chrom` | str | Required | Chromosome identifier |
| `ctx` | str | Required | Context (CG, CHG, CHH) |
| `output_dir` | str | Required | Output directory |
| `new_samples` | List[str] | [] | Additional samples to add |
| `min_coverage` | int | 4 | Minimum mC+uC coverage |
| `max_iterations` | int | 10 | Max outlier removal iterations |
| `max_iterations_percentage` | float | 0.1 | Percentage of samples for max iterations (overrides max_iterations if > 0) |
| `α` | float | 0.05 | Significance level for outliers |
| `min_samples` | int | 3 | Minimum samples to continue |

### Configuration Management

MethylCentroid supports saving and loading configurations using Pydantic models for reproducible analyses.

#### Saving Configuration

```python
from methylcentroid.methyl_centroid import MethylCentroid

# Create MethylCentroid instance
mc = MethylCentroid(
    samples=["data/sample1", "data/sample2"],
    chrom="1",
    ctx="CG",
    output_dir="output",
    min_coverage=5,
    α=0.01
)

# Get current configuration as Pydantic model
config = mc.get_config()

# Save to JSON
config_dict = config.model_dump()
with open('my_config.json', 'w') as f:
    json.dump(config_dict, f, indent=2)
```

#### Loading Configuration

```python
# Load from JSON
with open('my_config.json', 'r') as f:
    config_dict = json.load(f)

# Create new instance from config
mc_new = MethylCentroid.from_json(config_dict)

# Or use Pydantic model directly
config_model = MethylCentroidConfig.model_validate(config_dict)
mc_new = MethylCentroid.from_config(config_model)
```

#### Use Cases

- **Reproducible Research**: Save exact parameters used for analysis
- **Batch Processing**: Reuse configurations across multiple datasets
- **Parameter Tuning**: Experiment with different settings and save successful configurations
- **Workflow Automation**: Store configurations for automated pipelines

## Data Format

### Input Format

Samples should be organized as directories containing HDF5 files named `{chrom}-{ctx}.h5`:

```
data/
├── sample1/
│   ├── 1-CG.h5
│   ├── 1-CHG.h5
│   └── 1-CHH.h5
├── sample2/
│   ├── 1-CG.h5
│   ├── 1-CHG.h5
│   └── 1-CHH.h5
└── samples.csv  # List of sample directories
```

### HDF5 File Structure

Each HDF5 file should contain a `methylation_data` group with the following datasets:

```python
methylation_data/
├── pos     # uint32: Genomic positions
├── mC      # uint32: Methylated cytosine counts
├── uC      # uint32: Unmethylated cytosine counts
├── tnc     # uint8:  Trinucleotide context codes
└── N       # uint32: Number of samples (for centroids)
```

### Output Format

Centroids are saved as compressed HDF5 files with the same structure, plus additional statistics for extended centroids.

## Features

### Basic vs Extended Centroids

**Basic Centroid**: Contains average mC and uC values across samples
**Extended Centroid**: Includes additional methylation level statistics (Sx, Sx2, log accumulators) for statistically rigorous analysis

```python
# Basic centroid
basic_result = mc.compute_centroid(extended=False)

# Extended centroid with statistics (recommended for outlier detection)
extended_result = mc.compute_centroid(extended=True)
```

#### Extended Centroid Statistics

The extended centroid provides accumulated statistics essential for accurate outlier detection:

- **Sx (Sum of methylation levels)**: Σᵢ₌₁ᴺ xᵢ where xᵢ is the methylation level for sample i
- **Sx2 (Sum of squared methylation levels)**: Σᵢ₌₁ᴺ xᵢ² for variance calculations
- **log_x_sum**: Σᵢ₌₁ᴺ log(xᵢ) for Beta distribution fitting
- **log_1_minus_x_sum**: Σᵢ₌₁ᴺ log(1-xᵢ) for Beta distribution fitting

#### Methylation Level Calculation

**Basic Centroid**: `methylation_level = mC / (mC + uC)` (average of raw counts)
**Extended Centroid**: `methylation_level = Sx / N` (correct statistical estimator)

⚠️ **Critical Difference**: These formulas are **not equivalent** when different positions have different sample counts. The extended centroid formula `Sx/N` is the correct statistical estimator that properly accounts for the number of samples contributing to each position.

**Important**: Outlier detection requires extended centroids to access pre-computed methylation level statistics, ensuring accurate Jeffreys divergence calculations without recomputing methylation levels from raw counts.

### Outlier Detection

MethylCentroid uses **Jeffreys divergence** as the distance metric for identifying outlier samples. This information-theoretic approach provides a statistically rigorous method for detecting samples that deviate significantly from the group centroid.

#### Distance Metric: Jeffreys Divergence

Jeffreys divergence is a symmetrized version of Kullback-Leibler divergence that measures the difference between two probability distributions:

**Mathematical Definition:**
```
J(p,q) = ½[D_KL(p||q) + D_KL(q||p)]
```

For methylation data, each sample is treated as a probability distribution over genomic positions, where the methylation level at each position serves as the probability value. Since methylation levels follow a Beta distribution (bounded between 0 and 1), the resulting Jeffreys divergence values are also bounded and typically range from 0 to 1, making them ideal for statistical analysis and visualization.

#### Methylation-Specific Jeffreys Divergence

For methylation samples represented as vectors of methylation levels **x** = (x₁, x₂, ..., xₙ) and centroid **c** = (c₁, c₂, ..., cₙ):

**Methylation Jeffreys Divergence (Average):**
```
J(x, c) = (1/n) * ½ Σᵢ₌₁ⁿ [xᵢ log(xᵢ/cᵢ) + cᵢ log(cᵢ/xᵢ) + (1-xᵢ) log((1-xᵢ)/(1-cᵢ)) + (1-cᵢ) log((1-cᵢ)/(1-xᵢ))]
```

*Note: Returns the average divergence across all positions for better chart scaling and interpretability.*

This formulation accounts for both methylated and unmethylated states at each position, providing a comprehensive measure of methylation pattern dissimilarity.

#### Statistical Testing Procedure

The outlier detection algorithm follows these steps:

1. **Calculate Centroid**: Compute the average methylation pattern across all samples
2. **Compute Distances**: Calculate Jeffreys divergence for each sample to the centroid
3. **Identify Outlier**: Select the sample with maximum divergence as the most extreme outlier
4. **Statistical Test**: Perform one-tailed hypothesis testing with adaptive distribution fitting:
   ```
   Distribution Fitting: Compare Normal vs Beta distribution fits using AIC
   If Beta fits better: p-value = 1 - Beta_CDF(J_max | α, β)
   Else: p-value = 1 - Φ((J_max - μ)/σ)  [Normal approximation]
   ```
   The algorithm automatically selects the best-fitting distribution for bounded [0,1] divergence averages
5. **Decision Rule**: If p-value > α (default α = 0.05), no significant outliers found
6. **Iterative Removal**: Remove identified outlier and recalculate centroid
7. **Convergence**: Repeat until no significant outliers remain or maximum iterations reached

#### Usage Examples

```python
from methylcentroid.methyl_centroid import MethylCentroid

# Initialize with outlier detection parameters
mc = MethylCentroid(
    samples=sample_paths,
    chrom="1",
    ctx="CG",
    output_dir="output",
    α=0.05,              # Significance level (default: 0.05)
    max_iterations=10,   # Maximum outlier removal iterations
    min_samples=3        # Minimum samples required to continue
)

# Build centroid with automatic outlier removal
results = mc.build_centroid()

# Manual outlier detection
outlier_path, outlier_id, p_value = mc.find_most_extreme_outlier()
if p_value <= mc.α:  # One-tailed test since Jeffreys divergence ≥ 0
    print(f"Outlier detected: {outlier_path} (p-value: {p_value:.4f})")
    mc.remove_sample(outlier_id[1], is_new_sample=outlier_id[0])

# Example with percentage-based max iterations (15 samples = max 2 iterations)
mc_percentage = MethylCentroid(
    samples=["data/sample1", "data/sample2", ..., "data/sample15"],
    chrom="1",
    ctx="CG",
    output_dir="output",
    max_iterations_percentage=0.15  # 15% of 15 samples = 2.25 → 3 iterations (rounded up)
)

# Results
print(f"Total outliers removed: {results.total_samples_removed}")
print(f"Final sample count: {len(mc.active_samples)}")

# Save configuration for later reuse
config = mc.get_config()
config_dict = config.model_dump()
# Save to JSON file
import json
with open('methylcentroid_config.json', 'w') as f:
    json.dump(config_dict, f, indent=2)

# Later: Load and recreate
with open('methylcentroid_config.json', 'r') as f:
    saved_config = json.load(f)
mc2 = MethylCentroid.from_json(saved_config)
```

#### Key Features

- **Information-Theoretic Distance**: Uses Jeffreys divergence for statistically sound outlier detection
- **One-Tailed Statistical Test**: Appropriate hypothesis testing since Jeffreys divergence ≥ 0
- **Adaptive Distribution Fitting**: Automatically selects Normal vs Beta distribution based on data characteristics
- **Average-Based Scaling**: Returns average divergence per position for interpretable chart values
- **Configuration Persistence**: Save and reload analysis configurations using Pydantic models
- **Iterative Algorithm**: Progressively removes outliers until convergence
- **Statistical Rigor**: Employs proper hypothesis testing with configurable significance levels
- **Memory Efficient**: Leverages pre-computed extended centroid statistics
- **Parallel Processing**: Uses multi-threading for distance calculations on large datasets

#### Interpretation of Results

- **Low p-values** (< α) indicate statistically significant outliers
- **Distance values** are now averages per position (typically 0-1 range) for better chart readability
- **Outlier samples** are typically those with substantially different methylation patterns
- **Convergence** occurs when no more statistically significant outliers are detected
- **Final centroid** represents the methylation pattern of the core biological group

The outlier detection algorithm ensures that the final centroid accurately represents the methylation patterns of similar biological samples by systematically removing samples that deviate significantly from the group consensus.

### GPU Acceleration

Automatic GPU detection and acceleration:

```python
from methyl_utils.gpu_detection import print_gpu_status

# Check GPU availability
print_gpu_status()

# GPU acceleration is automatically used when available
mc = MethylCentroid(...)  # Will use GPU if available
```

### Incremental Operations

Add or remove samples without full recalculation:

```python
# Add new sample
mc.add_sample(sample_index=0, is_new_sample=True)

# Remove sample
mc.remove_sample(sample_index=1, is_new_sample=False)
```

## Examples

### Complete Workflow Example

See `methylcentroid/examples/extended_centroid_example.py` for comprehensive examples including:

- Basic vs extended centroid comparison
- Incremental operations demonstration
- Outlier removal workflow
- Data validation methods

### Batch Processing

```python
# Process multiple chromosome/context combinations
chromosomes = [str(i) for i in range(1, 23)] + ["X"]
contexts = ["CG", "CHG", "CHH"]

for chrom in chromosomes:
    for ctx in contexts:
        mc = MethylCentroid(
            samples=sample_paths,
            chrom=chrom,
            ctx=ctx,
            output_dir=output_dir,
            max_iterations_percentage=0.1  # 10% of samples, rounded up
        )
        # build_centroid() automatically uses extended centroids for proper outlier detection
        results = mc.build_centroid()
        print(f"Completed {chrom}-{ctx}: {results.total_samples_removed} outliers removed")
```

## Performance

### GPU Acceleration Benefits

- **Array Operations**: 50x speedup
- **Position Alignment**: 50x speedup
- **Centroid Calculation**: 20x speedup
- **Overall Pipeline**: 18x speedup

### Memory Optimization

- Efficient HDF5 compression (Zstd level 9)
- Sparse data handling
- Memory-aware caching
- GPU memory pooling

### Benchmarking

```bash
# Run performance benchmarks
python benchmark_gpu_performance.py
```

## Testing

### Run Tests

```bash
# Install test dependencies
poetry install --with dev

# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=methylcentroid
```

### Quality Assurance

The project includes BugSpot integration for automated code quality analysis:

```bash
# Run BugSpot analysis
python scripts/bugspot_analyzer.py .

# Pre-commit hooks (automatic)
poetry run pre-commit install
git commit -m "Your changes"
```

## Contributing

### Development Setup

```bash
# Clone repository
git clone <repository-url>
cd MethylCentroid

# Install development dependencies
poetry install --with dev

# Install pre-commit hooks
poetry run pre-commit install

# Run tests and linting
poetry run pytest
poetry run black .
poetry run flake8 .
poetry run mypy .
```

### Code Quality

- **BugSpot**: Automated bug detection and code quality analysis
- **Black**: Code formatting
- **Flake8**: Linting
- **MyPy**: Type checking
- **Pre-commit**: Automated checks

### Adding New Features

1. Create feature branch
2. Write tests
3. Implement feature
4. Run full test suite
5. Submit pull request

## Changelog

### Version 2.0.0 (2024-10-XX)
- **Modular Architecture**: Complete refactoring following SOLID principles for maintainability
- **MethylUtils Integration**: Leverages shared utilities for logging, performance profiling, and GPU management
- **Advanced Outlier Detection**: Probabilistic Beta classifier for ≥20 samples, multi-metric consensus
- **Dynamic Memory Management**: Intelligent chunking, LRU caching, and memory-aware processing
- **Performance Profiling**: Context manager support and comprehensive performance monitoring
- **Code Deduplication**: Eliminated duplicate logging and utility code
- **Enhanced CLI**: Clean, organized command-line interface with grouped options
- **Factory Pattern**: Pluggable outlier detection algorithms

### Version 1.0.0 (2024-09-XX)
- **Release Ready**: Production-ready version with comprehensive documentation
- **Docker Container Support**: Full support for execution within epimethyl Docker containers
- **Enhanced CLI**: Improved command-line interface with container-aware examples
- **Configuration Management**: Pydantic-based configuration validation and management
- **GPU Acceleration**: Automatic GPU detection and acceleration (10-50x speedup)
- **Multiple Distance Metrics**: Support for Jeffreys Divergence, Jensen-Shannon Distance, Weighted Jensen-Shannon Distance, Hellinger Distance, and Wasserstein Distance
- **Robust Outlier Detection**: Statistical significance testing with adaptive distribution fitting
- **Incremental Operations**: Add/remove samples from existing centroids without full recalculation
- **Memory Optimization**: Efficient HDF5 compression and memory-aware processing
- **BugSpot Integration**: Automated code quality monitoring and analysis

### Version 0.1.0 (2024)
- Initial release with core methylation centroid functionality
- Basic outlier detection using Jeffreys divergence
- Command-line interface for batch processing
- Support for CG, CHG, CHH contexts across all chromosomes

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Citation

If you use MethylCentroid in your research, please cite:

```bibtex
@software{methylcentroid,
  title = {MethylCentroid: High-Performance Methylation Centroid Calculation},
  author = {David Izada Rodriguez},
  year = {2024},
  url = {https://github.com/your-repo/MethylCentroid}
}
```

## Support

For questions, issues, or contributions:

- **Issues**: [GitHub Issues](https://github.com/your-repo/MethylCentroid/issues)
- **Documentation**: [docs/](docs/)
  - **Theoretical Foundations**: [docs/MethylCentroid_Theoretical_Foundation.md](docs/MethylCentroid_Theoretical_Foundation.md)
  - **Technical Documentation**: [docs/MethylCentroid_Theory.html](docs/MethylCentroid_Theory.html)
- **Email**: dizada@epimethyl.com

---

**Note**: This package assumes all input samples belong to the same biological group. Use extended centroids (`extended=True`) for accurate outlier detection based on multiple metrics. The outlier detection algorithm systematically removes samples with statistically significant deviations from the group consensus, ensuring high-quality centroids for downstream analysis.