---
name: Config propagation analysis
overview: Produce a deep, stage-by-stage analysis of tunable and path config propagation for a methylation process pack (buffy/cfDNA → holdout validation), and fix the highest-risk prepare_freeze binding seams that new packs (shorthand comparisons) expose.

> **Status: IMPLEMENTED.** Analysis at [`docs/architecture/config-propagation-methylation.md`](../architecture/config-propagation-methylation.md); prepare_freeze binders use `get_comparisons()` + canonical `detectOutDir`.

azure_devops:
  type: Feature
  title: "Config propagation analysis (methylation)"
  work_item_id: null
  epic_id: 413
todos:
  - id: analysis-doc
    content: Write docs/architecture/config-propagation-methylation.md (bake → stages → holdout, risks, checklist)
    status: completed
  - id: fix-prepare-freeze-bind
    content: Use get_comparisons() + canonical detectOutDir in validation.py and action_skip.py
    status: completed
  - id: regression-tests
    content: Add tests for shorthand comparisons and detectOutDir shape (live + CAAS enrich)
    status: completed
  - id: docs-wire-plan
    content: Link from architecture index/e2e; promote plan to docs/plans/
    status: completed
---

# Methylation config-parameter propagation analysis

## Goal

Document how config actually flows along a long methylation run (buffy coat or cfDNA → SamplePrep → MC stability → freeze → model → holdout validation), and harden the prepare_freeze path-binding seam that recent pack additions (`control_vs_each_disease` shorthand) can break.

**Primary deliverable:** architecture analysis doc at [`docs/architecture/config-propagation-methylation.md`](../architecture/config-propagation-methylation.md), linked from [`docs/architecture/index.md`](../architecture/index.md).

**Companion fix:** make prepare_freeze live + CAAS replay use `get_comparisons()` and canonical detection dirs via [`production_centroid_detect_dirs`](../../workers/methyl_worker/handler_helpers.py).

## End-to-end model

See the analysis doc. Precedence (code truth): site → profile → instance/program overlays → analyte fill-missing-only (`resolve_action_config`). Program `stepOverride` is task-scoped.

## Findings fixed

1. **Critical** — iterating raw `comparisons` string broke centroid/detect binding for shorthand manifests.
2. **High** — `detectOutDir` now uses `get_detection_output_dir` → `detections/{control}/{disease}`.

## Out of scope (documented only)

- Reworking analyte precedence / null-cap clearing
- full_lifecycle adding `model_mc`
- Changing SaMD profile default `primary_analyte`
- RNA/proteomics pack topology
