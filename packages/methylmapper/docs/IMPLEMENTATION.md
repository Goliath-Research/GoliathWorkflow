# MethylMapper Implementation Notes

## Canonical Theory

For formulas, assumptions, and caveats, see [`docs/theory/chapters/07-methylmapper.qmd`](../../../docs/theory/chapters/07-methylmapper.qmd).

## Main Code Paths

- `methyl_mapper/bedtools_mapper.py`: **canonical** interval mapping (default: all GTF feature types), per-gene aggregation with feature-mix summaries, optional auxiliary BED overlaps and `bedtools closest` to nearest gene, biological importance scoring.
- `methyl_mapper/mapper.py`: Azure SQL upload and stored-procedure orchestration (legacy / comparison).
- `methyl_mapper/gene_disease_enricher.py`: Grok (synchronous annotation by default) + Open Targets (evidence and scores); DisGeNET only if explicitly enabled; caching and threshold profiles.
- `methyl_mapper/project_resolver.py`: project-config integration.
- `methyl_mapper/secure_credentials.py`: local encrypted cache and optional cloud secret resolution.

## Implementation Notes

- **Bedtools** is the primary mapping path for new WGBS work; Azure SQL SP remains available for backfill or parity checks.
- By default the GTF intersect keeps **every** `feature` type; restrict with `feature_types` / `--feature-types`.
- Gene-level aggregation includes `feature_types_hit`, `feature_type_counts`, and Stouffer/Storey statistics over **all** intersecting rows for that gene.
- Disease enrichment: merged outputs use **Open Targets** for association evidence and scores; **Grok** supplies narrative annotation (`grok_annotation_summary`, `gene_basic_description`). Grok defaults to **single-threaded** synchronous `chat/completions` (batch size ≤ 20); xAI Batch API is opt-in.
- Optional **auxiliary BED** files (e.g. enhancers, ChIP) add per-DMP overlap columns; **`--closest-gene`** adds nearest gene body distance from the GTF.
- Disease enrichment is an annotation layer and may depend on network availability, credentials, and cache state.

## Additional Package Guides

- [`../BEDTOOLS_MAPPER_README.md`](../BEDTOOLS_MAPPER_README.md)
- [`../QUICK_START.md`](../QUICK_START.md)
- [`../INSTALLATION.md`](../INSTALLATION.md)
