# MethylCentroid Comprehensive Documentation

## 1. Overview

`MethylCentroid` builds representative methylation profiles for a cohort. It is
used upstream of `MethylDetector`, `MethylClassifier`, and validation workflows.

The current public contract is:

1. `samples`, `add_samples`, and `remove_samples` are supported build inputs.
2. centroid comparison is ECDF-only.
3. `binned_stats_bins` is required and must be positive.
4. validation workflows may drive centroid updates through explicit cohort deltas.

## 2. Two MethylCentroid Concepts

There are two classes with the same conceptual name:

- `methyl_centroid.MethylCentroid`
  The runner/orchestrator. This is the class used by configs, the CLI, project
  resolution, and validation orchestration.

- `methyl_utils.core.methyl_frame.MethylCentroid`
  The data object written to HDF5. It stores sufficient statistics and ECDF
  histogram data.

Keeping those roles separate is important:

- the runner resolves cohort membership and executes builds
- the data object holds the final centroid state for downstream consumers

## 3. Theoretical Foundation

For each sample `j` at position `i`:

- coverage: `c_ij = mC_ij + uC_ij`
- methylation fraction: `x_ij = mC_ij / c_ij`

The centroid stores per-position sufficient statistics:

- `N`
- `Sx`
- `Sx2`
- `Sm`
- `Su`
- `Sc2`
- `Swx2`

This supports derived summaries such as:

- mean methylation
- sample variance of methylation fractions
- average methylated and unmethylated counts

### Required ECDF Histogram

Each supported centroid must also include:

- `bins`
- `bin_counts`

These define the empirical distribution of methylation fractions for each
position. `binned_stats_bins` must be `>= 1`; the supported default is `20`.

## 4. Why ECDF Only

The centroid comparison path no longer exposes Normal, Beta, Beta-Binomial, or
Beta-Mixture runtime switches.

The supported comparison path is:

- statistical testing based on per-position moments already stored in the
  centroid
- overlap and effect-size work based on the empirical histogram data
- downstream DMP selection in `MethylDetector` using those ECDF-based results

Derived `alpha` and `beta` values may still exist as derived statistics on the
data object, but they are no longer a runtime comparison mode.

## 5. Build Semantics

### Cohort Resolution

At the runner level, cohort membership is resolved as:

```text
effective_samples = samples - remove_samples + add_samples
```

That resolved cohort is what gets built for the current chromosome/context.

### Persisted Cohort State

After a successful build, the final active cohort is written to:

- HDF5 metadata field `samples_used`
- sidecar config field `samples` in `{chrom}-{ctx}_config.json`

This is what lets downstream tools and validation runs understand exactly which
cohort produced a centroid.

## 6. CPU And GPU Implementation

### CPU

The CPU path uses:

- NumPy/pandas accumulation
- sorted position unions
- chunked processing for large contexts
- the same sufficient-statistics and histogram schema as the GPU path

### GPU

The GPU path uses CuPy through `MethylCentroidBuilder` when available.

Important behavior:

- GPU acceleration is optional
- CPU fallback is automatic when GPU support is unavailable
- finalized centroids are converted back to CPU objects before persistence

## 7. Core Implementation Components

### Runner

`packages/methylcentroid/methyl_centroid/methyl_centroid.py`

Responsibilities:

- validate config
- resolve cohort deltas
- load sample files
- apply coverage and minimum-sample filters
- save HDF5 + sidecar config

### Builder

`packages/methylutils/methyl_utils/core/centroid_builder.py`

Responsibilities:

- accumulate `N`, `Sx`, `Sx2`, `Sm`, `Su`, `Sc2`, `Swx2`
- accumulate ECDF `bin_counts`
- finalize a `MethylCentroid` data object

### Data Object And I/O

- `packages/methylutils/methyl_utils/core/methyl_frame.py`
- `packages/methylutils/methyl_utils/core/io.py`

Responsibilities:

- represent samples and centroids
- attach and validate histogram data
- load and save the supported centroid schema

## 8. Usage

### Single Config JSON

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

### Batch Config JSON

```json
{
  "chromosomes": ["1", "2", "3"],
  "contexts": ["CG", "CHG", "CHH"],
  "base_config": {
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
  },
  "parallel_combinations": 1,
  "continue_on_error": true,
  "save_batch_summary": true
}
```

### CLI

Activate the repo virtual environment first:

```bash
source .venv/bin/activate
```

Then run one of:

```bash
python -m methyl_centroid.cli --config packages/methylcentroid/configs/example_config.json
python -m methyl_centroid.cli --batch-config packages/methylcentroid/configs/multi_chromosome_config.json
python -m methyl_centroid.cli --config /path/to/config.json --no-gpu
```

Project-driven usage:

```bash
methyl-centroid --project /path/to/project.json --group group1
methyl-centroid --project /path/to/project.json --group group2
methyl-centroid --project /path/to/project.json --group all
```

Validation or orchestration can pass per-group centroid deltas through
`--step-override`.

### Python Class

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
    samples=["/data/samples/sample_001"],
    add_samples=["/data/samples/sample_002"],
    remove_samples=[],
    min_coverage=4,
    min_samples=1,
    binned_stats_bins=20,
)

mc.build_centroid()
```

## 9. Dependencies

### MethylSample

`MethylSample` is the per-sample container used while loading individual cohort
members from `{sample_dir}/{chrom}-{ctx}.h5`.

### MethylCentroidPair

`MethylCentroidPair` compares two centroids and now requires matching ECDF
histogram data. It is the comparison engine used by `MethylDetector`.

### MethylDetector

`MethylDetector` consumes centroids and no longer accepts legacy
distribution-selection config fields for centroid comparison.

Current detector-side ECDF work also depends on centroid histogram data and
stored sufficient statistics:

- `bin_counts` supports ECDF-based comparison and bin-count statistical tests
- `Sc2` and `Swx2` support heterogeneity estimates such as tau-squared filters

### MethylUtils

`MethylUtils` provides the builder, centroid data object, HDF5 I/O, GPU
utilities, and statistical helpers used by `methyl_centroid`.

### MethylValidation

`MethylValidation` can generate run-specific centroid overrides so each
iteration passes group-specific:

- `samples`
- `add_samples`
- `remove_samples`

If prior cohort state is unavailable, validation can still fall back to a full
rebuild from the resolved cohort.

## 10. Output Files

Each build writes:

- `{chrom}-{ctx}.h5`
- `{chrom}-{ctx}_config.json`

The HDF5 file contains:

- centroid datasets under `methylation_data/`
- `methylation_data.attrs["bins"]`
- `methylation_data["bin_counts"]`
- metadata including `samples_used`

## 11. Common Caveats

- The runner class and data class are different objects with different roles.
- Sample paths are sample directories, not direct centroid HDF5 paths.
- Supported centroids require positive ECDF bins; missing `bin_counts` is now an
  error, not a late fallback.
- In-memory add/remove operations exist on the data object, but the supported
  public build contract is the resolved cohort described above.

## 12. Troubleshooting

- Missing sample files:
  each sample directory must contain `{chrom}-{ctx}.h5`.
- Import problems:
  activate `.venv` and install `packages/methylutils` and
  `packages/methylcentroid` in editable mode.
- GPU problems:
  rerun with `--no-gpu` or set `use_gpu` to `false`.
- Detector comparison failures:
  rebuild centroids with a positive `binned_stats_bins` value so ECDF histogram
  data is present.

## 13. Verification

The contract is covered by targeted regression tests for:

- cohort delta resolution and persisted final membership
- rejection of `binned_stats_bins <= 0`
- ECDF-only centroid comparison
- validation handoff of per-group centroid delta overrides
