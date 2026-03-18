---
name: Remove Mann-Whitney reporting
overview: Remove the user-facing message that says the program is "using Mann-Whitney U" so reporting reflects the actual default (Kolmogorov-Smirnov on ECDF). The log lives in MethylUtils; MethylDetector already logs the correct test when using ks_ecdf.
todos: []
isProject: false
---

# Remove Mann-Whitney U from program reporting

## Problem

The program logs: **"Comparing centroids at N common positions using histogram-derived Mann-Whitney U"**. This is emitted by [packages/methylutils/methyl_utils/methyl_centroid_pair.py](packages/methylutils/methyl_utils/methyl_centroid_pair.py) inside `compare_centroids()`, which is called by MethylDetector. MethylDetector’s **default** is `significance_test = "ks_ecdf"` (Kolmogorov-Smirnov on the precise ECDF); it only uses the Mann-Whitney–derived p-values as an intermediate step when using KS, then overwrites them. So the log is misleading.

## Change (MethylUtils only)

**File:** [packages/methylutils/methyl_utils/methyl_centroid_pair.py](packages/methylutils/methyl_utils/methyl_centroid_pair.py)

1. **Log message (lines 542–545)**
  Replace the message that mentions "histogram-derived Mann-Whitney U" with a neutral one that does not name a test, for example:
  - **Before:** `"Comparing centroids at %s common positions using histogram-derived Mann-Whitney U"`
  - **After:** `"Comparing centroids at %s common positions"`  
   (Optionally: `"... (non-parametric comparison)"` if you want to keep a generic description.)
2. **Class docstring (lines 76–80)**
  Update the sentence that says "the statistical gate defaults to histogram-derived Mann-Whitney" so it doesn’t imply Mann-Whitney is the only or default test. For example:  
   `"the statistical gate uses a non-parametric comparison from bin counts; callers (e.g. MethylDetector) may replace p-values with KS on the precise ECDF"`.

## What stays unchanged

- **Mann-Whitney implementation**: `mann_whitney_from_bin_counts` in MethylUtils and its use inside `_process_batch` remain; MethylDetector still uses that path for initial comparison and then overwrites p/q when `significance_test == "ks_ecdf"`.
- **Config**: `significance_test: Literal["ks_ecdf", "mann_whitney"]` and the `mann_whitney` option stay; only the **reporting** is corrected.
- **Docs**: No change required for this fix; optional follow-up could align README/docs to say "Kolmogorov-Smirnov (default)" where they currently emphasize Mann-Whitney.

## Result

Users will no longer see "using Mann-Whitney U" in the log when running with default settings. When `ks_ecdf` is used they already see `"significance from KS on precise ECDF"` from MethylDetector; with this change the earlier message will no longer contradict that.