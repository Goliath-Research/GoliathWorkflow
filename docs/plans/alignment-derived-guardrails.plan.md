---
name: Alignment Derived Guardrails
overview: Add alignment-layer guardrails to methylalignmentqc — Phase 1 derived Picard metrics and Phase 2 samtools flagstat — with analyte profile defaults for cfdna and buffy_coat.
azure_devops:
  type: Feature
  title: "Alignment-derived guardrails"
  work_item_id: 628
  epic_id: 413
todos:
  - id: calibrate-thresholds
    content: Add calibrate_alignment_guardrails.py and extend compare_alignment_qc_groups.py
    status: completed
    work_item_id: 629
  - id: alignment-derived-qc
    content: Implement alignment_derived_qc.py and AlignmentGuardrailsConfig
    status: completed
    work_item_id: 630
  - id: bam-flagstat
    content: Implement bam_flagstat.py and properly-paired guardrails
    status: completed
    work_item_id: 631
  - id: writer-wiring
    content: Wire into writer, handlers, project_resolver, CLI; Pydantic models and schemas
    status: completed
    work_item_id: 632
  - id: analyte-profiles
    content: Enable alignment_guardrails defaults in analyte_profiles for cfdna and buffy_coat
    status: completed
    work_item_id: 633
  - id: tests-docs
    content: Unit tests and documentation updates
    status: completed
    work_item_id: 634
---

> **Status: IMPLEMENTED.** Alignment-layer guardrails ship in `methylalignmentqc` with profile defaults. Operator guide: [sample-preparation-flow.md](../implementation/sample-preparation-flow.md).

# Alignment-Derived Guardrails

## Summary

- **Phase 1:** `alignment_stats` from Picard dedup + GC bias (`mapping_rate`, `secondary_supplementary_rate`, `gc_coverage_uniformity`).
- **Phase 2:** `alignment_flagstat` via `samtools flagstat` on `{sample_id}.bam` during `methyl_qc`.
- **Rollout:** `alignment_guardrails.enabled: true` by default for `cfdna` and `buffy_coat` analyte profiles.
- **Calibration:** `scripts/calibrate_alignment_guardrails.py`

## Key files

| Path | Role |
|------|------|
| `packages/methylalignmentqc/methyl_alignment_qc/core/alignment_derived_qc.py` | Derived metrics + Phase 1 guardrails |
| `packages/methylalignmentqc/methyl_alignment_qc/core/bam_flagstat.py` | flagstat run/parse + Phase 2 guardrails |
| `packages/methylalignmentqc/methyl_alignment_qc/models/config.py` | `AlignmentGuardrailsConfig` |
| `packages/methylutils/methyl_utils/analyte_profiles.py` | Profile defaults |
