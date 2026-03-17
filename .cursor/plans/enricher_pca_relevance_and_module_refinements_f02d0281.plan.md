---
name: Enricher PCa relevance and module refinements
overview: Improve PCa_relevance tiering with a curated map for top canonical modules, add a neuro/synaptic theme and optional collapse of overlapping neuro modules, flag or merge very small modules, and add a Main_theme short description column to the module table.
todos: []
isProject: false
---

# MethylEnricher: PCa relevance tiering and module refinements

## Goals (from user feedback)

1. **PCa_relevance no longer "Low" for everything** – Use a simple manual/literature-based tiering (Low/Medium/High) for the top 5–8 canonical modules so the story is sharper for manuscripts and talks.
2. **Collapse overlapping neuro/synaptic modules** – Map Long-term potentiation, neuronal system, calcium/GPCR, RTK/MAPK (NMDA-centric) into one or two higher-order neuro-signaling themes to avoid over-counting.
3. **Handle very small modules** – Single-gene or 2-gene modules near the bottom: either merge into larger functional groups or flag as "candidate" (noisy on their own).
4. **Main_theme column** – Add a short, human-readable theme description (e.g. "Calcium handling, GPCR and NMDA axes") to the module table for quick comparison.

---

## 1. PCa_relevance: curated tier for canonical modules

**Current behavior:** [module_scorer.py](packages/methylenricher/methyl_enricher/module_scorer.py) sets `pca_relevance` via `pca_relevance_label(disease_score)` where `disease_score` = fraction of module genes in `DEFAULT_PCA_RELEVANT_GENES`. With small overlap, almost all modules get "Low".

**Change:** Add a **curated override** for the top canonical themes so that known PCa-relevant modules get High/Medium regardless of overlap count.

- **Data:** In [pathway_theme_mapping.json](packages/methylenricher/methyl_enricher/data/pathway_theme_mapping.json) (or a small Python constant in `module_scorer.py`), add a map: theme label → PCa tier.
  - Example: `"pca_relevance_tier": { "Calcium / GPCR signaling": "High", "ECM / adhesion / migration": "High", "PI3K / growth-factor signaling": "High", "Immune signaling": "High", "RTK / MAPK signaling": "High", "WNT / developmental": "Medium", "EMT / invasion": "High", "Androgen / steroid metabolism": "High" }`.
- **Logic:** In `score_and_rank_modules` (or in [module_pipeline.py](packages/methylenricher/methyl_enricher/module_pipeline.py) when building the output table), after assigning the module label: if the **module label** (e.g. "Calcium / GPCR signaling") is in the curated tier map, set `pca_relevance` from that map; otherwise keep the current score-based `pca_relevance_label(disease_score)`.
- **Result:** Top canonical modules will show High/Medium as specified; other modules still use the computed tier. No change to `final_score` computation unless you also want to boost score by tier (optional).

---

## 2. Collapse neuro/synaptic modules

**Problem:** Long-term potentiation, neuronal system, calcium/GPCR, RTK/MAPK (with NMDA-centric pathways) appear as separate modules and over-count neuro signaling.

**Approach:**

- **Theme mapping:** In [pathway_theme_mapping.json](packages/methylenricher/methyl_enricher/data/pathway_theme_mapping.json), add patterns that map neuronal/synaptic/NMDA/LTP pathways to a **single** higher-order theme, e.g. **"Neuro / synaptic signaling"**:
  - Patterns (placed early so they match before generic "calcium" or "MAPK"): `long-term potentiation`, `long term potentiation`, `neuronal`, `synaptic`, `NMDA`, `glutamate receptor`, `neurotransmitter`, `synapse`.
  - This way, pathways like "Long-term potentiation" or "Neuronal system" get the label "Neuro / synaptic signaling" instead of falling through to more specific themes. Pathways that are purely "Calcium signaling" (no neuronal/synaptic in the name) still map to "Calcium / GPCR signaling".
- **Optional post-merge:** If desired, add a step in [module_pipeline.py](packages/methylenricher/methyl_enricher/module_pipeline.py): after clustering and labeling, **merge** any two modules whose labels are in a fixed set (e.g. `["Neuro / synaptic signaling", "Calcium / GPCR signaling"]`) into one module (e.g. take the union of pathways/genes and one label "Neuro / calcium signaling"). This is a stronger collapse and can be controlled by a flag (e.g. `--collapse-neuro-modules`). For a minimal first step, the theme mapping alone (one "Neuro / synaptic signaling" theme) already reduces fragmentation; the post-merge can be a follow-up.

**Recommendation:** Implement the new theme "Neuro / synaptic signaling" with the patterns above and add it to `canonical_pca_themes` and to the PCa relevance tier (e.g. High). Omit the post-merge unless you want to explicitly merge Calcium/GPCR and Neuro/synaptic into one table row.

---

## 3. Very small modules: flag or merge

**Problem:** Single-gene or 2-gene modules at the bottom are noisy.

**Options:**

- **A. Flag only:** Add a column **`module_type`** (or **`size_class`**) to `modules_ranked.csv`: e.g. `"core"` when `n_genes > 2` (and optionally `n_pathways >= 2`), and `"candidate"` when `n_genes <= 2`. No merging; users can filter or de-emphasize "candidate" in figures and text.
- **B. Merge:** After clustering, for each module with `n_genes <= 2` (or `n_pathways == 1` and `n_genes <= 2`), reassign its pathways to the **nearest** larger module (e.g. by shared theme, or by Jaccard similarity of gene sets). Then recompute scores and drop the tiny module. More invasive; needs a clear rule for "nearest".

**Recommendation:** Implement **Option A** first: add **`module_type`** with values `"core"` (e.g. `n_genes > 2`) and `"candidate"` (e.g. `n_genes <= 2`). Option B can be a later enhancement.

**Implementation:** In [module_pipeline.py](packages/methylenricher/methyl_enricher/module_pipeline.py), when building each row, se