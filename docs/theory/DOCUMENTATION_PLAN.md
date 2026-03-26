# MethylPipeline Documentation Plan

**Date:** 2026-03-25  
**Scope:** Restructure the Quarto theory book into four parts covering mathematical foundations, workflows, configuration reference, and user guide.

---

## Motivation

The existing Quarto book at `docs/theory/` documents the mathematical and statistical foundations well (chapters 01–10), but it does not cover:

- The two main operational workflows (Model Creation and Model Use for Prediction)
- The `step_config.validation` embedded configuration pattern
- The `--freeze` flag and production freeze path
- The `fixed_dmp_panel` mechanism that bypasses DMP discovery
- The `min_sample_coverage` vs centroid `min_coverage` diagnostic
- The `multiclass_learned_class_weight` parameter for class imbalance
- A complete, exhaustive `step_config` configuration reference
- An end-to-end user guide

This plan extends the book into four clearly partitioned parts.

---

## New Book Structure

```
docs/theory/
├── _quarto.yml                    UPDATE — add parts + new chapters
├── index.qmd                      minor update — add parts overview paragraph
├── references.bib                 (unchanged)
└── chapters/
    ├── 01-methylutils.qmd         (unchanged — complete)
    ├── 02-methylcentroid.qmd      (unchanged — complete)
    ├── 03-methyldetector.qmd      UPDATE — add §fixed_dmp_panel + §min_sample_coverage
    ├── 04-methylclassifier.qmd    UPDATE — add §multiclass_learned_head_class_weighting
    ├── 05-methylpredictor-and-validation.qmd   UPDATE — add §stability_analysis, §production_freeze, §two_workflows
    ├── 06-methylcluster.qmd       (unchanged)
    ├── 07-methylmapper.qmd        (unchanged)
    ├── 08-methylenricher.qmd      (unchanged)
    ├── 09-methylalignmentqc.qmd   (unchanged)
    ├── 10-limitations-and-open-questions.qmd  (unchanged)
    ├── 11-project-configuration.qmd  NEW — anatomy of project.json
    ├── 12-two-workflows.qmd          NEW — full workflow guide with theory
    ├── 13-configuration-reference.qmd  NEW — exhaustive step_config tables
    └── 14-user-guide.qmd              NEW — end-to-end commands + diagnostics

packages/methylvalidation/docs/USAGE.md     REPLACE — with complete version
```

---

## Part Structure (`_quarto.yml`)

```yaml
book:
  title: "MethylPipeline: Theory, Workflows, and Reference"
  chapters:
    - index.qmd
    - part: "Part I: Mathematical and Statistical Foundations"
      chapters:
        - chapters/01-methylutils.qmd
        - chapters/02-methylcentroid.qmd
        - chapters/03-methyldetector.qmd
        - chapters/04-methylclassifier.qmd
        - chapters/05-methylpredictor-and-validation.qmd
        - chapters/06-methylcluster.qmd
        - chapters/07-methylmapper.qmd
        - chapters/08-methylenricher.qmd
        - chapters/09-methylalignmentqc.qmd
        - chapters/10-limitations-and-open-questions.qmd
    - part: "Part II: Workflows and Production"
      chapters:
        - chapters/11-project-configuration.qmd
        - chapters/12-two-workflows.qmd
    - part: "Part III: Configuration Reference"
      chapters:
        - chapters/13-configuration-reference.qmd
    - part: "Part IV: User Guide"
      chapters:
        - chapters/14-user-guide.qmd
```

---

## Chapter Content Outlines

### Chapter 03 Updates (`03-methyldetector.qmd`)

Add two new sections after the existing "Publication Guidance" section:

**§ Production Freeze Panel (`fixed_dmp_panel`)**
- Explains the bypass path in `MethylDetector._run_multi_context()`
- CSV requirements: must contain `chromosome` and `position` columns
- How the result is constructed (all counts reported as n_dmps; retention rate = 1.0)
- Cross-reference to Workflow 1 in chapter 12

**§ DMP Coverage in New Samples (`min_sample_coverage`)**
- Documents the mismatch risk: DMP positions discovered at centroid `min_coverage` threshold may be absent in test samples when `min_sample_coverage` is set higher
- The critical diagnostic: `sample_dmp_coverage.dmps_used_fraction_median < 0.5` indicates this mismatch
- Recommendation: align `min_sample_coverage` with centroid `min_coverage`

---

### Chapter 04 Updates (`04-methylclassifier.qmd`)

Add one new section after "Calibration":

**§ Multiclass Learned Head: Class Weighting**
- Explains that the multinomial logistic regression (`NativeMulticlassLearnedClassifier`) accepts `class_weight`
- Formula: `w_k = n_total / (K * n_k)` when `class_weight="balanced"`
- Documents that `sklearn_version` is saved in the model PKL metadata for reproducibility
- Cross-reference to `multiclass_learned_class_weight` in chapter 13

---

### Chapter 05 Updates (`05-methylpredictor-and-validation.qmd`)

Add three new sections after "Publication Guidance":

**§ Stability Analysis**
- Formal definition of DMP recurrence frequency:
  `f_hat(d) = (1/R*) * sum_r 1[d in D_disc_r]`
  where R* = qualifying runs (those with BA >= threshold if set)
- Threshold τ to define a "stable" panel
- Gene stability analogue

**§ Production Freeze**
- The `--freeze` path: stable panel → `fixed_dmp_panel` in project → single full-data pipeline run
- How `freeze_production_model()` in `stability.py` works
- Predictor-only MC for post-freeze evaluation

**§ Two Workflows Summary**
- Brief summary of Workflow 1 (Model Creation) and Workflow 2 (Prediction)
- Mermaid diagram
- Cross-reference to chapter 12 for full detail

---

### Chapter 11 (NEW): Project Configuration File

Sections:
1. The single source of truth principle
2. Top-level keys: `project_name`, `output_base`, `samples_base_path`, `chromosomes`, `contexts`, `comparisons`
3. The `controls`/`diseases` hierarchy and cohort structure
4. The `step_config` dictionary as per-step override hub
5. The `step_config.validation` pattern for embedded MC settings
6. Annotated example using `project_Healthy_vs_PCa1-4-CG.json`
7. Design rules: no duplication, single source of truth

---

### Chapter 12 (NEW): The Two Workflows

Sections:
1. Overview and when to use each workflow
2. Workflow 1: Model Creation
   - Theory: why repeated splits → stability → full-data model
   - The `--stability` flag: MC iterations + DMP frequency aggregation
   - The `--freeze` flag: stable panel → production run with `fixed_dmp_panel`
   - Commands and expected outputs
   - Mermaid diagram
3. Workflow 2: Model Use for Prediction
   - Theory: evaluating the frozen model on held-out data
   - The `--predictor-only` flag
   - Commands and expected outputs
   - Mermaid diagram
4. Diagnostic: DMP coverage
5. Diagnostic: Class imbalance
6. Diagnostic: sklearn version mismatch

---

### Chapter 13 (NEW): Configuration Reference

One section per step_config key, each as a reference table with:
- Parameter, Type, Default, Constraints, Description

Sections:
1. `step_config.centroid` (base_config + batch wrapper fields)
2. `step_config.detection` (runtime MethylDetectorConfig fields)
3. `step_config.detection` (multiclass export-only fields)
4. `step_config.mapper`
5. `step_config.enricher`
6. `step_config.classifier`
7. `step_config.predictor`
8. `step_config.validation`
9. `step_config.cluster`
10. `step_config.alignment_qc`

Cross-references to theory chapters for each parameter group.

---

### Chapter 14 (NEW): User Guide

Sections:
1. Prerequisites and environment setup
2. Creating a project configuration file
3. Adding `step_config.validation` for MC settings
4. Running Workflow 1 (Model Creation)
5. Running Workflow 2 (Prediction)
6. Output directory layout under `monte_carlo_runs/`
7. Interpreting results (metrics, confusion matrix, DMP coverage)
8. Three key diagnostics:
   - Low DMP coverage → `min_sample_coverage` alignment
   - Class imbalance → `multiclass_learned_class_weight: "balanced"`
   - sklearn version mismatch → `sklearn_version` in model metadata
9. Running individual pipeline steps
10. Troubleshooting

---

## Files Changed Summary

| File | Action | Approx. lines |
|------|--------|--------------|
| `docs/theory/DOCUMENTATION_PLAN.md` | CREATE (this file) | 150 |
| `docs/theory/_quarto.yml` | UPDATE | 60 |
| `docs/theory/index.qmd` | minor UPDATE | +20 |
| `docs/theory/chapters/03-methyldetector.qmd` | UPDATE | +80 |
| `docs/theory/chapters/04-methylclassifier.qmd` | UPDATE | +40 |
| `docs/theory/chapters/05-methylpredictor-and-validation.qmd` | UPDATE | +120 |
| `docs/theory/chapters/11-project-configuration.qmd` | CREATE | 200 |
| `docs/theory/chapters/12-two-workflows.qmd` | CREATE | 350 |
| `docs/theory/chapters/13-configuration-reference.qmd` | CREATE | 600 |
| `docs/theory/chapters/14-user-guide.qmd` | CREATE | 350 |
| `packages/methylvalidation/docs/USAGE.md` | REPLACE | 300 |
