# Buffy coat vs cfDNA methylation (MethylPipeline analyte choice)

**Status:** research / design note (not operator runbook).  
**Canonical config:** [`docs/ANALYTE_PROFILES.md`](../ANALYTE_PROFILES.md) — set `regulatory.primary_analyte` to `buffy_coat`, `cfdna`, or `combined`.  
**Empirical comparison canvas:** [`docs/canvas/analyte-comparison.canvas.tsx`](../canvas/analyte-comparison.canvas.tsx).  
**Landscape context:** [`Gemini_on_Cancer_Detection.md`](Gemini_on_Cancer_Detection.md) (MCED competitors / analytes) and [`Grok_on_Gemini_conclusions.md`](Grok_on_Gemini_conclusions.md) (verification + caveats).

MethylPipeline is **analyte-agnostic**: the same DomainProgram + profile path runs for leukocyte DNA and plasma cfDNA. Analyte choice changes biology, QC defaults, and how you interpret features — not which CLI you use.

---

## Biological roles (not competitors by default)

| Analyte | What the methylation signal mainly reflects | Typical detection role |
|---------|---------------------------------------------|------------------------|
| **cfDNA (plasma)** | DNA shed into circulation, including tumor-derived fragments when tumor fraction is high enough; tissue-of-origin and fragmentomic structure | Direct tumor / MCED / monitoring / MRD-oriented signal |
| **Buffy coat (leukocyte DNA)** | Host immune / systemic epigenome (inflammation, aging, exposures, cell-type mix); also matched hematopoietic background for plasma assays | Indirect risk / host-response; CHIP / germline noise filter; complementary layer |

cfDNA methylation assays can carry **tumor-derived** patterns and support tissue-of-origin style inference when tumor fraction and assay design allow it ([Liu et al., PNAS 2023](https://www.pnas.org/doi/10.1073/pnas.2209852119); MCED methylation reviews such as [Chen et al., Cancer Cell 2022](https://www.sciencedirect.com/science/article/pii/S153561082200513X)). Buffy-coat methylation is usually **not tumor DNA**; it tracks host state that may correlate with cancer risk or presence ([WBC methylation epidemiology overview](https://pmc.ncbi.nlm.nih.gov/articles/PMC6896050/)).

**Implication for this pipeline:** treat the two as complementary analytes under one orchestration model — matching how the broader liquid-biopsy field pairs plasma signal with leukocyte background rather than forcing a single-analyte bet.

---

## What the MCED landscape implies (Gemini + Grok)

The commercial MCED / liquid-biopsy field has moved past “cfDNA methylation alone” (GRAIL Galleri-style) toward **multiomics** and **noise control**. Summarized from [`Gemini_on_Cancer_Detection.md`](Gemini_on_Cancer_Detection.md); accuracy and caveats in [`Grok_on_Gemini_conclusions.md`](Grok_on_Gemini_conclusions.md):

| Industry pattern | Examples (landscape notes) | Relevance to MethylPipeline |
|------------------|----------------------------|-----------------------------|
| **cfDNA methylation ± fragmentomics** | Gene Solutions SPOT-MAS; Delfi (fragmentomics-first); Freenome multiomic stack | Pipeline already supports methylation + **cfDNA fragmentomics** QC/features when `primary_analyte: cfdna` |
| **Multiomics beyond DNA methylation** | Exact Cancerguard (methylation + mutations + proteins); Freenome (+ cfRNA, proteins, immune) | Out of scope as first-class analytes today; do not invent protein/RNA steps in Python — keep study design honest about methylation±fragmentomics coverage |
| **Buffy coat as CHIP / germline filter** | Guardant (plasma + buffy to subtract hematopoietic mutations); Freenome / Exact use WBC DNA for background noise in validation | Critical for **mutation** assays. For **methylation** studies, paired buffy still helps: matched host epigenome, cell-type confounding, and “is this plasma signal leukocyte-like?” checks |
| **Bisulfite vs enrichment chemistry** | Adela cfMeDIP (affinity, bisulfite-free) vs chemical conversion | MethylPipeline assumes **bisulfite WGBS / extractor** inputs from Illumina sequencing; chemistry choice is upstream of this repo |

Grok’s caveats apply here too: published sensitivity/specificity are stage- and cohort-dependent; commercial status differs by product (e.g. Guardant Shield is CRC-focused in its approved form); do not copy vendor AUCs into pipeline success metrics.

**CHIP in one paragraph:** aging hematopoietic clones shed mutated DNA into plasma. Mutation-only cfDNA tests can call CHIP as solid-tumor signal. Sequencing buffy coat alongside plasma lets pipelines subtract leukocyte-origin variants. Methylation-first assays are less about CHIP SNVs and more about **host leukocyte methylomes contaminating or confounding plasma features** — still a reason to keep buffy as a first-class analyte and to prefer paired designs when logistics allow.

---

## Goal → preferred analyte (within MethylPipeline)

| Goal | Prefer | Why in this stack |
|------|--------|-------------------|
| Early detection / MCED-like tumor signal, localization, response / MRD | **`cfdna`** | Tumor-shed DNA + fragmentomics (`methyl-fragmentomics`) and cfDNA enricher defaults — aligned with methylation+fragmentomics industry direction |
| Host-risk / systemic signatures, abundant DNA, simpler preanalytics | **`buffy_coat`** | Stable leukocyte DNA; alignment/bisulfite guardrails without cfDNA fragmentomics profile |
| CHIP / germline / leukocyte-background control for plasma work | **Paired `cfdna` + `buffy_coat`** | Same subjects: plasma for tumor-oriented signal, buffy for host/hematopoietic background (industry pattern; methylation analogue of Guardant-style pairing) |
| Host score + tumor burden / ToO | **`combined`** or **paired projects** | Same workflow engine; separate manifests or matched cohort IDs |
| Assay development / feature stability under MC | Either, then compare | MC gene recurrence + cross-analyte concordance (analyte-comparison canvas) |

Published MCED performance claims are **assay- and cohort-specific**. Use MethylPipeline MC stability, hold-out, and analyte-match guards — not vendor brochure numbers.

---

## How MethylPipeline encodes the choice

Set once in the study manifest:

```json
"regulatory": {
  "primary_analyte": "cfdna"
}
```

Allowed tokens normalize to `cfdna`, `buffy_coat`, or `combined` (`packages/methylutils/methyl_utils/analyte_profiles.py`). With `auto_apply_analyte_profile` left on, the resolver merges analyte defaults into `actionConfig` (profile/site keys still win).

| Layer | `cfdna` | `buffy_coat` |
|-------|---------|--------------|
| Alignment QC | Guardrails + bisulfite + **cfDNA fragmentomics** | Guardrails + bisulfite (no cfDNA fragmentomics profile) |
| Fragmentomics action | Enabled (`profile: cfdna`) | Disabled |
| Enricher defaults | `cancer-core` + broader CIS-BP modes | CIS-BP gene_sets emphasis |
| Validation | `enforce_training_analyte_match: true` | Typically `false` |

Sample prep is shared: SamplePrepPipeline → alignment QC → (optional fragmentomics) → extract → extraction QC. See [`docs/implementation/sample-preparation-flow.md`](../implementation/sample-preparation-flow.md).

Orchestration stays DomainProgram-first (`methyl-workflow-run`); analyte does not select a legacy CLI.

---

## Depth: is ~30× enough?

Clarify what “depth” means here:

- Libraries are typically sequenced on **Illumina instruments** (e.g. NovaSeq). That is the sequencing platform — not the Infinium MethylationEPIC **BeadChip array**. MethylPipeline’s production path is **WGBS / extractor-based** methylation from BAM/FASTQ, so depth means **genome-wide sequencing coverage**, not array probe intensity.
- For **buffy-coat / leukocyte WGBS**, ~30× whole-genome–equivalent depth on Illumina is generally **technically adequate** for CpG-level methylation once reads are aggregated. Further depth usually yields diminishing returns; variance is dominated by biology (cell-type composition, inter-individual differences), not Poisson sampling of methylated counts ([related WBC methylation depth discussion](https://pmc.ncbi.nlm.nih.gov/articles/PMC10262593/)).
- For **cfDNA**, depth and library complexity matter more because **tumor fraction** can be very low in early disease. “Enough depth” is inseparable from tumor fraction, duplex/UMI design, and feature aggregation — not a single magic number copied from buffy coat.

**Practical rule for this repo**

- Buffy-only classifier: invest in **feature selection, cell-type awareness, and MC stability**, not automatically in deeper sequencing past a solid WGBS depth.
- cfDNA / MCED-oriented work: invest in **preanalytics, fragmentomics QC, tumor-fraction–aware design**, and analyte-matched training (`model_training_analyte` / plasma retrain path).
- Depth does **not** convert buffy coat into tumor DNA.

---

## Recommended study designs on this pipeline

1. **Buffy-first development** — `primary_analyte: buffy_coat`, MC stability + freeze on leukocyte cohorts; use for host markers and operational learning with abundant DNA.
2. **Plasma / cfDNA production path** — `primary_analyte: cfdna`, fragmentomics on, enforce training analyte match; see [`packages/methylvalidation/docs/PLASMA_RETRAIN_PATH.md`](../../packages/methylvalidation/docs/PLASMA_RETRAIN_PATH.md). Aligns with methylation + fragmentomics MCED direction (SPOT-MAS / Freenome-style DNA layers — not full protein/RNA multiomics).
3. **Paired plasma + buffy (preferred when both tubes exist)** — separate study manifests (or `combined`) with matched subject IDs: cfDNA for tumor-oriented signal; buffy for host epigenome and leukocyte-background control (methylation analogue of industry CHIP/germline filtering). Compare with the analyte-comparison rubric (MC gene recurrence, cross-analyte concordance, discovery direction agreement).
4. **Do not** assume a buffy-trained panel transfers to plasma without retrain and analyte-match validation.
5. **Do not** treat MethylPipeline as a full Cancerguard/Freenome multiomic stack — proteins, cfRNA, and mutation CHIP subtraction are outside the current DomainProgram surface; document study claims accordingly.

Empirical prostate buffy vs plasma MC comparison (marginal separation on one rubric; shared gene core) lives in the canvas and on-disk under `/work/projects/prostate-cancer/analyte_comparison/` when present — use it as **assay-development evidence**, not a clinical performance claim.

---

## Bottom line

- **cfDNA** is the better *direct* analyte for tumor detection and localization when logistics allow; industry peers reinforce methylation **plus** fragmentomics (and often more modalities).
- **Buffy coat** is not only a host-risk analyte: in the MCED field it is also the standard **hematopoietic / germline background** control. MethylPipeline should keep it first-class for host signatures *and* paired plasma designs.
- The pipeline already accepts both; choose via `regulatory.primary_analyte` and profiles, validate with MC + hold-out under the matching analyte, and prefer paired cohorts when both materials are available — not deeper buffy sequencing alone.

---

## Related

- [`docs/ANALYTE_PROFILES.md`](../ANALYTE_PROFILES.md) — analyte defaults and study examples
- [`docs/implementation/sample-preparation-flow.md`](../implementation/sample-preparation-flow.md) — shared prep + cfDNA fragmentomics QC
- [`docs/canvas/analyte-comparison.canvas.tsx`](../canvas/analyte-comparison.canvas.tsx) — buffy vs plasma MC comparison explorer
- [`Gemini_on_Cancer_Detection.md`](Gemini_on_Cancer_Detection.md) — MCED competitors, multiomics, buffy as CHIP filter
- [`Grok_on_Gemini_conclusions.md`](Grok_on_Gemini_conclusions.md) — verification of that landscape note and performance/regulatory caveats
