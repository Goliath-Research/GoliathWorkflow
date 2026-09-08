# Moffitt partnership opportunity brief

**Status:** external-facing research / BD note (not an operator runbook).  
**Date:** 2026-09-08  
**Audience:** Goliath Omics + Moffitt (Wang laboratory and collaborators).  
**Anchor paper:** Wong J. et al. *Plasma cell-free DNA methylation-based prognosis in metastatic castrate-resistant prostate cancer.* npj Precision Oncology (2026) 10:29. [doi:10.1038/s41698-025-01232-w](https://doi.org/10.1038/s41698-025-01232-w). Corresponding author affiliation: Moffitt Cancer Center (`Liang.Wang@Moffitt.org`). Local PDF: [`41698_2025_Article_1232.pdf`](41698_2025_Article_1232.pdf).

**Related**

| Document | Role |
|----------|------|
| [Wong2026_EMSeq_mCRPC_MethylPipeline_Gaps.md](Wong2026_EMSeq_mCRPC_MethylPipeline_Gaps.md) | Capability gap note vs the paper (updated after native MHL) |
| [Prostate cancer options catalog (usage ch.25)](../usage/25-prostate-cancer-pack.md) | Operator procedure IDs |
| [Methylation application packs (ch.24)](../usage/24-methylation-application-packs.md) | `cfdna_emseq_mhl_survival` in the procedure table |
| [mhap store contract](../reference/mhap_store_contract.md) | Per-read haplotype sidecar |
| Plan | [`mhl-survival-alternative.plan.md`](../plans/mhl-survival-alternative.plan.md) (**implemented**) |

---

## Why this brief exists

Moffitt’s published mCRPC work is **haplotype-block MHL + overall-survival modeling** on targeted EM-Seq plasma, not MethylPipeline’s default gene FeatureCuts / ECDF classification path.

Until the MHL survival work landed, a partnership conversation had to say: we can align and extract a capture panel, but we **cannot** run their analysis. That is no longer true. MethylPipeline now ships a **parallel** assay+science path that implements their *method class* (MHB discovery or locked blocks, Guo/Wong MHL, Cox / KM / time-AUC, optional nomogram and nested LRT). FeatureCuts on `cfdna_emseq_targeted` is unchanged and remains a **different study**.

This note is a collaboration framing, not a claim that we reproduced their 15-MHB nomogram, GREAT enrichment, or ctdna.org fusion.

---

## What Moffitt published (method class)

| Layer | Wong et al. 2026 |
|-------|------------------|
| Material | Plasma cfDNA; localized PC / mHSPC / mCRPC (OS on mCRPC) |
| Chemistry | NEB EM-Seq + Twist custom methylome capture (~3.44 Mbp) |
| Align | Bismark + bowtie2, hg38, Bismark dedup |
| Features | mHapSuite → MHBDiscovery (window 3, \(r^2>0.3\), \(p<0.05\)) → **MHL** (consecutive load, lengths 1–10) |
| Filters | ≥3 CpGs; median reads >50; drop controls; tumor-like MHL ≤0.05 in localized PC |
| Endpoint | Univariable / multivariable **Cox PH**, KM, LOOCV composite; time-dependent ROC; nomograms |
| Fusion | PSA, ALP, LDH + **predicted ctDNA fraction** (ctdna.org), nested test vs labs/ctDNA alone |

Intended use in the paper: **mCRPC overall-survival prognostication**. It is not a pre-biopsy GG≥2 NPV gatekeeper and not healthy-vs-PCa detection.

---

## What Goliath now supports

Shipped procedure: [`cfdna_emseq_mhl_survival`](../../workflow_engine/domain/profiles/procedures/cfdna_emseq_mhl_survival.procedure.json)  
Mode: `researchMode: mhl_survival`  
Lifecycle: `study_validation_mhl_survival`  
SamplePrep: same EM-Seq linear path as `cfdna_emseq_targeted` (`sample_prep_emseq`), with methylation BAM tags on.

| Paper step | MethylPipeline (now) |
|------------|----------------------|
| EM-Seq + capture BAM | Linear align (Parabricks `fq2bam_meth` or Mojo); optional `XM:Z` / `XG:Z`; panel extract via operator `target_panel_bed` |
| Per-read haplotypes | Same extract pass: `{chrom}-CG.mhap.h5` (`mhap.enabled`) |
| MHB discovery | `pipeline.mhb_mhl` — `core_window` 3, `r2_min` 0.3, `p_max` 0.05, `min_cpgs` 3, `min_median_reads` 50 (procedure defaults; site/profile overlay) |
| Locked MHB BED | Same action, operator BED instead of discovery |
| MHL | Native caller, lengths 1–`mhl_max_length` (default 10); **not** mHapSuite, **not** informME NME/MML, **not** `patterns.h5` tiles |
| Capture / control QC | Optional `extraction_qc` panel + pos/neg control BEDs |
| Cox / KM / time-AUC / nomogram | `backend_profiles.cox` + study `survival_path` CSV (`sample_id`, `time`, `event`, optional labs / ctDNA column) |
| Nested LRT vs clinical covariates | Procedure `nested_lrt: true` when the sidecar carries those columns |

**Still operator- or Moffitt-supplied (not hardcoded in product):**

- Twist / custom **panel BED** (their 437-region design is their IP)
- **Survival sidecar** (time, event, PSA, ALP, LDH, optional predicted ctDNA)
- Optional **locked 15-MHB gene list** (intentionally not a package default)
- GREAT as a pipeline node (optional later)
- In-process ctdna.org API (a sidecar column is enough)

**Intentionally not this path:** wrapping mHapSuite, adding Bismark as a required SamplePrep node, replacing `gene_fc` / ECDF, or treating HiTIMED `tumor_fraction` as the ctdna.org clinical predictor.

---

## Partnership shapes that now make sense

1. **Method transfer / independent implementation** — Run Moffitt FASTQs (or a jointly agreed capture) through `cfdna_emseq_mhl_survival` and compare MHB/MHL matrices and Cox fits to mHapSuite+R, without asking them to adopt FeatureCuts.
2. **Scale and operations** — Same method class on Goliath’s distributed workers, `/work` layout, SaMD research profile, and audit trail; Moffitt keeps science ownership of panel and clinical follow-up.
3. **Extension, not substitution** — Pair Moffitt MHL+OS (plasma, mCRPC) with Goliath buffy WGBS host biology and/or EM-Seq FeatureCuts **gatekeeper** geometry as **separate** intended uses, labeled as such.
4. **Locked-panel productization** — If they share or license a BED + survival dictionary, the procedure already accepts `mhb_mhl.mode` locked-BED plus `survival_path`.

A collaboration does **not** require merging their nomogram into the default prostate detection pack.

---

## What we would ask Moffitt to bring

| Asset | Why |
|-------|-----|
| Capture panel BED (hg38) and control-region BEDs | Required for extract `-L` and for dropping control MHBs |
| Per-sample OS (and labs) table keyed to FASTQ / sample IDs | `survival_path` |
| Optional: mHapSuite MHL matrix on a shared subset | Concordance vs native caller |
| Optional: predicted ctDNA fraction (ctdna.org or equivalent) | Nested LRT vs methylation-only |
| Statement of intended use | Prognosis in mCRPC vs any detection/gatekeeper claim |

Goliath would bring: procedure + native MHL stack, alignment/extract QC, Cox backend, and a written gap list for GREAT / host-arm plasma MHL if they want those next.

---

## Claim boundary

- Supporting **Moffitt methods** means we can execute the **same class of analysis** (EM-Seq capture → MHB/MHL → time-to-event). It does **not** mean we have rerun their 96-patient cohort or matched their published C-indices.
- ECDF / gene FeatureCuts balanced accuracy on panel HDF5 is **not** a Wong repeat.
- Registered PCa feasibility packages remain **engineering** evidence; they must not be cited for OS nomogram performance or biopsy deferral.

---

## Suggested next conversation (one page)

1. Confirm they want a **prognosis** collaboration on mCRPC plasma, not a FeatureCuts detection bake-off.
2. Exchange a **minimal BED + survival dictionary** (even a subset of samples) for a concordance pilot.
3. Agree whether discovery MHBs or a **locked** Moffitt MHB list is the shared object.
4. Keep GREAT, ctdna.org automation, and the high-MHL “host” plasma arm as explicit follow-ons.
