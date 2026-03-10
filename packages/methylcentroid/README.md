# MethylCentroid

`MethylCentroid` builds cohort methylation centroids from per-sample HDF5 data.
It is the user-facing runner in `methyl_centroid`. The persisted centroid data
object lives in `methyl_utils`.

## Current Contract

- `samples`, `add_samples`, and `remove_samples` are the supported cohort inputs.
- Centroid comparison is ECDF-only in `MethylCentroidPair` and `MethylDetector`.
- `binned_stats_bins` is required and must be `>= 1` for supported centroids.
- The final active cohort is saved in both HDF5 metadata (`samples_used`) and
  `{chrom}-{ctx}_config.json`.

## Two MethylCentroid Classes

- `methyl_centroid.MethylCentroid`: runner/orchestrator used by the CLI,
  config files, project resolution, and validation workflows.
- `methyl_utils.core.methyl_frame.MethylCentroid`: data object written to HDF5
  with sufficient statistics and ECDF histogram data.

## What The Centroid Stores

Each position stores:

- `pos`, `tnc`
- `N`, `Sx`, `Sx2`
- `Sm`, `Su`, `Sc2`, `Swx2`
- `bin_counts` plus a global bin count (`bins`) for the ECDF histogram

The in-memory data object exposes derived properties such as mean, variance,
`alpha`, and `beta`, but centroid-to-centroid comparison uses the empirical
histogram data rather than alternate distribution modes.

## Quick Start

Activate the repository virtual environment first:

```bash
source .venv/bin/activate
```

Run a single-config build:

```bash
python -m methyl_centroid.cli --config packages/methylcentroid/configs/example_config.json
```

Run a batch build:

```bash
python -m methyl_centroid.cli --batch-config packages/methylcentroid/configs/multi_chromosome_config.json
```

Run from a pipeline project:

```bash
methyl-centroid --project /path/to/project.json --group group1
```

## Single Config Example

```json
{
  "laboratory": "example-lab",
  "disease": "example-disease",
  "group": "healthy",
  "batch": "2026-03",
  "chrom": "1",
  "ctx": "CG",
  "output_dir": "/path/to/output/centroids/healthy",
  "samples": [],
  "add_samples": [
    "/path/to/samples/sample_001",
    "/path/to/samples/sample_002"
  ],
  "remove_samples": [],
  "min_coverage": 4,
  "min_samples": 1,
  "binned_stats_bins": 20,
  "use_gpu": true,
  "verbose": true
}
```

Sample paths are sample directories, not `{chrom}-{ctx}.h5` file paths. The
runner resolves each cohort member to `{sample_dir}/{chrom}-{ctx}.h5`.

## Python API

Initial build:

```python
from methyl_centroid import MethylCentroid

mc = MethylCentroid(
    laboratory="example-lab",
    disease="example-disease",
    group="healthy",
    batch="2026-03",
    chrom="1",
    ctx="CG",
    output_dir="./centroids/healthy",
    add_samples=[
        "/data/samples/sample_001",
        "/data/samples/sample_002",
    ],
    remove_samples=[],
    min_coverage=4,
    min_samples=1,
    binned_stats_bins=20,
    use_gpu=True,
)

results = mc.build_centroid()
print(results.final_centroid_path)
```

Update an existing cohort:

```python
mc = MethylCentroid(
    laboratory="example-lab",
    disease="example-disease",
    group="healthy",
    batch="2026-03",
    chrom="1",
    ctx="CG",
    output_dir="./centroids/healthy",
    samples=[
        "/data/samples/sample_001",
        "/data/samples/sample_002",
    ],
    add_samples=["/data/samples/sample_003"],
    remove_samples=["/data/samples/sample_001"],
    min_coverage=4,
    min_samples=1,
    binned_stats_bins=20,
)

mc.build_centroid()
```

## CPU And GPU Paths

- CPU builds use NumPy/pandas accumulation and chunked processing when needed.
- GPU builds use CuPy through `MethylCentroidBuilder` when available.
- Both paths finalize to the same `MethylCentroid` HDF5 schema.

## Dependencies

- `MethylSample`: individual sample container loaded from per-sample HDF5 files.
- `MethylCentroidPair`: ECDF-only centroid comparison layer.
- `MethylDetector`: downstream DMP detection built on centroid pairs. Current
  detector-side ECDF utilities also consume centroid `bin_counts`, and its
  heterogeneity filters use stored sufficient statistics such as `Sc2` and
  `Swx2`.
- `MethylUtils`: builder, data model, I/O, GPU helpers, and statistical helpers.
- `MethylValidation`: can pass cohort deltas via project step overrides.

## Output Files

- `{chrom}-{ctx}.h5`: centroid HDF5 with required ECDF histogram data.
- `{chrom}-{ctx}_config.json`: resolved config including final active `samples`.

## Documentation

- `docs/MethylCentroid_Theoretical_Foundation.md`
- `docs/METHYLCENTROID_IMPLEMENTATION.md`
- `docs/USAGE.md`
- `docs/METHYLCENTROID_COMPREHENSIVE_DOCUMENTATION.md`
