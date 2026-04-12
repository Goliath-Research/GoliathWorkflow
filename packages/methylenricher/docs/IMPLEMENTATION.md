# MethylEnricher Implementation Notes

## Canonical Theory

For formulas, assumptions, and caveats, see [`docs/theory/chapters/08-methylenricher.qmd`](../../../docs/theory/chapters/08-methylenricher.qmd).

## Main Code Paths

- `methyl_enricher/enricher.py`: gene-list loading, Enrichr calls, filtering.
- `methyl_enricher/pathway_graph.py`: pathway overlap graph and clustering.
- `methyl_enricher/module_scorer.py`: heuristic module scoring and disease relevance.
- `methyl_enricher/module_pipeline.py`: end-to-end orchestration.
- `methyl_enricher/ppi_network.py`: optional STRING/local-edge PPI refinement (graph build, metrics, communities, module coherence).
- `methyl_enricher/module_network_plot.py`: shared pathway network exporters (Plotly, PyVis, Cytoscape.js) and Cytoscape payload builder.
- `methyl_enricher/module_network_dash.py`: optional Dash + dash_cytoscape interactive viewer.
- `methyl_enricher/pathway_normalizer.py`: pathway theme normalization and labeling.

## Implementation Notes

- Statistical enrichment is delegated to Enrichr through `gseapy`.
- Module construction depends on graph thresholds and clustering settings.
- Several ranking and labeling steps are intentionally heuristic and should remain documented as such.
- Optional `network_refinement` adds a second graph layer from gene-level PPI edges (STRING API or local edge CSV) and writes:
  - `ppi_network_edges.csv`
  - `ppi_node_metrics.csv`
  - `ppi_hubs.csv`
  - `ppi_module_coherence.csv`
- Module ranking remains backward compatible; `modules_ranked.csv` preserves historical columns and now also reports `Base_score`, `PPI_coherence_score`, and `Blended_score`.
- PPI refinement is best interpreted as structural support for module quality, not as a replacement for disease evidence sources.
- For `source=string_api`, `network_refinement.cache_path` (or `--network-refinement-cache-path`) enables shared edge caching across runs/instances.
- `network_plot=dash` launches an interactive Cytoscape-style server; static exports (`plotly`, `cytoscape`) remain the reproducible offline default.
- Dash mode can optionally include a second dataset tab for refinement PPI topology when network refinement is enabled.
