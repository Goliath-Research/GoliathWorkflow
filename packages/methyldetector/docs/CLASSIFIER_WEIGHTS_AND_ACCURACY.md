# How effect_size and p-values Flow Into the Classifier (and Why Accuracy Should Increase with DMP Count)

This document traces how **effect_size** (from MethylCentroidPair) and **p-values** are used from DMP detection through classifier training, and why classifier accuracy is expected to either increase or asymptotically approach a maximum as the number of DMPs increases.

---

## 1. Role of p-values vs effect_size

### p-values (and q-values)

- **Purpose:** Decide *which* positions are considered statistically significant. They are **not** used as per-DMP weights in the classifier.
- **Where used:**
  - **Significance filter:** Positions are retained only if `q_value <= alpha` (FDR control). So p/q-values gate entry into the “significant DMP” set.
  - **Optional EAT refinement:** If EAT is enabled, an importance score (from the EAT transformation) is used to *modify* p-values (boost for high-importance, penalty for low-importance) before FDR; the modified p-values are then used only to recompute q-values and thus which positions pass the significance filter. Again, no p-value is passed as a weight into the classifier.

So: **p-values affect which DMPs exist in the pipeline; they do not weight the classifier.**

### effect_size

- **Definition (MethylCentroidPair):**  
  `effect_size = |delta_mean| / (max(overlap, min_floor) * combined_std)`  
  So it is a variance- and overlap-adjusted measure of separation, not raw delta_mean.
- **Where used:**
  1. **Ranking:** DMPs are sorted by `effect_size` descending (`_compute_biological_importance`). All downstream “top-k” or “select DMPs” logic uses this order.
  2. **Context weights (multi-context):** Trimmed mean of `effect_size` per context → `context_weight` per context. Used for aggregating across contexts (e.g. in multi-chromosome classifiers); it is **not** the per-DMP weight inside a single classifier.
  3. **Per-DMP classifier weight:** When building the BetaClassifier (or BetaBinomialClassifier), the **per-DMP weight** is set from `effect_size` (normalized and bounded to `[1e-6, 1]`). So the classifier’s internal weights are effect_size-based.

So: **effect_size drives both the order in which DMPs are added (ranking) and how much each DMP contributes to the classifier (per-DMP weight).**

---

## 2. How the classifier uses these weights

The underlying classifier (e.g. `BetaClassifier` in methylutils) receives a weight per DMP (from effect_size). For each sample it computes:

- Per position: `log P(x_i | class)` under the fitted Beta (or mixture) model for each class.
- Weighted sum (joint log-likelihood under independence):
  - `log P(data | class) = sum_i ( weight_i * log P(x_i | class) )`
- Weights are the normalized effect_size values (`self.weights` in the classifier).

So the **score** for each class is a **weighted sum of log-likelihoods**, where higher effect_size DMPs contribute more. Probabilities are then derived from these scores (e.g. softmax with optional temperature and optional Platt calibration). So:

- **effect_size** → determines both **which** DMPs are used (via ranking) and **how much** each contributes (via per-DMP weight).
- **p-values** → only influence **which** positions pass the significance filter and thus ever get an effect_size and enter the ranked list.

---

## 3. Flow summary (effect_size + p-value → classifier)

```
Centroid comparison
       ↓
  p_value, q_value, effect_size, delta_mean, overlap, ...
       ↓
  Filter: q_value <= alpha  (and optional biological filters)
       ↓
  Optional: EAT modifies p_value → recompute q_value → filter again
       ↓
  effect_size required → _compute_context_weights (trimmed mean per context → context_weight)
       ↓
  Biological filters (e.g. min_effect_size, min_delta_mean, max_overlap)
       ↓
  Sort by effect_size (desc) → sorted_df
       ↓
  DMP selection: top-k from sorted_df (k from binary search / Bayesian / featurecuts or all if optimize_dmps=False)
       ↓
  For selected DMPs: per-DMP weight = effect_size (normalized to [1e-6, 1])
       ↓
  BetaClassifier/BetaBinomialClassifier(positions, alpha1, beta1, alpha2, beta2, weight=effect_size)
       ↓
  Prediction: weighted sum of log P(x_i|class) → class probabilities
```

So **only effect_size (and fallbacks like context_weight if effect_size were missing) is used as the classifier’s per-DMP weight;** p-values do not appear in the classifier formula.

---

## 4. Why accuracy should increase or asymptotically approach a maximum as DMP count increases

- **Ordering:** DMPs are always taken in **descending effect_size**. So the first DMP is the most discriminative, then the next, and so on.
- **Classifier formula:** The class score is a **weighted sum** of log-likelihood terms. Each added DMP adds a term `weight_i * log P(x_i | class)` with `weight_i > 0` (effect_size-based). Under the model, truly differential positions have positive expected contribution to the correct class.
- **Expectation:** Adding more (true) differential DMPs adds more signal. So:
  - As k (number of DMPs) increases, we add more weighted terms.
  - In expectation, more signal → better separation → higher accuracy, or at least no systematic decrease.
  - With finite validation data, accuracy can have small random fluctuations; in the limit, it should **increase or asymptotically approach** the best achievable for that set of positions and that model.

The binary-search optimization in the code explicitly **assumes** that balanced accuracy is non-decreasing in k (see `_optimize_dmps_binary_search`: “Assumes monotonic BA increase with k”). So the pipeline is designed under the assumption that **classifier accuracy should either increase or asymptotically approach the maximum** as the number of DMPs increases, which matches the theoretical picture above when weights and ranking are both effect_size-based and p-values are used only for filtering.

---

## 5. Code references (methyl_detector and classifier)

| Step | Location (methyldetector / methylutils) |
|------|----------------------------------------|
| effect_size required for context weighting | `_compute_context_weights`: requires `effect_size` column; no delta_mean fallback |
| Ranking by effect_size | `_compute_biological_importance`: `sort_values("effect_size", ascending=False)` |
| Per-DMP weight for classifier | `_validate_classifier_subset`, `_save_classifier`: `weights = dmps_for_classifier['effect_size']` then normalized; same for saved model |
| Weighted log-likelihood in classifier | `methyl_utils.beta_classifier`: `weighted_log_p_class0 = self.weights[np.newaxis, :] * log_p_class0`, then sum over positions |
| DMP selection (top-k by effect_size) | `_select_dmps_multicontext` → `_optimize_dmps_binary_search` (or bayesian/featurecuts): `sorted_df.iloc[:k]` |
| p-value only for filtering | Comparison results filtered by `q_value <= alpha`; EAT optionally modifies p_value before FDR |

---

## 6. Summary

- **p-values:** Used only to decide which positions are significant (and optionally modulated by EAT). They do **not** weight the classifier.
- **effect_size:** Used to (1) rank DMPs, (2) compute context weights, and (3) set the **per-DMP weight** in the classifier. The classifier score is a **weighted sum of log-likelihoods** with these weights.
- **Accuracy vs DMP count:** Because DMPs are added in descending effect_size and the classifier uses effect_size as weight, adding more DMPs adds more (positive-weight) signal in expectation, so classifier accuracy should **increase or asymptotically approach the maximum** as the number of DMPs increases; the code’s binary search assumes monotonic (non-decreasing) BA in k.
