---
name: SP vs BEDTOOLS results validation
overview: Confirm that MethylMapper's STRING-DB stored procedure (spMapDMP2Genes) and the BEDTOOLS path produce similar gene-mapping results when using the same parameter set. This requires aligning inputs (sample_dmps format and param row), optionally extending BedtoolsMapper to support the SP's region model and weights, and adding a comparison script or test.
todos:
  - id: upload-sample-dmps
    content: Switch DB upload from dmp_staging to sample_dmps; derive p_value, weight, direction; register sample in Samples
  - id: bedtools-all-contexts
    content: Make BEDTOOLS process all contexts per chromosome (single run per chr)
  - id: bedtools-all-features
    content: Add SP-equivalent regions (promoter, terminator, gene body, exon, intron, unknown) and region weights to BedtoolsMapper
  - id: storey-auto-lambda
    content: Use automatic Storey lambda by default in BEDTOOLS; optional fixed lambda for SP parity tests
  - id: comparison-script
    content: Add comparison script (gene set overlap, p/q correlation, direction) for SP vs BEDTOOLS outputs
isProject: false
---

# Plan: Confirm SP vs BEDTOOLS Results Match for Same Parameters

## Current state

**Stored procedure ([spMapDMP2Genes.sql](packages/methylmapper/methyl_mapper/spMapDMP2Genes.sql))**
- Reads DMPs from **`dbo.sample_dmps`** (columns: `sample_id`, `chromosome`, `context`, `position`, `p_value`, `weight`, `direction`).
- Loads region sizes and weights from **`dbo.params`** by `@paramID`: `upstream_size`, `downstream_size`, `min_intron_size`, `w_promoter`, `w_terminator`, `w_gene_body`, `w_exon`, `w_intron`, `w_unknown`, `max_gap`, `lambda`.
- Builds **weighted regions**: gene body, promoter (upstream), terminator (downstream), exon and intron (only for genes with a body hit), and unknown (unmapped DMPs grouped by `max_gap`).
- Maps each DMP to a region; **combined weight** = `region_weight * d.weight`.
- **Stouffer**: `signed_Z = direction * NormalCDFInverse(1 - p_value/2)`; gene p-value from `sum(combined_weight * signed_Z) / sqrt(sum(combined_weight^2))`.
- **Storey FDR** using the single `lambda` from params for π₀.
- Writes to **`dbo.sample_genes`** (`sample_id`, `chromosome`, `gene_id`, `gene_name`, `p_value`, `q_value`, `direction`, `strand`).

**BEDTOOLS path ([bedtools_mapper.py](packages/methylmapper/methyl_mapper/bedtools_mapper.py))**
- Input: DMP CSV with `chromosome`, `position`; optional `p_value`, `q_value`, `delta_mean`, `effect_size`, etc.
- **Intersects only** with GTF features; default `feature_types = ['gene']` (gene body only). **No** promoter/terminator extension, no exon/intron/unknown regions, no region-type weights.
- **Weight** = product of p_value, q_value, and effect_size-based terms (no `w_promoter`, etc.).
- **Stouffer**: same formula (signed Z by `delta_mean`, weighted combination).
- **Storey**: `storey_qvalues()` with default lambda grid (median π₀), not a single fixed lambda.

**Azure Python path ([mapper.py](packages/methylmapper/methyl_mapper/mapper.py), [database.py](packages/methylmapper/methyl_mapper/database.py))**
- Currently uploads to `dmp_staging`; SP reads from `sample_dmps`. These will be aligned (see below).

---

## Agreed direction (user clarifications)

1. **Python pipeline uploads to `sample_dmps`** (replacing the old `dmp_staging` flow) as part of creating/using a new `sample_id`. The DB path will write directly to `sample_dmps` with columns: `sample_id`, `chromosome`, `context`, `position`, `p_value`, `weight`, `direction`.
2. **paramID = 1** already contains the default values (5000, 2000, 0, 2, 0.5, 1, 1.5, 0.7, 1, 1, 0.4); no change needed.
3. **BEDTOOLS must process all contexts per chromosome** (like `spMapDMP2Genes`), not per-context. So for each chromosome, aggregate DMPs across all contexts (e.g. CG, CHG, CHH) in one run, then map to genes.
4. **BEDTOOLS should use all genomic features**: promoter, terminator, gene body, exon, intron, and unknown regions (SP-equivalent), not just gene features.
5. **Comparison** should show similar results so the validation looks correct (same logic on both sides).
6. **Storey λ**: Prefer **automatic** calculation of λ (e.g. median π₀ over a λ grid, as in `storey_qvalues`) rather than a fixed parameter; can be the default, with optional override for SP parity testing.

---

## Implementation summary

- **DB path**: Switch upload target from `dmp_staging` to `sample_dmps`; derive `p_value`, `weight`, `direction` from CSV (e.g. `weight = -log10(p_value)` or from effect_size; `direction = sign(delta_mean)`); ensure new sample is registered in `Samples` with correct `species_id`.
- **BEDTOOLS path**: (a) Process **all contexts per chromosome** (single run per chromosome, DMPs from all contexts). (b) Add **SP-equivalent region model**: build promoter, terminator, gene body, exon, intron, unknown from GTF + params; apply region weights; use **auto λ** for Storey by default (optional param λ for comparison). (c) Output schema aligned to `sample_genes` for comparison.
- **Comparison script**: Compare SP vs BEDTOOLS outputs (gene set overlap, p/q correlation, direction agreement) to confirm similarity.

---

## Which algorithm is best to map DMPs to genes?

**Recommendation: use the same algorithm in both implementations; prefer the BEDTOOLS (local) implementation as the primary reference.**

- **Same algorithm**: The “best” mapping is the **shared design**: weighted regions (promoter, terminator, gene body, exon, intron, unknown), region weights, DMP weight × region weight, weighted Stouffer for gene p-value, and Storey FDR for q-value. Once BEDTOOLS is extended to match the SP’s region model and weights, both paths implement the same algorithm; the only difference is where it runs (SQL vs local GTF + bedtools).
- **Why prefer BEDTOOLS (local) as primary**:
  - **Portability**: No Azure/STRING-DB dependency; runs anywhere with a GTF and bedtools.
  - **Reproducibility**: Single codebase and GTF file; easier to version and rerun.
  - **Flexibility**: Auto λ (and optional fixed λ), per-chromosome all-context runs, and future tweaks are easier in Python than in T-SQL.
  - **Validation**: Implementing the same logic in both SP and BEDTOOLS gives a direct comparison; once they agree, the BEDTOOLS path can be the canonical implementation for new development.
- **When to keep the SP**: Keep the stored procedure when you need to run inside STRING-DB (e.g. integration with other DB tools, or operations that must stay in Azure). Use it in parallel with BEDTOOLS for comparison; long term, new features (e.g. auto λ, new regions) can be added in BEDTOOLS first and, if needed, mirrored in the SP.

**Bottom line**: The best algorithm is the **unified design** (all regions + weights + Stouffer + Storey). Implement it in BEDTOOLS with auto λ and all-context-per-chromosome as the main path; keep the SP for DB-centric workflows and use the comparison to ensure both stay in sync.