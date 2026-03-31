---
name: Strict typed config cleanup
overview: "Perform a repo-wide strict-typed cleanup for pipeline config handling: remove `Any` config plumbing and reduce `hasattr`/defensive guards where Pydantic schemas already define fields, while preserving CLI behavior and adding focused tests for early-fail config shape errors."
todos:
  - id: type-signatures
    content: Convert remaining config Any/object signatures to concrete Pydantic types or explicit unions
    status: pending
  - id: remove-defensive-access
    content: Replace getattr/hasattr config access with strict typed attribute access
    status: pending
  - id: strict-validation-branches
    content: Add explicit type checks and clear TypeError/ValueError where dynamic shapes were previously tolerated
    status: pending
  - id: tests-strictness
    content: Add/update tests for strict typed config behavior and early-fail error paths
    status: pending
  - id: run-targeted-checks
    content: Run targeted pytest + lints across touched pipeline packages and fix regressions
    status: pending
isProject: false
---

# Strict Typed Config Simplification Plan

## Goal

Replace dynamic/defensive config access patterns with strict typed Pydantic access across pipeline packages, so invalid config shapes fail early and code paths become simpler and more predictable.

## Scope (as requested)

- Do both:
  - replace remaining `Any`-style config plumbing with concrete model types
  - remove `hasattr` / dynamic guards where typed models already guarantee fields
- Use **strict typed behavior** (no silent fallback for malformed config objects)

## Targeted Modules

- [packages/methylvalidation/methyl_validation/pipeline_runner.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/pipeline_runner.py)
- [packages/methylvalidation/methyl_validation/stability.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py)
- [packages/methylpredictor/methyl_predictor/project_resolver.py](/home/ubuntu/MethylPipeline/packages/methylpredictor/methyl_predictor/project_resolver.py)
- [packages/methylpredictor/methyl_predictor/core/predictor.py](/home/ubuntu/MethylPipeline/packages/methylpredictor/methyl_predictor/core/predictor.py)
- [packages/methylclassifier/methyl_classifier/cli/main.py](/home/ubuntu/MethylPipeline/packages/methylclassifier/methyl_classifier/cli/main.py)
- [packages/methylmapper/methyl_mapper/cli.py](/home/ubuntu/MethylPipeline/packages/methylmapper/methyl_mapper/cli.py)
- [packages/methyldetector/methyl_detector/utils/multiclass_merge.py](/home/ubuntu/MethylPipeline/packages/methyldetector/methyl_detector/utils/multiclass_merge.py)
- [packages/methylenricher/methyl_enricher/cli.py](/home/ubuntu/MethylPipeline/packages/methylenricher/methyl_enricher/cli.py)

## Work Plan

1. **Typed signature sweep**
  - Convert config-bearing function signatures from `Any`/`object` to concrete config models (or `Protocol` where shared behavior is intentional).
  - Add `TYPE_CHECKING` imports to avoid runtime dependency cycles.
2. **Guard simplification pass**
  - Replace `getattr(config, "field", ...)` with direct attribute access for typed models.
  - Replace `hasattr(config, ...)` branches with typed access + explicit validation errors.
  - Keep dynamic fallback only where the function intentionally accepts `dict | Path | str` (with explicit type branches and `TypeError` for unsupported shapes).
3. **Validation hardening**
  - Add explicit early checks when a helper currently tolerates mixed config shapes (e.g. detector merge helpers) and make errors actionable.
  - Ensure CLI/project resolver remains the single source of config normalization before strict execution code paths.
4. **Test and lint coverage**
  - Extend/adjust tests to assert strict failures on malformed config structures.
  - Run targeted suite for all touched packages and verify no new lint diagnostics.

## Expected Behavior Changes

- Mis-typed/malformed config objects now fail earlier with clear exceptions instead of silently bypassing fields.
- No intended behavior changes for valid CLI/project-driven Pydantic configs.

## Verification Matrix

- `methylvalidation` tests for production/model/freeze orchestration
- `methylpredictor` tests for run prediction and project resolver
- `methylclassifier` CLI/model loading smoke tests
- `methylmapper` and `methylenricher` CLI config-apply tests (existing + small strictness cases)
- repo grep checks:
  - `getattr(config,` occurrences eliminated or justified by intentional union-typed inputs
  - `hasattr(config,` occurrences eliminated in strict typed execution paths

