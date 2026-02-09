# MethylEnricher: Functionality and Expected Output After MethylMapper

This document describes what MethylEnricher does when run **after MethylMapper**, what input it expects, and what output it produces.

---

## 1. Pipeline position

```
MethylDetector  →  MethylMapper  →  MethylEnricher
(DMPs + models)    (DMPs → genes)   (genes → pathways/ontology)
```

- **MethylMapper** consumes MethylDetector DMP CSVs, maps DMPs to genes (e.g. via bedtools + GTF), and writes gene-level tables such as **`all-gene_name-combined.csv`** (and optionally disease-enriched columns).
- **MethylEnricher** takes that gene table (or a plain gene list), optionally filters and ranks genes, then runs **Over-Representation Analysis (ORA)** using **Enrichr** to find enriched pathways, ontologies, and gene sets.

---

## 2. Functionality

### 2.1 Purpose

MethylEnricher answers: **“Which pathways, Gene Ontology terms, and gene sets are over-represented in my list of genes?”**  
It uses the **Enrichr** API (via the **gseapy** library) to perform ORA: given a list of gene symbols, it tests each Enrichr library and returns terms whose gene sets overlap the input list more than expected by chance.

### 2.2 Input options

| Input type | Description |
|------------|-------------|
| **MethylMapper combined CSV** | Preferred after MethylMapper. Typically **`all-gene_name-combined.csv`** (or `all-gene_id-combined.csv`) from MethylMapper’s `mapped_features/` directory. |
| **Plain gene list** | A text file with one gene symbol per line (e.g. `example_genes.txt`). |

For CSV input, the tool:

1. **Loads** the table and identifies the gene column (e.g. `gene_name`, `gene_symbol`, or `gene_id`).
2. **Optionally filters** rows using MethylMapper-derived columns (disease association, DMP counts, gene q-value, effect size, gene_z, gene importance, feature type).
3. **Optionally sorts** by a numeric column (e.g. `total_weight`, `gene_importance`) and takes the **top N** genes.
4. **Extracts** a unique list of gene symbols and runs Enrichr on that list.

So “functionality after MethylMapper” = **use MethylMapper’s gene table as the gene list**, with optional filters and ranking so enrichment is focused on **disease-relevant and/or high-signal genes**.

### 2.3 Filtering (MethylMapper CSV only)

When the input is a MethylMapper combined CSV, the following filters can be applied **before** building the gene list sent to Enrichr. Only columns that exist are used.

| Filter | CLI option | Column(s) | Effect |
|--------|------------|-----------|--------|
| Disease-associated only | `--disease-only` | `disease_associated` | Keep rows where `disease_associated == True` |
| Association type | `--disease-association-type direct indirect` | `disease_association_type` | Keep only listed types |
| Min evidence level | `--min-disease-evidence-level medium` | `disease_evidence_level` | Keep high, medium (or low if set) |
| Min publications | `--min-disease-publications 2` | `disease_publications` | Minimum publication count |
| Min disease score | `--min-disease-score 0.2` | `disease_score` | Minimum Open Targets (or source) score |
| Min DMP count | `--min-dmp-count 2` | `dmp_count` | Minimum DMPs per gene |
| Min unique DMPs | `--min-unique-dmps 1` | `unique_dmps` | Minimum unique DMPs |
| Max gene q-value | `--max-gene-q-value 0.05` | `gene_q_value` | Keep genes with q ≤ threshold |
| Min effect size | `--min-mean-effect-size 0.3` | `mean_effect_size` / `total_weight` | Minimum signal strength |
| Min \|gene_z\| | `--min-gene-z 1.5` | `gene_z` | Minimum absolute combined z-score |
| Min gene importance | `--min-gene-importance 0.5` | `gene_importance` / `total_importance` / `total_weight` | Minimum importance |
| Feature types | `--feature-types gene exon` | `feature_type` | Keep only listed feature types |

### 2.4 Sorting and top-N

- **Sort column**: For CSV input, you can set `--sort-by` (e.g. `total_weight`, `gene_importance`). If not set, the code auto-uses `total_weight` or `gene_importance` when present.
- **Sort order**: Default is descending (highest weight/importance first); use `--sort-ascending` for ascending.
- **Top N**: After filtering and sorting, only the first **`--top N`** genes (default 200) are sent to Enrichr. This keeps the gene list size manageable and focuses on the most relevant genes.

### 2.5 Enrichment analysis

- **Method**: Over-Representation Analysis (ORA) via **Enrichr** (using **gseapy**).
- **Libraries**: By default, several Enrichr libraries are queried (e.g. KEGG_2021_Human, Reactome_2022, GO_Biological_Process_2023, GO_Molecular_Function_2023, GO_Cellular_Component_2023, MSigDB_Hallmark_2020, WikiPathway_2023_Human). You can override with `--libraries`.
- **Organism**: Default `Human`; change with `--organism`.
- **Cutoff**: Results are filtered for reporting by adjusted p-value (Enrichr’s “Adjusted P-value”, used as q-value) ≤ `--cutoff` (default 0.05). All terms are stored; the “top” file contains only significant ones.

---

## 3. Expected input (after MethylMapper)

### 3.1 Primary input file

- **Path**: Typically the combined gene table produced by MethylMapper, e.g.  
  `mapped_features/all-gene_name-combined.csv`  
  or, if using gene IDs,  
  `mapped_features/all-gene_id-combined.csv`.

### 3.2 Expected columns (when using MethylMapper CSV)

- **Required for gene list**: A column containing gene symbols (or IDs), e.g. **`gene_name`** or **`gene_id`**. The tool auto-detects from: `gene_name`, `gene_symbol`, `gene`, `symbol`, `gene_id`.
- **Optional (used only if present)**:
  - `disease_associated`, `disease_association_type`, `disease_evidence_level`, `disease_publications`, `disease_score`
  - `dmp_count`, `unique_dmps`
  - `gene_q_value`, `gene_z`, `gene_importance`, `total_weight`, `total_importance`
  - `mean_effect_size`, `feature_type`

If MethylMapper was run **with disease enrichment**, the CSV will contain the disease columns and filtering options like `--disease-only` and `--min-disease-score` will apply. If run without disease enrichment, those columns are absent and disease filters are skipped.

---

## 4. Expected output

All output is written under the directory given by **`--outdir`** (default `results`). The following files are produced.

### 4.1 Per-library result files

- **File pattern**: `enrich_<LibraryName>.csv`
- **Example**: `enrich_KEGG_2021_Human.csv`, `enrich_Reactome_2022.csv`, …
- **Contents**: Full Enrichr result table for that library. Typical columns (from gseapy/Enrichr):
  - `Term`, `Gene_set`, `Overlap`, `P-value`, `Adjusted P-value`, `Old P-value`, `Old Adjusted P-value`
  - `Z-score`, `Combined Score`, `Genes`, `Adjusted P-value` (q-value)
  - Plus any library-specific fields.
- **Use**: Inspect which pathways/terms are enriched in each database separately.

### 4.2 Merged results

- **File**: `enrichment_merged.csv`
- **Contents**: All per-library result tables concatenated, with an extra column **`library`** indicating the source library. Sorted by `Adjusted P-value` (ascending), then `P-value` (ascending), then `Odds Ratio` (descending).
- **Use**: Single table for all libraries; filter or pivot by `library` as needed.

### 4.3 Top significant hits

- **File**: `enrichment_top_q<cutoff>.csv`  
  Example: `enrichment_top_q0.05.csv` when `--cutoff 0.05`.
- **Contents**: Rows from the merged table where **`Adjusted P-value` ≤ cutoff**, limited to the top 200 such terms (by the same sort order). This is the “summary” of significant enrichments.
- **Use**: Quick view of the most significant pathways/terms across all libraries.

### 4.4 Console summary

At the end of the run, a short summary is printed:

- Total terms tested (number of rows in merged results).
- Number of significant terms (q ≤ cutoff).
- Per-library counts of significant terms.
- Top 5 most significant terms (Term name, library, q-value, Overlap, Odds Ratio).

---

## 5. Example workflow (MethylMapper → MethylEnricher)

1. **Run MethylMapper** (e.g. bedtools path) on MethylDetector DMP CSVs; ensure the combined table is produced, e.g.  
   `mapped_features/all-gene_name-combined.csv`.  
   Optionally run with disease enrichment so that `disease_associated`, `disease_score`, etc. are present.

2. **Run MethylEnricher** with that CSV:
   ```bash
   methyl_enricher --input mapped_features/all-gene_name-combined.csv \
                  --gene-column gene_name \
                  --outdir enricher_results
   ```
   Or with filters and top-N for a focused list:
   ```bash
   methyl_enricher --input mapped_features/all-gene_name-combined.csv \
                  --gene-column gene_name \
                  --disease-only \
                  --min-disease-score 0.2 \
                  --max-gene-q-value 0.05 \
                  --sort-by total_weight \
                  --top 150 \
                  --outdir enricher_results
   ```

3. **Inspect output** in `--outdir`:
   - `enrich_*.csv` — per-library details.
   - `enrichment_merged.csv` — all terms, all libraries.
   - `enrichment_top_q0.05.csv` — significant terms only (up to 200).

---

## 6. Dependencies

- **gseapy**: Used to call Enrichr and process results. Install with: `pip install gseapy`
- **Network access**: Enrichr is queried via the internet; the machine must have connectivity to the Enrichr API.

---

## 7. References in code

- **Input loading and filtering**: `methyl_enricher/enricher.py` — `EnrichmentAnalyzer.load_gene_list()`, `_apply_csv_filters()`.
- **Enrichment and output**: `methyl_enricher/enricher.py` — `EnrichmentAnalyzer.run_enrichment()` (per-library CSV, merged CSV, top-hits CSV, console summary).
- **CLI**: `methyl_enricher/cli.py` — all `--input`, `--gene-column`, filter, and `--outdir`/`--top`/`--cutoff` options.
