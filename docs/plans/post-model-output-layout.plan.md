---
name: Post Model Output Layout
overview: Move the one-shot DomainProgram post-model evaluation out of the misleading `run_0001/` directory and write its reports directly under `monte_carlo_runs/post_model_validation/`, while preserving the legacy iterative CLI layout.

> **Status: IMPLEMENTED.** One-shot workflow output is rooted directly at `post_model_validation/`; legacy CLI `run_000N/` artifacts remain supported and are not moved.

azure_devops:
  type: Feature
  title: "Post-model validation output layout"
  work_item_id: null
  epic_id: 413
todos:
  - id: fix-output-root
    content: Change the one-shot handler default to post_model_validation/ and align the typed outputDir contract.
    status: completed
    work_item_id: null
  - id: update-contracts-tests
    content: Regenerate schemas/compiled fixtures and add tests for default and overridden output locations.
    status: completed
    work_item_id: null
  - id: document-layout
    content: Document one-shot versus legacy iterative layouts and preserve historical run_0001 artifacts.
    status: completed
    work_item_id: null
---

# Post-Model Validation Output Layout

## Implementation
- Update [`workers/methyl_worker/handlers/validation.py`](../../workers/methyl_worker/handlers/validation.py) so `_handle_validation_post_model_validation` defaults to `<mc_root>/post_model_validation/` and places `predictors/`, `logs/`, `step_timings.csv`, and `post_model_validation_report.json` directly there.
- Make path precedence `outputDir` → deprecated `runDir` → root default. Keep compatibility fields typed while making `outputDir` canonical in the action catalog.
- Keep the legacy `methyl-validation --post-model-validation` iterative workflow unchanged: it continues to use `post_model_validation/run_000N/` plus aggregate metrics at the root.

## Contracts and verification
- Regenerate task schemas, the action catalog, and compiled workflow fixtures with `outputDir` bindings.
- Test the root default, explicit `outputDir`, deprecated `runDir`, and binary/multiclass paths.
- Return the actual selected directory through `ValidationPostModelValidationOutput.outputDir`.

## Documentation and compatibility
- Distinguish one-shot DomainProgram output from legacy iterative output in operator documentation.
- Do not delete, move, or symlink historical `run_0001` results.
