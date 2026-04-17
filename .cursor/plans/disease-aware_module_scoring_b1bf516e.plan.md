---
name: disease-aware module scoring
overview: Make module disease scoring derive from mapper disease evidence when available, and hide disease columns when no valid disease prior exists to avoid misleading outputs.
todos:
  - id: derive-disease-prior
    content: Implement disease prior extraction from mapper CSV and CLI disease filters in module pipeline.
    status: pending
  - id: conditional-disease-columns
    content: Emit disease columns only when a non-empty disease prior is active.
    status: pending
  - id: score-plumbing
    content: Adjust module scorer return payload to communicate whether disease scoring is valid.
    status: pending
  - id: tests
    content: Add tests for with-prior, no-prior, and empty-prior scenarios.
    status: pending
  - id: docs
    content: Update methylenricher usage docs to describe conditional disease columns and scoring behavior.
    status: pending
isProject: false
---

# Disease-Aware Module Scoring Plan

## Goal
Align `modules_ranked` disease columns with actual mapper disease evidence, and omit those columns when no disease prior can be built.

## Current Gap
- Module scoring computes `disease_relevance` from `disease_genes`, but CLI module runs do not construct/pass a disease prior from mapper inputs.
- Output always includes disease columns, even when the score is neutral/default and potentially misleading.

## Proposed Changes
- Add a mapper-driven disease-prior builder in [packages/methylenricher/methyl_enricher/module_pipeline.py](/home/ubuntu/MethylPipeline/packages/methylenricher/methyl_enricher/module_pipeline.py):
  - Read disease evidence columns from input CSV when present (`disease_associated`, `disease_score`, `disease_evidence_level`, optional association type/publications).
  - Build `disease_genes` using existing CLI thresholds (`--disease-only`, `--min-disease-score`, `--min-disease-evidence-level`, etc.).
  - Pass this derived set into `score_and_rank_modules(...)`.
- Update [packages/methylenricher/methyl_enricher/module_scorer.py](/home/ubuntu/MethylPipeline/packages/methylenricher/methyl_enricher/module_scorer.py):
  - Keep disease scoring only when a non-empty disease prior exists.
  - Return an explicit marker (e.g., `has_disease_prior`) so downstream export can conditionally include disease columns.
- Update module export in [packages/methylenricher/methyl_enricher/module_pipeline.py](/home/ubuntu/MethylPipeline/packages/methylenricher/methyl_enricher/module_pipeline.py):
  - Include `Disease_relevance_score` / `Disease_relevance_tier` only when `has_disease_prior=True`.
  - Omit disease columns when no disease prior exists (healthy-vs-healthy or non-disease workflows).
- Keep final output semantics explicit:
  - `modules_ranked.csv` remains the primary table.
  - If useful, log whether disease prior was active and how many genes were in the prior.

## Validation
- Add/extend tests in [packages/methylenricher/tests](/home/ubuntu/MethylPipeline/packages/methylenricher/tests):
  - Case A: mapper CSV with disease columns + thresholds -> disease columns present and non-neutral.
  - Case B: mapper CSV without disease columns -> disease columns absent.
  - Case C: disease columns exist but filters yield zero prior genes -> disease columns absent.
- Regression check existing module ranking output shape for non-disease runs.

## Rollout Notes
- Document behavior in [packages/methylenricher/docs/USAGE.md](/home/ubuntu/MethylPipeline/packages/methylenricher/docs/USAGE.md):
  - Disease columns are conditional on inferred/provided disease prior.
  - Clarify difference between gene filtering and module disease scoring.