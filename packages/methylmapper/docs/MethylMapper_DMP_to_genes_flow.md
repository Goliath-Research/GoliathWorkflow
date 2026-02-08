# How MethylMapper Uses MethylDetector Output for Gene Mapping

This document describes how MethylMapper consumes MethylDetector DMP CSVs to identify genomic features (genes) and compute gene-level p-values and biological importance.

---

## 1. MethylDetector output MethylMapper expects

MethylDetector writes per-chromosome DMP CSVs to its `output_dir`, for example:

- `dmps-1.csv`, `dmps-2.csv`, … (final selected DMPs), or  
- `dmps-1-biological-sorted.csv`, … (pre-optimization, sorted by importance)

**Relevant columns** (from `_export_unified_csv` in MethylDetector):

| Column           | Description |
|------------------|-------------|
| `chromosome`     | Chromosome (e.g. `"1"`, `"X"`) |
| `context`        | Context (e.g. `"CG"`) |
| `position`       | Genomic position |
| `p_value`        | Per-DMP p-value |
| `q_value`        | Per-DMP q-value (FDR) |
| `delta_mean`     | Methylation difference (mean1 − mean2) |
| `overlap`        | Distribution overlap (e.g. Bhattacharyya-based) |
| `effect_size`    | Effect size used for ranking |
| `context_weight` | Context weight (if multi-context) |
| `alpha1`, `beta1`, `alpha2`, `beta2` | Beta parameters (centroid1, centroid2) |
| `mean1`, `mean2` | Centroid means |

If present, `importance` (biological importance from the detector) is also used by MethylMapper.

---

## 2. Two mapping paths in MethylMapper

### A. Azure SQL path (`DMPMapper` in `mapper.py`)

- **Input**: Same DMP CSV (required columns include `position`, `chromosome`, `context`, `q_value`, `delta_mean`, `overlap`, `effect_size`).
- **Flow**: Load CSV → upload to Azure SQL staging table → call stored procedure `spMapDMP2Genes` → save gene results to CSV/JSON.
- **Use case**: When you have the Azure SQL pipeline and stored procedure set up.

### B. Bedtools path (`BedtoolsMapper` in `bedtools_mapper.py`) – **focus for genes**

- **Input**: DMP CSV with at least `chromosome` and `position`. Optional but used when present: `p_value`, `q_value`, `effect_size`, `delta_mean`, `overlap`, `importance`, `alpha1`/`beta1`/`alpha2`/`beta2`.
- **Flow**:  
  1. Convert DMP CSV → BED (chrom, start, end, name).  
  2. Run `bedtools intersect` with a gene GTF/GFF.  
  3. Join intersections back to DMP table to attach p-value, q-value, effect_size/importance.  
  4. Aggregate by feature (e.g. by `gene_name`) to get gene-level stats and **gene p-value** / **biological importance**.

---

## 3. Identifying genes (Bedtools path)

1. **CSV → BED** (`csv_to_bed`):  
   - Required: `chromosome`, `position`.  
   - BED is 0-based: `start = position - 1`, `end = position`.  
   - Chromosome is normalized to `chr*` (e.g. `1` → `chr1`) to match typical GTFs.

2. **Intersect with GTF** (`intersect_with_features`):  
   - `bedtools intersect -a <DMP BED> -b <gene_gtf> -wa -wb`  
   - Each row is a (DMP, GTF feature) pair.  
   - GTF attributes are parsed for `gene_id`, `gene_name`, `transcript_id`, etc.

3. **Filter by feature type**:  
   - `feature_types` (default `['gene']`) restricts to rows where GTF `feature_type` is in that list (e.g. `gene` only).

4. **Join DMP weights** (`_join_with_dmp_weights`):  
   - For each intersection, the DMP is matched back to the CSV row on `(chromosome, position)` so that `p_value`, `q_value`, `effect_size`, `importance`, `delta_mean`, etc. are attached.

So “identifying genes” = DMPs that overlap a gene feature in the GTF, with optional use of transcripts/exons by changing `feature_types`.

---

## 4. Gene-level p-values (Bedtools path)

Implemented in `aggregate_by_feature()` in `bedtools_mapper.py`:

1. **Per-DMP weights** (used as Stouffer weights):  
   - `p_weight`: `-log10(p_value)` (or `1/p_value` if not log-transformed).  
   - `q_weight`: `-log10(q_value)`.  
   - `eff_weight`: from `importance`, or `effect_size`, or a derived biological importance (e.g. from `delta_mean`, `overlap`, and Beta variance).  
   - Combined weight = product of the enabled weights, then normalized.

2. **Stouffer’s method (signed, weighted)**:  
   - For each DMP in the gene: convert `p_value` to a z-score: `z = norm.ppf(1 - p_value/2)`, then apply sign of `delta_mean` → `signed_z`.  
   - Gene-level combined z:  
     `gene_z = sum(weight * signed_z) / sqrt(sum(weight^2))`.  
   - Gene-level p-value:  
     `gene_p_value = 2 * (1 - norm.cdf(|gene_z|))`.

3. **Gene-level q-value**:  
   - Storey’s FDR is applied across gene p-values to produce `gene_q_value` (see note below on import).

So gene p-values are **aggregated from the DMPs within that gene** via weighted Stouffer, using the DMPs’ p-values and directions (`delta_mean`).

---

## 5. Gene-level biological importance (Bedtools path)

- **Per DMP**: MethylMapper uses, in order of preference:  
  - `importance` from the DMP table, or  
  - `effect_size`, or  
  - a **biological importance** computed from `delta_mean`, overlap, and (if available) Beta variance:  
    `calculate_biological_importance(delta_mean, std, overlap, min_delta_mean=0.1, max_overlap=0.6)`  
    (bounded in [0, 1], higher when `|delta_mean|` is large and overlap is small).

- **Per gene**:  
  - `total_importance` = sum of DMP importances in that gene.  
  - `gene_importance` is set to `total_importance` (or, if missing, to `total_weight`).

So biological importance at the gene level is the **sum of the per-DMP importance** of DMPs falling inside that gene.

---

## 6. Summary table (Bedtools, gene-focused)

| Step              | What happens |
|-------------------|------------------------------------------------------------------|
| Input             | MethylDetector DMP CSV(s), e.g. `dmps-*-biological-sorted.csv` or `dmps-*.csv`. |
| DMP → BED         | `chromosome`, `position` → BED; optional `context`, `effect_size` in name. |
| Gene overlap      | `bedtools intersect` with GTF; keep rows with `feature_type == 'gene'` (or other `feature_types`). |
| DMP stats on gene | Join back to CSV to get `p_value`, `q_value`, `effect_size`/`importance`, `delta_mean`, etc. |
| Gene p-value      | Weighted Stouffer over DMP p-values (signed by `delta_mean`) → `gene_p_value`, then FDR → `gene_q_value`. |
| Gene importance   | Sum of per-DMP importance (or effect_size) over DMPs in the gene → `gene_importance` / `total_importance`. |

---

## 7. `storey_qvalues` import

Gene-level q-values use Storey’s FDR via `storey_qvalues` from `methyl_utils`. The import in `bedtools_mapper.py` uses `methyl_utils` (with fallback to `methyl_utils.statistical_tests`) so that gene q-values are computed without `NameError`.

---

## 8. References in code

- **Detector CSV export**: `methyldetector/methyl_detector/core/methyldetector.py` → `_export_unified_csv()` (columns and filenames).  
- **Mapper CSV load**: `methylmapper/methyl_mapper/mapper.py` → `load_dmps()` (required columns for SQL path); `bedtools_mapper.py` → `csv_to_bed()`, `_join_with_dmp_weights()` (required/optional columns for Bedtools path).  
- **Gene p-value and importance**: `methylmapper/methyl_mapper/bedtools_mapper.py` → `_join_with_dmp_weights()`, `aggregate_by_feature()` (Stouffer, `gene_importance`), and `calculate_biological_importance()`.
