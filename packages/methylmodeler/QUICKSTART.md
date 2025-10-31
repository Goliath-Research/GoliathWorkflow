# MethylModeler Quick Start Guide

This guide will help you get MethylModeler up and running quickly.

## Prerequisites

- Docker and Docker Compose
- NVIDIA GPU with CUDA support
- NVIDIA Container Toolkit

## Quick Start with Docker Container

### 1. Container Setup

```bash
# Navigate to the project directory
cd /home/ubuntu/MethylModeler

# Build and start the Docker container
make docker-build
make docker-run

# Access the container shell
make docker-shell
```

### 2. Package Installation

```bash
# Install the package in development mode
poetry install

# Test the installation
make test
```

### 3. Run Your First Analysis

```bash
# Run with JSON configuration
python -m methyl_modeler examples/config_WT-msh1.json

# With verbose output
python -m methyl_modeler examples/config_WT-msh1.json --verbose
```

## Container Management

```bash
# Build container
make docker-build

# Start container
make docker-run

# Access container shell
make docker-shell

# Stop container
make docker-stop
```

## Using MethylModeler

### Command Line Interface

MethylModeler uses JSON configuration files for all parameters:

```bash
# Single comparison
python -m methyl_modeler examples/config_single_comparison.json

# Multiple comparisons
python -m methyl_modeler examples/config_WT-msh1.json

# With verbose output
python -m methyl_modeler examples/config_WT-msh1.json --verbose
```

### Python API

#### Using Pydantic Configuration
```python
from methyl_modeler import MethylModeler
from methyl_modeler.models.config import MethylModelerConfig
from pathlib import Path

# Create configuration
config = MethylModelerConfig(
    centroid1_path=Path("/path/to/centroid1.h5"),
    centroid2_path=Path("/path/to/centroid2.h5"),
    output_dir=Path("./results"),
    alpha=0.05,
    min_N_pct=0.1,
    use_gpu=True
)

# Run analysis
detector = MethylModeler(config)
result = detector.run()

# Access results
print(f"Total positions: {result.comparisons[0].total_positions}")
print(f"Significant positions: {result.comparisons[0].significant_count}")
```

#### Loading Configuration from JSON
```python
from methyl_modeler import MethylModeler
from methyl_modeler.utils.file_utils import load_config_from_json

# Load configuration from JSON file
config = load_config_from_json("config.json")

# Initialize detector with config
detector = MethylModeler(config)

# Run analysis
result = detector.run()
```

## Data Format

Your centroid files should be in HDF5 format with the following structure:
- Extended centroid format with methylation data
- Required columns: `pos`, `mC`, `uC`, `N`, `Sx`, `Sx2`, `log_x_sum`, `log_1_minus_x_sum`
- Consistent structure across all files

## Output Files

The analysis generates several output files:

### Single Comparison
- `{prefix}_significant_positions.csv` - Significant positions with p-values and q-values
- `{prefix}_summary.txt` - Summary statistics
- `{prefix}_pi0_vs_lambda.html` - FDR analysis plot
- `{prefix}_significant_regions.csv` - Grouped significant regions
- `{prefix}_config.json` - Input configuration
- `{prefix}_results.json` - Complete results in JSON format

### Multiple Comparisons
- `methyl_modeler_summary_report.txt` - Overall summary
- `all_comparisons_summary.csv` - Summary table for all comparisons
- Individual comparison files in subdirectories

## Development

### Running Tests
```bash
make test
```

### Code Formatting
```bash
make format
```

### Linting
```bash
make lint
```

### All Checks
```bash
make check
```

## Troubleshooting

### Container Issues
- Ensure Docker and Docker Compose are installed
- Check GPU availability: `nvidia-smi`
- Verify container has GPU access: `docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu20.04 nvidia-smi`

### GPU Issues
- Ensure NVIDIA Container Toolkit is installed
- Check GPU availability: `nvidia-smi`
- Verify Docker has GPU access: `docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu20.04 nvidia-smi`

### Memory Issues
- Reduce batch size or number of samples
- Use CPU-only mode if GPU memory is insufficient

### File Path Issues
- Ensure all data files exist and are accessible
- Use absolute paths if relative paths don't work
- Check file permissions

## Getting Help

- Check the full documentation in `README.modeler`
- Run `python -m methyl_modeler --help` for CLI options
- Examine example files in the `examples/` directory
- Run tests to verify installation: `make test` 