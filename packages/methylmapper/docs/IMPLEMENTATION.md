# MethylMapper Implementation Notes

## Canonical Theory

For formulas, assumptions, and caveats, see [`docs/theory/chapters/07-methylmapper.qmd`](../../../docs/theory/chapters/07-methylmapper.qmd).

## Main Code Paths

- `methyl_mapper/bedtools_mapper.py`: interval mapping, per-gene aggregation, biological importance scoring.
- `methyl_mapper/mapper.py`: Azure SQL upload and stored-procedure orchestration.
- `methyl_mapper/gene_disease_enricher.py`: external disease-evidence enrichment, caching, and threshold profiles.
- `methyl_mapper/project_resolver.py`: project-config integration.
- `methyl_mapper/secure_credentials.py`: local encrypted cache and optional cloud secret resolution.

## Implementation Notes

- Bedtools-style mapping and Azure SQL mapping are separate operational paths.
- Gene-level aggregation is performed after mapping, not during detector-side DMP testing.
- Disease enrichment is an annotation layer and may depend on network availability, credentials, and cache state.

## Additional Package Guides

- [`../BEDTOOLS_MAPPER_README.md`](../BEDTOOLS_MAPPER_README.md)
- [`../QUICK_START.md`](../QUICK_START.md)
- [`../INSTALLATION.md`](../INSTALLATION.md)
