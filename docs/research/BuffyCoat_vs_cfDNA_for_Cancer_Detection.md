# Buffy coat vs cfDNA methylation (MethylPipeline analyte choice)

**Status:** research / design note (not operator runbook).  
**Canonical config:** [`docs/ANALYTE_PROFILES.md`](../ANALYTE_PROFILES.md) — set `regulatory.primary_analyte` to `buffy_coat`, `cfdna`, or `combined`.  
**Empirical comparison canvas:** [`docs/canvas/analyte-comparison.canvas.tsx`](../canvas/analyte-comparison.canvas.tsx).

MethylPipeline is **analyte-agnostic**: the same DomainProgram + profile path runs for leukocyte DNA and plasma cfDNA. Analyte choice changes biology, QC defaults, and how you interpret features — not which CLI you use.

---

## Biological roles (not competitors by default)

| Analyte | What the methylation signal mainly reflects | Typical detection role |
|---------|---------------------------------------------|------------------------|
| **cfDNA (plasma)** | DNA shed into circulation, including tumor-derived fragments when tumor fraction is high enough; tissue-of-origin and fragmentomic structure | Direct tumor / MCED / monitoring / MRD-oriented signal |
| **Buffy coat (leukocyte DNA)** | Host immune / systemic epigenome (inflammation, aging, exposures, cell-type mix) | Indirect risk / host-response / confounder and complementary layer |

cfDNA methylation assays can carry **tumor-derived** patterns and support tissue-of-origin style inference when tumor fraction and assay design allow it ([Liu et al., PNAS 2023](https://www.pnas.org/doi/10.1073/pnas.2209852119); MCED methylation reviews such as [Chen et al., Cancer Cell 2022](https://www.sciencedirect.com/science/article/pii/S153561082200513X)). Buffy-coat methylation is usually **not tumor DNA**; it tracks host state that may correlate with cancer risk or presence ([WBC methylation epidemiology overview](https://pmc.ncbi.nlm.nih.gov/articles/PMC6896050/)).

**Implication for this pipeline:** treat the two as complementary analytes you can run under one orchestration model, not as a forced either/or.

---

## Goal → preferred analyte (within MethylPipeline)

| Goal | Prefer | Why in this stack |
|------|--------|-------------------|
| Early detection / MCED-like tumor signal, localization, response / MRD | **`cfdna`** | Tumor-shed DNA + fragmentomics QC (`methyl-fragmentomics`) and cfDNA enricher defaults |
| Host-risk / systemic signatures, abundant DNA, simpler preanalytics | **`buffy_coat`** | Stable leukocyte DNA; alignment/bisulfite guardrails without cfDNA fragmentomics profile |
| Host score + tumor burden / ToO in one study program | **`combined`** or **paired projects** | Same workflow engine; separate manifests or paired cohorts with matched IDs |
| Assay development / feature stability under MC | Either, then compare | Use MC gene recurrence + cross-analyte concordance (see analyte-comparison canvas) |

Published MCED performance claims (high AUCs, multi-cancer localization) are **assay- and cohort-specific**. Do not copy vendor or review AUCs into MethylPipeline success criteria; use your own MC stability, hold-out, and analyte-match guards.

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

Clarify assay type:

- **MethylPipeline production path** is WGBS / extractor-based methylation (not Illumina EPIC arrays). Depth here means **genome-wide sequencing coverage**, not array probe intensity.
- For **buffy-coat / leukocyte WGBS**, ~30× whole-genome–equivalent depth is generally **technically adequate** for CpG-level methylation once reads are aggregated. Further depth usually yields diminishing returns; variance is dominated by biology (cell-type composition, inter-individual differences), not Poisson sampling of methylated counts ([related WBC methylation depth discussion](https://pmc.ncbi.nlm.nih.gov/articles/PMC10262593/)).
- For **cfDNA**, depth and library complexity matter more because **tumor fraction** can be very low in early disease. “Enough depth” is inseparable from tumor fraction, duplex/UMI design, and feature aggregation — not a single magic number copied from buffy coat.

**Practical rule for this repo**

- Buffy-only classifier: invest in **feature selection, cell-type awareness, and MC stability**, not automatically in deeper sequencing past a solid WGBS depth.
- cfDNA / MCED-oriented work: invest in **preanalytics, fragmentomics QC, tumor-fraction–aware design**, and analyte-matched training (`model_training_analyte` / plasma retrain path).
- Depth does **not** convert buffy coat into tumor DNA.

---

## Recommended study designs on this pipeline

1. **Buffy-first development** — `primary_analyte: buffy_coat`, MC stability + freeze on leukocyte cohorts; use for host markers and operational learning with abundant DNA.
2. **Plasma / cfDNA production path** — `primary_analyte: cfdna`, fragmentomics on, enforce training analyte match; see [`packages/methylvalidation/docs/PLASMA_RETRAIN_PATH.md`](../../packages/methylvalidation/docs/PLASMA_RETRAIN_PATH.md).
3. **Paired complementary layers** — same subjects (or matched cohorts) with separate study manifests (or `combined` where appropriate): buffy host-risk score + cfDNA tumor/burden layer. Compare with the analyte-comparison rubric (MC gene recurrence, cross-analyte concordance, discovery direction agreement).
4. **Do not** assume a buffy-trained panel transfers to plasma without retrain and analyte-match validation.

Empirical prostate buffy vs plasma MC comparison (marginal separation on one rubric; shared gene core) lives in the canvas and on-disk under `/work/projects/prostate-cancer/analyte_comparison/` when present — use it as **assay-development evidence**, not a clinical performance claim.

---

## Bottom line

- **cfDNA** is the better *direct* analyte for tumor detection and localization when logistics allow.
- **Buffy coat** remains a first-class MethylPipeline analyte for host/systemic signal, logistics, and complementary scoring.
- The pipeline already accepts both; choose via `regulatory.primary_analyte` and profiles, then validate with MC + hold-out under the matching analyte — not by chasing depth alone on leukocytes.

---

## Related

- [`docs/ANALYTE_PROFILES.md`](../ANALYTE_PROFILES.md) — analyte defaults and study examples
- [`docs/implementation/sample-preparation-flow.md`](../implementation/sample-preparation-flow.md) — shared prep + cfDNA fragmentomics QC
- [`docs/canvas/analyte-comparison.canvas.tsx`](../canvas/analyte-comparison.canvas.tsx) — buffy vs plasma MC comparison explorer
- [`docs/research/Gemini_on_Cancer_Detection.md`](Gemini_on_Cancer_Detection.md) — broader MCED landscape notes
