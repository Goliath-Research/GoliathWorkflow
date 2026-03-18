# Bedtools Mapper

The bedtools mapper is the supported local mapping engine behind the current MethylMapper workflow.

## Preferred Usage

Project-driven:

```bash
methyl-mapper --project /path/to/project.json
```

Direct:

```bash
methyl_mapper_bedtools \
  --csv-pattern "/path/to/dmps-*.csv" \
  --gtf /path/to/gencode.gtf \
  --output-dir /path/to/out
```

## Expected Inputs

- detector DMP CSVs, typically `dmps-*.csv`
- a GTF annotation file

## Expected Outputs

- per-feature overlap CSVs
- combined gene tables such as `all-gene_name-combined.csv`

## Notes

- Comparison-aware project runs resolve input/output directories automatically.
- Disease enrichment credentials should come from environment variables or local override files.
