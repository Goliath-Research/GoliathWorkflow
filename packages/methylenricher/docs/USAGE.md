# MethylEnricher Usage

## CLI Entry Points

The package exposes:

- `methyl-enricher`
- `methyl_enricher`
- `methyl-enricher-network-discovery`
- `methyl_enricher_network_discovery`

- `methyl-enricher` / `methyl_enricher` resolve to `methyl_enricher.cli:main`.
- `methyl-enricher-network-discovery` / `methyl_enricher_network_discovery` resolve to `methyl_enricher.network_discovery_cli:main`.

## Main run modes

`methyl-enricher` supports three practical modes:

- single-input enrichment (`--input`, optional filters and library controls),
- module pipeline mode (`--modules`) with pathway clustering and ranking outputs,
- project-driven mode (`--project`) that resolves input/output paths from pipeline config.

When `--project` points to a project with multiple cancer-group comparisons and no explicit `--input`/`--outdir` overrides, the CLI runs once per comparison using:

- mapper input from `mapper/<control>/<disease>/...combined.csv`,
- output under `enricher/<control>/<disease>/`.

Passing explicit `--input` or non-default `--outdir` with `--project` forces a single run.

## Library selection precedence

Library resolution is explicit and stable:

- `--libraries` (or `step_config.enricher.libraries`) wins,
- else `--library-preset`,
- else package defaults.

Presets currently include `cancer-core` and `cancer-extended`.

## Module + network outputs

With `--modules`, MethylEnricher runs enrichment + pathway graph clustering and writes `modules_ranked.csv`.

Module naming is disease-agnostic by default:

- Primary labels are derived from canonical library evidence (KEGG/Reactome/GO/Hallmark/WikiPathways) when present.
- Perturbation/drug libraries (for example LINCS/DSigDB) are retained as supporting evidence, not primary names.
- `modules_ranked.csv` now includes:
  - `Module_primary` (canonical label),
  - `Module_supporting_perturbation` (top perturbation signatures),
  - `Module_display` (presentation label).
- Use `--module-label-mode canonical_only|dual_label` (or `step_config.enricher.module_label_mode`) to control display behavior. Default: `dual_label`.

Disease columns in module outputs are conditional:

- When a disease prior can be inferred from mapper-style disease columns in the input CSV (or explicitly provided by callers), `modules_ranked.csv` includes `Disease_relevance_score` and `Disease_relevance_tier`.
- When no valid disease prior exists (for example healthy-vs-healthy runs, or disease filters that leave zero prior genes), disease columns are omitted to avoid misleading interpretation.
- Disease-related CLI filters (`--disease-only`, `--min-disease-score`, `--min-disease-evidence-level`, etc.) can narrow both input genes and inferred module disease prior when disease metadata exists.
- Use `--cluster-seed` to make Louvain module assignments reproducible across runs with identical inputs/parameters.
- When mapper exports `hits_*` columns, enricher computes a default feature-weight score from SP weights (`promoter=2.0`, `exon=1.5`, `gene_body=1.0`, `intron=0.7`, `terminator=0.5`) and uses it as the default gene weight.

`--network-plot` behavior:

- default when omitted in module mode: `plotly`,
- `none`: disable exports,
- `plotly`, `pyvis`, `cytoscape`, `all`: offline artifacts,
- `dash`: interactive server (`--dash-host`, `--dash-port`, optional `--dash-open-browser`).

Optional PPI refinement can be enabled via CLI flags or `step_config.enricher.network_refinement`:

- `source=string_api` (default) or `source=local_edges`,
- writes `ppi_network_edges.csv`, `ppi_node_metrics.csv`, `ppi_hubs.csv`, `ppi_module_coherence.csv`,
- adds blended scoring columns in `modules_ranked.csv` (`Base_score`, `PPI_coherence_score`, `Blended_score`).

Hub ranking and module-level PPI coherence use **methylation signal** by default (`hub_ranking_mode=signal_weighted`, CLI `--network-refinement-hub-ranking-mode`):

- `ppi_node_metrics.csv` includes `methylation_weight`, `topology_score`, and `combined_hub_score` (topology × normalized input weight × optional disease boost).
- `ppi_hubs.csv` is sorted by `combined_hub_score` unless you set `hub_ranking_mode=topology` (pure graph centrality).
- `ppi_module_coherence.csv` includes `ppi_mean_combined_hub_score` when signal-weighted mode is active, and the coherence blend uses that metric instead of raw degree centrality alone.
- Optional: `hub_disease_boost` scales genes in the disease prior; `hub_w_degree` / `hub_w_betweenness` / `hub_w_closeness` weight the three normalized centrality terms inside `topology_score` (defaults: equal thirds).

## Custom network discovery workflow

The network discovery CLI scans completed enricher outputs (for example directories containing
`ppi_network_edges.csv` and `modules_ranked.csv`), computes candidate edges and novelty against STRING,
writes a versioned SQLite snapshot, and exports curated edges in `source,target,score` format for
`network_refinement.source=local_edges`.

By convention, persistent artifacts resolve under:

- `step_config.enricher.methyl_enricher_home`
- default fallback: `/work/cache/methyl_enricher`

Paths created by default:

- `<methyl_enricher_home>/network_discovery/custom_network.sqlite`
- `<methyl_enricher_home>/network_discovery/exports/local_edges.csv`

Example:

```bash
methyl-enricher-network-discovery \
  --project /path/to/project.json \
  --scan-root /work/prostate-cancer/Healthy_vs_PCa1-4-CG/enricher
```

## Project step config mapping

`step_config.enricher` maps onto CLI arguments through `EnricherStepConfig`.

- Both nested `network_refinement.{...}` and flat `network_refinement_*` keys are supported.
- For `network_plot`, explicit CLI value wins over config.
- In project mode, `--step-override` can inject temporary step-level overrides without editing the project JSON.

## Typical Inputs

Typical runs start from:

- mapped genes or weighted gene lists from `methylmapper`,
- optional disease-specific prior genes,
- a selected set of Enrichr libraries and pathway-theme mappings.

## Typical Outputs

The package can emit:

- filtered enrichment result tables,
- pathway-overlap graphs,
- module rankings,
- disease-relevance summaries and pathway-theme labels.

## Ensure-complete mode

Use **`--ensure-complete`** on production projects so every Enrichr library is present before progression or modeling:

```bash
methyl-enricher --project /path/to/monte_carlo_runs/production/project.json --ensure-complete
```

- Retries transient Enrichr failures (429, parse errors) with exponential backoff.
- Skips libraries whose `enrich_<library>.csv` already exists (use `--force` to re-query).
- Writes `enricher_task_status.json` per comparison and `enricher/enricher_completeness.json` at the enricher root.
- Exit **0** only when all comparisons are complete; otherwise **1**.

Config (`step_config.enricher`):

| Key | Default | Purpose |
|-----|---------|---------|
| `ensure_complete` | false | When true with `--project`, same as CLI flag |
| `enricher_max_retries` | 5 | Per-library attempts |
| `enricher_retry_base_seconds` | 30 | Initial backoff |
| `enricher_retry_max_seconds` | 600 | Backoff cap |
| `enricher_inter_library_delay_seconds` | 2 | Pause between libraries |
| `distributed` | false | Freeze plans tasks only (see queue below) |

Other flags: `--verify-only`, `--comparison LABEL`, `--no-retry`.

## Distributed enricher queue (per comparison)

After freeze mapper outputs exist:

```bash
methyl-enricher plan-tasks --project .../production/project.json
methyl-enricher export-queue --project .../production/project.json
# workers (one comparison each):
methyl-enricher run-task --task .../enricher/queue/tasks/enricher_PCa_PCa1.json
methyl-enricher verify-complete --project .../production/project.json
```

Set `step_config.enricher.distributed: true` in freeze config to run **plan-tasks** during `--freeze` instead of blocking on Enrichr (workers must finish before progression).

## Related Documentation

- Theory: [`THEORY.md`](THEORY.md)
- Implementation: [`IMPLEMENTATION.md`](IMPLEMENTATION.md)
