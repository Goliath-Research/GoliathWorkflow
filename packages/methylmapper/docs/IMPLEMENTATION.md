# MethylMapper Implementation Notes

## Canonical Theory

For formulas, assumptions, and caveats, see [`docs/theory/chapters/07-methylmapper.qmd`](../../../docs/theory/chapters/07-methylmapper.qmd).

## Main Code Paths

- `methyl_mapper/bedtools_mapper.py`: **canonical** interval mapping (default: all GTF feature types), per-gene aggregation with exclusive per-(DMP,gene) feature-hit summaries (`hits_*`), optional auxiliary BED overlaps and `bedtools closest` to nearest gene, biological importance scoring.
- `methyl_mapper/mapper.py`: Azure SQL upload and stored-procedure orchestration (legacy / comparison).
- `methyl_mapper/gene_disease_enricher.py`: Grok (synchronous annotation by default) + Open Targets (evidence and scores); DisGeNET only if explicitly enabled; caching and threshold profiles.
- `methyl_mapper/project_resolver.py`: project-config integration.
- `methyl_mapper/secure_credentials.py`: local encrypted cache and optional cloud secret resolution.

## Implementation Notes

- **Bedtools** is the primary mapping path for new WGBS work; Azure SQL SP remains available for backfill or parity checks.
- By default the GTF intersect keeps **every** `feature` type; restrict with `feature_types` / `--feature-types`.
- Gene-level aggregation emits a slimmed schema for downstream enrichment (`gene_name`, `gene_id`, `unique_dmps`, `mean_effect_size`, `gene_effect_size`, `gene_effect_signed_wsum`, `gene_direction`, `gene_score`, `gene_effect_compound`, `gene_feature_effect_compound`, `feature_importance_*`, `feature_direction_*`, `feature_effect_signed_wsum_*`, `hits_*`, `gene_p_value`, `gene_q_value`, disease subset, links). Feature hits are built from **exclusive** per-(DMP,gene) assignment with priority `promoter > exon > intron > gene_body > terminator`.
- Canonical biological-importance ranking now uses a count-aware burden (`gene_importance = gene_effect_abs_wsum * gene_direction_coherence * sqrt(gene_support_freq)`), while `gene_effect_compound` remains as a mean-normalized companion diagnostic.
- Stability/fixed-panel `gene_score` uses strict frequency validation (`frequency` required and bounded in `[0,1]`). Non-stability inputs retain neutral fallback `frequency=1.0`.
- Disease enrichment: merged outputs use **Open Targets** for association evidence and scores; **Grok** supplies narrative annotation (`grok_annotation_summary`, `gene_basic_description`). Grok defaults to **single-threaded** synchronous `chat/completions` (batch size ≤ 20); xAI Batch API is opt-in.
- Optional **auxiliary BED** files (e.g. enhancers, ChIP) add per-DMP overlap columns; **`--closest-gene`** adds nearest gene body distance from the GTF.
- Disease enrichment is an annotation layer and may depend on network availability, credentials, and cache state.

## Additional Package Guides

- [`../BEDTOOLS_MAPPER_README.md`](../BEDTOOLS_MAPPER_README.md)
- [`../QUICK_START.md`](../QUICK_START.md)
- [`../INSTALLATION.md`](../INSTALLATION.md)
