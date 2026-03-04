# MethylCentroid User Manual

## Overview

MethylCentroid calculates representative methylation profiles (centroids) from groups of samples, with accurate aggregation, memory efficiency, and optional GPU acceleration. It is built on **MethylUtils** for centroid construction (see **METHYLCENTROID_IMPLEMENTATION.md**).

There are **two ways to run MethylCentroid**:

1. **Docker container** — all commands run inside the `methylpipeline` image (GPU and dependencies included).
2. **Local host with virtual environment** — you create a venv, install MethylUtils and MethylCentroid, activate the venv, and run on the host.

Use one or the other; the CLI and Python API are the same once the environment is active.

---

## Setup 1: Docker container

Use this when you want a single, reproducible environment (e.g. shared GPU, CI, or no local Python install).

**Prerequisites:** Docker; for GPU, NVIDIA Container Toolkit.

**1. Start the container**

```bash
cd /path/to/MethylPipeline/docker
docker compose up -d
```

**2. Run MethylCentroid**

From the methylcentroid package directory, use the wrapper script (it runs the CLI inside the container):

```bash
cd /path/to/MethylPipeline/packages/methylcentroid
./mc --batch-config configs/pb-cancer_batch_stage1_config.json
```

Other examples:

```bash
./mc --config configs/example_config.json
./mc --no-gpu --batch-config configs/batch.json
```

**Alternative:** run the CLI directly in the container (paths must be valid inside the container, e.g. `/workspace/...`):

```bash
docker exec -w /workspace/packages/methylcentroid methylpipeline \
  python3 -m methyl_centroid.cli --batch-config configs/pb-cancer_batch_stage1_config.json
```

---

## Setup 2: Local host with virtual environment

Use this when you run on the host (e.g. your laptop or a login node) and want to activate a virtual environment before running MethylCentroid.

**Prerequisites:** Python 3.8+; optional CuPy for GPU.

**1. Create a virtual environment**

From the repo root or from `packages/methylcentroid`:

```bash
python3 -m venv venv
```

(You can use another name, e.g. `.venv`; the rest of the doc uses `venv`.)

**2. Activate the virtual environment**

```bash
source ./venv/bin/activate
```

On Windows: `venv\Scripts\activate`. After activation, your shell prompt usually shows `(venv)`.

**3. Install MethylUtils (required dependency)**

```bash
cd /path/to/MethylPipeline/packages/methylutils/methyl_utils
pip install -e .
```

**4. Install MethylCentroid**

```bash
cd /path/to/MethylPipeline/packages/methylcentroid
pip install -e .
```

(Or use Poetry: `poetry install` in the methylcentroid package.)

**5. Optional: GPU support**

If you have CUDA and want GPU acceleration:

```bash
pip install cupy-cuda12x   # adjust to your CUDA version (e.g. cupy-cuda11x)
```

**6. Run MethylCentroid**

With the virtual environment **activated** (e.g. `source .venv/bin/activate` or `source ./venv/bin/activate` from the repo root), use the CLI from any directory:

```bash
python -m methyl_centroid.cli --batch-config configs/pb-cancer_batch_stage1_config.json
python -m methyl_centroid.cli --config configs/example_config.json
python -m methyl_centroid.cli --config config.json --no-gpu
```

Or run Python and use the API (see Python API below). You do **not** use the `./mc` script when using the venv; that script is for Docker only.

---

## Quick Start

After you have chosen a setup and completed it:

- **Docker:** from `packages/methylcentroid`, run `./mc --batch-config <your_batch_config.json>`.
- **Virtual environment:** activate the venv (`source ./venv/bin/activate`), then run `python -m methyl_centroid.cli --batch-config <your_batch_config.json>` (paths in the config must be valid on your host).

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
