---
name: MHL Survival Alternative
overview: "Add a first-class alternative to FeatureCuts/ECDF: accelerated linear alignment with methylation BAM tags, a native high-performance MHB/MHL caller (no mHapSuite), capture QC, and a time-to-event validation path, wired as a new EM-Seq procedure and DomainProgram."

> **Status: IMPLEMENTED.** Parallel assay+science path: `cfdna_emseq_mhl_survival` + `researchMode: mhl_survival`. Existing `cfdna_emseq_targeted` + `gene_fc` is unchanged.

azure_devops:
  type: Feature
  title: "Native MHB/MHL + survival as an alternative methodology"
  work_item_id: null
  epic_id: 413
todos:
  - id: bam-tags
    content: Emit methylation BAM tags from Mojo linear align; native caller prefers tags, falls back to sequence+XG; parity test vs extract.
    status: completed
  - id: mhap-extract
    content: "MethylExtractor: one-pass panel haplotype store contract + sidecar; Python loader in methyl_utils."
    status: completed
  - id: mhb-mhl-action
    content: "packages/methylmhl + pipeline.mhb_mhl (discovery + locked BED + MHL matrix); schemas, catalog, worker CLI."
    status: completed
  - id: panel-qc
    content: On-target depth + pos/neg control methylation guardrails for EM-Seq capture.
    status: completed
  - id: survival-backend
    content: Study survival sidecar schema + validation cox/survival backend (Cox, KM, time-AUC, optional nomogram).
    status: completed
  - id: procedure-program
    content: New cfdna_emseq_mhl_survival procedure + study_validation_mhl_survival program + mode; docs (ch.24/25, Wong gaps); CI smoke.
    status: completed
---

# Native MHB/MHL + survival as an alternative methodology

Wong et al. 2026 (npj Precis Oncol; gap note [`docs/research/Wong2026_EMSeq_mCRPC_MethylPipeline_Gaps.md`](../research/Wong2026_EMSeq_mCRPC_MethylPipeline_Gaps.md)) is **not** FeatureCuts classification. This plan adds a **parallel** assay+science path. Existing `cfdna_emseq_targeted` + `gene_fc` stays unchanged.

**Locked choices:** keep **accelerated** Parabricks/Mojo linear align; emit **BAM methylation tags**; **native** MHB/MHL caller (no mHapSuite/Bismark dependency). Performance is the constraint: one BAM walk in C, cohort LD on a compact haplotype store—not Python over BAM.

## What shipped

| Layer | Keep | Added |
|-------|------|-------|
| Align | `sample.parabricks_fq2bam` (`linear`) | Optional `XM:Z`/`XG:Z` via `write_methylation_tags` (Mojo) |
| Extract | Panel `samtools -L` + marginal H5 | Same pass: `{chrom}-CG.mhap.h5` (`--mhap`) |
| Science | `gene_fc` / ECDF lifecycle | `pipeline.mhb_mhl` + Cox model-MC |
| Procedure | `cfdna_emseq_targeted` | `cfdna_emseq_mhl_survival` + `study_validation_mhl_survival` + `mhl_survival` mode |

`patterns.h5` (fixed k=2–8 tile histograms) **cannot** produce Wong MHL. Contract: [`docs/reference/mhap_store_contract.md`](../reference/mhap_store_contract.md).

## Out of scope (still)

- Replacing `gene_fc` / ECDF
- Wrapping mHapSuite or adding a Bismark SamplePrep node
- Hardcoded Wong 15-MHB panel or GREAT as a required node
- In-process ctdna.org API (operator sidecar column is enough)
- Spatial / pattern-4% endpoints
