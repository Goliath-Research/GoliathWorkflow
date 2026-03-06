---
name: Effect size scale calibration for ks_p
overview: Calibrate the sigmoid scale (and optionally the T cap) so that effect_size correlates better with ks_p or approximates the "expected p-value for DMP classification." Propose data-driven scale selection and optional formula tweaks.
todos: []
isProject: false
---

# Effect size scale calibration for better agreement with ks_p

## Why correlation is still limited

- **ks_p** depends only on **T** = sqrt(n_eff)*D: `ks_p = kstwobign.sf(T)`. So (1 - ks_p) = kstwobign.cdf(T) is a strict monotone function of T.
- **effect_size** = sigmoid(scale * welch_d * T) depends on **both** welch_d and T. For the same T (hence same ks_p), effect_size varies with welch_d. So effect_size and ks_p cannot be perfectly correlated unless we drop welch_d.
- The **scale** controls how fast the sigmoid saturates: larger scale → more positions near 0 or 1; smaller scale → more spread in (0,1). So scale changes the *spread* of effect_size and can improve or worsen correlation with (1 - ks_p) depending on the joint distribution of welch_d and T in your data.

## Goal

Improve the match between effect_size and the "expected p-value required to classify a position as DMP" (e.g. so that high effect_size tends to go with small ks_p, and optionally so a chosen effect_size threshold approximates a chosen ks_p threshold). Do this by **calibrating the scale** (and optionally the T cap) rather than changing the formula (keep welch_d for biological meaning).

---

## Option A: Data-driven scale to maximize correlation (recommended)

**Idea**: Choose the scale (and optionally the T cap) that **maximizes** correlation between effect_size and (1 - ks_p) or -log10(ks_p) on the refined positions (Explorer output or a reference run).

**Steps**:

1. For a fixed dataset (e.g. one Explorer run with `--csv`), take the refined rows that have both `bounded_effect_size` and `ks_p`.
2. For each scale in a grid (e.g. [0.5, 1.0, 2.0, 4.0, 8.0, 12.0]) and optionally T_cap in [5, 10, 15, 20], compute effect_size = sigmoid(scale * welch_d * min(T, T_cap)).
3. Compute correlation (Pearson or Spearman) between this effect_size and (1 - ks_p) or -log10(ks_p).
4. Pick (scale, T_cap) that gives the highest correlation. Use that as the default or document it as a "calibrated" default for that pipeline.

**Implementation**:

- Add a small helper or script (e.g. in Explorer or as a standalone util) that takes a CSV with columns welch_d, ks_d, ks_p, n1, n2 (or T and welch_d), and returns the best scale (and optionally T_cap) and the achieved correlation. No change to the main formula; Explorer and MethylUtils could accept a config/default scale that is set from this calibration.
- Alternatively: in [packages/methyldetector/methyl_detector/explorer.py](packages/methyldetector/methyl_detector/explorer.py), after Phase 2, run a quick grid over scale (and T_cap if exposed), compute effect_size for each, and choose the scale that maximizes correlation with (1 - ks_p); then **recompute** bounded_effect_size with that scale and report the chosen scale in the report JSON. That would make each Explorer run self-calibrated.

**Pros**: No change to the formula; keeps welch_d; scale becomes data-appropriate.  
**Cons**: Scale is dataset-dependent; may need to re-run calibration for very different cohorts.

---

## Option B: Scale so effect_size ≈ (1 - ks_p) at a target (e.g. DMP boundary)

**Idea**: Choose scale so that at a "typical" or "boundary" point (e.g. ks_p = 0.05), the median (or mean) effect_size across positions near that boundary equals a target (e.g. 0.5). So "effect_size > 0.5" roughly corresponds to "ks_p < 0.05" in a percentile sense.

**Steps**:

1. From the KS distribution, get T_05 such that kstwobign.sf(T_05) = 0.05.
2. On your data, among positions with T near T_05, compute the median welch_d. Then solve for scale so that sigmoid(scale * welch_d_median * T_05) = 0.5, i.e. scale * welch_d_median * T_05 = 0, which gives scale = 0 (impossible). So we need an offset: effect_size = sigmoid(scale * (welch_d * T - offset)). Set offset = welch_d_median * T_05 so that at (welch_d_median, T_05) we get 0.5. Then scale can be chosen so that the spread of effect_size matches (1 - ks_p) (e.g. by matching variances or quantiles).

**Implementation**: More invasive (add offset term to the formula). Could be done in [packages/methylutils/methyl_utils/statistical_tests.py](packages/methylutils/methyl_utils/statistical_tests.py) with an optional offset parameter, and calibrate offset (and scale) from data.

**Pros**: Direct interpretation ("effect_size > 0.5 ≈ significant at 0.05").  
**Cons**: Requires offset and per-dataset calibration; formula change.

---

## Option C: Expose scale (and T cap) in Explorer and document calibration

**Idea**: Keep the current implementation but expose **scale** and optionally **T cap** in the Explorer CLI and config so users can tune them. Document that:

- Larger scale → effect_size saturates more (more values near 0 or 1); often **increases** correlation with (1 - ks_p) when welch_d is relatively stable.
- Smaller scale → effect_size more spread; can **decrease** correlation if the sigmoid is in a flat region.
- Users can run Explorer once with `--csv`, then in a small script or notebook compute correlation(effect_size, 1 - ks_p) for different scale values (by re-running with different scale or by recomputing effect_size from welch_d, T in the CSV), and set the scale that maximizes correlation for future runs.

**Implementation**:

- Explorer already has `sigmoid_scale`; ensure it is passed to `welch_d_ks_overlap` (already is). Add CLI flag `--sigmoid-scale` if not present.
- In [packages/methylutils/methyl_utils/statistical_tests.py](packages/methylutils/methyl_utils/statistical_tests.py), optionally expose T_cap (e.g. 15) as a parameter so it can be tuned.
- In [packages/methyldetector/docs/METHYLDETECTOR_EXPLORER.md](packages/methyldetector/docs/METHYLDETECTOR_EXPLORER.md) and Effect_Size_Theory.tex, add a short "Calibrating the scale" subsection: explain that scale (and T cap) affect the spread of effect_size and its correlation with ks_p; suggest maximizing correlation on a representative CSV to choose scale (and optionally T cap).

**Pros**: Minimal code change; users keep full control.  
**Cons**: Manual calibration; no automatic "best" scale.

---

## Option D: Self-calibrating Explorer run (Option A in-run)

**Idea**: After Phase 2, Explorer has welch_d, T (or ks_d, n1, n2), and ks_p for the refined positions. In the same run, do a quick grid search over scale (e.g. 0.5 to 12 in steps of 0.5), compute effect_size for each scale, and choose the scale that maximizes Spearman (or Pearson) correlation between effect_size and (1 - ks_p). Recompute bounded_effect_size (and update the DataFrame) with that scale. Report the chosen scale and the achieved correlation in the JSON.

**Implementation**:

- In [packages/methyldetector/methyl_detector/explorer.py](packages/methyldetector/methyl_detector/explorer.py), after the Phase 2 loop that fills bounded_effect_size, ks_d, ks_p: compute n_eff and T for the refined rows; for each scale in a grid, compute effect_size_candidate = sigmoid(scale * welch_d * T); compute correlation with (1 - ks_p); pick best scale; recompute bounded_effect_size with that scale for the refined rows; store `sigmoid_scale_used` and `effect_size_vs_ks_p_correlation` in the report.
- Optionally make this behavior gated by a flag (e.g. `--calibrate-scale`) so default remains scale=4.

**Pros**: One run gives a scale that best matches ks_p for that sample; report includes correlation.  
**Cons**: Slightly longer run; scale can vary by run/sample.

---

## Recommendation

- **Short term**: Implement **Option C** (expose and document scale and T cap) and add a "Calibrating the scale" note so users can tune scale to improve correlation.
- **Next**: Add **Option D** (self-calibrating scale in Explorer) behind a flag like `--calibrate-scale`, and report the chosen scale and correlation; this gives a concrete "better approximation to the expected p-value for DMP classification" without changing the formula.
- Option B (offset) only if you need a strict "effect_size > 0.5 ⇔ ks_p < 0.05" interpretation; Option A as a standalone script is optional if you prefer not to bake calibration into Explorer.

