---
name: Model-MC Shared Reuse Enforcement
overview: Ensure `--model-mc --model-mc-all` reuses existing stability run artifacts by default (via symlinks) and only re-executes centroid/detector when source runs are missing or unusable.
todos:
  - id: reuse-policy-cli
    content: Update `_build_model_mc_shared_runs` to prefer symlink reuse of primary runs when artifacts are valid, with fallback to recomputation.
    status: pending
  - id: shared-timings-compat
    content: Ensure shared timings metadata remains valid for reused runs so downstream loader marks detector_ok and keeps sample counts.
    status: pending
  - id: test-shared-symlink
    content: Add/adjust CLI resume tests to assert reusable runs are symlinked and pipeline execution is skipped.
    status: pending
  - id: validate-with-pytest
    content: Run targeted test suite for model-mc resume/reuse paths and confirm pass.
    status: pending
  - id: runtime-smoke
    content: Verify on project artifacts that shared run folders are symlinks and model-mc-all does not re-run centroid/detector when reuse is possible.
    status: pending
isProject: false
---

# Enforce Shared-Run Reuse in Model-MC

## Goal
Prevent unnecessary recomputation/storage by making model-MC shared stage prefer existing `monte_carlo_runs/run_XXXX` artifacts and only run centroid/detector when a reusable source run is unavailable.

## Confirmed Issue Pattern
- Shared-stage can still run expensive detector path even when source run artifacts exist.
- Reused shared entries can become inconsistent (e.g., partial directories instead of links), causing backend failures.
- ECDF logs can look misleading when run project wiring is stale or incomplete.

## Proposed Changes
- **Shared-stage reuse policy in** [`/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/cli.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/cli.py)
  - In `_build_model_mc_shared_runs`, after `resolve_iteration_split(..., split_src='reused')`, check if `primary_monte_carlo_runs_root/run_XXXX` contains required artifacts (`project.json`, `centroids/`, `detections/`).
  - If reusable, replace/create `model_mc/shared/run_XXXX` as a symlink to source run.
  - Import step-timing metadata from primary `step_timings.csv` into shared timings (or synthesize minimal detector-ok row when unavailable) so downstream shared-row loader accepts reused runs.
  - Only call `generate_run_project*` + `run_pipeline_for_iteration*` when source run is missing/unusable.

- **Shared-run integrity guardrails**
  - Ensure existing non-symlink `shared/run_XXXX` entries are replaced when choosing reuse path.
  - Keep resume semantics intact (delete future runs on resume, retain prior completed runs).

- **Tests in** [`/home/ubuntu/MethylPipeline/packages/methylvalidation/tests/test_cli_resume.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/tests/test_cli_resume.py)
  - Add test that verifies reusable source run leads to symlink creation and skips pipeline execution.
  - Keep/adjust backend-profile fixtures so model-mc-all backend selection tests remain stable.

## Data Flow (target behavior)
```mermaid
flowchart LR
  split[resolveIterationSplit] --> decision{splitSrc reused?}
  decision -->|no| build[GenerateRunProject + CentroidDetector]
  decision -->|yes| check[CheckSourceRunArtifacts]
  check -->|valid| link[CreateOrReplaceSymlink shared/run_XXXX -> primary/run_XXXX]
  check -->|invalid| build
  link --> timing[AppendSharedTimingsMetadata]
  build --> timing
  timing --> sharedRows[LoadSharedRows for backend stages]
```

## Validation Plan
- Run targeted tests:
  - `pytest packages/methylvalidation/tests/test_cli_resume.py -q`
- Runtime smoke checks:
  - Run `--model-mc --model-mc-all` on project with existing `run_0001..run_0030`.
  - Confirm shared logs report reuse and that `model_mc/shared/run_XXXX` are symlinks.
  - Confirm no centroid/detector steps are executed for reused runs.

## Acceptance Criteria
- Existing stability runs are reused by default in shared stage via symlinks.
- Centroid/detector execute only for missing/incomplete runs.
- Shared-stage outputs remain consumable by all backends (`ecdf`, `tabular_sklearn`, `generative_hybrid`).
- No regressions in model-mc resume/reuse tests.