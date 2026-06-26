# Configuration Parameter Matrix (Four-Layer Model)

This matrix documents the **new-only** configuration stack. **`step_config` in study manifests is removed** — see [`docs/plans/simplify-study-config.plan.md`](plans/simplify-study-config.plan.md).

Pipeline **topology** (stage order, IF branches) belongs in **DomainProgram** JSON. **Tunable tool parameters** belong in **profile `actionConfig`**, **site manifest**, or program **`with` / `stepOverride`** — not in `project_*.json`.

Status legend:

- `declared`: present in a JSON schema or Pydantic model
- `consumed`: read and used by resolver/runtime logic
- `inherited`: derived from study manifest fields (cohorts, paths, comparisons)
- `materialized`: merged at plan/claim time into task `resolvedConfig`

## Layer map

| Layer | Artifact | Schema | Owns |
|-------|----------|--------|------|
| Study manifest | `/work/<disease>/configs/project_*.json` | `schemas/config/project_config.schema.json` | Cohorts, stages, comparisons, chromosomes, paths, regulatory, validation_partitions, progression_order |
| Program | `workflow_engine/domain/**/*.program.json` | `schemas/domain/domain_program.schema.json` | Control flow, per-action `with` / `stepOverride` |
| Profile | `workflow_engine/domain/profiles/*.profile.json` | `schemas/config/profile.schema.json` | Scope booleans + `actionConfig` parameter packs |
| Site | `/work/site/methyl_site.json` (or `METHYL_SITE_CONFIG`) | `schemas/config/site_manifest.schema.json` | Genomes, GTF, caches, cluster defaults |

**Precedence** (highest wins): instance override → program `with` / `stepOverride` → profile `actionConfig` → analyte defaults (`regulatory.primary_analyte`) → site manifest → package defaults.

## Study manifest (project_*.json)

| Key | Status | Notes | Evidence |
|-----|--------|-------|----------|
| `controls` / `diseases` | declared + consumed | Normalized to control/disease cohorts | `packages/methylutils/methyl_utils/pipeline_config.py` |
| `diseases.groups[].stages[]` | declared + consumed | Staged comparisons; optional `description`, `order_index` | `pipeline_config.py` |
| `comparisons` | declared + consumed | Drives per-comparison output layout | `pipeline_config.py` |
| `progression_order` | declared + consumed | `from_stages` \| `from_comparisons` \| `explicit` | `pipeline_config.py` |
| `progression_labels` | declared + consumed | Required when `progression_order` is `explicit` | `pipeline_config.py` |
| `regulatory` | declared + consumed | Study-level regulatory metadata; `primary_analyte` seeds analyte defaults | `pipeline_config.py` |
| `validation_partitions` | declared + consumed | Sample-list partitions for validation/freeze | `pipeline_config.py` |
| `output_base`, `project_name` | declared + consumed | Root path for derived outputs | `pipeline_config.py` |
| `samples_base_path` | declared + consumed | MC path expansion, sample resolution | `packages/*/project_resolver.py` |
| `chromosomes`, `contexts` | declared + consumed | FOREACH bindings in compiled workflows | `workflow_engine/domain/compiler.py` |
| `path_remap` | declared + consumed | Operator path aliasing on shared storage | `pipeline_config.py` |
| `step_config` | **rejected** | Schema and `ProjectConfig` reject this key | `project_config.schema.json`, `pipeline_config.py` |

## Profile (actionConfig + scope flags)

Profiles combine **IF-friendly booleans** with **`actionConfig`** slices keyed by catalog action section (same keys historically used under `step_config`):

| Scope flag | Typical use | Set by |
|------------|-------------|--------|
| `runDmpSelection` | Gate `pipeline.dmp_select` | Profile preset or `actionConfig.dmp_selection` |
| `runGeneFeaturecuts` | Gate gene FeatureCuts branch | Profile preset or validation/gene_selection keys |
| `runBiomarkerFilter` | PPI/disease shrink before gene FC | Profile preset |
| `runGeneFeatureSelect` | Structural gene×region selection | Profile preset |
| `runProgressionAnalysis` | Gate `pipeline.progression` | Profile preset or `actionConfig.progression.enabled` |
| `stabilityFeaturecutsEnabled` | DMP stability axis in MC | Profile or `actionConfig.validation` |
| `stabilityGeneFeaturecutsEnabled` | Gene stability axis in MC | Profile or `actionConfig.validation` |

Named staged/Buffy packs (repo): `staged_ovr_mc`, `staged_full_lifecycle`, `staged_progression_interpretation`, `buffy_mc_gene_fc`. See [`workflow_engine/domain/profiles/`](../../workflow_engine/domain/profiles/).

Loader and flag seeding: `workflow_engine/domain/pipeline_profiles.py`, `workflow_engine/domain/workflow_context.py`.

## Site manifest

| Key | Status | Notes | Evidence |
|-----|--------|-------|----------|
| `reference_genome.fasta` | declared + consumed | Alignment, extraction reference | `action_config_resolver.py` (Phase 2) |
| `annotation.gtf` | declared + consumed | Mapper annotation | site manifest schema |
| `methyl_mapper_home` | declared + consumed | Mapper cache root | site manifest schema |
| `caches.*` | declared + consumed | Shared cache paths (e.g. STRING edges) | `site_grch38.example.json` |
| `actionConfig.*` | declared + consumed | Optional per-action infra defaults | `site_manifest.schema.json` |

Example: `workflow_engine/domain/profiles/site_grch38.example.json`.

## Program overrides

| Mechanism | Status | Notes |
|-----------|--------|-------|
| `with.stepOverride` | declared + materialized | Per-invocation action parameter overlay |
| `with` literal / `{ "ref": "..." }` | declared + consumed | Scope-bound inputs (chromosome, comparison, …) |
| IF on `${runDmpSelection}` etc. | declared + consumed | Composable branches without manifest edits |

## Per-action actionConfig sections

Parameters resolve into **`resolvedConfig`** on each workflow task (Phase 4). Section keys map from the action catalog (`action_config_key`).

| Section | Config model | Resolver / runner |
|---------|--------------|-------------------|
| `centroid` | `packages/methylcentroid/methyl_centroid/config.py` | `methyl_centroid/project_resolver.py` |
| `detection` | `packages/methyldetector/methyl_detector/models/config.py` | `methyldetector/.../project_resolver.py` |
| `classifier` | `packages/methylclassifier/methyl_classifier/models/config_schema.py` | `methyl_classifier/project_resolver.py` |
| `predictor` | `packages/methylpredictor/methyl_predictor/models/config.py` | `methyl_predictor/project_resolver.py` |
| `mapper` | `packages/methylmapper/methyl_mapper/config.py` | `methyl_mapper/project_resolver.py` |
| `enricher` | `packages/methylenricher/methyl_enricher/config.py` | `methyl_enricher/project_resolver.py` |
| `validation` | `packages/methylvalidation/methyl_validation/config.py` | `methyl_validation/cli.py`, runners |
| `progression` | `packages/methyldiseaseprogression/methyl_disease_progression/config.py` | progression runner (manifest order + profile params) |
| `alignment_qc` | `packages/methylalignmentqc/methyl_alignment_qc/models/config.py` | `methyl_alignment_qc/project_resolver.py` |
| `fragmentomics` | `packages/methylfragmentomics/methyl_fragmentomics/config.py` | `methyl_fragmentomics/project_resolver.py` |
| `methyl_extract` | sample-prep / extraction | workers + site manifest |

## High-impact validation keys (profile actionConfig.validation)

Recent contracts that belong in **profile** `actionConfig.validation`, not the study manifest:

| Key / behavior | Status | Current contract |
|----------------|--------|------------------|
| `n_iterations`, `run_stability`, stability early-stop keys | declared + consumed | MC iteration count and adaptive stability stop |
| `stability_featurecuts_enabled`, `stability_gene_featurecuts_enabled` | declared + consumed | Also surfaced as profile scope booleans |
| `backend_profiles` (ecdf, tabular_sklearn, generative_hybrid) | declared + consumed | Model-backend parameter packs for MC/freeze |
| `feature_family_set`, `gene_scored_*`, `structural_scored_*` | declared + consumed | Observed-hybrid feature schema; progression order from manifest when not overridden |
| `ecdf_aggregated_enabled`, `tabular_max_dmps` | declared + consumed | ECDF/tabular backend tuning |
| `require_biological_review_for_model`, `biological_review_confirmed` | declared + consumed | Freeze gate flags |

Progression **order** comes from the study manifest (`progression_order`, `progression_labels`, stage `order_index`). Progression **scoring/report options** stay in profile `actionConfig.progression`.

## CI guard

Committed `project*.json` files must not contain `step_config`:

```bash
python scripts/check_no_step_config.py
```

Legacy backups use the `*.legacy.bak` suffix and are excluded.

## Related docs

- [DomainProgram language](reference/domain-program-language.md) — profiles, site, instance context
- [Architecture review](architecture/index.md) — layer map and migration status
- [Simplify study config plan](plans/simplify-study-config.plan.md) — phased implementation
