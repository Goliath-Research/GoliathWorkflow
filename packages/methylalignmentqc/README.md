# MethylAlignmentQC

Parse NVIDIA Clara Parabricks / bwa-mem2 alignment QC metrics into **per-sample JSON** files for database storage. Output: one JSON per sample as `{output_dir}/{sample_basename}.json`.

## Installation

From the MethylPipeline monorepo (install methylutils first):

```bash
pip install -e ../methylutils
pip install -e .
```

## Usage

### CLI

**Using pipeline project config** (recommended):

```bash
methyl-qc --project /path/to/project.json
methyl-qc --project project.json --step-override alignment_qc_overrides.json
```

Output is written to `{output_base}/alignment_qc/` (one JSON per sample from group1 and group2).

**Batch from a sample list** (requires `--output-dir`):

```bash
methyl-qc --samples sample_dirs.txt --output-dir /out/alignment_qc
methyl-qc --samples /path/to/sample1 /path/to/sample2 --output-dir /out/alignment_qc
```

**Discover samples under a metrics root** (legacy; requires `--output-dir`):

```bash
methyl-qc --metrics-root /path/to/metrics --output-dir /out/alignment_qc
```

**Options:**

- `--project`, `-p`: Path to pipeline project JSON.
- `--step-override`: Optional JSON overrides for the `alignment_qc` step.
- `--samples`: Sample directory path(s) or path to a file (one path per line or JSON array). Requires `--output-dir`.
- `--metrics-root`: Directory to search for `*deduplicate_metrics.txt` / `*duplication_metrics.txt`. Requires `--output-dir`.
- `--output-dir`, `-o`: Output directory (required when using `--samples` or `--metrics-root`).
- `--no-validation`: Skip schema validation of each sample JSON.
- `--verbose`, `-v`: Verbose output.

### Python API

```python
from methyl_alignment_qc import main
from methyl_alignment_qc.project_resolver import resolve_alignment_qc_config
from methyl_alignment_qc.core import process_samples_to_qc_jsons

# From project config
config = resolve_alignment_qc_config("project.json")
process_samples_to_qc_jsons(
    config.sample_paths,
    config.output_dir,
    validate_schema=config.validate_schema,
)

# Or with explicit sample list
process_samples_to_qc_jsons(
    ["/path/to/sample1", "/path/to/sample2"],
    "/out/alignment_qc",
    validate_schema=True,
)
```

## Features

- Parses Picard-style deduplication metrics (Parabricks / bwa-mem2).
- Output: one JSON per sample (`{output_dir}/{sample_basename}.json`) for database ingestion.
- Optional validation of each sample JSON structure.
- Integrates with MethylPipeline project config: `step_config.alignment_qc`, output under `{output_base}/alignment_qc`.
