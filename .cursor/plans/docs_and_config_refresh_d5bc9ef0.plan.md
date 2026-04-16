---
name: docs and config refresh
overview: Update documentation for recent MethylEnricher, MethylAlignmentQC, and MethylValidation behavior and tune the prostate-cancer project config to use current pipeline capabilities while honoring your strict-stability and fixed-runtime preferences.
todos:
  - id: audit-enricher-docs
    content: Align MethylEnricher docs with current CLI, presets, network refinement, and per-group project behavior.
    status: completed
  - id: audit-alignmentqc-docs
    content: Align MethylAlignmentQC docs with current CLI modes, guardrail migration, and schema export workflow.
    status: completed
  - id: audit-validation-docs
    content: Align MethylValidation docs with current MonteCarloConfig fields, stability/freeze/model options, and rollout flags.
    status: completed
  - id: update-prostate-config
    content: Apply strict-profile config updates in project_Healthy_vs_PCa1-4-CG.json while keeping n_iterations at 30.
    status: completed
  - id: validate-and-summarize
    content: Validate JSON and produce a stage-by-stage summary of resulting improvements and rationale.
    status: in_progress
isProject: false
---

# Documentation and Config Alignment Plan

## Scope
Align docs and one project config with the current behavior of:
- `MethylEnricher`
- `MethylAlignmentQC`
- `MethylValidation`

And update config at:
- [`/home/ubuntu/Work/prostate-cancer/configs/project_Healthy_vs_PCa1-4-CG.json`](/home/ubuntu/Work/prostate-cancer/configs/project_Healthy_vs_PCa1-4-CG.json)

## Assumptions Locked From Your Choices
- Use a **strict stability profile**.
- Keep Monte Carlo iterations at **30**.

## Planned Changes
- Update MethylEnricher docs to match current CLI/features (project-per-group resolution, network refinement, library presets, network-discovery wiring, plot modes).
  - Targets:
    - [`/home/ubuntu/MethylPipeline/packages/methylenricher/docs/USAGE.md`](/home/ubuntu/MethylPipeline/packages/methylenricher/docs/USAGE.md)
    - [`/home/ubuntu/MethylPipeline/packages/methylenricher/docs/IMPLEMENTATION.md`](/home/ubuntu/MethylPipeline/packages/methylenricher/docs/IMPLEMENTATION.md)
    - [`/home/ubuntu/MethylPipeline/docs/theory/chapters/08-methylenricher.qmd`](/home/ubuntu/MethylPipeline/docs/theory/chapters/08-methylenricher.qmd)

- Update MethylAlignmentQC docs to reflect current CLI modes and guardrail/schema workflow.
  - Targets:
    - [`/home/ubuntu/MethylPipeline/packages/methylalignmentqc/docs/USAGE.md`](/home/ubuntu/MethylPipeline/packages/methylalignmentqc/docs/USAGE.md)
    - [`/home/ubuntu/MethylPipeline/packages/methylalignmentqc/docs/IMPLEMENTATION.md`](/home/ubuntu/MethylPipeline/packages/methylalignmentqc/docs/IMPLEMENTATION.md)

- Update MethylValidation docs to align with current config fields and operational flags (stability/freeze/model/predictor interactions, observed-hybrid + ECDF second stage, rollout controls).
  - Targets:
    - [`/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/USAGE.md`](/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/USAGE.md)
    - [`/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/IMPLEMENTATION.md`](/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/IMPLEMENTATION.md)
    - [`/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/ROLLOUT.md`](/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/ROLLOUT.md)

- Update project config to explicitly leverage relevant improvements without increasing runtime.
  - File:
    - [`/home/ubuntu/Work/prostate-cancer/configs/project_Healthy_vs_PCa1-4-CG.json`](/home/ubuntu/Work/prostate-cancer/configs/project_Healthy_vs_PCa1-4-CG.json)
  - Proposed key updates under `step_config.validation`:
    - Keep `n_iterations: 30`.
    - Keep strict filtering posture (`stability_min_balanced_accuracy: 0.9`).
    - Explicitly set `stability_gene_freq` (for reproducibility and clarity).
    - Enable `stability_featurecuts_enabled: true` and align with existing detector policy by setting:
      - `stability_target_balanced_accuracy: 0.95`
      - `stability_min_selected_dmps: 1000`
    - Preserve current advanced model settings already using latest path (`model_backend: ecdf`, `feature_mode: observed_hybrid`, `ecdf_second_stage_enabled: true`).

## Validation / QA
- Cross-check each doc section against current CLI/config implementation in:
  - [`/home/ubuntu/MethylPipeline/packages/methylenricher/methyl_enricher/cli.py`](/home/ubuntu/MethylPipeline/packages/methylenricher/methyl_enricher/cli.py)
  - [`/home/ubuntu/MethylPipeline/packages/methylalignmentqc/methyl_alignment_qc/cli/main.py`](/home/ubuntu/MethylPipeline/packages/methylalignmentqc/methyl_alignment_qc/cli/main.py)
  - [`/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/cli.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/cli.py)
  - [`/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/config.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/config.py)
- Run a JSON validity check on the updated project config.
- Provide a concise change summary with a “what changed and why” mapping for each stage: stability, freeze, model, prediction.