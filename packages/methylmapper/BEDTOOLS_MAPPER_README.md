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
- **Default GTF mapping** uses all feature types in the file (gene, transcript, exon, CDS, UTR, …). Pass `--feature-types gene exon` (for example) to restrict.
- **Grok** runs synchronously (one request at a time, ≤20 genes per batch) unless you opt in to the xAI Batch API (`--grok-batch-api`). **Open Targets** supplies disease evidence and scores in merged tables.
- Optional: `--auxiliary-bed path.bed` (repeatable) for regulatory overlaps; `--closest-gene` for nearest gene body per DMP.
