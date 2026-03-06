# MethylDetectorExplorer

MethylDetectorExplorer is a CLI utility that analyzes and optimizes how MethylDetector chooses positions for refined effect size computation. It implements a **two-phase strategy** so that the CPU-bound ECDF (Pchip) overlap is used only for the most biologically important positions.

## Why two phases?

- **ECDF overlap** (from centroid `binned_stats` via spline interpolation) is CPU-bound and expensive at chromosome scale (e.g. millions of positions).
- **Phase 1** computes an **approximate** bounded effect size for many positions using only fast metrics: delta_mean, centroid variances, and **rough overlap** from discrete bin counts (or discrete Bhattacharyya). No Pchip/ECDF is used.
- Positions are **sorted** by this approximate effect size (descending).
- A **decay analysis** decides how many positions (**K**) should get a **refined** effect size.
- **Phase 2** runs **ECDF overlap and refined bounded effect size** only for the **top K** positions, then merges results.

So the Explorer helps you choose how many positions to refine and produces a report and optional CSV/plot for inspection.

## Position filter (min-N)

Before Phase 1, positions are filtered so that only those with sufficient N in **both** centroids are compared. This avoids comparing when one group has almost no data at a position.

- **`--min-N`** (absolute): Keep a position only if n1 ≥ min-N and n2 ≥ min-N. If set, this overrides the percentage rule.
- **`--min-N-pct`** (default **5%**): Keep a position only if min(n1, n2) ≥ min-N-pct × max(n1, n2) at that position (and max(n1, n2) > 0). So the smaller group must have at least 5% of the larger group’s count.

Subsampling (e.g. `--sample-fraction`) and Phase 1 then operate only on this filtered set. The report includes `positions_after_min_N_filter`.

## Approximate overlap (Phase 1) and bin alignment

Phase 1 uses an **approximate overlap** to compute bounded effect size without ECDF. Two modes:

- **Discrete Bhattacharyya** (sum √(p₁·p₂) over bins): Used only when both centroids share the **same** `bin_edges`. If the two centroids were built with different `binned_stats_bins` or bin edges, bin index *i* in one is a different value range than in the other, so discrete overlap can be misleading (often inflated → approximate effect size too low).
- **Normal-based overlap** (2·Φ(−welch_d/2)): Does not use bin counts; avoids bin alignment issues.

With **`--approx-overlap auto`** (default): discrete Bhattacharyya is used when `bin_edges` match; otherwise a warning is logged and Normal-based overlap is used. Use **`--approx-overlap normal`** to force Normal overlap and get approximate effect sizes that do not depend on bin alignment (useful when approx vs exact counts differ a lot). For comparable exact vs approx results, build both centroids with the same `binned_stats_bins`; the report field `approx_overlap_method` shows which method was used (`discrete_bhattacharyya` or `normal`).

## Scale calibration (effect size vs ks_p)

Use **`--calibrate-scale`** to have the Explorer choose the sigmoid scale that **maximizes Spearman correlation** between refined `bounded_effect_size` and (1 − ks_p) on the top K positions. The grid search tries scales from 0.5 to 12 in steps of 0.5; the chosen scale and the achieved correlation are written to the report (`sigmoid_scale_used`, `effect_size_vs_ks_p_correlation`) and the refined effect sizes are recomputed with that scale. This gives a data-driven scale so effect size better approximates the “expected p-value for DMP classification” on that run.

**How exact is the refined effect size?** It is exact relative to: (1) the binned ECDF (finer bins → closer to the true distribution), (2) PCHIP interpolation between bin edges, and (3) the KS statistic computed on a finite grid (default 256 points), which can slightly underestimate the true sup. Approx (e.g. Normal overlap) and refined (KS-based) can still differ in scale because they use different overlap notions; the refined value is the more distribution-aware estimate. See [Effect_Size_Theory.tex](Effect_Size_Theory.tex) § “Precision of the exact effect size”.

## Refined effect size and ECDF cut-point

The biologist’s goal is to select DMPs with **significant differences in means** (corrected by variance and overlap). Because the refined effect size has no known null distribution, significance is assessed practically by building the **ECDF of (refined) effect_size** and using it to define a cut-point (extreme values).

- **`--refine-all`**: Refine effect size with ECDF for **all** positions (no K limit). Slower, but gives refined effect_size and ECDF for every position so the cut-point is based on the full distribution.
- For refined rows, the CSV includes **`effect_size_ecdf`**: the empirical CDF value of that row’s `bounded_effect_size` among the refined set (so ECDF ∈ (0, 1); high effect → high ECDF). Use it to flag “top” positions (e.g. effect_size_ecdf ≥ 0.95).
- The report JSON includes **`effect_size_90th_percentile`**, **`effect_size_95th_percentile`**, **`effect_size_99th_percentile`** (when K > 0): the value of refined effect_size at that quantile. Use e.g. `effect_size_95th_percentile` as a suggested cut: keep positions with `bounded_effect_size` ≥ that value (top 5%).

In **MethylDetector**, set **`effect_size_quantile`** in the config (e.g. `0.95`) to keep only DMPs with refined effect_size ≥ that empirical quantile. When set, the detector uses the full ECDF path (refined effect_size for all statistical DMPs), adds `effect_size_ecdf` to the table, and applies the quantile cut.

## Requirements

- Centroids must have **binned_stats** (in memory: bin_edges, bin_counts). Build them with MethylCentroid using `binned_stats_bins` (e.g. 20). For comparable Phase 1 vs Phase 2 results, use the same bin count for both centroids. Centroid H5 files store only `methylation_data.attrs["bins"]` and `methylation_data["bin_counts"]`; bin edges are derived as `np.linspace(0, 1, bins+1)` (proportions are always in [0,1]).
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
| `--refine-all` | false | Refine effect_size with ECDF for all positions (slow). Use for ECDF-based cut-point on full set. |
| `--k-heuristic` | decay_limit | How to choose K: `decay_limit`, `knee`, `threshold`, `fraction`, or `fixed`. |
| `--max-decay-per-position` | 0.01 | For `decay_limit`: stop when decay rate (drop per position) exceeds this. |
| `--threshold-fraction` | 0.1 | For `threshold`: keep positions with effect_size ≥ this fraction of max. |
| `--fraction-top` | 0.01 | For `fraction`: fraction of (sorted) positions to refine. |
| `--min-coverage` | 4 | Minimum coverage passed to load_and_align. |
| `--min-N` | - | Minimum N per group (absolute): keep positions where n1 ≥ min-N and n2 ≥ min-N. Overrides `--min-N-pct` if set. |
| `--min-N-pct` | 0.05 | Minimum N as fraction of max at position (default 5%): keep where min(n1,n2) ≥ min-N-pct × max(n1,n2). Used when `--min-N` is not set. |
| `--approx-overlap` | auto | Phase 1 overlap: `auto` (discrete when bin_edges match, else normal), `discrete` (Bhattacharyya from bin counts), `normal` (2·Φ(−welch_d/2)). Use `normal` to avoid bin alignment issues. |
| `--calibrate-scale` | false | Calibrate sigmoid scale to maximize Spearman correlation between effect_size and (1 − ks_p) on refined positions; report includes chosen scale and correlation. |
| `--sigmoid-scale` | 3.0 | Sigmoid scale for bounded effect size. Ignored when `--calibrate-scale` is set. Same parameter as detector config `sigmoid_scale`. |
| `--output-dir`, `-o` | . | Directory for report and optional CSV. |
| `--output` | - | Explicit path for report JSON. |
| `--csv` | false | Write result table to CSV in output-dir. |
| `--verbose`, `-v` | false | Verbose logging. |

## Outputs

- **Report JSON** (default: `methyldetectorexplorer_report.json` in output-dir):  
  `total_positions`, `positions_after_min_N_filter`, `phase1_sample_size`, `sample_fraction`, `approx_overlap_method`, `sigmoid_scale_used`, `k_chosen`, `k_heuristic`, `k_info`, `time_phase1_s`, `time_phase2_s`, `time_total_s`. With `--calibrate-scale`: also `effect_size_vs_ks_p_correlation` (Spearman). When K > 0: `effect_size_90th_percentile`, `effect_size_95th_percentile`, `effect_size_99th_percentile` (refined effect_size at that quantile, for cut-point selection).
- **Optional CSV** (with `--csv`): Table of positions with `position`, `mean1`, `mean2`, `delta_mean`, `variance1`, `variance2`, `n1`, `n2`, `overlap_approx`, `bounded_effect_size_approx`, `welch_d`, and for refined rows `bounded_effect_size`, `overlap`, `ks_d`, `ks_p`, **`effect_size_ecdf`** (ECDF of refined effect_size among refined set; use for extreme-value cut). Non-refined rows have NaN for `ks_d`, `ks_p`, and `effect_size_ecdf`. Bounded effect size is in [0,1] with **0 = no difference**, 1 = maximum separation.

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
    min_N=None,       # or e.g. 10 for absolute; default uses min_N_pct=0.05
    min_N_pct=0.05,
    approx_overlap="auto",  # or "normal" to avoid bin alignment issues
    calibrate_scale=False,  # set True to maximize correlation effect_size vs (1 - ks_p)
    sigmoid_scale=3.0,     # same default as detector config
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
