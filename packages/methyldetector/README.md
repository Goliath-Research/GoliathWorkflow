# MethylDetector

**Detect Differentially Methylated Positions and Train ECDF Classifiers**

## Overview

MethylDetector is a production-ready package for detecting Differentially Methylated Positions (DMPs) between two methylation centroids. It combines an ECDF-first statistical gate (Welch or histogram-derived Mann-Whitney with two-stage BH FDR correction) with effect-mass biological filtering to identify meaningful biomarkers for downstream analysis.

### What is MethylDetector?

MethylDetector provides comprehensive DMP detection and analysis:

- **DMP Detection**: Statistical comparison of two ECDF centroids with FDR control
- **Biological Filtering**: A single canonical `effect_size` score combining mean separation, distributional overlap, and a variance reliability penalty
- **Multi-Chromosome Support**: Process single or multiple chromosomes in one run
- **Multi-Context Support**: Process CG, CHG, CHH contexts together with context weighting
- **GPU Acceleration**: High-performance processing with NVIDIA GPUs
- **ECDFClassifier**: Trains a PCHIP-PDF log-likelihood classifier on the selected DMPs
- **Comprehensive Output**: Detailed DMP tables with statistical and biological metadata

## Key Features

- 🔬 **Statistical Rigor**: Welch or histogram-derived Mann-Whitney testing with two-stage BH FDR correction
- 📊 **Biological Filtering**: Single canonical `effect_size` score combining mean separation, distributional overlap, and variance reliability
- 🎯 **Held-out Selection**: Repeated stratified validation splits with balanced-accuracy top-k selection
- 🧬 **Multi-Context Support**: Process CG, CHG, CHH contexts together
- 🧬 **Multi-Chromosome Support**: Process multiple chromosomes in a single run
- 🚀 **GPU Acceleration**: High-performance processing with NVIDIA GPUs
- 📊 **Comprehensive Output**: Detailed DMP tables with statistical metadata
- ⚡ **Memory Efficient**: Intelligent chunking for large genomic datasets
- ✅ **Type Safe**: Full type hints with comprehensive validation
- 📋 **Clean Configuration**: Simplified parameter management with validation warnings

## Installation

```bash
cd packages/methyldetector
pip install -e .

# GPU verification
python -c "import cupy as cp; print(f'GPU count: {cp.cuda.runtime.getDeviceCount()}')"
```

**Note:** Requires MethylUtils (RAPIDS/CUDA) for GPU acceleration.

## Quick Start

### Basic Usage - Single Chromosome

```json
{
  "chromosome": "1",
  "contexts": ["CG"],
  "centroid1_dir": "/path/to/healthy/centroids",
  "centroid2_dir": "/path/to/cancer/centroids",
  "output_dir": "/path/to/output",
  "alpha": 0.05,
  "statistical_test": "mann_whitney",
  "delta_mean_reduction": 0.1,
  "effect_size_coverage": 0.95,
  "validation_split_ratio": 0.2,
  "validation_n_repeats": 3,
  "lambda_var": 2.0
}
```

```bash
methyl-detector config.json
```

### Multi-Chromosome Usage

Process multiple chromosomes in a single run:

```json
{
  "chromosome": ["1", "2", "3", "X"],
  "contexts": ["CG", "CHG", "CHH"],
  "centroid1_dir": "/path/to/healthy/centroids",
  "centroid2_dir": "/path/to/cancer/centroids",
  "output_dir": "/path/to/output",
  "alpha": 0.05,
  "statistical_test": "mann_whitney",
  "delta_mean_reduction": 0.1,
  "effect_size_coverage": 0.95,
  "validation_split_ratio": 0.2,
  "validation_n_repeats": 3,
  "lambda_var": 2.0
}
```

Each chromosome will:
- Process independently with its own centroids
- Generate separate output files: `dmps-1.csv`, `dmps-2.csv`, etc.
- Continue processing even if one fails (with error logging)

### Command Line Interface

```bash
# Run with JSON configuration
./detector config.json

# With verbose output
./detector config.json --verbose

# With log file
methyl-detector config.json --log-file output.log
```

### Python API

```python
from methyl_detector.models.config import MethylModelerConfig
from methyl_detector.core.methyldetector import MethylDetector
from methyl_detector.utils.file_utils import load_config_from_json

# Load configuration
config = load_config_from_json("config.json")

# Initialize and run
detector = MethylDetector(config)
result = detector.run()

# Handle single or multiple results
if isinstance(result, list):
    print(f"Processed {len(result)} chromosomes")
    for r in result:
        print(f"  DMPs: {r.total_biological_dmps:,}")
else:
    print(f"DMPs: {result.total_biological_dmps:,}")
```

## Configuration Parameters

### Input/Output

- **`chromosome`**: Single chromosome (e.g., `"1"`) or list (e.g., `["1", "2", "X"]`)
- **`contexts`**: List of contexts to process (default: `["CG"]`)
  - Options: `"CG"`, `"CHG"`, `"CHH"` or any combination
- **`centroid1_dir`** / **`centroid2_dir`**: Directories containing centroid `.h5` files (format: `{chrom}-{context}.h5`). Centroids must have binned stats for ECDF comparison: in HDF5, `methylation_data.attrs["bins"]` and `methylation_data["bin_counts"]` (build with MethylCentroid using `binned_stats_bins` e.g. 20).
- **`output_dir`**: Output directory for results

### Statistical Parameters

- **`alpha`**: FDR q-value threshold (default: `0.05`). Uses two-stage Benjamini-Hochberg correction applied to the pre-filtered position set.
- **`statistical_test`**: `"welch"` or `"mann_whitney"`. The latter reconstructs a rank test directly from centroid `bin_counts`.
- **`delta_mean_reduction`**: Pre-ECDF gate applied **before** the statistical test. Positions with `|delta_mean| < value` are discarded before testing, making large contexts (CHG, CHH) tractable.

### Biological Filtering

- **`effect_size_coverage`**: Per context, keep the smallest prefix of DMPs whose cumulative `effect_size` reaches this fraction of the total effect mass (e.g. `0.95` keeps the top loci that explain 95% of the effect mass).
- **`biological_only_effect_size_coverage`**: Optional rescue track for high-effect loci that fail the statistical gate. Rescue loci remain explicitly flagged and are never mixed into the confirmed statistical count.
- **`max_tau2_for_dmp`**: Optional heterogeneity filter; drops loci where both groups have high between-sample variance (`tau2`).
- **`lambda_var`**: Variance penalty strength in `effect_size` (default `2.0`). Higher values penalise diffuse, heterogeneous positions more strongly.
- **`enable_eat_transform`**: Optional EAT metadata; reweights the final `effect_size` only. It does **not** change p-values or q-values.

### Validation and Top-k Selection

- **`validation_split_ratio`**: Fraction of samples in each held-out test split. Use a positive value (for example `0.2`) for biologically trustworthy BA reporting.
- **`validation_n_repeats`**: Number of repeated stratified holdout splits used when selecting/reporting top-k by balanced accuracy.
- **`optimization_method`**: `"featurecuts"`, `"binary_search"`, or `"bayesian_optimization"`. FeatureCuts is the default and now reuses cached ECDF log-likelihood prefixes instead of rebuilding the classifier at every `k`.

### MethylDetectorExplorer (staged effect-size analysis)

**MethylDetectorExplorer** is a standalone CLI that mirrors the detector pipeline — statistical significance, `delta_mean` reduction, continuous ECDF overlap, and final `effect_size` — to explore the effect of `lambda_var` and biological filter thresholds without running the full detector. See [METHYLDETECTOR_EXPLORER.md](docs/METHYLDETECTOR_EXPLORER.md) for usage and options.

```bash
methyl-detector-explorer --centroid1-dir /path/to/c1 --centroid2-dir /path/to/c2 --chromosome 1 --context CG --output-dir /out --csv
```

### Filter funnel exploration

You can sweep `effect_size_coverage` over a range in a **single run** and write `filter_funnel.csv` describing how confirmed/rescued DMPs are filtered biologically—no large DMP CSV, no re-runs.

- **Config:** Set `filter_funnel_explore.effect_size_coverage` with `{ "min", "max", "step" }`.
- **Output:** `filter_funnel.csv` in the detection output directory with columns: `n_statistical_dmps`, `effect_size_coverage`, `n_biological_dmps`.
- **Charting:** Use the CSV to plot n_biological_dmps vs filter value (one-at-a-time) or heatmaps/surfaces (full_grid: two filters on axes, color = n_biological_dmps, third as facet).

### Context Weighting

- **`use_context_weights`**: Enable context weighting for multi-context analysis (default: `true`)

### Performance

- **`use_gpu`**: Enable GPU acceleration (default: `true`)
- **`random_state`**: Random seed for reproducibility (default: `42`)

## Output Files

### Per Chromosome

1. **`dmps-{chromosome}-biological-sorted.csv`** - Biological DMPs sorted by importance

`results-{chromosome}.json` includes `bmm_summary` and `bmm_centroid_files` when BMM refinement runs.

### CSV Columns

- `chromosome`, `context`, `position`
- `p_value`, `q_value`
- `mean1`, `mean2`, `delta_mean` (unsigned magnitude), `delta_sign` (+1 hyper, -1 hypo)
- `variance1`, `variance2` (sample variance from Sx/Sx2)
- `n1`, `n2` (sample counts)
- `overlap` (continuous ECDF overlap: ∫ min(f1, f2) dx)
- `effect_size`, `effect_size_reliability`, `effect_size_ecdf`
- `context_weight` (multi-context runs)
- `alpha1`, `beta1`, `alpha2`, `beta2` (Beta MoM parameters; retained for EAT and reference, not used for comparison or classification)

## Core Workflow

```
1. Load Centroids
   ├─ Read {chrom}-{context}.h5 for each context
   ├─ Centroids must have binned_stats (build with binned_stats_bins=20)
   └─ Align to common positions (min coverage filter)

2. Pre-filter (delta_mean gate)
   ├─ Compute |mean1 - mean2| from centroid means (Sx/N)
   └─ Discard positions below delta_mean_reduction threshold
      (avoids running expensive Welch test on positions that
       would be removed by the biological filter anyway)

3. Statistical Testing
   ├─ Welch-style unequal-variance mean-difference test
   ├─ Two-stage Benjamini-Hochberg FDR correction
   └─ Retain positions with q_value <= alpha

4. Continuous ECDF Overlap and Effect Size
   ├─ Build ECDFView lazily for surviving DMP positions only
   ├─ Compute overlap = ∫₀¹ min(f1(x), f2(x)) dx (PCHIP PDFs)
   └─ Compute effect_size = |delta_mean| * (1-overlap) * exp(-λ*(√v1+√v2))

5. Biological Filtering
   ├─ Per-context effect_size_coverage cumulative-mass selection
   ├─ Optional biological-only rescue track
   └─ Sort by effect_size descending

6. Context Weighting (multi-context only)
   ├─ Trimmed mean of effect_size per context
   ├─ Normalize to sum=1.0
   └─ Assign context_weight to each DMP

7. Held-out Validation and Classifier Training
   ├─ Repeated stratified holdouts for balanced accuracy
   ├─ Prefix-cached ECDF log-likelihood scoring for top-k selection
   ├─ Optional Platt calibration on the first held-out split
   └─ ECDFClassifier: PCHIP PDF log-likelihood, effect_size-weighted

8. Generate Reports
   ├─ DMP CSV with all statistical and biological columns
   └─ Summary JSON and classifier artifact
```

## Multi-Chromosome Processing

MethylDetector supports processing multiple chromosomes in a single run:

### Benefits

- **Efficient**: Single Python process, shared GPU memory management
- **Robust**: One chromosome failure doesn't stop others
- **Consistent**: Same configuration applied to all chromosomes
- **Organized**: Each chromosome gets its own output files

### Example

```json
{
  "chromosome": ["1", "2", "3", "X"],
  "contexts": ["CG"],
  "centroid1_dir": "/centroids/healthy",
  "centroid2_dir": "/centroids/cancer",
  "output_dir": "/models/all_chromosomes"
}
```

**Output structure:**
```
/models/all_chromosomes/
├── dmps-1-biological-sorted.csv
├── dmps-2-biological-sorted.csv
└── ...
```

## Statistical Design

MethylDetector uses **Two-Stage Benjamini-Hochberg FDR correction** (statsmodels `fdr_tsbh`) on the pre-filtered position set:

- **Pre-filtering before FDR**: Positions below the `delta_mean_reduction` gate are excluded before the Welch test. FDR correction is therefore applied to a non-random subset. Q-values are liberal relative to full testing — this is a known computational genomics trade-off.
- **Welch test, not LRT**: The significance stage uses `welch_mean_test` (unequal-variance t-test) on sample means and variances from `(Sx2 - Sx²/N)/(N-1)`. This is consistent with the sample variances used in `effect_size`.
- **ECDF-only**: No Beta, Normal, or Beta-Binomial distribution models are used at any stage. All comparison, overlap, and classifier density evaluation uses the ECDF from `binned_stats`.

## Integration with MethylPipeline

### Workflow Position

```
MethylCentroid → MethylDetector → MethylClassifier / MethylMapper / MethylEnricher
   (Centroids)      (DMPs + Models)     (Classification / Mapping / Enrichment)
```

### Inputs

- Centroids from **MethylCentroid** (HDF5 files: `{chrom}-{context}.h5`)

### Outputs

**Per chromosome:**
- `dmps-{chrom}-biological-sorted.csv`: Ranked biological DMPs
- `classifier-{chrom}.pkl`: Bayesian classifier model (for MethylClassifier)
- `results-{chrom}.json`: Summary statistics

### Running MethylClassifier with MethylDetector Output

**No need to wait for MethylMapper or MethylEnricher!**

1. Set `model_dir` = this `output_dir`
2. `input_path` = directory of sample `.h5` files

**Example config** (`configs/PCa_Healthy_classify_config.json`):
```json
{
  "model_dir": "/path/to/PCa_vs_Healthy",  // MethylDetector output_dir
  "input_path": "/path/to/samples/",
  "output_path": "classification_results.csv"
}
```

```bash
methyl-classifier --config configs/PCa_Healthy_classify_config.json
```

See [MethylClassifier README](../methylclassifier/README.md#running-methylclassifier-with-methyldetector-output) for details.


## Performance

### GPU Acceleration

| Operation | CPU Time | GPU Time | Speedup |
|-----------|----------|----------|---------|
| DMP Detection (1M positions) | 45 min | 3 min | 15x |
| FeatureCuts Optimization (~18 evals) | 60 min | 5 min | 12x |
| Complete Analysis | 105 min | 8 min | 13x |

### Memory Usage

- Typical: 4-8 GB
- Peak: 10-15 GB (during optimization)
- Scales linearly with number of positions

## Troubleshooting

### No DMPs Found

**Problem**: `total_biological_dmps = 0`

Use `methyl-detector-explorer` to inspect how many positions survive each filter stage and what the `effect_size` distribution looks like before committing to a full run.

Relax individual filters:
```json
{
  "alpha": 0.10,
  "delta_mean_reduction": 0.05,
  "effect_size_coverage": 0.99,
  "validation_split_ratio": 0.2
}
```

### Too Many DMPs Detected

**Problem**: `dmps-{chromosome}.csv` contains too many positions

Tighten individual filters:
```json
{
  "alpha": 0.01,
  "delta_mean_reduction": 0.2,
  "effect_size_coverage": 0.80,
  "max_tau2_for_dmp": 0.05
}
```
Or enable the optional rescue track only for the strongest underpowered loci with `biological_only_effect_size_coverage`.

### Effect Size Values Are Very Low

**Problem**: All `effect_size` values are below `0.05`

The canonical `effect_size` is bounded by `|delta_mean|` × `(1 - overlap)` × reliability. Typical prostate-cancer CG context values (95th percentile ~0.047) are expected for weakly separated groups. Adjust `effect_size_coverage` to keep more or less of the cumulative effect mass, and use `methyl-detector-explorer` to explore the distribution before running the full detector.

### GPU Out of Memory

**Problem**: CUDA out of memory errors

**Solutions**:
```json
{
  "use_gpu": false  // Disable GPU
}
```

Or process chromosomes sequentially instead of in parallel.

### Out-of-Bounds Errors During Validation

**Problem**: Index errors when loading validation samples

**Solution**: This has been fixed in recent versions. Ensure you're using the latest code.

## Examples

**Examples** (`configs/`):
- `PCa_Healthy_config.json`: Prostate Cancer vs Healthy (all chrom, all contexts)
- `pc-hc1-1-CG_config.json`: Single chrom CG with validation
- `TEMPLATE_simple_CG_only.json`: Basic CG-only template

Copy and customize for your data!


## Documentation

- **[Theoretical Foundation](docs/MethylDetector_Theoretical_Foundation.md)** — ECDF-based comparison, Welch/Mann-Whitney gates, effect size, overlap
- **[MethylDetectorExplorer](docs/METHYLDETECTOR_EXPLORER.md)** — Staged effect-size analysis: significance, delta_mean reduction, lambda_var exploration
- **[Implementation (MethylUtils)](docs/METHYLDETECTOR_IMPLEMENTATION.md)** — MethylCentroidPair, statistical_tests, classifier usage
- **[User Manual](docs/USAGE.md)** — Docker container and virtual environment setup and usage
- **[Quick Start Guide](QUICKSTART.md)** — Get started quickly
- **[Context Selection Guide](CONTEXT_SELECTION_GUIDE.md)** — Choosing methylation contexts
- **[Comprehensive Documentation](docs/METHYLMODELER_COMPREHENSIVE_DOCUMENTATION.md)** — Complete API reference
- **[Classifier Weights and Accuracy](docs/CLASSIFIER_WEIGHTS_AND_ACCURACY.md)** — effect_size and classifier accuracy

## Contributing

Please ensure:
1. Tests pass: `pytest tests/`
2. Configurations validate: Check with Pydantic
3. Documentation updated

## License

MIT License - see [LICENSE](../../LICENSE) file for details.

---

For more information, see:
- [MethylPipeline Documentation](../../docs/)
