# MethylMapper Biological Importance Audit (Genes and Features)

## Purpose

This note audits current gene/feature scoring in `MethylMapper`, identifies duplication risk introduced by interval intersections, and defines an implementation-ready redesign for biological-importance measures aligned with DMP `effect_size`.

Primary code reference: [`packages/methylmapper/methyl_mapper/bedtools_mapper.py`](../methyl_mapper/bedtools_mapper.py)

---

## 1) Current metrics inventory

## Join-level and row-level weights

- `weight` (row-level, heuristic+statistical mix)
  - Built in `_join_with_dmp_weights()`.
  - Formula:
    - start at `1.0`
    - multiply by `p_weight` (`-log10(p)` or `1/p`)
    - multiply by `q_weight` (`-log10(q)`)
    - multiply by `eff_weight = |effect_size|` (or fallback proxy)
    - normalize by global row max (within current intersect frame)
  - Interpretation: prioritization weight, not an effect-size estimate.

- `combined_weight` (SP-region mode)
  - Formula: `weight * region_weight` (when SP-equivalent regions are used).

## Aggregated gene/feature outputs (current)

- `dmp_count`: count of intersect rows per group.
- `unique_dmps`: count of unique `dmp_name` per group.
- `total_weight`: sum of row `weight`.
- `mean_weight`, `max_weight`: summary of row `weight`.
- `mean_effect_size`, `max_effect_size`: group summaries from row `effect_size`.
- `gene_p_value`, `gene_q_value`, `gene_z`: signed weighted Stouffer aggregation (approximate dependence assumption).

## Feature-distribution metrics (exclusive per `(group, dmp_name)`)

- Exclusive row selection by priority:
  - `promoter > exon > intron > gene_body > terminator`
  - Implemented by `_exclusive_feature_rows()`.

- `hits_*` (`hits_promoter`, `hits_exon`, ...):
  - Count of exclusive DMP assignments per parent feature.

- `gene_feature_score` (count-based):
  - `2.0*hits_promoter + 1.5*hits_exon + 0.7*hits_intron + 1.0*hits_gene_body + 0.5*hits_terminator`
  - Heuristic count score.

- `effect_size_*`, `direction_*`, `direction_balance_*`:
  - Built by `_build_feature_effect_scores()`.
  - For each feature, directionalized effect is computed from signed `effect_size`.
  - Exon/intron use segment-first aggregation (`feature_start`, `feature_end`) to reduce segment mixing artifacts.

- `gene_feature_importance` (effect-based weighted composition):
  - `w_promoter*effect_size_promoter + w_exon*effect_size_exon + w_intron*effect_size_intron + w_gene_body*effect_size_gene_body + w_terminator*effect_size_terminator`

- `gene_importance` (current canonical ranking):
  - Fallback chain:
    1. `gene_feature_importance`
    2. `gene_score`
    3. `total_weight`

- `gene_score` (current domain score):
  - Computed from exclusive rows when available, else all rows.
  - Formula:
    - `sum( |effect_size| * frequency * region_weight )`
  - Stability-like inputs enforce strict `frequency in [0,1]`.

---

## 2) Duplication risk audit

## Where duplication is expected and meaningful

- A DMP can overlap multiple genes and should contribute to each gene (biologically plausible multi-gene attribution).
- A DMP can overlap multiple feature annotations; parent-bucket assignment should avoid over-counting within gene.

## Where duplication can bias importance

- Raw intersection rows before exclusivity can over-inflate:
  - `dmp_count`
  - `total_weight`
  - `mean_effect_size` (if one DMP appears many times in detailed subfeatures)
- Non-exclusive aggregations can overweight annotation-dense genes compared with sparse-annotation genes.

## Current mitigation

- Feature-level and `gene_score` use `_exclusive_feature_rows()` (one row per `(group, dmp)`), which is good.
- But some aggregate stats (`total_weight`, `mean_effect_size`, row counts) are still computed pre-exclusivity and remain sensitive to row multiplicity.

---

## 3) Recommended dedup keys by metric family

- **Gene biological-effect metrics**:
  - Dedup key: `(gene_name_or_id, dmp_name)`

- **Feature biological-effect metrics**:
  - Dedup key: `(gene_name_or_id, feature_parent_bucket, dmp_name)`
  - Parent bucket in `{promoter, exon, intron, gene_body, terminator}`

- **Statistical aggregation metrics (`gene_p_value`, `gene_q_value`)**:
  - Keep weighted Stouffer path, but document dependence caveat and expose effective-contributor counts.

- **Descriptive raw intersection metrics**:
  - Keep row-based columns only when needed for diagnostics; do not use them as canonical biological-importance measures.

---

## 4) Recommended biological-importance family (DMP-like)

Use DMP `effect_size` as the core biological signal and keep p/q-based quantities as orthogonal confidence/statistics.

For each gene `g`, over deduped unique mapped DMPs indexed by `i`:

- `e_i = effect_size_i`
- `s_i = sign(delta_mean_i)` when available, else inferred direction
- `w_i = frequency_i * region_weight_i` (or `1 * region_weight_i` outside stability/freeze)

Recommended components:

- `gene_effect_abs_wmean = sum(w_i * |e_i|) / sum(w_i)`
- `gene_effect_abs_wsum = sum(w_i * |e_i|)` (burden/size-sensitive)
- `gene_effect_signed_wsum = sum(w_i * s_i * |e_i|)` (signed burden)
- `gene_direction = sign(gene_effect_signed_wsum)` (hyper/hypo direction)
- `gene_direction_coherence = |sum(w_i * s_i * |e_i|)| / sum(w_i * |e_i|)`
- `gene_support_n = number of unique mapped DMPs`
- `gene_support_freq = mean(frequency_i)` (or recurrence-derived support from panel)

## Primary recommendation

Use the following as primary biological-importance score:

- `gene_importance = gene_effect_abs_wsum * gene_direction_coherence * sqrt(gene_support_freq)`

Why this one:

- Preserves DMP-scale biological effect (`|effect_size|`).
- Penalizes directional inconsistency (mixed hyper/hypo signal).
- Rewards reproducibility/support (frequency).
- Explicitly scales with burden (more concordant DMP support -> larger importance).

Keep `gene_effect_compound` as a secondary, mean-normalized diagnostic.

---

## 5) Feature-level recommendation

Apply the same pattern per parent feature bucket:

- `feature_effect_abs_wmean_<bucket>`
- `feature_direction_coherence_<bucket>`
- `feature_effect_signed_wsum_<bucket>`
- `feature_direction_<bucket>`
- `feature_importance_<bucket> = sum(w_i * |e_i|)_<bucket> * feature_direction_coherence_<bucket> * sqrt(feature_support_freq_<bucket>)`
- `feature_effect_compound_<bucket> = feature_effect_abs_wmean_<bucket> * feature_direction_coherence_<bucket> * sqrt(feature_support_freq_<bucket>)`

For whole-gene composition from features, keep a separate weighted composite:

- `gene_feature_effect_compound = w_promoter*feature_effect_compound_promoter + ... + w_terminator*feature_effect_compound_terminator`

This must be separate from existing `gene_feature_importance`.

---

## 6) Column design (canonical replacement)

Use compound-effect columns as canonical outputs for biological-importance ranking:

- `gene_effect_abs_wmean`
- `gene_effect_abs_wsum`
- `gene_effect_signed_wsum`
- `gene_direction`
- `gene_direction_coherence`
- `gene_support_n`
- `gene_support_freq`
- `gene_importance` (primary biological importance; count-aware burden)
- `gene_effect_compound` (secondary mean-normalized companion)
- `gene_feature_effect_compound` (feature-composed companion)
- `feature_importance_<bucket>`
- `feature_direction_<bucket>`
- `feature_effect_signed_wsum_<bucket>`

Optional convenience:

- `gene_importance_rank`

Canonical ranking field:

- `gene_importance := gene_effect_abs_wsum * gene_direction_coherence * sqrt(gene_support_freq)`

Legacy columns (`gene_score`, `gene_feature_importance`, row-density summaries) may remain available for traceability, but they are no longer canonical ranking fields.

---

## 7) Implementation checklist

## Code

- [`packages/methylmapper/methyl_mapper/bedtools_mapper.py`](../methyl_mapper/bedtools_mapper.py)
  - Add explicit deduped intermediate table for gene effect metrics.
  - Compute canonical `*_compound` columns from deduped contributions.
  - Keep legacy columns untouched.
  - Add comments marking legacy vs canonical biological importance.

## Tests

- [`packages/methylmapper/tests/test_gene_stat_export.py`](../tests/test_gene_stat_export.py)
  - Add tests for dedup policy (`(gene,dmp)` and `(gene,feature,dmp)` behavior).
  - Add tests for `gene_effect_compound` monotonic behavior with:
    - higher effect size,
    - higher coherence,
    - higher support.
  - Add regression test ensuring legacy columns remain unchanged.

## Docs

- [`packages/methylmapper/docs/IMPLEMENTATION.md`](IMPLEMENTATION.md)
  - Document new columns and formulas.
  - Clarify which columns are legacy heuristic vs canonical biological-effect.

---

## 8) Suggested adoption strategy

1. Promote count-aware `gene_importance` as the canonical ranking field.
2. Validate against known stage markers/pathways and progression monotonicity.
3. Keep legacy fields for diagnostics only, not for ranking semantics.
