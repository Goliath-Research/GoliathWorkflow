---
name: Production config enforcement
overview: Enforce production-final config semantics — complete deep_merge null-clearing, restore model_mc in full_lifecycle, study-owned analyte, clear RNA/proteomics pack boundaries with shared generic seams, and first-class single-scenario hyperparam experiments for stability targets without requiring a grid search.

> **Status: IMPLEMENTED.** Null-delete `deep_merge`, `full_lifecycle` + `model_mc`, study-owned analyte, modality gates, `scenario-start`. See [`docs/architecture/config-propagation-methylation.md`](../architecture/config-propagation-methylation.md).

azure_devops:
  type: Feature
  title: "Production config enforcement"
  work_item_id: null
  epic_id: 413
todos:
  - id: deep-merge-null-delete
    content: Make deep_merge treat null as key delete (resolver + pipeline_profiles); retire package-local null hacks; align precedence docs to code; add resolver/gene-select tests
    status: completed
  - id: full-lifecycle-model-mc
    content: Insert validation.model_mc into full_lifecycle.program.json before select_best; sync compiled smoke + deploy; fix any wrong description/bindings
    status: completed
  - id: study-owned-analyte
    content: Remove nested primary_analyte (and nested regulatory analyte) from samd_*/staged profiles; bake prefers study regulatory; document study analyte matrix
    status: completed
  - id: pack-boundaries
    content: Document shared vs pack-owned DomainProgram seams; modality×program×profile allow-list at instance start; study_init non-methyl analyte handling
    status: completed
  - id: scenario-experiments
    content: Add first-class scenario/single-trial start (HyperparamTrialOverlay → one instance + executionScope) for stability-target knobs without Cartesian grid
    status: completed
  - id: docs-promote
    content: Update config-propagation-methylation + portal/HPO docs; promote plan to docs/plans/; README row under AB#413
    status: completed
---

# Production config enforcement

Near-production posture: **enforce the final contracts** (not deprecate-only). Supersedes earlier “document-only” recommendations for deferred config-propagation gaps, and adds scenario experiments for stability targets without a mandatory grid.

## Delivered

1. **`deep_merge` null-delete** — shared resolver + `pipeline_profiles._deep_merge`; docs aligned to site → profile → overlay → analyte fill-missing.
2. **`full_lifecycle` + `model_mc`** — node inserted before `select_best_model`; compile smoke assert; compiled artifact refreshed.
3. **Study-owned analyte** — stripped nested `primary_analyte` from `samd_*` / staged profiles; bake syncs study regulatory into `resolvedConfig__validation.regulatory`; fail-closed for methyl without analyte.
4. **Pack boundaries** — [`modality_gate.py`](../../packages/methylutils/methyl_utils/modality_gate.py); `study_init` supports proteomics and omits analyte for non-methyl; methyl-only actions refuse under wrong modality.
5. **Scenario start** — `HyperparamScenarioRequest` + `methyl-study-start scenario-start` + schema; optional single-trial cfg ledger.

## Out of scope (still)

- Bayesian / Hyperband HPO strategies
- Rewiring RNA/proteomics study programs to full methyl MC stability DAGs
- Changing analyte fill-missing-last into analyte-overwrites-site
- EpiPortal UI screens (API/CLI/DB first)
