# Project Overview

MethylPipeline is a monorepo for methylation-centric analysis, modeling, and downstream interpretation.

## Core Chain

```text
samples -> centroids -> detections -> classifier bundles -> predictions
```

Optional side branches:

- detections -> mapper -> enricher
- samples -> alignment_qc
- samples -> clustering
- predictor -> validation summaries

## Main Packages

- `methylutils`: shared utilities and project contract
- `methylcentroid`: centroid generation
- `methyldetector`: DMP detection and classifier packaging
- `methylclassifier`: sample classification
- `methylpredictor`: metrics on holdout samples
- `methylvalidation`: Monte Carlo validation
- `methylmapper`: DMP-to-gene mapping
- `methylenricher`: enrichment
- `methylalignmentqc`: alignment QC parsing
- `methylcluster`: optional subgroup clustering

## Start Here

- `README.md`: repository overview and install entry points
- `docs/OPERATIONS_MANUAL.md`: supported workflow and developer contract
- `docs/UNIFIED_PROJECT_CONFIG_GUIDE.md`: project JSON schema
- `docs/THEORY_AND_PACKAGES.md`: theory map and package responsibilities
- `docs/ARCHITECTURE.md`: repository architecture

## Canonical Workflow

```bash
methyl-centroid --project project.json --group all
methyl-detector --project project.json
methyl-mapper --project project.json
methyl-enricher --project project.json
methyl-classifier --project project.json
methyl-predictor --project project.json
```

Validation is separate:

```bash
methyl-validation --config monte_carlo.json
```
