# MethylCentroid Usage

## Environment

Activate the repository virtual environment before using the CLI:

```bash
source .venv/bin/activate
```

If the packages are not installed into the environment yet:

```bash
pip install -e packages/methylutils
pip install -e packages/methylcentroid
```

## Single Config

Use `MethylCentroidConfig` when you want to build one chromosome/context pair.

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

Important points:

- `samples` is the current cohort membership.
- `add_samples` are appended after removals are applied.
- `remove_samples` removes by sample directory identity.
- Sample entries are directories, not `.h5` files.
- `binned_stats_bins` is required and must be positive.

Run it with:

```bash
python -m methyl_centroid.cli --config packages/methylcentroid/configs/example_config.json
```

## Batch Config

Use `BatchProcessingConfig` when the same cohort should be built across multiple
chromosomes and contexts.

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

Run it with:

```bash
python -m methyl_centroid.cli --batch-config packages/methylcentroid/configs/multi_chromosome_config.json
```

## CLI Modes

### Config-driven CLI

```bash
python -m methyl_centroid.cli --config /path/to/config.json
python -m methyl_centroid.cli --batch-config /path/to/batch_config.json
python -m methyl_centroid.cli --config /path/to/config.json --no-gpu
```

### Project-driven CLI

This mode resolves cohorts from a pipeline project file and is the path used by
`MethylValidation`.

```bash
methyl-centroid --project /path/to/project.json --group group1
methyl-centroid --project /path/to/project.json --group group2
methyl-centroid --project /path/to/project.json --group all
```

For **hierarchical diseases** (`diseases.groups[].stages`), centroids are built per **resolved leaf** (e.g. `pca` + stage `pca1` → `pca_pca1`). Use `--group all` so every leaf runs. If you see **no samples** for a parent label like `pca` alone, the `stages` field was not loaded—install a current **methyl_utils** from this repo: `pip install -e packages/methylutils`.

When validation or another orchestrator wants to pass cohort deltas explicitly,
use a step override:

```bash
methyl-centroid \
  --project /path/to/project.json \
  --group group1 \
  --step-override /path/to/centroid_group1_override.json
```

Expected step override shape:

```json
{
  "base_config": {
    "samples": [
      "/path/to/previous/sample_001",
      "/path/to/previous/sample_002"
    ],
    "add_samples": ["/path/to/new/sample_003"],
    "remove_samples": ["/path/to/previous/sample_001"]
  }
}
```

## Python Class Usage

### Initial build

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

### Update build

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

The runner resolves the effective cohort as:

```text
effective_samples = samples - remove_samples + add_samples
```

The resulting active cohort is written back to:

- HDF5 metadata field `samples_used`
- sidecar config field `samples`

## Direct CLI Parameters

When not using a JSON config, the important direct flags are:

- `--chromosome`
- `--context`
- `--samples`
- `--output-dir`
- `--min-coverage`
- `--binned-stats-bins`
- `--no-gpu`

The direct CLI path is best for ad hoc usage. Project and JSON configs are the
recommended entry points for reproducible runs.

## Outputs

Each successful build writes:

- `{chrom}-{ctx}.h5`
- `{chrom}-{ctx}_config.json`

The HDF5 centroid contains the required ECDF histogram data in
`methylation_data.attrs["bins"]` and `methylation_data["bin_counts"]`.

## Troubleshooting

- Missing sample files: each sample directory must contain `{chrom}-{ctx}.h5`.
- Import errors: activate `.venv` and ensure both `methylutils` and
  `methylcentroid` are installed in editable mode.
- GPU issues: rerun with `--no-gpu` or `use_gpu: false`.
- Comparison failures downstream: rebuild centroids with a positive
  `binned_stats_bins` value so `bin_counts` is present.
