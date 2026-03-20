# MethylEnricher Usage

## CLI Entry Points

The package exposes:

- `methyl-enricher`
- `methyl_enricher`

Both resolve to `methyl_enricher.cli:main`.

## Typical Inputs

Typical runs start from:

- mapped genes or weighted gene lists from `methylmapper`,
- optional disease-specific prior genes,
- a selected set of Enrichr libraries and pathway-theme mappings.

## Typical Outputs

The package can emit:

- filtered enrichment result tables,
- pathway-overlap graphs,
- module rankings,
- disease-relevance summaries and pathway-theme labels.

## Related Documentation

- Theory: [`THEORY.md`](THEORY.md)
- Implementation: [`IMPLEMENTATION.md`](IMPLEMENTATION.md)
