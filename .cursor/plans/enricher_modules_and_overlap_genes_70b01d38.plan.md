---
name: Enricher modules and overlap genes
overview: Reduce module count to 3-5 by tuning Jaccard clustering (threshold and/or Louvain resolution), add canonical themes (Calcium/GPCR, RTK/MAPK) and align labels with expected cancer hallmarks, and expose overlap genes per module and per pathway in the output.
todos: []
isProject: false
---

# MethylEnricher: fewer modules and overlap genes

## Current state

- **Clustering**: [pathway_graph.py](packages/methylenricher/methyl_enricher/pathway_graph.py) already uses Jaccard `|A ∩ B| / |A ∪ B|` and Louvain. Default `similarity_threshold=0.25` and no resolution tuning, so runs often yield many small modules (e.g. 41).
- **Themes**: [pathway_theme_mapping.json](packages/methylenricher/methyl_enricher/data/pathway_theme_mapping.json) has PI3K, WNT, TGF-beta/EMT, immune, ECM, etc. Missing: **Calcium / GPCR** (neuroendocrine), **RTK / MAPK** (EGFR/MET/BRAF) as first-class themes.
- **Output**: [module_pipeline.py](packages/methylenricher/methyl_enricher/module_pipeline.py) writes `modules_ranked.csv` with `Main_genes` (top 10 by weight). There is no explicit “overlap genes” column and no per-pathway overlap listing.

## Goals

1. **Fewer, interpretable modules (3–5)**  
   Cluster pathways by gene overlap (Jaccard) and tune so that typical runs produce a small number of hallmark-style modules.

2. **Canonical themes**  
   Align with expected modules: Calcium/GPCR, RTK/MAPK, WNT/developmental, EMT/invasion, immune signaling.

3. **Show genes that drive each pathway**  
   Output overlap genes (input genes that hit each pathway/module) so interpretation is straightforward.

---

## 1. Cluster to 3–5 modules (Jaccard + tuning)

**Keep:** Jaccard and Louvain in [pathway_graph.py](packages/methylenricher/methyl_enricher/pathway_graph.py) (no algorithm change).

**Tuning to get fewer, larger modules:**

- **Option A – Lower default similarity threshold**  
  In [pathway_graph.py](packages/methylenricher/methyl_enricher/pathway_graph.py) and [module_pipeline.py](packages/methylenricher/methyl_enricher/module_pipeline.py), lower default `similarity_threshold` from `0.25` to e.g. `0.15` so more pathway pairs get an edge and Louvain merges them into fewer communities.

- **Option B – Louvain resolution**  
  In `cluster_pathways_louvain(G)`, call `best_partition(G, resolution=...)`. Lower resolution (e.g. 0.5–0.8) yields fewer, larger communities. Add a parameter (e.g. `resolution=0.8`) and pass it from [module_pipeline.py](packages/methylenricher/methyl_enricher/module_pipeline.py) / CLI so it can be tuned without code changes.

- **Option C – Post-merge by theme**  
  After Louvain, optionally merge modules that share the same dominant theme (e.g. two “PI3K” clusters become one). Simpler but depends on theme mapping quality.

**Recommendation:** Implement Option A (lower default threshold) and Option B (Louvain resolution parameter, default e.g. 0.8). Document in CLI/help that `--similarity-threshold` and a new `--cluster-resolution` (or similar) can be adjusted to target 3–5 modules.

---

## 2. Canonical themes (pathway_theme_mapping.json)

In [pathway_theme_mapping.json](packages/methylenricher/methyl_enricher/data/pathway_theme_mapping.json):

- **Add theme: “Calcium / GPCR signaling”**  
  Patterns: calcium, GPCR, G-protein, neuroendocrine, CAMK, ITPR, CACNA, GRM, VIPR, calmodulin, etc., so neuroendocrine/calcium pathways map here.

- **Add theme: “RTK / MAPK signaling”**  
  Patterns: MAPK, ERK, RTK, MET, BRAF, RAF, MEK (without duplicating PI3K-specific ones already mapped). Ensure EGFR/MET/BRAF-axis pathways map to this or a single RTK/MAPK theme.

- **Keep/align existing:**  
  - WNT, beta-catenin, HOXA, SHH → “WNT / developmental”.  
  - EMT, cytoskeleton, ECM, invasion → “EMT / invasion” (can alias or merge with current “TGF-beta / EMT” and “ECM / adhesion / migration” for the module label).  
  - HLA, cytokine, T-cell, etc. → “Immune signaling” (already “Immune checkpoint / inflammatory”; optionally add a short alias for display).

- **canonical_pca_themes**  
  Extend the list to include “Calcium / GPCR signaling” and “RTK / MAPK signaling” so module labels and downstream logic can use these five hallmark-style themes.

Order of patterns matters (first match wins). Place the new Calcium/GPCR and RTK/MAPK patterns so they are not overridden by more generic terms.

---

## 3. Overlap genes in output

**Meaning:** “Overlap genes” = genes from the user’s input list that appear in a given pathway (or module), i.e. the Enrichr “Genes” column. These are the genes that “drive” that pathway/module in this run.

**Changes:**

- **modules_ranked.csv**
  - Add column **`Overlap_genes`**: full list of overlap genes for the module (union over pathways in the module), comma-separated. Optionally cap at 50 for readability.
  - Keep **`Main_genes`** as the top N overlap genes by weight (current behavior). So: Main_genes = top-weighted overlap genes; Overlap_genes = all overlap genes for the module (or a capped list). This makes “which genes drive this module” explicit.

- **Optional supplementary file (e.g. `pathway_overlap_genes.csv` or `pathway_overlap_genes.tsv`)**  
  Two columns: `Pathway` (Term name), `Overlap_genes` (comma-separated genes from Enrichr “Genes” for that pathway). Written only when `--modules` is used. Gives per-pathway “which genes drive this pathway” as in the user example (e.g. “Calcium signaling pathway” with CAMK2B, ITPR3, CACNA2D1, GRM3, VIPR2).

Implementation in [module_pipeline.py](packages/methylenricher/methyl_enricher/module_pipeline.py): (1) when building each module row, set `Overlap_genes` from the union of `pathway_to_genes` for that module (and optionally cap); (2) optionally build a small DataFrame from merged_df Term + Genes and write `pathway_overlap_genes.csv` (or .tsv) in the same output dir.

---

## 4. Summary of file changes

| File | Change |
|------|--------|
| [pathway_graph.py](packages/methylenricher/methyl_enricher/pathway_graph.py) | Add `resolution` argument to `cluster_pathways_louvain`; pass through `run_pathway_clustering`. |
| [module_pipeline.py](packages/methylenricher/methyl_enricher/module_pipeline.py) | Lower default `similarity_threshold` (e.g. to 0.15); add `cluster_resolution` (default e.g. 0.8); add `Overlap_genes` column to module table; optionally write `pathway_overla