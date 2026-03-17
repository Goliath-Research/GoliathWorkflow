---
name: Pathway-to-module pipeline
overview: "Design an automated pathway-to-module pipeline that extends MethylEnricher: run multi-source enrichment, normalize pathway names, cluster pathways by gene overlap into modules, score/rank modules, and apply a disease-aware prior so output is ranked modules instead of flat pathway tables."
todos: []
isProject: false
---

# Pathway-to-module pipeline (MethylEnricher 2.0)

## Current state

- **MethylMapper** ([packages/methylmapper](packages/methylmapper)) outputs gene-level tables (e.g. `all-gene_name-combined.csv`) with: `gene_name`, `dmp_count`, `gene_q_value`, `mean_effect_size`, `gene_importance`, `total_weight`, `gene_z`, `feature_type`, and optional disease columns (`disease_associated`, `disease_score`, etc.). When `use_sp_regions=True`, region-level data (promoter, exon, intron) exists before aggregation.
- **MethylEnricher** ([packages/methylenricher/methyl_enricher/enricher.py](packages/methylenricher/methyl_enricher/enricher.py)) runs **ORA via Enrichr** (gseapy): loads genes from CSV (with filters/top-N), queries multiple libraries (KEGG, Reactome, GO, Hallmark, WikiPathways), and writes per-library CSVs + merged + top-hits. **No** pathway merging, clustering, or module-level output.

## Target behavior

**Input:** MethylMapper combined CSV (or plain gene list) with optional gene weights.  
**Output:** A single table of **ranked pathway modules** (e.g. PI3K/growth-factor, WNT, immune, ECM, DNA repair) with module score, main genes, main pathways, and disease relevance—instead of hundreds of raw pathway rows.

---

## Architecture: pipeline stages

```mermaid
flowchart LR
  subgraph input [Input]
    CSV[MethylMapper CSV]
    Genes[Gene list + weights]
  end
  subgraph A [A. Gene weighting]
    GW[Weights from effect_size / region / importance]
  end
  subgraph B [B. Enrichment]
    ENR[ORA Enrichr: Hallmark, KEGG, Reactome, GO BP, WikiPathways]
  end
  subgraph C [C. Pathway graph]
    Norm[Normalize names]
    Sim[Pairwise overlap: Jaccard]
    Cluster[Cluster: Louvain/Leiden or spectral]
  end