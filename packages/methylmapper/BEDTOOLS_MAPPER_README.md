# MethylMapper Bedtools - Quick Start Guide

## Overview

The `methyl_mapper_bedtools` command provides comprehensive DMP-to-feature mapping using bedtools, without requiring Azure SQL Database. It maps DMPs to all genomic features (genes, transcripts, exons, introns, etc.) with weighting by statistical significance.

**New Feature**: Disease association enrichment using Grok API! Automatically enrich your gene mappings with disease associations (e.g., early-stage prostate cancer).

## Installation

Make sure bedtools is installed:
```bash
conda install -c bioconda bedtools
# or
sudo apt-get install bedtools  # Ubuntu/Debian
```

## Basic Usage

### 1. Download a Gene Annotation File

Download a GTF/GFF file (e.g., GENCODE or Ensembl):

```bash
# GENCODE (recommended for human)
wget https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_44/gencode.v44.annotation.gtf.gz
gunzip gencode.v44.annotation.gtf.gz

# Or Ensembl
wget https://ftp.ensembl.org/pub/release-110/gtf/homo_sapiens/Homo_sapiens.GRCh38.110.gtf.gz
gunzip Homo_sapiens.GRCh38.110.gtf.gz
```

### 2. Set Default GTF Path (Optional)

You can set an environment variable to avoid specifying `--gtf` every time:

```bash
export GENE_GTF="/path/to/gencode.v44.annotation.gtf"
```

### 3. Run Mapping

```bash
# Map optimized DMPs from all chromosomes
cd /home/ubuntu/Work/w/humans/psomagen/pc/models/hc1-1-CG
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" --gtf /path/to/gencode.v44.annotation.gtf

# Or use environment variable
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv"
```

### 4. Enable Disease Enrichment (NEW!)

```bash
# Set Grok API key
export GROK_API_KEY="your-api-key-here"

# Run with disease enrichment
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" \
                       --gtf /path/to/gencode.v44.annotation.gtf \
                       --enrich-disease \
                       --disease-term "early-stage prostate cancer"
```

## Output Files

The script creates a `mapped_features/` directory with:

- **`dmps-{chromosome}-3-optimized-features-{group_by}.csv`**: Aggregated features per chromosome
  - Columns: `gene_name`, `dmp_count`, `unique_dmps`, `total_weight`, `mean_weight`, `min_p_value`, `mean_effect_size`, etc.
  - **NEW**: If `--enrich-disease` is enabled, also includes:
    - `disease_associated`: Boolean indicating if gene is associated with the disease
    - `disease_association_type`: Type of association (direct, indirect, predicted, none)
    - `disease_evidence_level`: Evidence level (high, medium, low, none)
    - `disease_description`: Description of the association
    - `disease_publications`: Number of publications
    - `disease_functional_role`: Functional role in the disease
    - `disease_source`: Source of information (grok_api, disgenet, none)
  
- **`dmps-{chromosome}-3-optimized-intersections.csv`**: Detailed DMP-feature intersections
  - All DMP-feature pairs with full metadata

- **`all-{group_by}-combined.csv`**: Combined results across all chromosomes
  - **Created automatically** after processing all chromosome files (only if multiple files are processed)
  - Aggregated statistics combining all chromosomes together
  - Location: Same output directory as per-chromosome files (default: `mapped_features/`)
  - Example: `all-gene_name-combined.csv` or `all-gene_id-combined.csv`
  - Contains: Sum of DMP counts, mean of weighted scores, and aggregated disease enrichment data
  - **Note**: This file is created at the end after all chromosomes are processed and enriched

## Advanced Options

### Disease Enrichment

```bash
# Enable disease enrichment with custom disease term
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" \
                       --gtf $GENE_GTF \
                       --enrich-disease \
                       --disease-term "prostate adenocarcinoma"

# Use custom API key
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" \
                       --gtf $GENE_GTF \
                       --enrich-disease \
                       --grok-api-key "your-key-here"
```

### Group By Different Features

```bash
# Group by transcript instead of gene
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" --gtf $GENE_GTF \
                       --group-by transcript_id

# Group by feature type
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" --gtf $GENE_GTF \
                       --group-by feature_type
```

### Customize Weighting

```bash
# Disable p-value weighting
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" --gtf $GENE_GTF \
                       --no-p-value-weight

# Use 1/p instead of -log10(p) for p-values
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" --gtf $GENE_GTF \
                       --no-log-transform
```

### Filter Feature Types

```bash
# Only map to genes and exons
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" --gtf $GENE_GTF \
                       --feature-types gene exon
```

### Custom Output Directory

```bash
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" --gtf $GENE_GTF \
                       --output-dir /path/to/results
```

## Example Workflow

```bash
# 1. Set default GTF and Grok API key
export GENE_GTF="/home/ubuntu/data/gencode.v44.annotation.gtf"
export GROK_API_KEY="your-grok-api-key"

# 2. Navigate to MethylModeler output directory
cd /home/ubuntu/Work/w/humans/psomagen/pc/models/hc1-1-CG

# 3. Map optimized DMPs to genes with disease enrichment
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" \
                       --enrich-disease \
                       --disease-term "early-stage prostate cancer" \
                       --output-dir /tmp/mapped_features

# 4. Check results (filter for disease-associated genes)
cat /tmp/mapped_features/all-gene_name-combined.csv | \
  awk -F',' 'NR==1 || $18=="true"' | head -20
```

## Weighting Scheme

DMPs are weighted by:
- **p-value**: `-log10(p_value)` (highly significant = higher weight)
- **q-value**: `-log10(q_value)` (FDR-corrected significance)
- **effect_size**: Direct value (biological importance)

Final weight = p_weight × q_weight × effect_size_weight (normalized)

## Disease Enrichment Details

### Grok API Integration

The disease enrichment uses Grok API to query biomedical knowledge about gene-disease associations. For each gene, it retrieves:

- **Association status**: Whether the gene is associated with the specified disease
- **Association type**: direct, indirect, predicted, or none
- **Evidence level**: high, medium, low, or none
- **Description**: Brief description of the association
- **Publications**: Number of publications mentioning this association
- **Functional role**: Gene's role in the disease context

### Fallback to DisGeNET

If Grok API is unavailable or fails, the system can fall back to DisGeNET database (requires `DISGENET_API_KEY` environment variable, free registration at https://www.disgenet.org/api/).

### Rate Limiting

API calls are rate-limited (default 1 second delay) to avoid overwhelming the services. You can adjust this in the code if needed.

## Python API

You can also use the mapper programmatically:

```python
from pathlib import Path
from methyl_mapper import BedtoolsMapper, GeneDiseaseEnricher

mapper = BedtoolsMapper(
    gene_gtf=Path("/path/to/gencode.v44.annotation.gtf"),
    use_p_value_weight=True,
    use_q_value_weight=True,
    use_effect_size_weight=True,
    enrich_disease=True,
    disease_term="early-stage prostate cancer",
    grok_api_key="your-api-key"
)

results = mapper.map_csv_files(
    csv_pattern="dmps-*-3-optimized.csv",
    output_dir=Path("mapped_features"),
    group_by="gene_name"
)
```

## Troubleshooting

**Error: "bedtools not found"**
- Install bedtools: `conda install -c bioconda bedtools`

**Error: "No CSV files found"**
- Check that the pattern matches your files: `ls dmps-*-3-optimized.csv`
- Use absolute path if needed: `--csv-pattern "/full/path/to/dmps-*-3-optimized.csv"`

**Error: "GTF file not found"**
- Specify with `--gtf` or set `GENE_GTF` environment variable
- Verify file exists: `ls /path/to/gencode.v44.annotation.gtf`

**No intersections found**
- Check that chromosome names match (e.g., "1" vs "chr1")
- Verify GTF file format is correct

**Disease enrichment not working**
- Ensure `GROK_API_KEY` is set or use `--grok-api-key`
- Check API key is valid and has sufficient credits
- API calls are rate-limited; be patient for large gene lists

## Output Columns Reference

### Aggregated Features CSV

| Column | Description |
|--------|-------------|
| `gene_name` | Gene name (or feature ID if grouping differently) |
| `dmp_count` | Total number of DMPs mapping to this feature |
| `unique_dmps` | Number of unique DMPs |
| `total_weight` | Sum of all DMP weights |
| `mean_weight` | Average weight per DMP |
| `max_weight` | Maximum weight (most significant DMP) |
| `min_p_value` | Most significant p-value |
| `mean_p_value` | Average p-value |
| `min_q_value` | Most significant q-value |
| `mean_q_value` | Average q-value |
| `mean_effect_size` | Average effect size |
| `max_effect_size` | Maximum effect size |
| `mean_delta_mean` | Average methylation difference |
| `feature_type` | Type of feature (gene, exon, etc.) |
| `feature_chrom` | Chromosome |
| `feature_strand` | Strand (+/-) |
| **`disease_associated`** | **Boolean: Is gene associated with disease?** |
| **`disease_association_type`** | **Type: direct, indirect, predicted, none** |
| **`disease_evidence_level`** | **Evidence: high, medium, low, none** |
| **`disease_description`** | **Description of association** |
| **`disease_publications`** | **Number of publications** |
| **`disease_functional_role`** | **Functional role in disease** |
| **`disease_source`** | **Source: grok_api, disgenet, none** |

## Getting a Grok API Key

1. Sign up at https://x.ai/ (X/Twitter account required)
2. Navigate to API settings
3. Generate an API key
4. Set it as environment variable: `export GROK_API_KEY="your-key"`
5. Or pass via CLI: `--grok-api-key "your-key"`

**Note**: If you don't have a Grok API key, the enrichment will still work but will only use DisGeNET (if configured) or skip enrichment entirely. The mapping will complete successfully without disease information.
