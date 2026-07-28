---
name: SamplePrep Pangenome Documentation
overview: Deepen and synchronize SamplePrep documentation around three-mode alignment, bisulfite-aware methylGrapher correction, expanded QC, extraction, and the downstream information-measure handoff. Also fix the discovered methylGrapher extraction-manifest incompatibility so extraction QC matches the documented workflow.

> **Status: COMPLETED.** Three-mode SamplePrep docs synchronized; methylGrapher extraction manifests satisfy extraction QC; diagram regenerated.

azure_devops:
  type: Feature
  title: "SamplePrep pangenome documentation + extraction-QC contract"
  work_item_id: null
  epic_id: 413
todos:
  - id: traceability
    content: Promote the approved plan into docs/plans and add AB#413 traceability
    status: completed
    work_item_id: null
  - id: manifest-contract
    content: Emit a canonical extraction-QC manifest from methylGrapher and add integration tests
    status: completed
    work_item_id: null
  - id: primary-diagram
    content: Replace and render the three-mode SamplePrep workflow diagram
    status: completed
    work_item_id: null
  - id: canonical-docs
    content: Deepen canonical SamplePrep operator and implementation documentation
    status: completed
    work_item_id: null
  - id: sync-references
    content: Synchronize stale workflow, architecture, deployment, theory, and regulatory references
    status: completed
    work_item_id: null
  - id: validate
    content: Run targeted tests, diagram checks, and documentation validation
    status: completed
    work_item_id: null
---

# SamplePrep Pangenome Documentation

## 1. Record and trace the work
- Promote this approved plan to [`docs/plans/sampleprep-pangenome-documentation.plan.md`](sampleprep-pangenome-documentation.plan.md), normalize its repository frontmatter/status, and add the Feature mapping to [`docs/plans/README.md`](README.md) under AB#413.

## 2. Repair methylGrapher → extraction-QC compatibility
- Update [`workers/methyl_worker/methylgrapher_wgbs_runner.py`](../../workers/methyl_worker/methylgrapher_wgbs_runner.py) so `sample.methylgrapher_wgbs_extract` writes the canonical extraction-manifest fields consumed by [`packages/methylextractionqc/methyl_extraction_qc/guardrails.py`](../../packages/methylextractionqc/methyl_extraction_qc/guardrails.py): `metadata.contexts_extracted`, per-chromosome/context site and coverage metrics, and weighted summary coverage derived from the emitted calls. Preserve graph assets, coordinate-system provenance, H5 files, and pattern files; explicitly leave unavailable read-filtering metrics absent so the existing guardrail reports a skipped check rather than inventing data.
- Extend [`workers/tests/test_methylgrapher_wgbs.py`](../../workers/tests/test_methylgrapher_wgbs.py) with dry-run assertions for the canonical manifest and an end-to-end extraction-QC evaluation proving the methylGrapher output passes coverage/completeness for its expected chromosome.

## 3. Replace the primary SamplePrep diagram
- Rewrite [`docs/diagrams/src/sample-prep-flow.mmd`](../diagrams/src/sample-prep-flow.mmd) from the canonical [`workflow_engine/domain/fixtures/sample_prep.program.json`](../../workflow_engine/domain/fixtures/sample_prep.program.json): three alignment branches, matching remediation realignment, methylGrapher-vs-MethylExtractor extraction, alignment and extraction QC gates, archive/cleanup, and the `.patterns.h5` handoff to downstream `pipeline.info_measures` (clearly outside SamplePrep).
- Regenerate checked-in diagram outputs with `scripts/render_diagrams.sh` and verify `--check` passes.

## 4. Deepen canonical operator and implementation documentation
- Expand [`docs/usage/03-sample-prep-and-qc.qmd`](../usage/03-sample-prep-and-qc.qmd) and [`docs/implementation/sample-preparation-flow.md`](../implementation/sample-preparation-flow.md) with:
  - exact stage ordering and remediation behavior;
  - linear, stock Giraffe, and WGBS pangenome selection/configuration;
  - the bisulfite-aware correction chain: dual C2T/G2A indexes → directional methylGrapher alignment → GAF (named-segment space, kept for `MethylCall`) → separate `vg giraffe -o BAM --ref-paths` C2T pass → restoration of original read sequences/qualities → sort/markdup/index → QC-compatible BAM;
  - graph-aware methyl calling, linear-coordinate projection, H5/pattern outputs, asset fingerprints, image/version provenance, and failure/no-fallback rules;
  - alignment-QC and extraction-QC metrics/gates and the corrected manifest contract;
  - a precise boundary showing SamplePrep emits read-level patterns while `pipeline.info_measures` runs later in the study lifecycle.

## 5. Synchronize canonical contracts and all stale references
- Update workflow/operator contracts in [`workflow_engine/sql_mssql/SamplePrepFlow.md`](../../workflow_engine/sql_mssql/SamplePrepFlow.md), [`workflow_engine/contract/sample_prep_capabilities.md`](../../workflow_engine/contract/sample_prep_capabilities.md), and [`workflow_engine/docs/pipeline_architecture.md`](../../workflow_engine/docs/pipeline_architecture.md) for methylGrapher actions, correct stage order, archive semantics, typed gates, and removal of retired `sample.upload_h5` wording.
- Refresh architecture diagrams/prose in [`docs/architecture/end-to-end-workflow.md`](../architecture/end-to-end-workflow.md), including the downstream information-measure handoff.
- Correct operator/deployment/theory terminology and setup guidance in [`docs/usage/24-methylation-application-packs.qmd`](../usage/24-methylation-application-packs.qmd), [`docs/regulatory/Regulatory-Ready Platform for Multiomics Diagnostics.md`](../regulatory/Regulatory-Ready Platform for Multiomics Diagnostics.md), [`docs/deployment/production_runbook.md`](../deployment/production_runbook.md), [`docs/theory/chapters/09a-methylextractionqc.qmd`](../theory/chapters/09a-methylextractionqc.qmd), [`workflow_engine/domain/profiles/procedures/README.md`](../../workflow_engine/domain/profiles/procedures/README.md), and [`docs/DOCUMENTATION_AUDIT.md`](../DOCUMENTATION_AUDIT.md).

## 6. Validate implementation and documentation
- Run targeted tests in `.venv` for methylGrapher extraction, extraction QC, procedure/profile routing, and SamplePrep graph compilation.
- Run diagram freshness checks and the repository’s available documentation/link validation for changed QMD/Markdown files.
- Inspect generated diffs for stale “Giraffe-only,” `upload-h5`, two-way alignment, or “information measures run inside SamplePrep” claims; update the plan status/todos to completed when verified.
