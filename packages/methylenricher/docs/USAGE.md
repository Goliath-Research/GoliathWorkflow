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

Disease columns in module outputs are conditional:

- When a disease prior can be inferred from mapper-style disease columns in the input CSV (or explicitly provided by callers), `modules_ranked.csv` includes `Disease_relevance_score` and `Disease_relevance_tier`.
- When no valid disease prior exists (for example healthy-vs-healthy runs, or disease filters that leave zero prior genes), disease columns are omitted to avoid misleading interpretation.
- Disease-related CLI filters (`--disease-only`, `--min-disease-score`, `--min-disease-evidence-level`, etc.) can narrow both input genes and inferred module disease prior when disease metadata exists.

`--network-plot` behavior:

- default when omitted in module mode: `plotly`,
- `none`: disable exports,
- `plotly`, `pyvis`, `cytoscape`, `all`: offline artifacts,
- `dash`: interactive server (`--dash-host`, `--dash-port`, optional `--dash-open-browser`).

Optional PPI refinement can be enabled via CLI flags or `step_config.enricher.network_refinement`:

- `source=string_api` (default) or `source=local_edges`,
- writes `ppi_network_edges.csv`, `ppi_node_metrics.csv`, `ppi_hubs.csv`, `ppi_module_coherence.csv`,
- adds blended scoring columns in `modules_ranked.csv` (`Base_score`, `PPI_coherence_score`, `Blended_score`).

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

## Related Documentation

- Theory: [`THEORY.md`](THEORY.md)
- Implementation: [`IMPLEMENTATION.md`](IMPLEMENTATION.md)
