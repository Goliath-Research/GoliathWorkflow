# MethylPipeline Operations Manual

This manual describes how to **run** the pipeline (users) and how to **extend and develop** it (developers). For theoretical foundations and package-level math, see [Theory and packages](THEORY_AND_PACKAGES.md).

---

## Table of Contents

1. [For users](#for-users)
   - [Installation](#installation)
   - [Project configuration](#project-configuration)
   - [Workflow order and data flow](#workflow-order-and-data-flow)
   - [CLI reference](#cli-reference)
   - [Key config fields per step](#key-config-fields-per-step)
   - [Inputs and outputs](#inputs-and-outputs)
   - [Troubleshooting](#troubleshooting)
   - [Rendering and printing documentation](#rendering-and-printing-documentation)
2. [For developers](#for-developers)
   - [Repository layout](#repository-layout)
   - [Adding or changing a pipeline step](#adding-or-changing-a-pipeline-step)
   - [Config schema and validation](#config-schema-and-validation)
   - [Testing](#testing)
   - [Logging and debugging](#logging-and-debugging)
   - [Documentation conventions](#documentation-conventions)

---

## For users

### Installation

- **Docker (recommended):** Build and start the dev container (see [README](../README.md#option-1-docker-recommended)). Use `scripts/setup_dev.sh`; then `docker exec -it methylpipeline bash`.
- **Host (non-Docker):** From repo root, run `bash scripts/setup_host.sh --system-deps --gpu`. Omit `--gpu` for CPU-only. Use `--venv /path/to/venv` to control the virtualenv. See [README_ENV.md](../README_ENV.md) and [ENV_SETUP.md](../ENV_SETUP.md) if you use conda or a custom env.

All pipeline CLIs: `methyl-centroid`, `methyl-centroid-explorer`, `methyl-detector`, `methyl-detector-explorer`, `methyl-mapper`, `methyl-enricher`, `methyl-classifier`, `methyl-predictor`, `methyl-validation`, `methyl-qc` / `methyl-alignment-qc`. Ensure the MethylPipeline packages are installed (e.g. `pip install -e .` in each package or use the repo-level setup script).

### Project configuration

Use a **single project JSON** with `--project` so each tool derives paths and sample lists from one place.

- **Project root:** `{output_base}/{project_name}`
- **Centroids:** `{project_root}/centroids/{group1.label}`, `{project_root}/centroids/{group2.label}`, etc.
- **Detection:** `{project_root}/detection`
- **Mapper:** `{project_root}/mapper`
- **Enricher:** `{project_root}/enricher`
- **Classifier:** `{project_root}/classifier`
- **Alignment QC:** `{project_root}/alignment_qc`

Main project fields:

| Field | Description |
|-------|-------------|
| `project_name` | Project identifier. |
| `output_base` | Global output directory; step outputs live under `{output_base}/{project_name}`. |
| `group1` / `group2` (or more) | Each has `label` (used in centroid subdir names) and `sample_paths`. |
| `sample_paths` | List of sample directories or path to a file (one path per line or JSON array). |
| `chromosomes` | Optional; shared chromosome list for centroid/detector. |
| `contexts` | Optional; e.g. `["CG"]`. |
| `path_remap` | Optional; prefix replacement when sample paths move (e.g. NAS). |
| `step_config` | Optional; per-step defaults (see [Key config fields per step](#key-config-fields-per-step)). |

**Resolution order:** Project shared + derived paths → `step_config[step]` → `--step-override` file / CLI. So you can set defaults in the project and override per run with `--step-override step.json` or CLI flags.

See [configs/README.md](../configs/README.md) for an example project JSON and `step_config` layout.

### Workflow order and data flow

Run steps in this order:

| Step | Tool | Input | Output |
|------|------|--------|--------|
| 1 | Centroid (per group) | Sample dirs from project | `{project_root}/centroids/{group.label}/` (HDF5 per chrom/context) |
| 1b (optional) | MethylCentroid Explorer | Centroid H5 paths | Report/CSV for centroid build options |
| 2 | MethylDetector | Centroid dirs (group1, group2, …) from project | `{project_root}/detection/` (DMP CSVs, classifier PKL, results JSON) |
| 2b (optional) | MethylDetector Explorer | Centroid H5 paths | Report/CSV for refinement and effect-size options |
| 3 | MethylMapper | DMP CSVs from detection | `{project_root}/mapper/` (gene/feature CSVs, optional disease enrichment) |
| 4 | MethylEnricher | Mapper combined gene CSV | `{project_root}/enricher/` (enrichment results) |
| 5 | MethylClassifier | Model from detection + centroid dirs from project | `{project_root}/classifier/` (e.g. results CSV) |
| 6 | MethylPredictor | Classifier + test samples | Classification metrics |
| 7 | MethylValidation | Project + validation config (e.g. Monte Carlo) | Runs centroid, detector, classifier, predictor per run |
| 0 (optional) | MethylAlignmentQC | Sample dirs from project | `{project_root}/alignment_qc/` (one JSON per sample) |

Classifier can be run whenever detection and centroid dirs are ready; it does not depend on mapper or enricher. Mapper reads DMP CSVs (e.g. `dmps-*-optimized.csv`) from detection. Centroid HDF5 files use only the `methylation_data` group (with optional `bins` attr and `bin_counts` dataset for binned stats); no separate `binned_stats` group.

### CLI reference

All commands support `--project PATH` (and where noted, `--step-override PATH`). Optional `-v` / `--verbose` is common.

| Command | Required (with --project) | Key options |
|---------|----------------------------|-------------|
| **methyl-centroid** | `--project`, `--group` (group1, group2, all, or 0-based index) | `--step-override`, `--use-gpu` / `--no-gpu` |
| **methyl-centroid-explorer** | Centroid H5 paths or `--centroid1` / `--centroid2` | Explore centroid build options; see package README. |
| **methyl-detector** | `--project` *or* CONFIG path (not both) | `--step-override`, `--verbose`, `--log-file` |
| **methyl-detector-explorer** | `--centroid1-dir`, `--centroid2-dir` (or `--centroid1`/`--centroid2`) | `--approx-overlap` (auto/discrete/normal), `--min-N`, `--sample-fraction`; see [METHYLDETECTOR_EXPLORER](../packages/methyldetector/docs/METHYLDETECTOR_EXPLORER.md). |
| **methyl-mapper** | `--project` (bedtools flow) or config + input/output | `--step-override`, mapper-specific (e.g. `--gtf`, env `GROK_API_KEY`) |
| **methyl-enricher** | `--project` or input + `--outdir` | `--step-override`, `--gene-column`, `--disease-only`, etc. |
| **methyl-classifier** | Config or `--model-dir` + `--input` + `--output` | See package README for full CLI. |
| **methyl-predictor** | Config or model + test input | Run classifier on test sets and compute metrics. |
| **methyl-validation** | `--config` (validation config), `--project` | Runs centroid, detector, classifier, predictor per run (e.g. Monte Carlo, stratified splits). |
| **methyl-qc** / **methyl-alignment-qc** | `--project` or `--samples` + `--output-dir` | `--step-override`, `--no-validation` |

Example (project-based):

```bash
methyl-centroid --project configs/project_PCa_vs_Healthy.json --group group1
methyl-centroid --project configs/project_PCa_vs_Healthy.json --group group2
methyl-detector --project configs/project_PCa_vs_Healthy.json
methyl-mapper --project configs/project_PCa_vs_Healthy.json
methyl-enricher --project configs/project_PCa_vs_Healthy.json
methyl-classifier --project configs/project_PCa_vs_Healthy.json
methyl-qc --project configs/project_PCa_vs_Healthy.json
```

For full option lists, see each package’s README and comprehensive documentation.

### Key config fields per step

- **Centroid:** `min_coverage`, `use_gpu`, `binned_stats_bins` (optional; e.g. 20 for ECDF/Explorer); batch options (e.g. `parallel_combinations`) when using batch config.
- **Detection:** `chromosomes`, `contexts`, `fdr_threshold` (or `min_pvalue`), `min_delta_mean`, `max_overlap`, `min_effect_size`, `target_balanced_accuracy`, `validation_mode`, `output_dir` (usually derived from project). Explorer: `approx_overlap` (auto/discrete/normal), `min_N`, `min_N_pct`, `sample_fraction`.
- **Mapper:** `csv_filename_pattern` (e.g. `dmps-*.csv`), `gtf`, `disease_term`, `enrich_*`; set `grok_api_key` via env or step-override.
- **Enricher:** `gene_column`, `libraries`, `disease_only`, `output_dir`.
- **Classifier:** `model_path` or `model_dir`, `input`, `output_path`; multi-chromosome and calibration options (see MethylClassifier docs).
- **Alignment QC:** `sample_paths`, `output_dir` (derived from project when using `--project`).

Full schemas live in each package (e.g. Pydantic models in `*_detector/models/config.py`, `*_classifier/models/config.py`). Use `step_config` in the project JSON to set defaults; override with `--step-override` or CLI.

### Inputs and outputs

| Step | Reads | Writes |
|------|--------|--------|
| Centroid | Sample dirs (HDF5 per sample), project or batch config | `centroids/{label}/*.h5` (methylation_data group only; optional `bins` attr + `bin_counts` for binned stats) |
| Detector | Centroid dirs (HDF5 with methylation_data; centroids used for DMP/ECDF must have binned stats: `bins` + `bin_counts`), project or detector config | `detection/dmps-*.csv`, `detection/classifier-*.pkl`, `detection/results-*.json` |
| Mapper | `detection/dmps-*.csv` (pattern from config), GTF | `mapper/` (gene/feature CSVs, combined CSV) |
| Enricher | Mapper combined CSV or gene list (TXT/CSV) | `enricher/` (per-library and merged results) |
| Classifier | Detection model (PKL), centroid dirs, sample dirs or methylation matrix | CSV/TSV of predictions and probabilities |
| Alignment QC | Sample dirs or metrics root | `alignment_qc/{sample_basename}.json` |

File naming: Detection uses patterns like `dmps-{chromosome}-{context}-3-optimized.csv`; mapper and enricher use configurable names. See package docs for exact patterns.

### Troubleshooting

- **GPU not detected:** Run `nvidia-smi`; install CuPy for your CUDA version; check `from methyl_utils import is_gpu_available; print(is_gpu_available())`.
- **Out of memory:** Reduce batch size or chromosome parallelism; use `cleanup_gpu_memory()` (MethylUtils); or set `use_gpu: false` in config.
- **No DMPs found:** Relax `fdr_threshold` (e.g. 0.05), lower `min_delta_mean` or `min_effect_size`; ensure centroid dirs and chromosomes/contexts match.
- **Path / file not found:** Use `path_remap` in the project JSON if sample or output paths have moved; check `output_base` and `project_name`.
- **Mapper/Enricher:** Ensure GTF path and (if used) `GROK_API_KEY` or other API keys are set (env or `--step-override`).

See individual package documentation (e.g. MethylDetector, MethylClassifier) for step-specific troubleshooting.

### Rendering and printing documentation

- **Formulas:** All theory and package docs use LaTeX in Markdown: block math with `$$ ... $$`, inline with `$ ... $`. The MkDocs site renders them via MathJax (see [mkdocs.yml](../mkdocs.yml) and `docs/javascripts/mathjax_config.js`).
- **Print to PDF (browser):** Open the desired page (e.g. [Theory and packages](THEORY_AND_PACKAGES.md), this manual), use the browser’s Print dialog, and choose “Save as PDF”. Formulas will appear as rendered math if the site was built with the math extension.
- **Building PDFs from Markdown (optional):** You can use tools such as `md-to-pdf` or Pandoc to convert `docs/THEORY_AND_PACKAGES.md` and `docs/OPERATIONS_MANUAL.md` to PDF while preserving LaTeX (e.g. Pandoc with `--mathjax` or `-t pdf` and a LaTeX engine). For a single-page printable manual, the browser “Print to PDF” from the built MkDocs site is usually sufficient.

---

## For developers

### Repository layout

- **Monorepo:** All packages live under `packages/`: `methylutils`, `methylcentroid`, `methylcluster`, `methyldetector`, `methylclassifier`, `methylmapper`, `methylenricher`, `methylalignmentqc`, `methylpredictor`, `methylvalidation`.
- **Shared config:** Repo-level project configs live under `configs/` (e.g. `project_PCa_vs_Healthy.json`). Per-package examples and configs live in `packages/<name>/configs/` or `packages/<name>/examples/`.
- **Docs:** Pipeline-level docs in `docs/` (this manual, THEORY_AND_PACKAGES, ARCHITECTURE, DEVELOPMENT, PRODUCTION). Package-level docs in `packages/<name>/docs/` and `packages/<name>/README.md`.

### Adding or changing a pipeline step

- **Config flow:** When using `--project`, the project JSON is loaded; then for each step a resolver (e.g. `resolve_detector_config`, `resolve_centroid_batch_config`) builds the step’s config from project paths + `step_config[step]` + optional `--step-override` file. CLI flags (e.g. `--use-gpu`) override last.
- **Adding a new step:** Implement a CLI (e.g. `methyl-mystep`) that accepts `--project` and optionally `--step-override`. Add a project resolver that reads `output_base`, `project_name`, and `step_config.mystep`, and writes outputs under `{project_root}/mystep/`. Register the step in docs and (if desired) in any orchestration or examples.
- **New `methyl-*` command:** Each package typically has an entry point in `pyproject.toml` (e.g. `methyl-detector = methyl_detector.cli.main:main`). Add a similar entry for your package and ensure it’s installed when the pipeline is installed.

### Config schema and validation

- **Schemas:** Pydantic models in each package define config (e.g. `packages/methyldetector/methyl_detector/models/config.py`, `packages/methylclassifier/methyl_classifier/models/config.py`). Validation runs when loading JSON or building config from project.
- **Extending `step_config`:** Add a key under `step_config` in the project JSON (e.g. `step_config.mystep`) and merge it in your step’s resolver. Use the same field names as the package’s config model so that the merged object validates.

### Testing

- **From repo root:** `pytest packages/` (or `pytest packages/methylutils packages/methyldetector ...` for a subset). Test discovery uses `test_*.py` and `*_test.py` under `packages/*/tests` (see root `pyproject.toml`).
- **Markers:** Use `@pytest.mark.slow`, `@pytest.mark.gpu`, `@pytest.mark.integration` for tests that are slow, require GPU, or are integration tests. Run with `-m "not slow"` to skip slow tests.
- **Single package:** `cd packages/methyldetector && pytest tests/ -v`.

See [DEVELOPMENT.md](DEVELOPMENT.md) for more on testing and code quality.

### Logging and debugging

- **Log level:** Many CLIs support `-v` / `--verbose` for DEBUG. Set `log_level` in config when supported (e.g. classifier).
- **Detector log file:** `methyl-detector --log-file path/to/detector.log ...` writes detailed logs to the file while keeping a summary on stdout.
- **Errors:** Check stack traces in the terminal; for GPU issues, check CuPy/CUDA errors and `methyl_utils` GPU helpers. Package comprehensive docs often have a “Troubleshooting” section.

### Documentation conventions

- **Theory and math:** Use LaTeX in Markdown: `$$ ... $$` for display, `$ ... $` for inline. This allows the MkDocs site and PDF/print to render formulas consistently.
- **Where to add content:** New pipeline-level theory or workflow text → `docs/THEORY_AND_PACKAGES.md` or `docs/OPERATIONS_MANUAL.md`. Package-specific theory → `packages/<name>/docs/` (e.g. `METHYL*_COMPREHENSIVE_DOCUMENTATION.md`). Update [mkdocs.yml](../mkdocs.yml) nav if you add new top-level docs.
- **API docs:** Generate with Sphinx from a package (e.g. `packages/methylutils`); see [docs/README.md](README.md#building-api-documentation) if configured.
