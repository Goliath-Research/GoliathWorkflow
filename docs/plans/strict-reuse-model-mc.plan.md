---
name: Strict Reuse Model MC
overview: Add a canonical slim DomainProgram that runs only ECDF model-MC from existing primary MC artifacts, with a strict reuse contract that fails rather than recomputing centroids or detections.

> **Status: IMPLEMENTED.** The slim program, strict runtime contract, generated schemas, tests, and operator documentation are complete.

azure_devops:
  type: Feature
  title: "Strict Reuse Model MC"
  work_item_id: null
  epic_id: 413
todos:
  - id: strict-reuse-contract
    content: Add typed strict artifact-reuse behavior through the model-MC action and runner without changing legacy fallback defaults.
    status: completed
    work_item_id: null
  - id: slim-program
    content: Add and compile a model-MC-only DomainProgram with strict reuse enabled.
    status: completed
    work_item_id: null
  - id: tests-schemas
    content: Regenerate contracts and test reuse, failure, and one-action graph behavior.
    status: completed
    work_item_id: null
  - id: docs-plan
    content: Document the canonical ECDF+covariates command, outputs, guarantees, and promote the plan.
    status: completed
    work_item_id: null
---

# Strict-Reuse Model-MC Program

## Runtime contract
- Add [`workflow_engine/domain/fixtures/validation_model_mc.program.json`](../../workflow_engine/domain/fixtures/validation_model_mc.program.json) containing only `validation.model_mc`, with a program override requiring artifact reuse. It does not run stability, freeze, final model selection, or post-model validation.
- Extend the typed model-MC action input and handler with `requireArtifactReuse`, passed to the workflow-facing model-MC runner.
- Require every `run_XXXX` split to resolve from the primary MC root with `project.json`, `centroids/`, and `detections/`. Missing or incompatible prerequisites fail before centroid/detector fallback. The legacy CLI/default behavior remains unchanged when strict reuse is false.

## Generated contracts and tests
- Regenerate task schemas, action catalog, golden fixtures, and a compiled check fixture for the new program.
- Test strict symlink reuse, missing and incompatible failures, handler propagation, and the one-action compiled graph.

## Operator documentation
- Document the canonical command using the existing ECDF+covariates context and expected `model_mc/ecdf/run_0001` … `run_0010` plus summary outputs.
- State explicitly that this program trains/evaluates model-MC only, uses the configured covariate stacker, and fails instead of rerunning centroid/detector science.
