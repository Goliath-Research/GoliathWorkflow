# MethylPipeline

MethylPipeline is a Python monorepo for DNA methylation analysis.  
The active production path is code-driven and centered on empirical distribution workflows:

1. centroid construction (`methylcentroid`)
2. DMP discovery and panel generation (`methyldetector`)
3. classification (`methylclassifier`)
4. prediction and metrics (`methylpredictor`)
5. Monte Carlo validation and production orchestration (`methylvalidation`)

This document is the canonical root guide and is written from repository code/config as source of truth.

## Theoretical Foundations

Core methods implemented in the active path:

- **ECDF/PCHIP likelihood modeling** in `packages/methylutils/methyl_utils/ecdf_classifier.py`
- **Hypothesis testing and correction** in `packages/methylutils/methyl_utils/statistical_tests.py`:
  - KS ECDF statistics
  - Mann-Whitney from histogram counts
  - Storey q-values and p-value aggregation methods
- **Biological effect ranking and overlap metrics** in `packages/methyldetector/methyl_detector/core/methyldetector.py`
- **OvR and multiclass fusion, isotonic calibration, chromosome weighting** in `packages/methylclassifier/methyl_classifier/core/classifier.py`
- **Prediction metrics and probabilistic diagnostics** in `packages/methylpredictor/methyl_predictor/core/predictor.py`

Method categories are intentionally separated in implementation and documentation:

- principled statistical methods
- approximations
- heuristics
- external-service-backed analysis

## Implementation

## Active package roles

- `methylutils`: shared mathematical/statistical/config foundation.
- `methylcentroid`: cohort centroid generation and binned summaries.
- `methyldetector`: DMP detection, effect-size filtering, export logic.
- `methylclassifier`: binary/multiclass/OvR model logic and calibration.
- `methylpredictor`: inference + reporting + evaluation metrics.
- `methylvalidation`: MC orchestration, stability, freeze/model flows, backend selection.
- `methylmapper`: DMP-to-gene and feature mapping.
- `methylenricher`: enrichment and module-level interpretation.
- `methyldiseaseprogression`: cross-stage synthesis reports.
- `methylalignmentqc`: alignment QC extraction/normalization.

## CLI entry points

CLI contracts are defined in package `pyproject.toml` files:

- `methyl-centroid`, `methyl-centroid-explorer`
- `methyl-detector`, `methyl-detector-explorer`
- `methyl-classifier`
- `methyl-predictor`
- `methyl-validation`
- `methyl-mapper`
- `methyl-enricher`
- `methyl-disease-progression`
- `methyl-alignment-qc`, `methyl-qc`

## Usage

## Installation

This repo expects the local virtual environment at `.venv`.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Install package stack (editable/develop mode) via:

```bash
bash scripts/install_all.sh
```

Optional dependency layers:

- `--pipeline-reqs` installs `requirements-pipeline.txt`
- `--gpu-reqs` installs `requirements-gpu.txt`

Container setup is available via:

```bash
bash scripts/setup_dev.sh
```

## Upgrades

When upgrading dependencies or package code:

1. activate `.venv`
2. rerun `scripts/install_all.sh` (same package order as production scripts)
3. rerun tests:

```bash
bash scripts/run_tests.sh
```

## Full project execution

Active production path (code-backed in `methyl_validation`):

1. run Monte Carlo iterations
2. run stability analysis to materialize stable DMP panel
3. run freeze (`--freeze`) to generate `production/project.json` with `fixed_dmp_panel`
4. run model build (`--model`)
5. optionally run post-model validation (`--post-model-validation`) or predictor-only evaluation

Typical command sequence:

```bash
source .venv/bin/activate
methyl-validation --project project.json --stability
methyl-validation --project project.json --freeze
methyl-validation --project project.json --model
```

## Step-by-step execution boundaries

Implemented pipeline boundaries in `packages/methylvalidation/methyl_validation/pipeline_runner.py`:

- MC iteration mode: `methyl-centroid` -> `methyl-detector`
- Freeze mode: `methyl-centroid` -> `methyl-detector` -> `methyl-mapper` -> `methyl-enricher` (+ optional progression)
- Model mode: `methyl-classifier` -> `methyl-predictor`
- Predictor-only mode: `methyl-predictor` using frozen production artifacts

## Strategy Playbooks

## 1) Initial research

- run baseline MC validation to characterize data behavior
- inspect detector exports and stability summaries
- establish candidate panel quality before freeze/model stages

## 2) Disease characterization

- use detector q-value/effect-size outputs for locus-level evidence
- run mapper + enricher during freeze for biological interpretation
- optionally run progression synthesis for stage-ordered interpretation

## 3) Model creation

- stabilize panel through MC + stability outputs
- freeze with `fixed_dmp_panel`
- build production model with `--model`
- use `--model-mc` and `--select-best-model` for backend comparisons when required

## 4) Final prediction from best model

- run predictor on holdout/blind cohorts with frozen artifacts
- track balanced accuracy, class-wise metrics, and probabilistic diagnostics
- use rollout comparison gates for baseline-vs-candidate promotion decisions

## Deprecated Appendix: MethylCluster

`MethylCluster` is excluded from the active workflow documented above.

- legacy package/CLI may remain in the repository for compatibility (`methyl-cluster`)
- do not treat clustering outputs as part of the canonical production path
- historical references should stay isolated to deprecated/legacy notes, not main workflow sections

## Additional references

- Theory book: `docs/theory/README.md`
- Deployment details: `docs/DEPLOYMENT.md`
- Active parameter contract matrix: `docs/config_parameter_matrix.md`
- Code-first discovery basis: `docs/code_first_discovery_report.md`
