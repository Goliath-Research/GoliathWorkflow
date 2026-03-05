# MethylDetectorExplorer

MethylDetectorExplorer is a CLI utility that analyzes and optimizes how MethylDetector chooses positions for refined effect size computation. It implements a **two-phase strategy** so that the CPU-bound ECDF (Pchip) overlap is used only for the most biologically important positions.

## Why two phases?

- **ECDF overlap** (from centroid `binned_stats` via spline interpolation) is CPU-bound and expensive at chromosome scale (e.g. millions of positions).
- **Phase 1** computes an **approximate** bounded effect size for many positions using only fast metrics: delta_mean, centroid variances, and **rough overlap** from discrete bin counts (or discrete Bhattacharyya). No Pchip/ECDF is used.
- Positions are **sorted** by this approximate effect size (descending).
- A **decay analysis** decides how many positions (**K**) should get a **refined** effect size.
- **Phase 2** runs **ECDF overlap and refined bounded effect size** only for the **top K** positions, then merges results.

So the Explorer helps you choose how many positions to refine and produces a report and optional CSV/plot for inspection.

## Requirements

- Centroids must have **binned_stats** (bin_edges, bin_counts). Build them with MethylCentroid using `binned_stats_bins` (e.g. 20).
- MethylUtils (methyl_utils) must be installed (e.g. from the monorepo `packages/methylutils`).

## CLI

Install the package then run:

```bash
methyl-detector-explorer --centroid1-dir /path/to/centroid1 --centroid2-dir /path/to/centroid2 --chromosome 1 --context CG --output-dir /path/to/out
```

Or with explicit H5 paths:

```bash
methyl-detector-explorer --centroid1 /path/to/1-CG.h5 --centroid2 /path/to/2-CG.h5 --output-dir /path/to/out
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--centroid1-dir`, `--centroid2-dir` | - | Directories containing `{chromosome}-{context}.h5` centroid files. |
| `--centroid1`, `--centroid2` | - | Paths to two centroid H5 files (alternative to dir + chromosome + context). |
| `--chromosome` | 1 | Chromosome identifier. |
| `--context` | CG | Methylation context (CG, CHG, CHH). |
| `--sample-fraction` | 0.01 | Fraction of positions used in Phase 1 (e.g. 0.01 = 1%). Use 1.0 for all positions. |
| `--refine-top-k` | - | Fixed number of top positions to refine (overrides K heuristic). |
| `--k-heuristic` | decay_limit | How to choose K: `decay_limit`, `knee`, `threshold`, `fraction`, or `fixed`. |
| `--max-decay-per-position` | 0.01 | For `decay_limit`: stop when decay rate (drop per position) exceeds this. |
| `--threshold-fraction` | 0.1 | For `threshold`: keep positions with effect_size ≥ this fraction of max. |
| `--fraction-top` | 0.01 | For `fraction`: fraction of (sorted) positions to refine. |
| `--min-coverage` | 4 | Minimum coverage passed to load_and_align. |
| `--output-dir`, `-o` | . | Directory for report and optional CSV. |
| `--output` | - | Explicit path for report JSON. |
| `--csv` | false | Write result table to CSV in output-dir. |
| `--verbose`, `-v` | false | Verbose logging. |

## Outputs

- **Report JSON** (default: `methyldetectorexplorer_report.json` in output-dir):  
  `total_positions`, `phase1_sample_size`, `sample_fraction`, `k_chosen`, `k_heuristic`, `k_info`, `time_phase1_s`, `time_phase2_s`, `time_total_s`.
- **Optional CSV** (with `--csv`): Table of positions with `position`, `delta_mean`, `variance1`, `variance2`, `n1`, `n2`, `overlap_approx`, `bounded_effect_size_approx`, `welch_d`, and for top K refined `bounded_effect_size` and `overlap`.

## K heuristics

- **decay_limit**: Stop when the per-position drop in effect size exceeds `--max-decay-per-position`. Use when the sorted curve has a clear “elbow” where the drop suddenly increases.
- **knee**: Simple curvature-based elbow on the effect_size vs rank curve.
- **threshold**: K = number of positions with approximate effect_size ≥ `threshold_fraction * max(effect_size)`.
- **fraction**: K = `fraction_top * N` (N = number of positions in Phase 1).
- **fixed**: K = `--refine-top-k` (must be set).

## Programmatic use

```python
from methyl_detector.explorer import MethylDetectorExplorer

explorer = MethylDetectorExplorer(
    centroid1_path="/path/to/c1.h5",
    centroid2_path="/path/to/c2.h5",
    sample_fraction=0.01,
    k_heuristic="decay_limit",
    max_decay_per_position=0.01,
)
df, report = explorer.run()
print(report["k_chosen"], report["time_total_s"])
# Optional: df.to_csv("results.csv")
```

## See also

- [METHYLDETECTOR_IMPLEMENTATION.md](METHYLDETECTOR_IMPLEMENTATION.md) – How MethylDetector uses MethylUtils.
- [MethylDetector_Theoretical_Foundation.md](MethylDetector_Theoretical_Foundation.md) – ECDF-based comparison and effect size.
