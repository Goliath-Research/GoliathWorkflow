---
name: Enricher modules and overlap genes
overview: Reduce module count to 3-5 by tuning Jaccard clustering (threshold and/or Louvain resolution), add canonical themes (Calcium/GPCR, RTK/MAPK) and align labels with expected cancer hallmarks, and expose overlap genes per module and per pathway in the output.
todos: []
isProject: false
---

# MethylEnricher: fewer modules and overlap genes

## Current state

- **Clustering**: [pathway_graph.py](packages/methylenricher/methyl_e