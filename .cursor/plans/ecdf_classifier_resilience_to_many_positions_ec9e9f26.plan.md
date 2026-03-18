---
name: ECDF classifier resilience to many positions
overview: Make the ECDF classifier's log-likelihood aggregation more resilient when using 40K–50K positions, so that many weak/small-difference positions do not dilute or distort the class probabilities. Options include weight concentration, robust aggregation, and an optional cap on the number of DMPs used in the classifier.
todos: []
isProject: false
---

# ECDF classifier resilience to many positions

## Problem

The ECDF classifier uses a **weighted mean** of per-position log PDFs: `sum(w_i * log p_i) / sum(w_i)` with weights from effect_size (normalised to [1e-6, 1]). There is already a per-position log-PDF cap (`_LOG_PDF_CAP = -20`) and weighted mean (not sum) in [packages/methylutils/methyl_utils/ecdf_classifier.py](packages/methylutils/methyl_utils/ecdf_classifier.py). With **40K–50K positions**:

- Many positions have small effect_size and get weight 1e-6 after normalisation.
- Large numbers of positions at or near the log-PDF cap can pull the weighted mean toward similar values for both classes, so **differences** between class log-likelihoods shrink and **probabilities** become less discriminative (closer to 0.5) or distorted.

So the aggregation is not sufficiently resilient to the **number** of positions when a large fraction are weak.

**Note:** MethylDetector already uses **trimmed mean** for **context weights** (trimmed mean of effect_size per context; see `_compute_context_weights`, `trimmed_percentile_low` / `trimmed_percentile_high` in [packages/methyldetector/methyl_detector/core/methyldetector.py](packages/methyldetector/methyl_detector/core/methyldetector.py) and [packages/methyldetector/methyl_detector/models/config.py](packages/methyldetector/methyl_detector/models/config.py)). The ECDF classifier in **MethylUtils** does not use trimmed mean for the per-position log-likelihood aggregation; it uses a plain weighted mean. The resilience improvements below target the classifier aggregation and DMP set size.

---

## Directions (implement 1, 3, 4; option 2 optional)

### 1. Weight concentration (recommended as first lever)

Make weights more concentrated on high–effect_size positions so that the effective number of contributors does not grow with total DMP count.

- **Where:** [packages/methylutils/methyl_utils/ecdf_classifier.py](packages/methylutils/methyl_utils/ecdf_classifier.py) and/or the place that builds the classifier and passes `weights` (e.g. MethylDetector’s `_get_classifier_weights` in [packages/methyldetector/methyl_detector/core/methyldetector.py](packages/methyldetector/methyl_detector/core/methyldetector.py)).
- **How:** After normalising effect_size to [1e-6, 1], apply a power: `weight_i = normalized_i^alpha` with **alpha > 1** (e.g. 2). Then low weights become even smaller; the weighted mean is dominated by fewer, stronger positions. Expose `weight_power` or `effect_size_weight_power` (default 1.0 for backward compatibility) in config so it can be tuned (e.g. 2.0 for large DMP sets).

### 2. Robust aggregation (optional; more of a hack)

Reduce the influence of the long tail of weak positions; possible fallback if options 1, 3, 4 are insufficient. Considered more of a hack than a structural fix.

- **Where:** [packages/methylutils/methyl_utils/ecdf_classifier.py](packages/methylutils/methyl_utils/ecdf_classifier.py) inside `predict_proba`.
- **Options:** Weight-mass threshold (e.g. 95% of sum(w_i)) or trimmed mean of per-position contributions; default `weighted_mean` to preserve current behaviour.

### 3. Cap number of DMPs in the classifier

Avoid ever building a classifier with 40K–50K positions by capping how many DMPs are passed to the ECDF classifier.

- **Where:** MethylDetector: when building the classifier (e.g. in `_build_ecdf_classifier`, or in the path that selects `selected_dmps_df` / `sorted_df` before top-k optimization). If `len(dmps_df) > max_dmps_for_classifier`, take the **top `max_dmps_for_classifier` by effect_size** and build the classifier from that subset only.
- **Config:** Add an optional `max_dmps_for_classifier: Optional[int] = None` (e.g. 10_000 or 15_000). If `None`, no cap (current behaviour). This is independent of `optimize_dmps`: it applies to the DMP set that is passed to the classifier after biological filter and before or after top-k (clarify in doc: e.g. “cap applied to the biological DMP set before top-k search” so optimization still sees the full set, but the final classifier uses at most this many).

This directly prevents “too many weak positions” by not including them in the model.

### 4. Temperature scaling with effective number of positions

If the spread of the weighted log-likelihood (across samples) shrinks when many positions are included, softmax with a fixed temperature can yield probabilities that are too or too little extreme. Scaling temperature with an “effective” number of positions could compensate.

- **Where:** [packages/methylutils/methyl_utils/ecdf_classifier.py](packages/methylutils/methyl_utils/ecdf_classifier.py) (temperature used in softmax).
- **Idea:** e.g. `T_eff = T * sqrt(n_effective)` or `T * log(1 + n_effective)` where `n_effective = (sum w_i)^2 / sum(w_i^2)` (inverse Simpson concentration). So as the effective number of contributors grows, temperature increases and probabilities become less extreme. This is more experimental; recommend as an optional follow-on after 1–3.

---

## Recommended order of implementation

1. **Weight concentration** (effect_size^alpha, alpha configurable, default 1): small code change, backward compatible, directly reduces the impact of many weak positions.
2. **Optional `max_dmps_for_classifier` cap** in MethylDetector: simple and interpretable; users with 50K biological DMPs can cap at e.g. 10K without changing the rest of the pipeline.
3. **Temperature scaling** with effective number of positions in ECDFClassifier (e.g. T_eff = T * f(n_effective)) so softmax remains well-behaved with many positions.
4. **Option 2 (robust aggregation)** only if needed: weight-mass threshold or trimmed mean in the classifier as an optional mode (more of a hack).

---

## Files to touch (minimal)

- [packages/methylutils/methyl_utils/ecdf_classifier.py](packages/methylutils/methyl_utils/ecdf_classifier.py): optional weight power applied to weights at prediction time (or accept pre-raised weights); temperature scaling with effective n (n_effective from weights) in softmax.
- [packages/methyldetector/methyl_detector/core/methyldetector.py](packages/methyldetector/methyl_detector/core/methyldetector.py): apply weight power in `_get_classifier_weights` when building the classifier; apply `max_dmps_for_classifier` (take top-k by effect_size before building classifier).
- [packages/methyldetector/methyl_detector/models/config.py](packages/methyldetector/methyl_detector/models/config.py): add `effect_size_weight_power: float = 1.0` and `max_dmps_for_classifier: Optional[int] = None`. Optionally add `classifier_aggregation` only if implementing option 2.

---

## Summary

The failure at 40K–50K positions is likely due to many weak positions diluting the weighted-mean log-likelihood and shrinking the difference between classes. MethylDetector already uses trimmed mean for **context weights**; the ECDF classifier in MethylUtils does not. **Implement options 1, 3, and 4:** (1) weight concentration (effect_size^alpha), (2) cap on DMPs in the classifier (max_dmps_for_classifier), (3) temperature scaling with effective n. Option 2 (robust aggregation in the classifier) is optional and considered more of a hack; add only if needed.