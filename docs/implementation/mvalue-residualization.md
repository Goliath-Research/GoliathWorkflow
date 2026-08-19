# M-value residualization — Implementation

> Theory: [ch.02 optional residualization](../theory/chapters/02-methylcentroid.md#sec-centroid-mvalue-residual) · [ch.12 pre-MC covariates](../theory/chapters/12-two-workflows.md#sec-pre-mc-covariates) | Usage: [ch.24 procedure row](../usage/24-methylation-application-packs.md) | Research note: [Buffy M-value residualization](../research/buffy-mvalue-residualization.md) (exploratory; not product truth)

Opt-in assay procedure `buffy_wgbs_mvalue_residual_gene_fc` plus forked programs `mc_stability_residual` and `study_validation_lifecycle_residual`. Still DNA methylation WGBS — not a new omics process pack. Shipped packs and `buffy_wgbs_pangenome_gene_fc` keep the unadjusted DMP path. Do not enable residualization from `primary_analyte: buffy_coat`.

## Role in pipeline

Label-free confounder scores and Houseman/HiTIMED Ω run **once** on the residual fork. Train-only OLS residualizes M-values against those covariates inside each Monte Carlo split and again at freeze. Centroids, DMPs, and `gene_importance` then see \(\beta_{\mathrm{adj}}\in(0,1)\). The `gene_importance` formula is unchanged; it reports confounder-adjusted host-response.

## Entry points (CLI, worker action)

| Entry | Purpose |
|-------|---------|
| `pipeline.methylation_confounder_scores` / `methyl-confounder-scores` | Label-free smoking / age / BMI / CRP scores |
| `pipeline.residualize_fit` / `methyl-residualize-fit` | Train-only \(M\sim Z\) coefficients (no Group term) |
| `methyl-residualize-sensitivity` | Unadjusted vs residualized DMP Jaccard and `gene_importance` Spearman |
| `pipeline.centroid` / classifier | Apply frozen coefficients iff `residualizeCoefDir` is bound |

## Key modules

| Module | Role |
|--------|------|
| [`methyl_utils/confounder_scores.py`](../../packages/methylutils/methyl_utils/confounder_scores.py) | Panel JSON load; `intercept + Σ w_i β_i`; coverage status |
| [`methyl_utils/mvalue_residualize.py`](../../packages/methylutils/methyl_utils/mvalue_residualize.py) | M-value round-trip; apply frozen \(\hat\gamma\) |
| [`methyl_utils/residualize_fit.py`](../../packages/methylutils/methyl_utils/residualize_fit.py) | Train-only OLS; Neu-referenced ALR for Ω |
| [`methyl_utils/residualize_config.py`](../../packages/methylutils/methyl_utils/residualize_config.py) | Typed `actionConfig.residualize` and `methylation_confounder_scores` |
| [`methyl_utils/data/confounder_panels/`](../../packages/methylutils/methyl_utils/data/confounder_panels/) | Versioned GRCh38 panel JSON |

Rebuild Hannum coordinates with the **dev-time** script [`methyl_utils/scripts/build_hannum2013_panel.py`](../../packages/methylutils/methyl_utils/scripts/build_hannum2013_panel.py). Workers must not download the Zhou manifest.

## Upstream / downstream artifacts

| Reads | Writes |
|-------|--------|
| Sample `{chrom}-CG.h5`; `cell_fractions.csv`; panel JSON | `confounder_scores.csv` + `.manifest.json` |
| Train sample IDs + covariate CSVs | `production/residualize/residualize-{chrom}-{ctx}.npz` + `residualize_manifest.json` |

Default procedure bindings: [`buffy_wgbs_mvalue_residual_gene_fc.procedure.json`](../../workflow_engine/domain/profiles/procedures/buffy_wgbs_mvalue_residual_gene_fc.procedure.json).

## Shared scoring contract {#sec-scoring-contract}

Every packaged methylation score is

\[
\text{score} = \text{intercept} + \sum_i w_i\,\beta_i
\]

on observed panel CpGs with coverage ≥ `min_coverage`. `score_kind` is `weighted_beta` for all shipped panels (Hannum included). Sample-level `score_status` is `ok` / `partial` / `insufficient_markers` when the observed-site fraction drops below `min_sites_fraction` (procedure default `0.5`). Knobs live in `actionConfig.methylation_confounder_scores` with Pydantic `default=None` — no Python science defaults.

Missing or low-coverage panel CpGs do not invent clinical BMI, smoking status, or chronological age.

## Smoking {#sec-smoking}

Packaged panel: [`smoking_ahr_v1.json`](../../packages/methylutils/methyl_utils/data/confounder_panels/smoking_ahr_v1.json) → column `smoking_score`.

AHRR `cg05575921` (weight −1) plus a small Joehanes / Zeilinger-style set: F2RL3, ALPPL2, IER3, GFI1. Coordinates are GRCh38. Operators may replace the JSON; the action does not use questionnaire smoking labels.

## Epigenetic age {#sec-epigenetic-age}

Packaged panel: [`hannum2013_v1.json`](../../packages/methylutils/methyl_utils/data/confounder_panels/hannum2013_v1.json) → column `age_score`.

**Selected default: Hannum 2013 (71 CpGs).** Purpose is a label-free covariate that tracks age-related methylation so OLS can residualize it out of DMP calling. It is **not** a product DNAmAge and must not be reported as biological age.

| Option | Sites | Tissue | Formula | Fit for this purpose |
|--------|-------|--------|---------|----------------------|
| Weidner 2014 | 3 | Blood | Linear | Too coarse |
| **Hannum 2013 (shipped)** | **71** | **Whole blood** | **Linear weighted betas** | **Good enough; matches the scorer** |
| Horvath 2013 | 353 | Pan-tissue | Linear predictor + anti-transform | More complex; worse tissue match |
| Horvath 2018 Skin & Blood | ~391 | Blood/skin | Linear + extra terms | More precise; more licensing/size |
| PhenoAge | 513 | Blood | Phenotypic age | Wrong target (mortality, not chronological confounder) |

Hannum was trained on whole-blood 450k. Whole-blood array DNA is almost entirely leukocyte nuclear DNA (red cells are anucleate). Buffy coat is that same leukocyte pellet, so applying a whole-blood clock to buffy is standard EWAS practice. Cell-mix residualization is a **separate** covariate (Ω ALR below); Hannum is not asked to double as a composition score.

The packaged file is Table S3 `CoefficientTraining` (same 71 methylation markers used by methylclock / pyaging / cgageR), intercept 0, GRCh38 via Zhou lab HM450.hg38.manifest (1-based). Array-trained weights applied to WGBS betas at the same CpGs; low coverage yields `partial` / `insufficient_markers`.

Operators may overlay a different clock with `actionConfig.methylation_confounder_scores.age_clock_path`. The scorer does not implement Horvath’s anti-transform. `horvath2013_stub_v1.json` is a one-site **test fixture only**.

## BMI / adiposity {#sec-bmi}

Packaged panel: [`bmi_adiposity_v1.json`](../../packages/methylutils/methyl_utils/data/confounder_panels/bmi_adiposity_v1.json) → column `bmi_score`.

Small replicated set with equal placeholder weights: HIF3A `cg22891070`, ABCG1 `cg06500161`, CPT1A `cg00574958`. Citation also names SREBF1 / PHGDH as related loci; they are not in this JSON. Operators should replace weights from Wahl / Mendelson meta-analyses. The score is not measured BMI.

## Inflammation / CRP {#sec-inflammation}

Packaged panel: [`crp_inflammation_v1.json`](../../packages/methylutils/methyl_utils/data/confounder_panels/crp_inflammation_v1.json) → column `crp_score`.

Focused CRP/inflammation neighbourhood: NLRC5 `cg08122652`, AIM2 `cg17501210`, equal placeholder weights. Replace with Wielscher et al. *Nat Commun* 2022 elastic-net weights for production. The score is not a serum CRP assay.

## Leukocyte mix Ω {#sec-omega}

Not a panel JSON. Procedure `residualize.composition_columns` reads Houseman / HiTIMED fractions from `{output_base}/cell_fractions/cell_fractions.csv` (`CD8T`, `CD4T`, `NK`, `Bcell`, `Mono`, `Neu`), encodes them as Neu-referenced ALR with `composition_pseudocount`, and residualizes those coordinates together with the numeric scores.

Procedure default **includes Ω**. Operators who want composition-mediated DMPs omit `composition_columns` and keep the ECDF second-stage ALR stack.

**Causal caveat:** if cancer → inflammation → Ω → methylation, residualizing Ω removes part of the buffy cancer signal from the DMP list.

## Isolation and leakage

Isolation, train-only OLS, Monte Carlo refit, and freeze-time inference live in the [research note](../research/buffy-mvalue-residualization.md). Math for the M-value round-trip is locked in [theory ch.02](../theory/chapters/02-methylcentroid.md#sec-centroid-mvalue-residual).
