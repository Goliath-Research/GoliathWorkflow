# MethylMapper

MethylMapper maps detector DMP exports onto genes and genomic features, then optionally enriches those mappings with disease-association metadata.

The supported workflow is the local bedtools-based flow driven by the shared project config.

## Supported Usage

Project-driven run:

```bash
methyl-mapper --project /path/to/project.json
```

Direct run:

```bash
methyl_mapper_bedtools --csv-pattern "/path/to/dmps-*.csv" --gtf /path/to/gencode.gtf --output-dir /path/to/out
```

## Canonical Inputs And Outputs

With `--project`, MethylMapper reads detector exports from:

```text
detections/<control_group>/<disease_group>/
```

and writes mapping outputs to:

```text
mapper/<control_group>/<disease_group>/
```

Typical outputs include:

- per-feature overlap tables
- aggregated gene tables
- `all-gene_name-combined.csv`

## Key Inputs

- detector DMP CSVs, typically `dmps-*.csv`
- a GTF annotation file
- optional disease enrichment credentials from the environment

Recommended secret handling:

- `GROK_API_KEY` via environment variable
- local override JSON for one-off runs

Do not commit secrets into tracked config files.

## Notes

- The historical Azure SQL flow is still present in the package for backward compatibility, but it is not the primary documented workflow.
- Project path resolution is implemented in `methyl_mapper/project_resolver.py`.
- For the shared project schema, see `docs/UNIFIED_PROJECT_CONFIG_GUIDE.md`.
