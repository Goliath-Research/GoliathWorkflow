# MethylMapper Usage

## CLI Entry Points

The package exposes:

- `methyl-mapper`
- `methyl_mapper`
- `methyl_mapper_bedtools`

## Typical Workflows

### SQL-backed mapping

Use `methyl-mapper` when your workflow relies on the Azure SQL mapping path configured for this package.

### Bedtools-backed mapping

Use `methyl_mapper_bedtools` when you want interval-based mapping from detector output to genes and genomic regions without the Azure SQL stored procedure.

## Inputs

Typical runs require:

- detector output or DMP tables,
- a GTF or region-annotation source for bedtools mapping,
- project configuration and output directories,
- credentials only when using protected services or databases.

## Outputs

Depending on the chosen path, the package can emit:

- mapped DMP-to-gene tables,
- per-gene aggregated scores and q-values,
- disease-evidence summaries,
- cacheable intermediate artifacts for downstream enrichment.

## Related Documentation

- Theory: [`THEORY.md`](THEORY.md)
- Implementation: [`IMPLEMENTATION.md`](IMPLEMENTATION.md)
- Operational guides: [`../BEDTOOLS_MAPPER_README.md`](../BEDTOOLS_MAPPER_README.md), [`../QUICK_START.md`](../QUICK_START.md)
