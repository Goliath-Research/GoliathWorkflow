# MethylPipeline

MethylPipeline is a monorepo for DNA methylation analysis. Its core supervised path is built around empirical distributions rather than a single parametric family, but the repository as a whole also includes clustering, mapping, enrichment, and QC packages that use additional statistical machinery, heuristics, and external services.

## Package Overview

The pipeline is organized into focused packages that share `methylutils` where appropriate:

- **`methylutils`**: shared mathematical layer for centroid summaries, ECDF views, testing, overlap, and classification scores.
- **`methylcentroid`**: builds cohort centroids with sufficient statistics and histogram summaries.
- **`methyldetector`**: performs locus-wise differential methylation screening and exports classifier-ready DMP sets.
- **`methylclassifier`**: applies ECDF-based binary, multi-chromosome, and OvR classification logic.
- **`methylpredictor`**: runs trained classifiers on holdout or blind cohorts and reports prediction metrics.
- **`methylvalidation`**: performs repeated split-sample validation of the full pipeline.
- **`methylcluster`**: exploratory clustering utilities over methylation samples and derived distances.
- **`methylmapper`**: maps DMPs to genes and genomic features, then aggregates gene-level evidence.
- **`methylenricher`**: performs downstream enrichment, pathway graph clustering, and module ranking.
- **`methylalignmentqc`**: parses and normalizes alignment QC metrics from external tools.

## Documentation Structure

MethylPipeline now has two documentation layers:

1. **Canonical theory book**: [`docs/theory/README.md`](docs/theory/README.md) and the Quarto sources under `docs/theory/`. This is the publication-grade mathematical and statistical reference for the repository, written from the code as the source of truth.
2. **Package-local docs**: each package keeps `README.md`, `docs/THEORY.md`, `docs/IMPLEMENTATION.md`, and `docs/USAGE.md` as local entry points. The local `THEORY.md` files are concise summaries that defer to the canonical theory book.

## Source Of Truth

For theory, the source of truth is the code. The documentation explicitly distinguishes among:

- principled statistical or numerical methods,
- approximations,
- heuristics, and
- external-service-backed steps.

That distinction matters because the core centroid-detector-classifier path is ECDF-centered, while downstream packages also use beta-based clustering, p-value aggregation, graph heuristics, and external knowledge services.

## Deployment

For details on how to deploy this repository on supported platforms via virtual environments or containers, see [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

### Virtual environment

From the repository root, activate the canonical environment before running `pytest`, `pip`, or any `methyl-*` CLI:

```bash
source .venv/bin/activate
pytest
```

If `.venv` does not exist yet, create it as described in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md). You can also run the full test suite without manually activating using [`scripts/run_tests.sh`](scripts/run_tests.sh), which invokes `.venv/bin/python -m pytest` directly.
