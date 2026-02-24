# MethylCentroid User Manual

## Overview

MethylCentroid calculates representative methylation profiles (centroids) from groups of samples, with accurate aggregation, memory efficiency, and optional GPU acceleration. It is built on **MethylUtils** for centroid construction (see **METHYLCENTROID_IMPLEMENTATION.md**).

---

## Installation and Running

You can run MethylCentroid either **inside the MethylPipeline Docker container** (recommended for GPU and consistent dependencies) or **in a local virtual environment** with the libraries installed.

### Option A: Using the Docker container

The monorepo provides a `methylpipeline` Docker image and a wrapper script so that all commands run inside the container with CUDA and dependencies configured.

**Prerequisites**

- Docker and (for GPU) NVIDIA Container Toolkit.
- MethylPipeline repo with `docker compose` setup (e.g. `docker compose up -d` from the repo’s `docker` directory).

**1. Start the container**

```bash
cd /path/to/MethylPipeline/docker
docker compose up -d
```

**2. Run MethylCentroid via the wrapper script**

From the methylcentroid package directory:

```bash
cd /path/to/MethylPipeline/packages/methylcentroid
./mc --batch-config configs/pb-cancer_batch_stage1_config.json
```

The `./mc` script runs `python3 -m methyl_centroid.cli` inside the `methylpipeline` container with the current directory mounted (host paths under `/home/ubuntu/MethylPipeline` are typically available under `/workspace` in the container).

**3. Single config or other CLI options**

```bash
./mc --config configs/example_config.json
./mc --no-gpu --batch-config configs/batch.json
```

**4. Run CLI directly inside the container (optional)**

```bash
docker exec -w /workspace/packages/methylcentroid methylpipeline \
  python3 -m methyl_centroid.cli --batch-config configs/pb-cancer_batch_stage1_config.json
```

Use the same paths as in the container (e.g. `/workspace/...` if the repo is mounted there).

### Option B: Virtual environment (pip or Poetry)

Install MethylUtils first (MethylCentroid depends on it), then MethylCentroid.

**1. Create and activate a virtual environment**

```bash
python3 -m venv .venv
source .venv/bin/activate   # Linux/macOS
# or:  .venv\Scripts\activate   # Windows
```

**2. Install MethylUtils (from monorepo)**

```bash
cd /path/to/MethylPipeline/packages/methylutils/methyl_utils
pip install -e .
```

**3. Install MethylCentroid (from monorepo)**

```bash
cd /path/to/MethylPipeline/packages/methylcentroid
pip install -e .
# or with Poetry:
# poetry install
```

**4. Optional: GPU support**

Install CuPy to match your CUDA version, e.g.:

```bash
pip install cupy-cuda12x   # adjust to your CUDA version
```

**5. Run**

```bash
python -m methyl_centroid.cli --config config.json
python -m methyl_centroid.cli --batch-config batch_config.json
python -m methyl_centroid.cli --config config.json --no-gpu
```

---

## Quick Start

### Command line (batch config)

```bash
cd /path/to/MethylPipeline/packages/methylcentroid
./mc --batch-config configs/pb-cancer_batch_stage1_config.json
```

### Python API

```python
from methyl_centroid import MethylCentroid

mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='./output',
    add_samples=['/data/sample1', '/data/sample2', '/data/sample3'],
    min_coverage=4
)

results = mc.build_centroid()
print(f"Centroid saved to: {results.final_centroid_path}")
```

---

## Configuration Files

### Batch processing

```json
{
  "chromosomes": ["1", "2", "3", "X"],
  "contexts": ["CG", "CHG", "CHH"],
  "base_config": {
    "samples": ["/data/healthy1", "/data/healthy2", "/data/healthy3"],
    "output_dir": "/output/centroids",
    "min_coverage": 4,
    "use_gpu": true
  },
  "continue_on_error": true
}
```

### Single (chrom, context) config

```json
{
  "chrom": "1",
  "ctx": "CG",
  "samples": ["/data/sample1", "/data/sample2", "/data/sample3"],
  "output_dir": "/output/centroids",
  "min_coverage": 4,
  "use_gpu": true,
  "verbose": true
}
```

---

## Key Parameters

- **`min_coverage`**: Minimum coverage (mC + uC) for a position (default: 4).
- **`use_gpu`**: Use GPU when available (default: true). Override with CLI `--no-gpu`.
- **`verbose`**: Verbose logging (default: true).
- **`samples`**: Current cohort sample paths (for updates).
- **`add_samples`**: New sample paths to add.
- **`remove_samples`**: Sample paths to remove.

---

## Output Files

1. **`{chrom}-{ctx}.h5`**: HDF5 centroid (pos, mC, uC, N, Sx, Sx2, log_x_sum, log_1_minus_x_sum; extended stats if built with them).
2. **`{chrom}-{ctx}_config.json`**: Metadata and configuration.

---

## Common Workflows

### Create centroid for a cohort

```python
from methyl_centroid import MethylCentroid

mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='./centroids/healthy',
    add_samples=['healthy_sample1', 'healthy_sample2'],
    min_coverage=4
)
mc.build_centroid()
```

### Incremental update (add samples)

```python
mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='./centroids/healthy',
    samples=['healthy_sample1', 'healthy_sample2'],
    add_samples=['healthy_sample_new1', 'healthy_sample_new2']
)
mc.build_centroid()
```

### Optional binned stats

```python
mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='./centroids/healthy',
    add_samples=['sample1', 'sample2'],
    min_coverage=4,
    enable_binned_stats=True,
    binned_stats_bins=32
)
mc.build_centroid()
```

---

## Integration with MethylPipeline

MethylCentroid is the first step in the pipeline:

```
MethylCentroid → MethylDetector → MethylClassifier
    (Generate)      (Detect)          (Predict)
```

- **Input**: Raw methylation samples (HDF5 per chrom/context), multiple samples per group.
- **Output**: Centroids (one per group) used by MethylDetector for DMP detection.

---

## Troubleshooting

- **GPU not used**: Set `use_gpu=false` in config or use CLI `--no-gpu`.
- **Large CHH memory use**: Increase `min_coverage` or run with `use_gpu=false`.
- **Missing sample files**: Ensure each sample path contains the expected `{chrom}-{ctx}.h5` file for the chrom/context you are building.

For theory and implementation details, see **MethylCentroid_Theoretical_Foundation.md** and **METHYLCENTROID_IMPLEMENTATION.md**.
