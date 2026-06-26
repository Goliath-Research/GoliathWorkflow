# Workflow Diagram Pack: `Healthy_vs_PCa1-4-CG`

This pack uses your project configuration at `/work/projects/prostate-cancer/configs/project_Healthy_vs_PCa1-4-CG.json` and separates:

- **External preprocessing** (Parabricks alignment and methyl extraction)
- **MethylPipeline-native stages** (AlignmentQC onward, MC/stability/freeze/model/predictor)

## Legend

- **External**: not orchestrated/implemented by MethylPipeline codebase, but upstream-required.
- **Optional**: branch controlled by config/flags.
- **Primary artifacts**: most relevant outputs for each stage.
- **Cohort mapping used here**:
  - Control: `all`
  - Disease leaves: `pca_pca1`, `pca_pca2`, `pca_pca3`, `pca_pca4`

---

## 1) Raw WGBS -> per-chromosome methylation HDF5

Orchestrated by **SamplePrepPipeline** ([`workflow_engine/sql/SamplePrepFlow.md`](../workflow_engine/sql/SamplePrepFlow.md), source: [`sample_prep.program.json`](../workflow_engine/domain/fixtures/sample_prep.program.json)). Two QC gates: **alignment** (`methyl-qc`, optional fastp remediation) then **extraction** (`methyl-extraction-qc`). Fragmentomics is conditional on `primary_analyte: cfdna`.

```mermaid
flowchart TD
  fastq[RawWgbsFastq] --> dl["External: download FASTQs"]
  dl --> pb_fq2bam["External: Parabricks fq2bam"]
  pb_fq2bam --> bam[BamCramOutputs]
  pb_fq2bam --> dedup_metrics[PicardStyleDedupMetricsTxt]
  pb_fq2bam --> parabricks_metrics[ParabricksMetricsJson]
  pb_fq2bam --> delFq["External: delete FASTQs"]

  dedup_metrics --> methyl_qc["MethylAlignmentQC (methyl-qc)"]
  parabricks_metrics --> methyl_qc
  methyl_qc --> qc_json[alignment_qc/sample.json]
  methyl_qc --> gate{guardrails.overall_pass?}

  gate -->|fail| failSample[mark sample QC failed]
  gate -->|pass| cfdnaCheck{primary_analyte cfdna?}
  cfdnaCheck -->|yes| fragomics["methyl-fragmentomics (BAM WPS + end motifs)"]
  cfdnaCheck -->|no| methyl_extractor["External MethylExtractor / MethylDackel fork"]
  fragomics --> methyl_extractor
  bam --> fragomics
  bam --> methyl_extractor
  methyl_extractor --> h5_samples["PerSamplePerChromFiles: {chrom}-{context}.h5"]
  methyl_extractor --> delBam["External: delete BAM"]
```

**Primary outputs**
- Alignment QC JSONs: `.../alignment_qc/<sample>.json` (or sample-dir sidecar from methyl-qc)
- cfDNA fragmentomics (when enabled): `{project}/fragmentomics/{sample_id}/`
- Per-sample methylation files consumed downstream: `{chrom}-{context}.h5` (for this project, context is `CG`)

---

## 2) Search for a stable set of DMPs

```mermaid
flowchart TD
  mc_config[ValidationConfig train_fraction n_iterations seed] --> mc_loop["MonteCarloRuns run_0001..run_N"]
  cohorts[ResolvedCohorts all pca_pca1..pca_pca4] --> mc_loop

  mc_loop --> centroid[MethylCentroid]
  centroid --> detector["MethylDetector discovery mode"]
  detector --> dmp_exports["dmps-*-discovery.csv and dmps-*-classifier.csv"]
  detector --> detector_results["results-*.json"]

  dmp_exports --> stability["MethylValidation StabilityAnalysis"]
  detector_results --> stability
  predictor_metrics["Optional predictors/*/validation_metrics.json"] --> stability

  stability --> stable_panel[stable_dmps_production.csv]
  stability --> stability_summary[stability_summary.json]
  stability --> dmp_freq[dmp_frequency.csv]
  stability --> gene_freq["optional gene_frequency.csv"]
```

**Primary outputs**
- `.../monte_carlo_runs/stability/stable_dmps_production.csv`
- `.../monte_carlo_runs/stability/stability_summary.json`

---

## 3) Frozen DMP panel analysis chain (Mapper/Enricher/Classifier/Progression/Predictor)

```mermaid
flowchart TD
  stable_panel_in[stable_dmps_production.csv] --> freeze["methyl-validation --freeze"]
  freeze --> production_project[production/project.json with fixed_dmp_panel]
  freeze --> stable_genomewide[production/stable_dmps_genomewide.csv]

  production_project --> prod_centroid[MethylCentroid production]
  prod_centroid --> prod_detector["MethylDetector fixed panel"]
  prod_detector --> prod_dmps[production detections dmps exports]

  prod_dmps --> mapper[MethylMapper]
  mapper --> mapper_outputs["mapper/*/all-gene_name-combined.csv"]
  mapper_outputs --> enricher[MethylEnricher]
  enricher --> enricher_outputs["enrichment_merged.csv modules_ranked.csv"]

  enricher_outputs --> progression_opt["Optional MethylProgression"]
  progression_opt --> progression_outputs["progression/*.csv summary.json report.md"]

  production_project --> model_backend["methyl-validation --model backend"]
  model_backend --> ecdf_path["ecdf: MethylClassifier -> MethylPredictor"]
  model_backend --> tabular_path["tabular_sklearn: bundle -> train -> predictor"]
  model_backend --> generative_path["generative_hybrid: bundle -> train -> predictor"]
  ecdf_path --> model_outputs[production/classifiers and production/predictors]
  tabular_path --> model_outputs
  generative_path --> model_outputs
```

**Primary outputs**
- Frozen project: `.../monte_carlo_runs/production/project.json`
- Biology analysis: mapper/enricher/progression outputs
- Model artifacts: `.../monte_carlo_runs/production/classifiers/` and `.../production/predictors/`

### Stage-2 disease feature families (all model backends)

When `feature_mode` is `observed_hybrid`, backend training can now use a unified second-stage feature contract:

- **DMP-derived summaries** (global/quantiles + disease-comparison aggregates)
- **DMR/region aggregates** (from explicit region metadata or fallback genomic windows)
- **Gene aggregates** (when DMP rows contain gene annotations)
- **Chromosome aggregates** (optional; still supported but no longer the only aggregate family)

For model-evaluation runs, backend predictor outputs now also include `feature_family_ablation.json`, which records active feature families and a recommended ablation matrix (`baseline`, `+DMP`, `+DMR`, `+gene`, `all`) to structure balanced-accuracy comparisons.

---

## 4) Search for the best model

```mermaid
flowchart TD
  model_mc_start["methyl-validation --model-mc-all"] --> backend_fanout[BackendRuns ecdf tabular_sklearn generative_hybrid]
  backend_fanout --> backend_metrics[PerRunMetrics validation_metrics.json]
  backend_metrics --> aggregate[AggregateMetrics all_metrics.csv metrics_summary.json]
  aggregate --> distributions[metrics_distributions_plotly.html]
  aggregate --> ranking["backend_ranking.csv and backend_ranking.json"]
  ranking --> select_best["methyl-validation --select-best-model"]
  select_best --> selected_backend[production/selected_backend.json]
  selected_backend --> final_model_build[RebuildProductionModelWithWinner]
```

**Selection controls**
- Metric: typically `balanced_accuracy`
- Statistic: typically `median`

---

## 5) Monte Carlo quality metric distributions (BA and others)

```mermaid
flowchart TD
  mc_runs[MonteCarloRunOutputs] --> metric_ingest[ValidatorMetricsLoader]
  metric_ingest --> primary_metrics["balanced_accuracy accuracy macro_f1"]
  metric_ingest --> calibration_metrics["nll brier_score ece"]
  metric_ingest --> class_metrics["sensitivity specificity precision recall"]

  primary_metrics --> schema_norm[MetricsSchemaNormalization]
  calibration_metrics --> schema_norm
  class_metrics --> schema_norm

  schema_norm --> summary_stats["metrics_summary.json percentiles mean median std"]
  schema_norm --> all_rows[all_metrics.csv]
  schema_norm --> plots[metrics_distributions_plotly.html]
```

**What this gives**
- Distribution-aware confidence in model quality, not just single-point BA.

---

## 6) Final model -> prediction of blind newly arrived samples

```mermaid
flowchart TD
  final_model[production/classifiers selected backend] --> predictor_blind["methyl-predictor blind mode"]
  blind_inputs[NewBlindSamplePaths] --> predictor_blind
  project_predictor_cfg["step_config.predictor blind or test_blind_paths"] --> predictor_blind

  predictor_blind --> blind_report[predictors/blind/prediction_report.json]
  predictor_blind --> sample_scores[PerSampleProbabilities and PredictedSubgroup]
  sample_scores --> triage["ClinicalResearchTriage and Review"]
```

**Primary outputs**
- `.../predictors/blind/prediction_report.json`
- Per-sample subgroup probabilities and predicted classes

---

## Project-specific path map (as used by diagrams)

- Base output: `/work/projects/prostate-cancer/Healthy_vs_PCa1-4-CG/`
- Monte Carlo runs: `/work/projects/prostate-cancer/Healthy_vs_PCa1-4-CG/monte_carlo_runs/`
- Production freeze/model root: `/work/projects/prostate-cancer/Healthy_vs_PCa1-4-CG/monte_carlo_runs/production/`

