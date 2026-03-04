# MethylCentroid

## Overview

**MethylCentroid** computes representative methylation profiles (centroids) from
groups of samples. A centroid summarizes per-position methylation across a
cohort and is used downstream for DMP detection, classification, and validation.

A **methylation centroid** enables:
- **Group Comparisons**: Compare healthy vs. disease cohorts
- **Downstream Analysis**: Generate centroids for DMP detection and classification
- **Efficient Storage**: Persist cohort summaries without full sample matrices

## Key Features

- **⚡ GPU Acceleration**: Optional CUDA acceleration with CPU fallback
- **🧠 Smart Memory Management**: Chunked processing and memory-aware batching
- **🔄 Incremental Operations**: Add/remove samples without full recalculation
- **📦 MethylUtils Integration**: Shared GPU utilities and optimized math kernels
- **🎯 Extended Statistics**: Sufficient stats for Normal/Beta/Beta-Binomial modeling
- **📊 Optional Binned Stats**: Histogram summaries for Beta Mixture refinement

## How It Works

For N samples at genomic position i:

```
Centroid_i = (1/N) × Σ(methylation_level_ij)
```

The extended centroid stores aggregate statistics (Sx, Sx2, log sums, count
moments) so downstream modules can estimate distribution parameters without
retaining full sample matrices.

## Installation

```bash
# Using Poetry (recommended)
cd packages/methylcentroid
poetry install

# Or using pip
pip install -e .
```

### Optional Dependencies

- **GPU Support**: `pip install cupy-cuda13x` (match your CUDA version)
- **Visualization**: `pip install plotly matplotlib`

## Usage

### Basic Example

```python
from methyl_centroid import MethylCentroid

mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='./centroids',
    add_samples=[
        '/data/samples/sample1',
        '/data/samples/sample2',
        '/data/samples/sample3'
    ],
    min_coverage=4
)

results = mc.build_centroid()
print(f"Centroid saved to: {results.final_centroid_path}")
```

### Incremental Updates

```python
# Initial centroid creation
mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='centroids',
    add_samples=['sample1', 'sample2', 'sample3']
)
mc.build_centroid()

# Later: add new samples
mc_updated = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='centroids',
    samples=['sample1', 'sample2', 'sample3'],
    add_samples=['sample4', 'sample5']
)
mc_updated.build_centroid()
```

### Command Line Interface

```bash
# Using configuration file
python -m methyl_centroid.cli --config config.json

# Disable GPU (force CPU)
python -m methyl_centroid.cli --config config.json --no-gpu
```

### MethylCentroidExplorer

Inspect a MethylFrame (a single `.h5` file or a folder of `.h5` files): detect type (MethylSample, MethylBasicCentroid, MethylExtendedCentroid, MethylBetaBinomialCentroid), print metadata, and optionally describe a range of positions in detail (pos, mC, uC, coverage, mean, N, Sx, Sx2, alpha, beta, variance).

**Run with the project virtual environment activated** (e.g. `source .venv/bin/activate` or `source venv/bin/activate` from the repo root). The `methyl-centroid-explorer` CLI is installed into the venv. If you see `ModuleNotFoundError: No module named 'methyl_centroid.explorer'`, reinstall the package so the CLI picks up the explorer module: from the repo root run `pip install -e packages/methylcentroid`.

```bash
# Activate venv first (required)
source .venv/bin/activate   # or: source venv/bin/activate

# Metadata and type for a folder (uses first .h5) or single file
methyl-centroid-explorer /path/to/centroid_or_sample

# Filter to one chromosome/context when path is a folder
methyl-centroid-explorer /path/to/centroids --chrom 1 --context CG

# Per-position detail for a genomic range (avoids loading full 4M–80M positions)
methyl-centroid-explorer /path/to/centroid.h5 --pos-start 1000000 --pos-end 1000100

# Single CSV + density plots (one HTML per coverage quartile); output in cwd
methyl-centroid-explorer /path/to/centroid.h5 --single-csv --pos-start 1000000 --max-positions 1000 --plot-quartiles

# JSON metadata and higher cap for position detail
methyl-centroid-explorer /path/to/centroid.h5 --json-metadata --pos-start 0 --pos-end 5000 --max-positions 5000
```

## Configuration

### JSON Configuration Example

```json
{
  "laboratory": "UCSF",
  "disease": "Breast Cancer",
  "group": "Tumor",
  "batch": "2024-01",
  "chrom": "1",
  "ctx": "CG",
  "output_dir": "./centroids",
  "add_samples": [
    "/data/samples/sample1",
    "/data/samples/sample2"
  ],
  "min_coverage": 4,
  "use_gpu": true,
  "verbose": true
}
```

### Key Parameters

- **chrom**: Chromosome identifier (e.g., '1', 'X', 'MT')
- **ctx**: Methylation context ('CG', 'CHG', 'CHH')
- **min_coverage**: Minimum mC + uC for position inclusion (default: 4)
- **use_gpu**: Enable GPU acceleration when available (default: true)
- **samples / add_samples / remove_samples**: Cohort update inputs

### Paired cohorts (healthy vs disease)

When building two centroids for DMP detection (e.g. healthy vs cancer), **ensure no sample appears in both configs**. A healthy centroid built from a mix of healthy and cancer samples is invalid and leads to failed classifier validation (e.g. 0% correct for the healthy class).

Before building, check for overlapping sample IDs:

```bash
python3 scripts/check_cohort_overlap.py --label-a healthy --label-b cancer \
  configs/PCa_Healthy_centroid_batch_config.json configs/PCa_Cancer_centroid_batch_config.json
```

If overlap is reported, remove the shared samples from one cohort config and rebuild.

## Output

### Centroid HDF5 Structure (core datasets)

```
centroid.h5
├── methylation_data/
│   ├── pos
│   ├── mC
│   ├── uC
│   ├── tnc
│   ├── N
│   ├── Sx
│   ├── Sx2
│   ├── log_x_sum
│   └── log_1_minus_x_sum
└── metadata (attributes)
```

Optional extended stats and binned histograms are included when enabled.

## Documentation

- **[Theoretical Foundation](docs/MethylCentroid_Theoretical_Foundation.md)** — Probabilistic distributions (Normal, Beta, Beta-Binomial, Beta Mixture), sufficient statistics, and formulas.
- **[Implementation (MethylUtils)](docs/METHYLCENTROID_IMPLEMENTATION.md)** — MethylCentroidBuilder, MethylExtendedCentroid/MethylBetaBinomialCentroid, I/O, and how the package uses them.
- **[User Manual](docs/USAGE.md)** — Docker container and virtual environment setup, CLI, Python API, config, and workflows.
- **[Comprehensive Documentation](docs/METHYLCENTROID_COMPREHENSIVE_DOCUMENTATION.md)** — Data model, configuration, GPU/memory, output files, examples, troubleshooting.
- **[Distributions Reference (LaTeX)](docs/METHYLCENTROID_DISTRIBUTIONS.tex)** — Full derivations and sufficient-statistics reference.
