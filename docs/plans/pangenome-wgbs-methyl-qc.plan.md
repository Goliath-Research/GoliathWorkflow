---
name: Pangenome WGBS methyl QC
overview: Make sample.methyl_qc mode-aware for linear / pangenome / pangenome_wgbs, re-run Buffy missing25 pangenome_wgbs alignments via gateway, then land the deferred MethylCall Mojo hot-path optimizations and cutover gate now that pangenome_wgbs science is validated.

> **Status: IMPLEMENTED (+ follow-on).** Mode-aware QC; missing25 SamplePrep (instance 59); native Mojo MethylCall/MergeCpG/ConversionRate; WGBS Align may run Picard `collectmultiplemetrics` on the QC BAM with optional QC enrichment. **Full Buffy 238 re-extract stays gated** until missing25 SamplePrep COMPLETED.

azure_devops:
  type: Feature
  title: "Pangenome WGBS methyl QC + MethylCall Mojo cutover"
  epic_id: 413
  # work_item_id: assign after Boards seed
todos:
  - id: detect-metrics-family
    content: Detect alignmentMode / artifact family; refuse stale linear Picard fallback on pangenome_wgbs
    status: completed
  - id: optional-models
    content: Make Parabricks-only payload and GuardrailDetails fields Optional; add WGBS provenance block
    status: completed
  - id: wgbs-guardrails
    content: Implement wgbs_pangenome_qc guardrails + wire writer/handler; skip inapplicable screening
    status: completed
  - id: tests-schemas
    content: Unit tests for three modes + schema export if needed
    status: completed
  - id: operator-rerun
    content: Cleanup stub/linear artifacts; gateway SamplePrep start for missing25
    status: completed
  - id: mcall-native-hot-loop
    content: Port alignment_to_methylation + GFA segment lookup to native Mojo; wire parallelize() (methylGrapher-mojo)
    status: completed
  - id: mcall-fullsample-gate
    content: Full-sample MethylCall parity/perf vs 0.2.0; mojo unit tests; gzip I/O as needed
    status: completed
  - id: mcall-cutover-flip
    content: Flip site/profile engine=mojo + image pin; raise MethylCall threads; Python rollback documented
    status: completed
  - id: docs-promote
    content: Promote plan + usage note for mode-aware methyl_qc and Mojo MethylCall cutover
    status: completed
---

# Mode-aware methyl_qc + MethylCall Mojo optimizations

## Problem

`writer.py` always required a full Parabricks payload. That hard-failed for **pangenome_wgbs** (methylGrapher provenance-only metrics). Separately, native MethylCall Mojo ports were deferred until pangenome_wgbs science landed.

## Delivered

### Part A — Mode-aware QC

- `metrics_family.py` — detect by `alignmentMode` / artifacts; refuse stale linear Picard under `pangenome_wgbs`
- Optional Parabricks fields + `WgbsAlignMetrics` on sample QC models
- `wgbs_pangenome_qc.py` guardrails; writer skips inapplicable screening
- Handler passes `alignmentMode`; unit tests + regenerated schemas
- Buffy missing25 cleanup + gateway `sample-prep-start` → instance **59**

### Part B — MethylCall Mojo

Primary code: `/home/ubuntu/methylGrapher-mojo`

- Native `alignment_to_methylation`, GFA `Dict` lookup, `parallelize()`, gzip helpers
- `MethylCall` CLI routes to native path (`METHYLGRAPHER_MCALL_ENGINE=python` rollback)
- Toy + DS20M subset `graph.methyl` parity OK; RSS ~15 GiB vs ~22 GiB python
- Image `epimethyl/methylgrapher:1.70-mojo` rebuilt with Mojo runtime + `src/`
- Site `actionConfig.methylgrapher_wgbs.engine=mojo`, `image=:1.70-mojo`, `threads=64`
- Rollback: `engine=python` + `epimethyl/methylgrapher:1.70` (see production runbook + cutover gate)

### Follow-on (former out-of-scope, now landed)

| Item | Status |
|------|--------|
| Picard `collectmultiplemetrics` after WGBS QC BAM (worker) | Done — soft-fail; provenance `collectmultiplemetrics`; optional Parabricks enrichment in mode-aware QC |
| Native Mojo MergeCpG | Done — toy + DS20M `graph.cpg.tsv` parity |
| Native Mojo ConversionRate | Done — CLI parity; SamplePrep unwired until spike-in lambda assets exist |
| Full Buffy 238 / rewrite Feb linear H5 | **Wait** — open only after missing25 SamplePrep COMPLETED |
| Long-read; re-PrepareGenome; QC BAM/H5 packaging into Mojo | Still deferred (not needed for short-read Buffy biomarkers) |

**Gate for Buffy 238:** do not start cohort-scale re-align/re-extract until the 25-sample SamplePrep instance (gateway **id=59**) reaches COMPLETED with science H5. Track via portal / `wf.workflow_instance` (`status`; was RUNNING at follow-on close). See [`extend-former-out-of-scope.plan.md`](extend-former-out-of-scope.plan.md).

## Cross-links

- [`methylgrapher-mojo-cutover.plan.md`](methylgrapher-mojo-cutover.plan.md) Phase 4 / [`methylgrapher-mojo-cutover-gate.md`](methylgrapher-mojo-cutover-gate.md)
- Usage: [`docs/usage/03-sample-prep-and-qc.qmd`](../usage/03-sample-prep-and-qc.qmd)
