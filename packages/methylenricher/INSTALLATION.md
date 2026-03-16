# MethylEnricher Installation Guide

## Quick Start

```bash
cd /home/ubuntu/MethylEnricher
pip install -e .
```

This will install MethylEnricher in editable mode along with all dependencies.

## Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- Internet connection (for querying Enrichr databases)

## Installation Steps

### 1. Install MethylEnricher

```bash
cd /home/ubuntu/MethylEnricher
pip install -e .
```

### 2. Verify Installation

```bash
methyl_enricher --version
```

You should see: `MethylEnricher 0.1.0`

### 3. Test with Example Data

```bash
# Run enrichment on example gene list
methyl_enricher --input example_genes.txt --outdir test_results --top 30

# Check results
ls test_results/
cat test_results/enrichment_top_q0.05.csv
```

## Dependencies

MethylEnricher requires the following Python packages:

### Core Dependencies
- **gseapy** (>=1.1.0): Interface to Enrichr databases
- **pandas** (>=1.3.0): Data manipulation and analysis
- **numpy** (>=1.20.0): Numerical computing

### Optional Dependencies
- **matplotlib** (>=3.3.0): Plotting (for future visualization features)
- **seaborn** (>=0.11.0): Statistical visualizations

## Using MethylEnricher

### Basic Usage

```bash
methyl_enricher --input genes.txt --outdir results
```

### Use MethylMapper Output Directly

```bash
methyl_enricher --input mapped_features/all-gene_name-combined.csv \
               --gene-column gene_name \
               --sort-by total_weight \
               --top 200
```

### Advanced Usage

```bash
# Analyze top 100 genes with custom libraries
methyl_enricher --input genes.txt \
               --outdir results \
               --top 100 \
               --libraries KEGG_2021_Human Reactome_2022

# Use stricter significance cutoff
methyl_enricher --input genes.txt \
               --outdir results \
               --cutoff 0.01
```

### List Available Libraries

```bash
methyl_enricher --list-libraries
```

## Integration with Methylation Workflow

### From MethylMapper to Enrichment

```bash
# 1. Run MethylMapper (produces mapped_features/all-gene_name-combined.csv)
cd /path/to/methyldetector/output
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" \
                      --enrich-disease

# 2. Run enrichment analysis on MethylMapper output
methyl_enricher --input mapped_features/all-gene_name-combined.csv \
               --gene-column gene_name \
               --disease-only \
               --sort-by total_weight \
               --top 200
```

## Troubleshooting

### ImportError: No module named 'gseapy'

```bash
pip install gseapy
```

### Connection Errors

Enrichr requires internet access. If you see connection errors:
- Check your internet connection
- Try again later (Enrichr servers may be temporarily down)
- Check firewall settings

### Permission Denied

If you get permission errors during installation:

```bash
pip install --user -e .
```

Or use a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e .
```

## Uninstallation

```bash
pip uninstall methyl_enricher
```

## Development Installation

For development, install with additional dev dependencies:

```bash
pip install -e ".[dev]"
```

## Support

For issues or questions:
- Check the README.md for usage examples
- Open an issue on GitHub
- Contact the MethylDetector team

## Related Projects

- **MethylDetector**: project `packages/methyldetector`
- ****: `/home/ubuntu/`
- **MethylClassifier**: `/home/ubuntu/MethylClassifier`
- **MethylUtils**: `/home/ubuntu/MethylUtils`

