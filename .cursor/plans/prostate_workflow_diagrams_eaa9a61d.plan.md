---
name: Prostate Workflow Diagrams
overview: Create a diagram pack tailored to your project config that covers six workflows from raw WGBS preprocessing through Monte Carlo, model selection, and blind prediction, while clearly separating external versus in-repo steps.
todos:
  - id: map-project-topology
    content: Extract cohort and output layout from project_Healthy_vs_PCa1-4-CG for diagram labels and path annotations.
    status: pending
  - id: draft-upstream-diagram
    content: Draft diagram 1 with external preprocessing boundary and in-repo AlignmentQC/guardrail integration points.
    status: pending
  - id: draft-dmp-stability-diagrams
    content: Draft diagrams 2 and 5 for stable DMP search and MC metric distributions with key artifacts.
    status: pending
  - id: draft-freeze-model-diagrams
    content: Draft diagrams 3 and 4 covering freeze analysis chain and best-model selection workflow.
    status: pending
  - id: draft-blind-prediction-diagram
    content: Draft diagram 6 for final-model blind inference and outputs.
    status: pending
  - id: polish-diagram-pack
    content: Apply consistent notation/legend and produce a presentation-ready markdown diagram pack.
    status: pending
isProject: false
---

# Workflow Diagram Pack for `project_Healthy_vs_PCa1-4-CG`

## Scope and framing
- Produce six polished workflow diagrams using repository-accurate stage names and artifact paths.
- Explicitly mark **external preprocessing** (Parabricks/BAM/MethylExtractor) versus **MethylPipeline-native** stages (AlignmentQC onward).
- Use your project’s hierarchical cohorts (`all`, `pca_pca1..pca_pca4`) and Monte Carlo/freeze/model conventions.

## Diagram set to produce

### 1) Raw WGBS to per-chromosome methylation HDF5
- Show: FASTQ -> Parabricks `fq2bam` -> BAM + dedup metrics -> `methyl-qc` JSON -> optional WGBS guardrails -> external methylation extraction -> `{chrom}-{context}.h5` sample directories.
- Annotate that Parabricks alignment + MethylExtractor are outside this repo’s implementation boundary.
- Key references:
  - [/home/ubuntu/MethylPipeline/packages/methylalignmentqc/methyl_alignment_qc/utils/monitor.py](/home/ubuntu/MethylPipeline/packages/methylalignmentqc/methyl_alignment_qc/utils/monitor.py)
  - [/home/ubuntu/MethylPipeline/packages/methylalignmentqc/methyl_alignment_qc/core/parser.py](/home/ubuntu/MethylPipeline/packages/methylalignmentqc/methyl_alignment_qc/core/parser.py)
  - [/home/ubuntu/MethylPipeline/packages/methylalignmentqc/methyl_alignment_qc/core/wgbs_parabricks_qc.py](/home/ubuntu/MethylPipeline/packages/methylalignmentqc/methyl_alignment_qc/core/wgbs_parabricks_qc.py)
  - [/home/ubuntu/MethylPipeline/packages/methylcentroid/methyl_centroid/core/sample_manager.py](/home/ubuntu/MethylPipeline/packages/methylcentroid/methyl_centroid/core/sample_manager.py)

### 2) Search for stable DMPs
- Show MC iteration loop: centroid -> detector discovery outputs -> optional predictor metrics ingestion -> stability aggregation -> `stable_dmps_production.csv`.
- Include BA-gated stability option and main outputs (`stability_summary.json`, frequency tables).
- Key references:
  - [/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/pipeline_runner.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/pipeline_runner.py)
  - [/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py)

### 3) Frozen DMP panel analysis (Mapper/Enricher/Classifier/Progression/Predictor)
- Show freeze production chain with fixed panel injection into detector.
- Include optional MethylProgression branch and model-backend branch (`ecdf`, `tabular_sklearn`, `generative_hybrid`) to predictor outputs.
- Key references:
  - [/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py)
  - [/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/trainer_api.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/trainer_api.py)
  - [/home/ubuntu/MethylPipeline/packages/methyldiseaseprogression/methyl_disease_progression/progression.py](/home/ubuntu/MethylPipeline/packages/methyldiseaseprogression/methyl_disease_progression/progression.py)

### 4) Search for the best model
- Show `--model-mc` backend fan-out, metric collection, ranking (`selection_metric`, `selection_stat`), and promotion to `production/selected_backend.json`.
- Include optional shared detector runs and resulting artifacts (`backend_ranking.csv`, distribution plots).
- Key references:
  - [/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/cli.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/cli.py)

### 5) Monte Carlo quality-metric distributions
- Show metric sources (`validation_metrics.json`, nested training/holdout blocks), normalization schema, aggregation to summary and distribution plots.
- Highlight BA plus macro-F1, NLL, Brier, ECE.
- Key references:
  - [/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/validator_metrics.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/validator_metrics.py)

### 6) Final model for blind samples
- Show post-selection frozen model usage path in `methyl-predictor` blind mode (`predictors/blind/`), with separation from MC evaluation.
- Include model artifact dependency and expected blind outputs (`prediction_report.json`, per-sample probabilities/subgroups).
- Key references:
  - [/home/ubuntu/MethylPipeline/packages/methylpredictor/methyl_predictor/project_resolver.py](/home/ubuntu/MethylPipeline/packages/methylpredictor/methyl_predictor/project_resolver.py)
  - [/home/ubuntu/MethylPipeline/packages/methylpredictor/methyl_predictor/core/predictor.py](/home/ubuntu/MethylPipeline/packages/methylpredictor/methyl_predictor/core/predictor.py)

## Deliverable format
- A compact “diagram pack” markdown document with:
  - six mermaid flowcharts,
  - one short legend section (external vs in-repo, optional branches, primary artifacts),
  - brief per-diagram notes to make it presentation-ready for customers.

## Project-specific mapping to preserve
- Cohort hierarchy from your config: control `all`; disease leaves `pca_pca1`, `pca_pca2`, `pca_pca3`, `pca_pca4`.
- Freeze/model paths centered under `.../monte_carlo_runs/production/`.
- MC outputs under `.../monte_carlo_runs/run_*/` and stability/model_mc subtrees.