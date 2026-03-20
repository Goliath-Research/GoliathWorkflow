# MethylEnricher Implementation Notes

## Canonical Theory

For formulas, assumptions, and caveats, see [`docs/theory/chapters/08-methylenricher.qmd`](../../../docs/theory/chapters/08-methylenricher.qmd).

## Main Code Paths

- `methyl_enricher/enricher.py`: gene-list loading, Enrichr calls, filtering.
- `methyl_enricher/pathway_graph.py`: pathway overlap graph and clustering.
- `methyl_enricher/module_scorer.py`: heuristic module scoring and disease relevance.
- `methyl_enricher/module_pipeline.py`: end-to-end orchestration.
- `methyl_enricher/pathway_normalizer.py`: pathway theme normalization and labeling.

## Implementation Notes

- Statistical enrichment is delegated to Enrichr through `gseapy`.
- Module construction depends on graph thresholds and clustering settings.
- Several ranking and labeling steps are intentionally heuristic and should remain documented as such.
