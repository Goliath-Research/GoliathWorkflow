# Configuration Parameter Matrix (Active Components)

This matrix is code-backed and scoped to the active canonical production workflow. Deprecated/legacy compatibility surfaces (including `methylcluster`) are out of scope except where explicitly called out as aliases.

Status legend:
- `declared`: present in a config schema/model or documented step config contract
- `consumed`: read and used by resolver/runtime logic
- `inherited`: from top-level project fields (`output_base`, `samples_base_path`, `controls/diseases`, etc.)
- `alias`: backward-compatible synonym
- `legacy`: compatibility-only key; avoid in new configs

Legacy compatibility boundary:
- entries marked `legacy` are retained for backward compatibility only
- they are not part of the active canonical production workflow

## Shared project contract

| Key | Status | Notes | Evidence |
|---|---|---|---|
| `controls` / `diseases` | alias + consumed | normalized to `control`/`disease` | `packages/methylutils/methyl_utils/pipeline_config.py` |
| `step_config.validator` | legacy alias | copied to `step_config.predictor`; warning emitted | `packages/methylutils/methyl_utils/pipeline_config.py` |
| `output_base`, `project_name` | inherited + consumed | root path for all derived outputs | `packages/methylutils/methyl_utils/pipeline_config.py` |
| `samples_base_path` | inherited + consumed | used in resolvers/MC path expansion | `packages/*/project_resolver.py` |
| `comparisons` | inherited + consumed | drives per-comparison output layout | `packages/methylutils/methyl_utils/pipeline_config.py` |

## Per-step summary

| Step | Declared source | Consumed source | Notable aliases / legacy |
|---|---|---|---|
| `centroid` | `packages/methylcentroid/methyl_centroid/config.py` | `packages/methylcentroid/methyl_centroid/project_resolver.py` | none |
| `detection` | `packages/methyldetector/methyl_detector/models/config.py` | `packages/methyldetector/methyl_detector/utils/project_resolver.py` | strict: unknown keys rejected; legacy ECDF grid aliases removed (use `ecdf_grid_size`) |
| `classifier` | `packages/methylclassifier/methyl_classifier/models/config_schema.py` | `packages/methylclassifier/methyl_classifier/project_resolver.py` | none |
| `predictor` | `packages/methylpredictor/methyl_predictor/models/config.py` | `packages/methylpredictor/methyl_predictor/project_resolver.py` | `validator` alias (legacy) |
| `mapper` | `packages/methylmapper/methyl_mapper/config.py` | `packages/methylmapper/methyl_mapper/project_resolver.py` | `csv_filename_pattern` alias in resolvers |
| `enricher` | `packages/methylenricher/methyl_enricher/config.py` | `packages/methylenricher/methyl_enricher/project_resolver.py` | `input`/`outdir` aliases (legacy) |
| `validation` | `packages/methylvalidation/methyl_validation/config.py` (`ValidationStepConfig` / `MonteCarloConfig`) | `packages/methylvalidation/methyl_validation/cli.py` + runner/stability | none |
| `progression` | `packages/methyldiseaseprogression/methyl_disease_progression/config.py` | `packages/methyldiseaseprogression/.../progression.py` + `packages/methylvalidation/.../pipeline_runner.py` | `ordered_disease_groups` alias |
| `alignment_qc` | `packages/methylalignmentqc/methyl_alignment_qc/models/config.py` | `packages/methylalignmentqc/methyl_alignment_qc/project_resolver.py` | `fragmentomics`, `auto_profile_from_analyte` (cfDNA insert-size QC) |
| `fragmentomics` | `packages/methylfragmentomics/methyl_fragmentomics/config.py` | `packages/methylfragmentomics/methyl_fragmentomics/project_resolver.py` | BAM WPS + end motifs (`methyl-fragmentomics`) |

## Redundancy candidate classification

| Candidate | Disposition | Risk | Rationale | Evidence |
|---|---|---|---|---|
| `step_config.validator` | deprecate, keep alias | low | still useful for old project files; canonical key is predictor | `packages/methylutils/.../pipeline_config.py`, `packages/methylpredictor/.../project_resolver.py` |
| Enricher `input`/`outdir` aliases | deprecate, keep alias | low | duplicate semantics with `input_file`/`output_dir`; warnings added | `packages/methylenricher/.../project_resolver.py` |
| Detector legacy ECDF keys | removed | low | strict config: use `ecdf_grid_size` only | `packages/methyldetector/.../models/config.py` |
| `disease_subdir` arg in detector per-group resolver | remove | low | unused in runtime; removed | `packages/methyldetector/.../utils/project_resolver.py` |
| Unused MC iteration runner args (`val_*`, predictor output in stability paths) | remove | low | no behavior effect; CLI calls updated | `packages/methylvalidation/.../pipeline_runner.py`, `cli.py` |

## Canonical key recommendations

Use these keys in new/updated `project_*.json` files:

- `step_config.predictor` (not `validator`)
- `step_config.enricher.input_file` / `step_config.enricher.output_dir` (not `input` / `outdir`)
- `step_config.detection.ecdf_grid_size` (not legacy grid aliases)
- `step_config.progression.ordered_comparison_labels` (prefer over `ordered_disease_groups`)

## Recent validation/runtime deltas (2026-05)

These are the highest-impact keys and behavioral contracts added or changed in recent mono-repo updates.

| Key / behavior | Status | Current contract |
|---|---|---|
| `stability_early_stop_enabled` + `stability_min_iterations` + `stability_convergence_*` | declared + consumed | Optional adaptive stop during `--stability`; convergence is checked on stable panel overlap/size drift with patience and still bounded by `n_iterations`. |
| `ecdf_aggregated_enabled` + `ecdf_aggregated_n_bins` | declared + consumed | Aggregated ECDF OvR backend controls for `model_backend=ecdf`; auto-enabled when `feature_mode=observed_hybrid` and `feature_family_set != dmp` unless explicitly overridden. |
| `feature_family_set` | declared + consumed | Governs observed-hybrid feature schema: `dmp`, `gene`, `structural`, `gene_scored`, `dmp+gene`, `dmp+structural`, `dmp+gene_scored`, `hybrid-all`. Non-`dmp` families require mapper-derived annotations during model build. `gene_scored` / `dmp+gene_scored` also require `frozen_genes_production.csv`. |
| `gene_scored_min_support_n` | declared + consumed | Minimum `gene_support_n` for genes in the frozen panel when building `gene_directional_score__*` features (default `2`). |
| `gene_scored_use_region_weight` | declared + consumed | When true, multiply per-locus weights by `region_weight` from the bundle DMP index. |
| `gene_scored_gene_weight` | declared + consumed | Gene pooling mode: `importance_x_sqrt_support` (default) or `importance_only`. |
| `tabular_max_dmps` | declared + consumed | `null`/`0` keeps all stable DMP loci from bundle index; positive values cap by descending effect size. Older docs/examples that imply default `5000` are stale. |
| model-MC shared reuse (`--model-mc --model-mc-all`) | consumed runtime behavior | When split source is reused, centroid/detector artifacts are symlinked from primary MC runs into `model_mc/shared/run_XXXX` instead of recomputation. |
| freeze mapper annotation cache | consumed runtime behavior | Freeze builds `production/model_bundle/mapper_dmp_annotations.csv`, wires `step_config.model_bundle.mapper_annotation_csv`, and records `mapper_annotation_cache` in `production_summary.json`. |

