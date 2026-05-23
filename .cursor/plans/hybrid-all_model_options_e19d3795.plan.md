---
name: Hybrid-all Model Options
overview: Evaluate `tabular_sklearn` with `feature_mode=observed_hybrid` by comparing `feature_family_set` choices only (no arbitrary DMP capping), using Monte Carlo iteration-wide empirical metric distributions to select the best family set.
todos:
  - id: audit-eval-splits
    content: Confirm holdout/test evaluation paths are explicit and no in-sample fallback is used during model comparison.
    status: pending
  - id: define-experiment-grid
    content: Define and run a controlled experiment grid over feature families (no tabular_max_dmps sweeps) and tabular methods with fixed seeds.
    status: pending
  - id: monte-carlo-eval-distribution
    content: Evaluate each family_set candidate across all stability Monte Carlo iterations and collect empirical distributions for balanced_accuracy and other core metrics.
    status: pending
  - id: summarize-metrics
    content: Produce comparative summaries using empirical metric distributions (mean, std, quantiles, confidence intervals, overlap) rather than single-point scores.
    status: pending
  - id: biological-coherence-check
    content: For top candidates, run progression/readiness and compare canonical/variant/detailed biological coherence before final selection.
    status: pending
  - id: decision-recommendation
    content: Recommend the best feature_family_set based on predictive distribution quality plus biological coherence evidence.
    status: pending
isProject: false
---

# Hybrid-all tabular_sklearn option analysis

## Current-state findings (from code)
- `tabular_sklearn` does not currently run explicit sklearn feature selectors (no RFE/SelectKBest/etc.); reduction is mainly via:
  - stable DMP bundle
  - `observed_hybrid` aggregation + `feature_family_set`
- `observed_hybrid` uses effect-size-driven weighting in feature aggregation; with `hybrid-all`, feature blocks are DMP + pooled gene summaries + structural region summaries.
- Important config caveat: several legacy `observed_feature_include_*` toggles are accepted but ignored by the current builder. Effective family control is via `feature_family_set`.
- Evaluation quality is highly sensitive to holdout setup; fallback behavior can accidentally evaluate in-sample if explicit holdout/test paths are not configured.

Key reference files:
- [`/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/tabular_backend.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/tabular_backend.py)
- [`/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/observed_feature_builder.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/observed_feature_builder.py)
- [`/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/trainer_api.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/trainer_api.py)
- [`/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/config.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/config.py)

## Option space to analyze (recommended order)
- Keep `hybrid-all` as baseline (your stated preference).
- Run controlled ablation models (for evidence, not immediate exclusion):
  - `dmp`, `gene`, `structural`, `dmp+gene`, `dmp+structural`, `hybrid-all`.
- Remove `tabular_max_dmps` from this comparison scope (no arbitrary DMP truncation).
- Run method sweep in `tabular_methods` (RF/LR/XGB/HGB as available) with the same feature settings and fixed seeds.

## Precision-first evaluation protocol
- Enforce explicit holdout/test groups in predictor/eval config (no train fallback).
- Run each candidate across all stability Monte Carlo iterations to estimate empirical metric distributions.
- Compare models using balanced metrics plus calibration/robustness diagnostics:
  - balanced_accuracy, macro_f1, calibration error/Brier (if available), confidence distribution.
- Use empirical distribution summaries (mean, std, quantiles, CI) for decision-making instead of single-run metrics.
- Keep a single decision table per experiment with:
  - distribution-level performance summaries
  - model complexity proxy (effective feature dimensionality)
  - biological coherence checks from readiness/Grok (canonical + detailed tracks).

## Decision policy (when to drop families)
- Do not remove genes/gene-features yet.
- Mark a family block as removable only if it is consistently inferior across:
  - predictive performance,
  - variability/robustness,
  - biological coherence in readiness outputs.
- If a simpler family set is within tolerance of `hybrid-all`, prefer simpler for deployment.

## Suggested near-term deliverables
- An experiment matrix config set (family-set × method, no DMP-cap axis).
- A comparative report artifact with empirical distributions for Balanced Accuracy and companion metrics across Monte Carlo iterations.
- A final recommendation for best `feature_family_set`, grounded in predictive distributions and biological coherence.