# MethylEnricher Usage

## CLI Entry Points

The package exposes:

- `methyl-enricher`
- `methyl_enricher`
- `methyl-enricher-network-discovery`
- `methyl_enricher_network_discovery`

- `methyl-enricher` / `methyl_enricher` resolve to `methyl_enricher.cli:main`.
- `methyl-enricher-network-discovery` / `methyl_enricher_network_discovery` resolve to `methyl_enricher.network_discovery_cli:main`.

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
