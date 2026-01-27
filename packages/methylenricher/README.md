# MethylEnricher

## Overview

A command-line tool for gene enrichment analysis of Differentially Methylated Positions (DMPs) from methylation studies. MethylEnricher performs Over-Representation Analysis (ORA) using Enrichr databases to identify significantly enriched pathways, ontologies, and gene sets.

## Features

- Multiple Database Support: Query KEGG, Reactome, GO, MSigDB Hallmark, WikiPathways, and more
- Batch Processing: Analyze multiple gene lists simultaneously
- Flexible Input: Accept gene lists (TXT) or MethylMapper CSV/TSV outputs
- Comprehensive Output: Per-library results plus merged summaries
- FDR Filtering: Automatic filtering of significant hits (q-value ≤ 0.05)
- Easy Integration: Works seamlessly with MethylMapper outputs

## Installation

```bash
pip install -e .
```

## Usage

### Command Line

```bash
methyl_enricher --input genes.txt --outdir enrichment_results
```

### Using MethylMapper Output

```bash
# Use the combined MethylMapper CSV directly
methyl_enricher --input mapped_features/all-gene_name-combined.csv \
               --gene-column gene_name

# Optional: enrich only disease-associated genes (if present)
methyl_enricher --input mapped_features/all-gene_name-combined.csv \
               --gene-column gene_name \
               --disease-only

# Sort by a weight/score column before selecting top genes
methyl_enricher --input mapped_features/all-gene_name-combined.csv \
               --gene-column gene_name \
               --sort-by total_weight \
               --top 200
```

**Note:** When input is CSV/TSV, the tool auto-sorts by `total_weight` if present (unless `--sort-by` is provided).

### Python API

```python
from methyl_enricher import run_enrichment

results = run_enrichment(
    input_file="mapped_features/all-gene_name-combined.csv",
    output_dir="enrichment_results",
    gene_column="gene_name",
    disease_only=True,
    sort_by="total_weight",
    top_n=200
)
```

## Configuration

Parameters via CLI; no separate config file.

## Output

Per-library CSVs, merged CSV, top significant hits CSV.

## Integration

Use with gene lists from MethylMapper in MethylPipeline, including CSV/TSV outputs.

## Troubleshooting

- No results: Increase top genes or relax cutoff
- Connection errors: Check internet and retry

## License

MIT License - see LICENSE file for details.
