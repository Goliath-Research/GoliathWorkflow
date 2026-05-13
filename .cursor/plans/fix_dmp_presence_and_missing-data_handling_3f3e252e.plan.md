---
name: Fix DMP presence and missing-data handling
overview: Ensure MethylDetector truly filters low-support loci by sample representation, and ensure prediction ignores missing stable-DMP positions without imputing biological meaning.
todos:
  - id: detector-cohort-denominator
    content: Harden detector min-sample denominator to use true cohort size and verify thresholds/logging.
    status: pending
  - id: classifier-missing-mask
    content: Stop treating sample NaN as observed 0.5; mask missing matched loci out of scoring.
    status: pending
  - id: abstain-observed-pct
    content: Add configurable minimum observed-DMP percentage gate for abstention in prediction.
    status: pending
  - id: tests-docs
    content: Add/adjust tests and docs for detector filtering and missing-safe inference behavior.
    status: pending
isProject: false
---

# Enforce per-sample support and missing-safe prediction

## Scope
- Keep Monte Carlo stability logic as-is.
- Fix two targeted behaviors:
  - DMP selection in detector must consistently enforce low-sample-frequency filtering.
  - Prediction must ignore missing stable-DMP positions (no assumed methylation value).

## Implementation plan
- **Detector min-sample filter correctness**
  - Audit and harden how cohort size is computed before `effective_min_samples()` in [`packages/methyldetector/methyl_detector/core/methyldetector.py`](packages/methyldetector/methyl_detector/core/methyldetector.py).
  - Replace/augment the current `N.max()`-based denominator with true cohort size when available (from configured validation sample lists or centroid metadata), with safe fallback.
  - Keep `min_samples=(min_s1,min_s2)` filtering in `MethylCentroidPair` and make the chosen thresholds explicit in logs/results for traceability.
  - Confirm config fields in [`packages/methyldetector/methyl_detector/models/config.py`](packages/methyldetector/methyl_detector/models/config.py) remain the source of truth (`min_samples_abs`, `min_samples_pct`).

- **Prediction: ignore missing DMPs without assumptions**
  - Update feature extraction in [`packages/methylclassifier/methyl_classifier/utils/data_loader.py`](packages/methylclassifier/methyl_classifier/utils/data_loader.py) so sample-side NaNs are not converted into “observed 0.5”.
  - Build `availability_mask` as: position matched **and** value finite/usable; unavailable loci remain excluded from scoring.
  - Preserve dense array compatibility for downstream scorers while ensuring masked loci contribute zero weight (existing classifier behavior already supports this when mask is correct).

- **Low-evidence abstention by percentage (not hard-coded count)**
  - Add a configurable minimum observed-DMP proportion gate in classifier inference config/CLI (default conservative value) and abstain when below threshold.
  - Wire this into batch prediction flow in [`packages/methylclassifier/methyl_classifier/cli/main.py`](packages/methylclassifier/methyl_classifier/cli/main.py), reusing computed `availability_mask` coverage.

- **Tests and docs**
  - Add/extend tests in detector/classifier test suites:
    - Detector: loci below min-sample threshold are excluded; denominator behavior uses expected cohort size.
    - Classifier: matched-but-NaN loci are masked out; low observed percentage triggers abstention.
  - Update usage docs for new/clarified behavior in relevant package docs (`methyl-detector` and `methyl-classifier`).

## Validation steps
- Run focused unit tests for modified detector/classifier modules.
- Run one end-to-end small pipeline check in `.venv` verifying:
  - DMP export shrinks when min-sample thresholds increase.
  - Prediction output marks low-coverage samples as abstained and does not bias toward 0.5-imputed behavior.