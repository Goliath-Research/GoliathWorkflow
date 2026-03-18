# MethylPipeline

MethylPipeline is a project-driven methylation analysis monorepo built around four core steps:

1. `MethylCentroid` builds cohort centroids from sample HDF5 directories.
2. `MethylDetector` finds DMPs and packages ECDF-based classifiers.
3. `MethylClassifier` scores new samples with those classifiers.
4. `MethylPredictor` and `MethylValidation` turn those predictions into holdout metrics and Monte Carlo summaries.

Downstream packages add interpretation and operations support: `MethylMapper`, `MethylEnricher`, `MethylAlignmentQC`, and `MethylCluster`.

## Core Model

The active pipeline is **ECDF-based** end to end.

- `MethylDetector` compares centroids with KS-on-ECDF or Mann-Whitney-from-bin-counts, then applies Storey q-values on the pre-filtered locus set.
- `MethylClassifier` uses per-position ECDF/PCHIP PDFs, weighted mean log-likelihoods, and temperature-scaled posteriors.
- Directory / multi-chromosome classifiers combine per-chromosome probabilities with chromosome weights.

This repository no longer treats Beta/BMM classifiers as the canonical workflow.

## Canonical Workflow

Use one project JSON with `controls`, `diseases`, `comparisons`, and `step_config`. All project-aware tools derive inputs and outputs from that file.

Typical run order:

```bash
# 1) Build centroids for every resolved group
methyl-centroid --project configs/project_PCa_vs_Healthy.json --group all

# 2) Detect DMPs and package classifier outputs
methyl-detector --project configs/project_PCa_vs_Healthy.json

# 3) Map DMPs to genes / features
methyl-mapper --project configs/project_PCa_vs_Healthy.json

# 4) Functional enrichment
methyl-enricher --project configs/project_PCa_vs_Healthy.json

# 5) Score labeled or unlabeled samples
methyl-classifier --project configs/project_PCa_vs_Healthy.json
methyl-predictor --project configs/project_PCa_vs_Healthy.json

# 6) Monte Carlo validation
methyl-validation --config configs/monte_carlo.json
```

Notes:

- For control/disease projects with multiple comparisons, detector, mapper, enricher, classifier, and predictor use comparison-specific output directories automatically.
- `methyl-validation` is driven by its own validation config. That config points at a `base_project`; the CLI does **not** take `--project`.
- Keep API keys out of tracked project JSON. Use environment variables or per-run override files instead.

## Project Layout

For a project named `MyStudy` with `output_base=/data/out`, the canonical root is:

```text
/data/out/MyStudy/
├── centroids/
│   ├── controls/<control-side-label>/<group>/
│   └── diseases/<disease-side-label>/<group>/
├── detections/<control_group>/<disease_group>/
├── mapper/<control_group>/<disease_group>/
├── enricher/<control_group>/<disease_group>/
├── classifiers/<control_group>/<disease_group>/
├── predictors/<control_group>/<disease_group>/
├── alignment_qc/
└── clustering/
```

Flat `group1` / `group2` projects still load, but `controls` / `diseases` / `comparisons` is the supported schema.

## Installation

### Host install

```bash
bash scripts/setup_host.sh --system-deps --gpu
```

Common variants:

- CPU-only: omit `--gpu`
- Custom virtualenv: add `--venv /path/to/venv`
- Pre-existing conda / RAPIDS workflow: use `scripts/setup_host_conda.sh`
- Verify the environment: `bash scripts/verify_setup.sh`

If you already manage Python and system dependencies yourself, `scripts/install_all.sh --pipeline-reqs [--gpu-reqs]` installs the local packages into the active environment.

### Docker / containers

- Development container scripts live under `scripts/`
- Production image definition lives in `docker/Dockerfile.production`

The production container installs the same canonical CLI surface as the host setup.

## Main CLIs

Project-aware commands:

- `methyl-centroid`
- `methyl-detector`
- `methyl-mapper`
- `methyl-enricher`
- `methyl-classifier`
- `methyl-predictor`
- `methyl-qc` / `methyl-alignment-qc`

Related tools:

- `methyl-centroid-explorer`
- `methyl-detector-explorer`
- `methyl-cluster`
- `methyl-validation`

## Packages

The repository ships these primary packages:

- `methylutils`: shared config, I/O, ECDF classifier, statistical utilities
- `methylcentroid`: centroid building
- `methyldetector`: DMP detection and classifier packaging
- `methylclassifier`: sample classification
- `methylpredictor`: holdout metrics from classifier predictions
- `methylvalidation`: Monte Carlo / repeated split validation
- `methylmapper`: DMP-to-gene mapping and optional disease enrichment
- `methylenricher`: enrichment on mapped gene sets
- `methylalignmentqc`: alignment QC parsing
- `methylcluster`: sample clustering and pre-centroid subgroup discovery

## Documentation

Start here:

- [Operations manual](docs/OPERATIONS_MANUAL.md)
- [Unified project config guide](docs/UNIFIED_PROJECT_CONFIG_GUIDE.md)
- [Config examples](configs/README.md)
- [Theory and packages](docs/THEORY_AND_PACKAGES.md)

Package-specific docs:

- [MethylCentroid](packages/methylcentroid/README.md)
- [MethylDetector](packages/methyldetector/README.md)
- [MethylClassifier](packages/methylclassifier/README.md)
- [MethylPredictor](packages/methylpredictor/README.md)
- [MethylValidation](packages/methylvalidation/README.md)
- [MethylMapper](packages/methylmapper/README.md)
- [MethylEnricher](packages/methylenricher/README.md)
- [MethylAlignmentQC](packages/methylalignmentqc/README.md)
- [MethylCluster](packages/methylcluster/README.md)

## Repository Layout

```text
MethylPipeline/
├── packages/
├── configs/
├── docs/
├── docker/
├── scripts/
├── requirements-pipeline.txt
├── requirements-gpu.txt
└── README.md
```

## License

MIT. See `LICENSE`.
