---
name: validation-config-dedup
overview: Make project configuration globally deduplicated by deriving panel/progression/split metadata from comparisons and cohort structure, then update resolvers so Monte Carlo runs no longer require repeated train/holdout and panel definitions.
todos:
  - id: derive-canonical-metadata
    content: Add comparison-ordered and panel-by-parent derivation helpers to ProjectConfig.
    status: pending
  - id: panel-defaulting
    content: Wire classifier/predictor resolvers to use derived panel defaults with explicit-overrides precedence.
    status: pending
  - id: mc-split-synthesis
    content: Make MC project generation and predictor resolution synthesize train/holdout group paths when omitted.
    status: pending
  - id: progression-default-order
    content: Default progression ordering from comparisons when explicit ordered labels are missing.
    status: pending
  - id: docs-dedup-guidance
    content: Update MethylValidation/theory docs to describe minimal non-duplicated config style and precedence.
    status: pending
  - id: regression-tests
    content: Add/adjust resolver + MC + progression tests for deduplicated configs and legacy compatibility.
    status: pending
isProject: false
---

# Global Config De-dup for MethylValidation

## Objectives
- Remove repeated authoring of `classifier.panel`, `predictor.panel`, and progression stage lists when these can be derived from `comparisons` + cohort hierarchy.
- Make `train_group_paths` / `holdout_group_paths` optional in Monte Carlo-oriented project configs by synthesizing them automatically.
- Preserve backward compatibility for existing project JSONs while making canonical behavior explicit.

## Canonical Rules (agreed)
- `comparisons` is the source of truth for stage/comparison identities and order.
- Panel families are derived by **grouping comparisons by disease parent**.
- Explicit per-step duplicates remain supported as override inputs for compatibility, but are no longer required.

## Implementation Plan

### 1) Add canonical derivation helpers in project config layer
- Extend [`/home/ubuntu/MethylPipeline/packages/methylutils/methyl_utils/pipeline_config.py`](/home/ubuntu/MethylPipeline/packages/methylutils/methyl_utils/pipeline_config.py) with read-only derivation helpers:
  - derive ordered comparison labels from `get_comparisons()`.
  - derive panel spec from comparisons grouped by disease parent.
  - expose resolved class ordering metadata that downstream resolvers can consume.
- Keep existing parsing behavior unchanged for legacy fields; add helpers rather than breaking schema first.

### 2) Make predictor/classifier panel defaults derived (no duplication required)
- Update [`/home/ubuntu/MethylPipeline/packages/methylclassifier/methyl_classifier/project_resolver.py`](/home/ubuntu/MethylPipeline/packages/methylclassifier/methyl_classifier/project_resolver.py):
  - if `step_config.classifier.panel` missing, synthesize from project derivation helper.
- Update [`/home/ubuntu/MethylPipeline/packages/methylpredictor/methyl_predictor/project_resolver.py`](/home/ubuntu/MethylPipeline/packages/methylpredictor/methyl_predictor/project_resolver.py):
  - resolution precedence: explicit predictor panel -> explicit classifier panel -> derived-from-comparisons panel.
- Ensure both paths produce identical family ordering for the same project.

### 3) Remove need to manually author train/holdout group path blocks
- Update Monte Carlo project generation in [`/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/project_gen.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/project_gen.py):
  - synthesize predictor split blocks from generated train/test CSV maps + resolved group ordering.
  - avoid requiring template `train_group_paths` / `holdout_group_paths` labels in input config.
- Update predictor resolver fallback behavior in [`/home/ubuntu/MethylPipeline/packages/methylpredictor/methyl_predictor/project_resolver.py`](/home/ubuntu/MethylPipeline/packages/methylpredictor/methyl_predictor/project_resolver.py):
  - when split blocks are absent, derive from project cohorts/test groups and MC-produced split artifacts.
  - keep strict error only when neither explicit nor derivable sources exist.

### 4) Progression order defaults from comparisons
- Update progression wiring in:
  - [`/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/pipeline_runner.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/pipeline_runner.py)
  - [`/home/ubuntu/MethylPipeline/packages/methyldiseaseprogression/methyl_disease_progression/progression.py`](/home/ubuntu/MethylPipeline/packages/methyldiseaseprogression/methyl_disease_progression/progression.py)
- Behavior:
  - if `ordered_comparison_labels` absent, use derived comparison order from project config.
  - keep explicit progression order as override.

### 5) Documentation and example updates
- Update canonical docs and examples to show minimal, non-duplicated config authoring:
  - [`/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/USAGE.md`](/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/USAGE.md)
  - [`/home/ubuntu/MethylPipeline/docs/theory/chapters/11-project-configuration.qmd`](/home/ubuntu/MethylPipeline/docs/theory/chapters/11-project-configuration.qmd)
  - [`/home/ubuntu/MethylPipeline/docs/theory/chapters/14-user-guide.qmd`](/home/ubuntu/MethylPipeline/docs/theory/chapters/14-user-guide.qmd)
- Add a “legacy compatibility” note documenting precedence rules and de-dup defaults.

### 6) Tests and validation
- Add/adjust tests in:
  - predictor resolver tests for derived panel and derived splits.
  - methylvalidation MC tests for configs without explicit `train_group_paths` / `holdout_group_paths`.
  - progression tests for default ordering from comparisons.
- Run focused suites:
  - methylpredictor resolver tests
  - methylvalidation MC/config tests
  - methyldiseaseprogression ordering tests
- Validate using the prostate project by removing duplicated panel/split definitions and confirming run-project generation + evaluation still works.

## Compatibility Strategy
- Keep legacy duplicated fields accepted.
- Precedence (deterministic):
  1. explicit step field
  2. inherited equivalent (where applicable)
  3. derived canonical default from `comparisons`/cohorts
- Emit clear warnings when explicit fields duplicate derived defaults (optional soft guidance, no hard failure).