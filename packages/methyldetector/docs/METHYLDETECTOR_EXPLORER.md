# MethylDetectorExplorer

`MethylDetectorExplorer` now mirrors the detector pipeline instead of using a two-phase approximate/refine ranking strategy.

## Pipeline

1. Align the centroids and keep positions supported in both groups after the min-coverage / min-N filter.
2. Apply a `delta_mean_reduction` gate on this aligned locus set before significance testing.
3. Run the histogram-derived Mann-Whitney U test on the surviving positions, then apply FDR correction and keep loci with `q_value <= alpha`.
4. Compute continuous ECDF overlap from the PCHIP-derived PDFs:

   `overlap = integral_0^1 min(f1(x), f2(x)) dx`

5. Compute the canonical biological score:

   `effect_size = |delta_mean| * (1 - overlap) * exp(-lambda_var * (sqrt(variance1) + sqrt(variance2)))`

6. Optionally optimize `lambda_var` by maximizing the Spearman correlation between `effect_size` and `(1 - q_value)` on the reduced set.

## Why the `delta_mean` reduction gate exists

The histogram-derived Mann-Whitney U stage and the continuous ECDF overlap stage are both expensive at large-context scale. The Explorer therefore applies `delta_mean_reduction` on the aligned locus set before significance testing so only biologically plausible candidates reach the non-parametric statistical and ECDF scoring stages.

## Requirements

- Centroids must contain `binned_stats` (`bin_edges`, `bin_counts`).
- Both centroids should be built with the same number of bins so the continuous ECDF representation is comparable.

## CLI

Directory-based usage:

```bash
methyl-detector-explorer \
  --centroid1-dir /path/to/centroid1 \
  --centroid2-dir /path/to/centroid2 \
  --chromosome 1 \
  --context CG \
  --output-dir /path/to/out
```

Direct-file usage:

```bash
methyl-detector-explorer \
  --centroid1 /path/to/1-CG.h5 \
  --centroid2 /path/to/2-CG.h5 \
  --output-dir /path/to/out
```

### Key options

| Option | Meaning |
|--------|---------|
| `--alpha` | FDR threshold after the histogram-derived Mann-Whitney U test. |
| `--min-N`, `--min-N-pct` | Minimum per-group support before any testing. |
| `--delta-mean-reduction` | Optional pre-ECDF reduction threshold. |
| `--min-delta-mean` | Biological filter on `delta_mean` after final scoring. |
| `--max-overlap` | Biological filter on continuous overlap. |
| `--min-effect-size` | Biological filter on the final canonical score. |
| `--lambda-var` | Variance-penalty strength in the final formula. |
| `--optimize-lambda-var` | Search for the `lambda_var` that best aligns `effect_size` with `(1 - q_value)` on the reduced set. |
| `--lambda-var-min`, `--lambda-var-max`, `--lambda-var-step` | Search range for `--optimize-lambda-var`. |
| `--ecdf-overlap-grid-size` | Grid size used to integrate the continuous overlap. |

## Outputs

- Report JSON:
  `total_positions`, `positions_after_min_N_filter`, `positions_after_delta_mean_reduction`, `positions_after_statistical_filter`, `positions_after_biological_filter`, `lambda_var_used`, `time_total_s`, and the effect-size percentiles when available.
- Optional CSV:
  `position`, `mean1`, `mean2`, `delta_mean`, `variance1`, `variance2`, `n1`, `n2`, `p_value`, `q_value`, `overlap`, `effect_size`, `effect_size_reliability`, and `effect_size_ecdf`.

## Programmatic use

```python
from methyl_detector.explorer import MethylDetectorExplorer

explorer = MethylDetectorExplorer(
    centroid1_path="/path/to/c1.h5",
    centroid2_path="/path/to/c2.h5",
    alpha=0.05,
    delta_mean_reduction=0.1,
    lambda_var=2.0,
    optimize_lambda_var=True,
)
df, report = explorer.run()
```
