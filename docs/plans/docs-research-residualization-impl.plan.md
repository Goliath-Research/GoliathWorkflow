---
name: Docs Research Residualization
overview: Add a Research section to the docs hub canvas (Theory / Usage / Implementation triptych), publish a site-facing implementation chapter that describes each residualization confounder, and replace the Horvath stub with a packaged Hannum 2013 blood clock as the default age covariate.

> **Status: IMPLEMENTED.** Hannum 2013 panel `hannum2013_v1.json`; implementation chapter [`docs/implementation/mvalue-residualization.md`](../implementation/mvalue-residualization.md); Research section on the docs hub canvas.

azure_devops:
  type: Feature
  title: "Docs research residualization (Hannum age clock)"
  work_item_id:
  epic_id: 413
todos:
  - id: hannum-panel
    content: Ship hannum2013_v1.json (71 CpGs, GRCh38 via Zhou HM450 manifest, published Table S3 weights); point buffy_wgbs_mvalue_residual_gene_fc at it; keep stub only as a test fixture if needed
    status: completed
  - id: hub-research-section
    content: Add Research section + per-confounder table to docs/canvas/methylpipeline-docs.canvas.tsx; sync canvases
    status: completed
  - id: impl-chapter
    content: Write docs/implementation/mvalue-residualization.md with one section per confounder (Hannum as selected age clock); wire MkDocs nav + implementation indexes
    status: completed
  - id: methylutils-trio
    content: Extend packages/methylutils/docs/{THEORY,USAGE,IMPLEMENTATION}.md for residualize/confounder scores
    status: completed
  - id: cross-links
    content: Point research note, usage ch.24, theory ch.02/12, and residualization canvas at the implementation chapter; drop stub honesty language
    status: completed
---

# Research section + per-confounder implementation

Residualization already has a research note and a dedicated canvas. This follow-on adds (1) a **Research** entry on the docs hub, (2) an **Implementation** write-up of each confounder in the same style as other packages, and (3) a **real age clock** (Hannum 2013) instead of the Horvath placeholder.

[`docs/CONTRIBUTING.md`](../CONTRIBUTING.md) keeps `docs/research/` as exploratory (not product truth) and **excluded** from MkDocs. Product-facing confounder mechanics live in Implementation + the methylutils package docs; the research note links **upward**.

See the original Cursor plan body for the design (Hannum vs Horvath, canvas layout, one-home-per-fact). Delivery artifacts:

- [`packages/methylutils/methyl_utils/data/confounder_panels/hannum2013_v1.json`](../../packages/methylutils/methyl_utils/data/confounder_panels/hannum2013_v1.json)
- [`docs/implementation/mvalue-residualization.md`](../implementation/mvalue-residualization.md)
- [`docs/canvas/methylpipeline-docs.canvas.tsx`](../canvas/methylpipeline-docs.canvas.tsx) Research section
- Procedure `buffy_wgbs_mvalue_residual_gene_fc` `age_clock_path`: `hannum2013_v1.json`
