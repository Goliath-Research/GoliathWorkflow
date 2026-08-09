---
name: Full Mojo pangenome WGBS
overview: Full Mojo-accelerated pangenome_wgbs SamplePrep→informME via actionConfig→resolvedConfig (Align, QC BAM, ConversionRate, remediation, true GAF patterns) without worker.env or shell access.

> **Status: IMPLEMENTED (code).** Phases 1–3 landed in repo + site bake helpers. Phase 4 gates (Buffy wall, DS20M parity, sister image load) remain operator measurement.

> **Docs sync (2026-08-09):** [`native-mojo-sample-prep-docs.plan.md`](native-mojo-sample-prep-docs.plan.md) updates living docs to match this actionConfig→resolvedConfig Mojo path (NVIDIA/AMD; no auto-Parabricks).

azure_devops:
  type: Feature
  title: "Full Mojo-accelerated pangenome_wgbs"
  epic_id: 413
todos:
  - id: actionconfig-align
    content: "Phase 1: Mojo/GPU Align knobs on MethylGrapherWgbsStepConfig → resolvedConfig → docker -e"
    status: completed
  - id: site-procedure-bake
    content: "Phase 1: Site + buffy procedure pins; live site updated"
    status: completed
  - id: mojo-qc-bam
    content: "Phase 2: qc_bam_engine mojo/vg with Mojo GAF→BAM packer + vg fallback"
    status: completed
  - id: conversionrate-qc
    content: "Phase 2: ConversionRate → bisulfite_conversion.json"
    status: completed
  - id: remediation-live
    content: "Phase 2: remediate_without_cycles → REALIGN_TRIM"
    status: completed
  - id: gaf-true-patterns
    content: "Phase 3: GAF→patterns.h5 with marginal surrogate fallback"
    status: completed
  - id: e2e-gates
    content: "Phase 4: operator wall/parity/fleet gates"
    status: pending
  - id: ops-actions-sketch
    content: "Docs: constrained-worker-ops-actions.md"
    status: completed
---

# Full Mojo-accelerated pangenome_wgbs (scope B)

See Cursor plan history and this file for the Feature scope. Implementation touchpoints:

- [`workers/methyl_worker/task_models/sample_prep_models.py`](../../workers/methyl_worker/task_models/sample_prep_models.py)
- [`workers/methyl_worker/methylgrapher_wgbs_runner.py`](../../workers/methyl_worker/methylgrapher_wgbs_runner.py)
- [`packages/methylutils/methyl_utils/action_config_resolver.py`](../../packages/methylutils/methyl_utils/action_config_resolver.py)
- [`packages/methylalignmentqc/`](../../packages/methylalignmentqc/)
- [`docs/architecture/constrained-worker-ops-actions.md`](../architecture/constrained-worker-ops-actions.md)

## Phase 4 gates (operator)

| Gate | Criteria |
|------|----------|
| Config | READY Align `resolvedConfig` has Mojo knobs; host env ignored |
| Align wall | Buffy sample ≤ ~2h science GAF vs ~6.2h vg |
| QC | `methyl_qc` pass with Mojo QC BAM + optional ConversionRate/Picard |
| Recovery | `REALIGN_TRIM` → trim → Mojo realign when signals fire |
| Extract / informME | H5 + `patternsSource=gaf` + `pipeline.info_measures` |
| Parity | DS20M `graph.methyl` vs `cpu_vg` |
| Fleet | Sisters load `:1.70-mojo` tar; caps restored |
