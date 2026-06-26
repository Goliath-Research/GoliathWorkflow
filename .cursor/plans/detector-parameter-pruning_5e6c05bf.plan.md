---
name: detector-parameter-pruning
overview: Prune obsolete MethylDetector parameters with strict removal semantics, aligning schema, runtime, and documentation to the current stability-first ECDF/effect-size workflow. Remove dead keys and legacy aliases that no longer serve detector behavior.
todos:
  - id: prune-schema-fields
    content: Remove unused/dead detector config fields from MethylDetectorConfig and corresponding runtime references.
    status: pending
  - id: drop-legacy-aliases
    content: Replace legacy ECDF alias handling with strict validation errors and keep clear migration messages.
    status: pending
  - id: remove-dead-validation-branches
    content: Eliminate non-schema validation_mode/n_validation_samples runtime branches or reconcile into schema explicitly.
    status: pending
  - id: strict-project-validation
    content: Ensure project_resolver and step overrides fail on removed/stale detector keys.
    status: pending
  - id: update-docs-and-templates
    content: Rewrite detector docs/examples to canonical keys and remove obsolete parameter names.
    status: pending
  - id: add-regression-tests
    content: Add tests for removed-key rejection and successful canonical configuration validation/execution.
    status: pending
isProject: false
---

# Prune Obsolete MethylDetector Parameters (Strict)

## Goal
Remove MethylDetector config and code paths that are no longer useful for the current stability-first workflow (ECDF significance + effect-size ranking + FeatureCuts + DMP frequency stability), and make stale keys fail fast.

## Findings to Act On
- Current schema/runtime mismatch and dead knobs are concentrated in [`/home/ubuntu/MethylPipeline/packages/methyldetector/methyl_detector/models/config.py`](/home/ubuntu/MethylPipeline/packages/methyldetector/methyl_detector/models/config.py) and [`/home/ubuntu/MethylPipeline/packages/methyldetector/methyl_detector/core/methyldetector.py`](/home/ubuntu/MethylPipeline/packages/methyldetector/methyl_detector/core/methyldetector.py).
- Stale detector keys appear in docs/templates and one project sample config (notably `max_dmps_for_classifier`, legacy ECDF key aliases, and old filter names).

## Scope
- Detector schema and runtime only (MethylDetector + immediate resolver/docs/templates).
- Strict removal mode: obsolete keys should error with migration guidance.

## Implementation Plan

### 1) Remove truly unused detector config fields from schema/runtime
- Edit [`/home/ubuntu/MethylPipeline/packages/methyldetector/methyl_detector/models/config.py`](/home/ubuntu/MethylPipeline/packages/methyldetector/methyl_detector/models/config.py):
  - Remove fields not used by detector logic (e.g., `use_gpu`, `min_sample_coverage`, `classifier_coverage_weighting`, `min_validation_coverage_per_position`, `synthetic_config`, and `classifier_type` if it is metadata-only).
  - Treat `use_gpu` as explicitly redundant: detector should always attempt GPU-capable flow and fall back automatically when GPU is unavailable, without a detector config toggle.
  - Remove `eps` if no computation consumes it.
- Edit [`/home/ubuntu/MethylPipeline/packages/methyldetector/methyl_detector/core/methyldetector.py`](/home/ubuntu/MethylPipeline/packages/methyldetector/methyl_detector/core/methyldetector.py):
  - Remove reads/exports tied only to deleted fields.
  - Ensure result metadata and logs no longer reference removed keys.

### 2) Remove legacy aliases and invalid compatibility branches
- In [`models/config.py`](/home/ubuntu/MethylPipeline/packages/methyldetector/methyl_detector/models/config.py):
  - Delete alias remapping for `ecdf_overlap_grid_size` / `ecdf_ks_grid_size` and convert to explicit validation errors that require `ecdf_grid_size`.
  - Keep hard errors for previously rejected keys (`statistical_test`, `distribution`, `delta_mean_mode`, `overlap_mode`, `max_N_for_ecdf`) with crisp migration messages.

### 3) Eliminate dead/ambiguous validation-mode paths
- In [`core/methyldetector.py`](/home/ubuntu/MethylPipeline/packages/methyldetector/methyl_detector/core/methyldetector.py):
  - Remove runtime reads of non-schema keys (`n_validation_samples`, `validation_mode`) so runtime cannot diverge from `MethylDetectorConfig`.
  - Keep one explicit real-validation path used by the current stability workflow and delete synthetic-only branches that are unsupported by schema.

### 4) Tighten project/config ingestion to fail on stale keys
- In [`/home/ubuntu/MethylPipeline/packages/methyldetector/methyl_detector/utils/project_resolver.py`](/home/ubuntu/MethylPipeline/packages/methyldetector/methyl_detector/utils/project_resolver.py):
  - Ensure detector step overrides and merged config payloads are validated strictly against the pruned schema.
  - Add targeted error text for stale keys that previously appeared in templates (`max_dmps_for_classifier`, legacy ECDF aliases).

### 5) Update docs/templates to canonical detector keys only
- Update stale docs/examples:
  - [`/home/ubuntu/MethylPipeline/packages/methyldetector/QUICKSTART.md`](/home/ubuntu/MethylPipeline/packages/methyldetector/QUICKSTART.md)
  - [`/home/ubuntu/MethylPipeline/packages/methyldetector/CONTEXT_SELECTION_GUIDE.md`](/home/ubuntu/MethylPipeline/packages/methyldetector/CONTEXT_SELECTION_GUIDE.md)
  - [`/home/ubuntu/MethylPipeline/packages/methylclassifier/docs/USAGE.md`](/home/ubuntu/MethylPipeline/packages/methylclassifier/docs/USAGE.md)
  - [`/home/ubuntu/MethylPipeline/docs/reference/configuration-reference.qmd`](/home/ubuntu/MethylPipeline/docs/reference/configuration-reference.qmd)
- Replace obsolete names (`min_delta_mean`, `max_bc`, `biological_filters`, `max_dmps_for_classifier`, legacy ECDF alias keys) with current detector parameters.

### 6) Clean sample project config and add regression tests
- Update stale sample config:
  - [`/home/ubuntu/MethylPipeline/.phase_a_cg_chr1/phase_a_project_CG_chr1.json`](/home/ubuntu/MethylPipeline/.phase_a_cg_chr1/phase_a_project_CG_chr1.json)
- Add tests under detector package to verify:
  - Removed keys are rejected with actionable errors.
  - Canonical keys (`ecdf_grid_size`, effect-size + FeatureCuts params) still validate and execute.
  - Stability-path-critical keys remain functional.

## Validation
- Run detector-focused test set (unit + resolver/config validation tests).
- Run one minimal end-to-end stability iteration (centroid + detector) using canonical config keys.
- Confirm no residual references to removed keys across code/docs/config templates.

## Expected Outcome
- Detector config surface reflects only parameters that actually influence current detector behavior.
- Legacy/stale keys fail fast instead of silently no-oping.
- Stability workflow documentation and templates match implemented code.