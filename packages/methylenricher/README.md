# MethylEnricher

## Overview

A command-line tool for gene enrichment analysis of Differentially Methylated Positions (DMPs) from methylation studies. MethylEnricher performs Over-Representation Analysis (ORA) using Enrichr databases to identify significantly enriched pathways, ontologies, and gene sets.

## Features

- Multiple Database Support: Query KEGG, Reactome, GO, MSigDB Hallmark, WikiPathways, and more
- Batch Processing: Analyze multiple gene lists simultaneously
- Flexible Input: Accept gene lists from DMP analysis or any gene symbol list
- Comprehensive Output: Per-library results plus merged summaries
- FDR Filtering: Automatic filtering of significant hits (q-value ≤ 0.05)
- Easy Integration: Works seamlessly with MethylDetector DMP outputs

## Installation

```bash
poetry install
```

## Usage

### Command Line

```bash
methylenricher --input genes.txt --outdir enrichment_results
```

### Python API

```python
from methylenricher import run_enrichment

results = run_enrichment(genes=genes, libraries=libraries, outdir='results')
```

## Configuration

Parameters via CLI; no separate config file.

## Output

Per-library CSVs, merged CSV, top significant hits CSV.

## Integration

Use with gene lists from MethylMapper in MethylPipeline.

## Troubleshooting

- No results: Increase top genes or relax cutoff
- Connection errors: Check internet and retry

## License

MIT License - see LICENSE file for details.
