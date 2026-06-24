# Configuration Parameter Matrix (Active Components)

This matrix is code-backed. **Pipeline orchestration** (stage order, conditional branches) belongs in **DomainProgram** JSON — see [`architecture_review.md`](architecture_review.md). `project.json` is the **study manifest** (cohorts, paths, chromosomes); `step_config` supplies per-action defaults until migrated into program `with` blocks.

This matrix is scoped to the active canonical production workflow. Deprecated/legacy compatibility surfaces (including `methylcluster`) are out of scope except where explicitly called out as aliases.

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
| `alignment_qc` | `packages/methylalignmentqc/methyl_alignment_qc/models/config.py` | `packages/methylalignmentqc/methyl_alignment_qc/project_resolver.py` | `fragmentomics`, `auto_profile_from_analyte`, `bisulfite_conversion` (sidecar JSON) |
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
| `ecdf_aggregated_enabled` + `ecdf_aggregated_n_bins` | declared + consumed | Aggregated ECDF OvR backend controls for `model_backend=ecdf`; auto-enabled when `feature_mode=observed_hybrid` and `feature_family_set != dmp_scored` unless explicitly overridden. Applies only when `feature_mode=observed_hybrid`. |
| `feature_family_set` | declared + consumed | Governs observed-hybrid feature schema (only when `feature_mode=observed_hybrid`): canonical tokens `dmp_scored`, `gene`, `structural`, `gene_scored`, `structural_scored`, `dmp_scored+gene`, `dmp_scored+structural`, `dmp_scored+gene_scored`, `dmp_scored+structural_scored`, `hybrid-all`. Legacy aliases `dmp`, `dmp+gene`, `dmp+structural`, `dmp+gene_scored`, `dmp+structural_scored` are accepted and normalized on load. Non-`dmp_scored`-only families require mapper-derived annotations during model build. `gene_scored` / `dmp_scored+gene_scored` require `frozen_genes_production.csv`. `structural_scored` / `dmp_scored+structural_scored` require `frozen_gene_features.csv`. |
| `gene_scored_min_support_n` | declared + consumed | Minimum `gene_support_n` for genes in the frozen panel when building `gene_scored` features (default `2`). Emits per comparison: `gene_directional_score__*`, `gene_panel_obs_fraction__*`, `gene_directional_iqr__*`, `gene_weighted_sign_agreement__*`. |
| `gene_scored_use_region_weight` | declared + consumed | When true, multiply per-locus weights by `region_weight` from the bundle DMP index when computing per-gene directional values. |
| `gene_scored_gene_weight` | declared + consumed | Gene pooling mode for `gene_directional_score__*`: `importance_x_sqrt_support` (default) or `importance_only`. |
| `gene_scored_ordered_comparison_labels` | declared + consumed | Optional override for progression order when building `gene_scored` derived features. When null, order comes from `step_config.progression.ordered_comparison_labels` or `ProjectConfig.get_ordered_comparison_labels()`. |
| `gene_scored_contrast_pairs` | declared + consumed | Optional list of `[left, right]` label pairs for extra `gene_directional_contrast__{left}__{right}` columns (= score(right)−score(left)). Auto extreme first→last contrast added when K≥2 unless already listed. |
| `structural_scored_min_support_n` | declared + consumed | Minimum `n_dmps_in_feature` for gene-feature rows in `frozen_gene_features.csv` when building `structural_scored` (default `2`). |
| `structural_scored_use_region_weight` | declared + consumed | When true, multiply per-locus weights by `region_weight` when computing structural directional values. |
| `structural_scored_weight` | declared + consumed | Gene-feature pooling mode for `structural_directional_score__*`: `compound_x_sqrt_support` (default) or `compound_only`. |
| `structural_scored_ordered_comparison_labels` | declared + consumed | Optional override for `structural_scored` progression order (same resolution chain as `gene_scored`). |
| `structural_scored_contrast_pairs` | declared + consumed | Optional extra `structural_directional_contrast__{left}__{right}__{region}` pairs per emitted region type. |
| `region_directional_region_types` + `region_directional_min_loci` | declared + consumed | Consumed by `structural_scored` only: candidate region types (default promoter/exon/intron/gene_body/terminator) and minimum panel loci in the classifier index to emit columns for a `(comparison, region)` pair. Columns are omitted entirely when unsupported (no all-NaN placeholders). |
| `mapper_annotation_collapse_mode` | declared + consumed | Collapse multi-feature mapper intersections to one row per locus when building `mapper_dmp_annotations.csv`: `priority` (default; promoter>exon>intron>gene_body>terminator) or `weight` (legacy highest combined_weight). |
| `mapper_annotation_unknown_fallback` | declared + consumed | Parent feature bucket for classifier loci with unknown/missing `feature_type` after mapper merge (default `gene_body`; set `null` to leave uncovered). |
| `tabular_max_dmps` | declared + consumed | `null`/`0` keeps all stable DMP loci from bundle index; positive values cap by descending effect size. Older docs/examples that imply default `5000` are stale. |
| model-MC shared reuse (`--model-mc --model-mc-all`) | consumed runtime behavior | When split source is reused, centroid/detector artifacts are symlinked from primary MC runs into `model_mc/shared/run_XXXX` instead of recomputation. |
| freeze mapper annotation cache | consumed runtime behavior | Freeze builds `production/model_bundle/mapper_dmp_annotations.csv`, wires `step_config.model_bundle.mapper_annotation_csv`, and records `mapper_annotation_cache` in `production_summary.json`. |

