---
name: Streamline Action Parameters
overview: Audit and slim all catalog actions so external task inputs carry only workflow-bound identity, internal tool parameters live exclusively in resolvedConfig/stepOverride, and handlers/CLIs shed legacy dual-path resolution—using a hard-cut policy aligned with the completed step_config retirement.

> **Status: COMPLETE.** Wire tunables removed, per-action task models split, MC sidecar overrides retired, CI boundary guard added.

todos:
  - id: contract-audit-ci
    content: Add action-parameter-contract.md + check_task_input_config_boundary.py CI guard; fix catalog typing/doc drift (extraction_qc, stale descriptions)
    status: completed
  - id: canonical-config-keys
    content: Document canonical homes for duplicated knobs; migrate profiles (dmp_selection/validation mirrors, gene caps, backend_profiles); remove materialize_action_input cap bridge
    status: completed
  - id: retire-mc-sidecars
    content: Remove mapper_step_override.json / detector_step_override.json read/write paths; rely on mc_config.json + stepOverride only
    status: completed
  - id: slim-sample-prep-inputs
    content: Split SamplePrepTaskInput; gut MethylExtractTaskInput/ParabricksFq2bamTaskInput wire tunables; remove sample.upload_h5; update sample_prep programs
    status: completed
  - id: slim-pipeline-inputs
    content: Per-action minimal pipeline TaskInputs + argv builders; DmpSelectStepOverride; remove wire caps from gene_select/gene_feature_select
    status: completed
  - id: slim-validation-inputs
    content: Replace shared ValidationTaskInput with per-action models; mark or remove internal-only validation sub-actions
    status: completed
  - id: slim-implementations
    content: Refactor extract_runner, QC handlers, validation handlers to single resolvedConfig path; thin handlers; drop legacy collectors where manifest-first
    status: completed
  - id: docs-promote-plan
    content: Update sample-preparation-flow + config-parameter-matrix; promote plan to docs/plans/streamline-action-parameters.plan.md
    status: completed
---

# Streamline workflow actions (parameters + implementations)

## Context

MethylPipeline has end-to-end documentation ([`docs/implementation/sample-preparation-flow.md`](../implementation/sample-preparation-flow.md), workflow engine guides) and a mature action surface:

- **33 actions** in [`workers/methyl_worker/action_catalog.py`](../../workers/methyl_worker/action_catalog.py) at plan time (`sample.upload_h5` removed; catalog is **37** actions as of action-provider-registry)
- **Strict typed I/O** (implemented per [`typed-action-observability.plan.md`](typed-action-observability.plan.md))
- **Four-layer config** (implemented per [`simplify-study-config.plan.md`](simplify-study-config.plan.md))

The remaining gap was **parameter hygiene** and **implementation bloat**: several actions still accepted tunable knobs on the wire *and* in `resolvedConfig`, shared overly generic input models, or resolved config through legacy `_pick(input_json, step_cfg, …)` dual paths.

**Policy for this plan:** **hard cut** — remove redundant wire fields in the same change set as profile/DomainProgram/test updates (no deprecation shim).

## Deliverables (shipped)

| Area | Artifact |
|------|----------|
| Contract docs | [`docs/reference/action-parameter-contract.md`](../reference/action-parameter-contract.md) |
| CI guard | [`scripts/check_task_input_config_boundary.py`](../../scripts/check_task_input_config_boundary.py) in `.github/workflows/db-parity.yml` |
| Profile migration | [`scripts/migrate_profile_action_config.py`](../../scripts/migrate_profile_action_config.py) |
| Task models | Per-action inputs in `workers/methyl_worker/task_models/` |
| MC overrides | Dict-based `build_*_override` in `mc_manifest.py`; no sidecar JSON writes |
| Collectors | Manifest-first only (legacy fallback removed from `actions/base.py`) |

## Success criteria (met)

- Every catalog action has a documented external-input field list with **zero overlap** with its `actionConfig` schema (CI enforced).
- No task input model carries operator-tunable science parameters on the wire.
- No handler/CLI uses `_pick(wire, resolvedConfig)` dual resolution for sample prep extract.
- MC iterations do not rely on `*_step_override.json` sidecars for worker dispatch.
- `methyl-export-task-schemas --check` and worker golden tests pass after hard-cut profile/program updates.

## Related plans

- **Depends on (complete):** typed-action-observability, simplify-study-config, composable-pipeline-flexibility.
- **Parallel / complementary:** [`dmp_gene_modeling_modes_c0d0bad6.plan.md`](dmp_gene_modeling_modes_c0d0bad6.plan.md).
