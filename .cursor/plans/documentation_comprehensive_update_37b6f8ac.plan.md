---
name: Documentation comprehensive update
overview: "After a full audit of the codebase, update all pipeline and package documentation so it reflects the current implementation: correct package and CLI inventory, current data formats (e.g. binned stats in methylation_data only), and removal or relegation of deprecated or exploratory options. Documentation is spread across root docs/, package docs/, READMEs, and operational/theoretical guides."
todos: []
isProject: false
---

# Comprehensive documentation update plan

## Scope

- **In scope**: Root and pipeline-level docs; every package’s README and `docs/`; configs README; key standalone guides (QUICKSTART, INSTALLATION, USAGE, etc.). Goal: one coherent, up-to-date story.
- **Out of scope**: `.cursor/plans/` (design history; only mine them for “current” decisions to reflect in main docs). Test-only READMEs (e.g. `CONTAINER_USAGE.md`) can be touched lightly. PR templates and devcontainer troubleshooting stay as-is unless they reference deprecated behavior.

## Current state (from codebase analysis)

- **11 packages** under `packages/`: methylutils (plus nested `methyl_utils`), methylcentroid, methyldetector, methylclassifier, methylcluster, methylmapper, methylenricher, methylalignmentqc, methylvalidation, methylpredictor.
- **Root README** lists “8 packages” in the architecture section; later it mentions methyl-predictor and methyl-validation as steps 7–8. **Decision**: Either list all 10 user-facing packages (excluding nested methyl_utils) in architecture with one line each, or keep “8” and add a short “Additional tools” for methyl-validation and methyl-predictor. Recommend: **list 10** and group by role (foundation, analysis, interpretation, validation/QC) so the count matches reality.
- **CLIs**: Explorer and deploy CLIs exist (`methyl-detector-explorer`, `methyl-centroid-explorer`, `methyl-utils-deploy`, etc.) but are not fully reflected in [docs/OPERATIONS_MANUAL.md](docs/OPERATIONS_MANUAL.md) CLI table or [README.md](README.md) workflow. Centroid/detector Explorer docs live in [packages/methyldetector/docs/METHYLDETECTOR_EXPLORER.md](packages/methyldetector/docs/METHYLDETECTOR_EXPLORER.md) and package READMEs.
- **Data model**: Binned stats are now **methylation_data only** (bins attr + bin_counts dataset; no `binned_stats` group, no stored bin_edges). This is already reflected in MethylUtils/MethylDetector Explorer docs from the recent schema change; ensure **all** docs that mention H5 layout or binned_stats (e.g. [METHYLSAMPLE_CLASS_HIERARCHY.md](packages/methylutils/docs/METHYLSAMPLE_CLASS_HIERARCHY.md), [MethylUtils_Theoretical_Foundation.md](packages/methylutils/docs/MethylUtils_Theoretical_Foundation.md), [OPERATIONS_MANUAL](docs/OPERATIONS_MANUAL.md), [THEORY_AND_PACKAGES](docs/THEORY_AND_PACKAGES.md)) are consistent.
- **Theory vs implementation**: Pipeline uses **ECDF-only** for centroid comparison and DMP detection (no Beta in the comparison path); Explorer has **approx-overlap** options (auto / discrete / normal) and **min-N** filters. Docs that still describe “multiple distribution options” or old Explorer behavior should be updated to the current, chosen approach and the rest relegated to “historical/alternative” or removed.

## Audit and update order

Work in three phases so pipeline-level docs stay aligned with package docs.

### Phase 1: Pipeline-level and root

1. **[README.md](README.md)**
  - Align package list with actual 10 packages; add Explorer CLIs where relevant (e.g. “MethylDetector Explorer” under MethylModeler).  
  - Ensure workflow table and “Complete Workflow” match OPERATIONS_MANUAL and current CLIs (methyl-centroid, methyl-detector, methyl-detector-explorer, methyl-mapper, methyl-enricher, methyl-classifier, methyl-predictor, methyl-validation, methyl-qc).  
  - Fix any dead or outdated links; ensure “Key Components” and data model bullets match current MethylUtils (e.g. single centroid type, binned stats in methylation_data).
2. **[docs/README.md](docs/README.md)**
  - Keep as index; add links to Explorer docs and to methyl-validation / methyl-predictor if they are not already there.  
  - Ensure “8 packages” wording is updated to match README (e.g. “10 packages” or “8 core + 2 validation/predictor”).
3. **[docs/index.md](docs/index.md)**
  - Same package list and quick links as docs/README; add Explorer and validation/predictor if missing.
4. **[docs/OPERATIONS_MANUAL.md](docs/OPERATIONS_MANUAL.md)**
  - **CLI reference**: Add `methyl-detector-explorer`, `methyl-centroid-explorer`; add `methyl-predictor`, `methyl-validation` with one-line purpose and key flags.  
  - **Workflow table**: Include Explorer as an optional step (e.g. “1b” or “Explorer”) and steps 7–8 for predictor/validation.  
  - **Config fields**: Align with current project JSON (e.g. [configs/project_Healthy_vs_PCa1-4.json](configs/project_Healthy_vs_PCa1-4.json)) and any step_config used by Explorer (e.g. binned_stats_bins, approx_overlap).  
  - **Inputs/outputs**: Mention centroid H5 layout (methylation_data only, bins + bin_counts) where it matters for “inputs to detector” or troubleshooting.
5. **[docs/UNIFIED_PROJECT_CONFIG.md](docs/UNIFIED_PROJECT_CONFIG.md)** and **[docs/UNIFIED_PROJECT_CONFIG_GUIDE.md](docs/UNIFIED_PROJECT_CONFIG_GUIDE.md)**
  - Ensure hierarchy and step order match OPERATIONS_MANUAL; add Explorer output dir or note if applicable; add validation/predictor config if they use project config.
6. **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**
  - Component list and data flow: 10 packages, Explorer tools, and “single data-driven centroid + ECDF” as the chosen model; remove or shorten deprecated alternatives.
7. **[docs/THEORY_AND_PACKAGES.md](docs/THEORY_AND_PACKAGES.md)**
  - Align with implementation: ECDF-only comparison; centroid H5 = methylation_data with bins + bin_counts; Explorer (approx overlap, min-N). Trim or move to appendix any “optional” distribution or detection paths that are no longer in use.
8. **[docs/METHYLPIPELINE_COMPREHENSIVE_DOCUMENTATION.md](docs/METHYLPIPELINE_COMPREHENSIVE_DOCUMENTATION.md)**
  - Full pass: package list, workflow, CLI list, and data model consistent with the above; remove obsolete options.
9. **[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)**
  - Same package and workflow alignment; fix links.
10. **[configs/README.md](configs/README.md)**
  - Example project and step_config; mention Explorer-related or validation-related keys if they exist in current configs.

### Phase 2: Foundation packages (MethylUtils, MethylCentroid)

1. **MethylUtils**
  - [packages/methylutils/README.md](packages/methylutils/README.md): Data structures and CLIs (methyl-utils, chrom-mapping, deploy); link to Explorer when it uses MethylUtils.  
    - [packages/methylutils/docs/](packages/methylutils/docs/): [METHYLSAMPLE_CLASS_HIERARCHY.md](packages/methylutils/docs/METHYLSAMPLE_CLASS_HIERARCHY.md), [MethylUtils_Theoretical_Foundation.md](packages/methylutils/docs/MethylUtils_Theoretical_Foundation.md), [METHYLUTILS_IMPLEMENTATION.md](packages/methylutils/docs/METHYLUTILS_IMPLEMENTATION.md), [METHYLUTILS_COMPREHENSIVE_DOCUMENTATION.md](packages/methylutils/docs/METHYLUTILS_COMPREHENSIVE_DOCUMENTATION.md): H5 layout = methylation_data only (bins + bin_counts); single centroid type; ECDF-only comparison; `close()` for samples.  
    - [packages/methylutils/MethylUtils.md](packages/methylutils/MethylUtils.md), USAGE.md, INSTALL.md: Align with current CLI and install path.
2. **MethylCentroid**
  - [packages/methylcentroid/README.md](packages/methylcentroid/README.md): CLI(s) (methyl-centroid, methyl-centroid-explorer if present), config, output H5 layout (bins + bin_counts in methylation_data).  
    - [packages/methylcentroid/docs/](packages/methylcentroid/docs/): Comprehensive, implementation, and theoretical foundation: extended centroid only; binned stats schema; memory/close behavior.  
    - [packages/methylcentroid/scripts/README_GPU_MEMORY_MANAGEMENT.md](packages/methylcentroid/scripts/README_GPU_MEMORY_MANAGEMENT.md): Keep consistent with current cleanup/close usage.

### Phase 3: Analysis and interpretation packages

1. **MethylDetector**
  - [packages/methyldetector/README.md](packages/methyldetector/README.md): methyl-detector and methyl-detector-explorer; inputs (centroids with binned stats in methylation_data).  
    - [packages/methyldetector/docs/](packages/methyldetector/docs/): [METHYLDETECTOR_EXPLORER.md](packages/methyldetector/docs/METHYLDETECTOR_EXPLORER.md) (already updated for bins/bin_counts); [METHYLDETECTOR_IMPLEMENTATION.md](packages/methyldetector/docs/METHYLDETECTOR_IMPLEMENTATION.md), [MethylDetector_Theoretical_Foundation.md](packages/methyldetector/docs/MethylDetector_Theoretical_Foundation.md), [METHYLMODELER_COMPREHENSIVE_DOCUMENTATION.md](packages/methyldetector/docs/METHYLMODELER_COMPREHENSIVE_DOCUMENTATION.md): ECDF, Explorer options (approx-overlap, min-N), centroid requirements.  
    - QUICKSTART.md, USAGE.md, EXPORT_*.md, CONTEXT_SELECTION_GUIDE.md: Align with current CLI and workflow.
2. **MethylClassifier**
  - README and docs: Current CLI (methyl-classifier), config, and model inputs; remove or shorten deprecated options.
3. **MethylCluster**
  - README and docs: Current CLI and behavior; align with single centroid type and MethylUtils APIs.
4. **MethylMapper**
  - README, QUICK_START, INSTALLATION, BEDTOOLS_MAPPER_README, MethylMapper_DMP_to_genes_flow: Preferred bedtools flow and optional Grok/Open Targets; legacy Azure SQL as secondary.
5. **MethylEnricher**
  - README, INSTALLATION, MethylEnricher_after_MethylMapper: Inputs from MethylMapper; current CLI.
6. **MethylAlignmentQC**
  - README: CLI (methyl-qc / methyl-alignment-qc), role in pipeline.
7. **MethylValidation and MethylPredictor**
  - READMEs and docs: Describe as pipeline steps 7–8; current CLI and config (e.g. validation config, project config); link from OPERATIONS_MANUAL and root README.

### Phase 4: Cross-checks and cleanup

1. **Link and reference pass**
  - All “see also” and “comprehensive guide” links point to existing files.  
    - All CLI names and flags in tables match the code (pyproject.toml / entry points).  
    - One pass over THEORY_AND_PACKAGES, OPERATIONS_MANUAL, and ARCHITECTURE for consistent terminology (e.g. “methylation_data only”, “bins + bin_counts”, “ECDF-only”).
2. **Deprecated/exploratory content**
  - In each package: either remove mentions of old binned_stats group, multiple centroid types, or deprecated CLI options, or add a short “Historical notes” subsection and point to current behavior as default.
3. **.cursor/plans**
  - Do not edit plan files. Use them only as a source of “what was decided” (e.g. binned_stats_schema_simplification, explorer_approx_overlap, single_data_driven_centroid) and ensure those decisions are reflected in the main docs above.

## Deliverables

- **Updated files**: Root README, docs/README, docs/index, OPERATIONS_MANUAL, UNIFIED_PROJECT_CONFIG*, ARCHITECTURE, THEORY_AND_PACKAGES, METHYLPIPELINE_COMPREHENSIVE_DOCUMENTATION, PROJECT_OVERVIEW, configs/README; each package’s README and its docs/*.md (and key top-level .md) so that:
  - Package and CLI lists are accurate (10 packages, all CLIs including Explorer and validation/predictor).
  - Data model and H5 layout are consistent (methylation_data only; bins + bin_counts).
  - Workflow order and config fields match current code and configs.
  - Theory and implementation describe the chosen approach (ECDF-only, Explorer options) and relegate or drop deprecated options.
- **No structural change**: No new doc files or renames unless you explicitly add a short “Documentation index” or “Changelog” section in an existing file; focus on content updates and link fixes.

## Execution note

Implement phase-by-phase; after Phase 1, root and pipeline docs are consistent so package authors can align their READMEs and docs in Phases 2–3. Run a quick link check (e.g. grep for `](path)` and verify paths exist) and spot-check CLI names against `pyproject.toml` scripts in each package.