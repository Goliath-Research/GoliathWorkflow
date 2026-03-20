---
name: Predictor blind vs labeled
overview: Add an optional **blind** cohort in `step_config.predictor` (same `groups`/`sample_paths` shape as controls/diseases) for samples with no ground-truth class. Labeled runs keep full validation metrics; blind runs omit them and emit a structured **blind** section in `prediction_report.json` with per-class probabilities and aggregate prediction statistics. Mutually exclusive with labeled control/disease paths in a single run (or document precedence if you prefer blind-only configs).
todos:
  - id: blind-config-resolver
    content: Add predictor.blind to PredictorConfig + project_resolver (paths, lineage, comparison policy)
    status: pending
  - id: blind-core-report
    content: _build_samples_and_expected + _build_prediction_report + blind_summary + mode field
    status: pending
  - id: blind-docs-tests
    content: Docs + pytest for blind-only and labeled unchanged
    status: pending
isProject: false
---

# MethylPredictor: labeled evaluation vs blind probability reporting

## Current behavior

- [`_build_samples_and_expected`](packages/methylpredictor/methyl_predictor/core/predictor.py) always assigns **0/1** for binary when `test_control_paths` + `test_disease_paths` are populated (from nested `controls`/`diseases`).
- [`classify_samples_from_list`](packages/methylclassifier/methyl_classifier/cli/main.py) already supports **`expected_classes=None`**: CSV has no `expected_class`, no validation report.
- [`run_prediction`](packages/methylpredictor/methyl_predictor/core/predictor.py) only writes **`validation_metrics.json`** when `expected_class` exists; blind path prints “metrics skipped” and still writes **`prediction_report.json`** via [`_build_prediction_report`](packages/methylclassifier/methyl_classifier/cli/main.py) but does not tag mode or add blind summaries.

## Target behavior

| Mode | How configured | Metrics | `prediction_report.json` |
|------|----------------|---------|---------------------------|
| **Labeled** | `predictor.controls` + `predictor.diseases` (or multiclass `test_group_paths`) | Existing sklearn metrics + `validation_metrics.json` | `mode: "labeled"`, nested `controls`/`diseases` + `samples` including `expected_class` where known |
| **Blind** | `predictor.blind` only (see below) | **No** accuracy/BA/confusion; optional **descriptive** stats only | `mode: "blind"`, full **`probabilities`** per class name per sample, **`predicted_subgroup`** (= `predicted_class`), aggregates: counts by predicted class, mean prob per class, optional entropy |

**Blind config shape** (mirror controls/diseases):

```json
"predictor": {
  "blind": {
    "groups": [
      { "label": "incoming_batch_a", "sample_paths": ["configs/new_samples.csv"] }
    ]
  }
}
```

- `groups[].label` is **metadata** (batch/cohort name), **not** a truth class.
- Single run = **either** labeled (`controls`+`diseases` or multiclass groups) **or** blind (`blind` with non-empty groups), **not both**; raise a clear `ValueError` if both are populated.

**Optional future extension** (out of scope unless you want it now): `blind` + empty `controls`/`diseases` only; or CLI `--blind-csv` for standalone.

## Implementation steps

1. **`PredictorConfig`** ([`models/config.py`](packages/methylpredictor/methyl_predictor/models/config.py)): add optional `blind: Optional[Dict[str, Any]]` (`groups` only, or optional top-level `label`). Resolver fills `test_blind_paths`, `report_blind`, `sample_lineage` with `side: "blind"` and `group_label` = group label.

2. **`project_resolver.py`**:  
   - If `step_cfg.get("blind")` has non-empty `groups`, build paths like `_expand_side_group_paths`, return `PredictorConfig` with **empty** `test_control_paths` / `test_disease_paths`, **non-empty** blind paths, `expected_classes` path handled in core.  
   - Per-comparison projects: typically **no** `blind` in the same step as comparison-specific labeled paths; if `blind` is set at predictor level, define behavior: **either** skip per-comparison loop and one blind output dir (e.g. `predictors/blind/`) **or** disallow `blind` when `uses_control_disease` and comparisons exist (simplest: allow blind only for non-comparison or a single global blind run — document).

   **Recommendation:** For `resolve_predictor_config_per_comparison`, if `blind` is present, return **one** `(config, "blind")` entry (or reuse `validator_dir` subfolder `blind`) and **do not** duplicate blind runs per comparison. If that’s too magical, **require** blind-only projects to use flat `resolve_predictor_config` (no comparisons) — simplest to implement first.

3. **`_build_samples_and_expected`**:  
   - If `config` has blind paths only: `samples_list = blind_paths`, `expected_classes=None`.  
   - Validate mutual exclusion with labeled paths.

4. **`_build_prediction_report`**:  
   - Branch on `config` / `expected_classes` / explicit `prediction_mode` field:  
     - **Labeled**: set `"mode": "labeled"`, keep current nested structure; optionally add top-level pointer to `validation_metrics`.  
     - **Blind**: `"mode": "blind"`, `"blind": { "groups": [...] }` with `samples` each containing `"probabilities": { class_name: p, ... }`, `"predicted_subgroup"`, `"max_probability"`; add `"blind_summary": { "n_samples", "predicted_counts_by_class", "mean_probability_by_class" }`.

5. **Console**: blind run prints short summary (n samples, histogram of predicted classes) instead of BA.

6. **Docs** ([`USAGE.md`](packages/methylpredictor/docs/USAGE.md), [`IMPLEMENTATION.md`](packages/methylpredictor/docs/IMPLEMENTATION.md)): document labeled vs blind, JSON examples, interaction with per-comparison projects.

7. **Tests** ([`test_run_prediction.py`](packages/methylpredictor/tests/test_run_prediction.py)): blind-only config, `expected_classes=None`, assert no `validation_metrics.json`, assert `prediction_report["mode"]=="blind"` and probability dict present.

## Files to touch

- [`methyl_predictor/models/config.py`](packages/methylpredictor/methyl_predictor/models/config.py)
- [`methyl_predictor/project_resolver.py`](packages/methylpredictor/methyl_predictor/project_resolver.py) (and narrow rule for comparisons + blind)
- [`methyl_predictor/core/predictor.py`](packages/methylpredictor/methyl_predictor/core/predictor.py)
- [`methyl_predictor/docs/USAGE.md`](packages/methylpredictor/docs/USAGE.md), [`IMPLEMENTATION.md`](packages/methylpredictor/docs/IMPLEMENTATION.md)
- [`methylpredictor/tests/test_run_prediction.py`](packages/methylpredictor/tests/test_run_prediction.py)

## Dependency

No MethylClassifier changes required; CSV already includes `prob_class*` and `predicted_class` when saving without `expected_class`.
