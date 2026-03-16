# MethylMapper

**Comprehensive DMP-to-gene mapping with disease enrichment capabilities**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

## Overview

MethylMapper provides two complementary approaches for mapping Differentially Methylated Positions (DMPs) to genes:

1. **Azure SQL Database Integration** (`methyl_mapper`) - Enterprise-scale mapping with stored procedures
2. **Bedtools-based Local Processing** (`methyl_mapper_bedtools`) - Fast local mapping with disease enrichment

Both integrate with the MethylDetector pipeline to provide gene-level interpretation of methylation analysis results.

## Quick Start

### For Disease Enrichment (Recommended)

```bash
# Install bedtools and MethylMapper
conda install -c bioconda bedtools
pip install -e .

# Set environment variables
export GENE_GTF="/path/to/gencode.v44.annotation.gtf"
export GROK_API_KEY="your-grok-api-key"
export DISGENET_API_KEY="your-disgenet-api-key"  # Optional

# Basic mapping with disease enrichment
cd /path/to/methylmodeler/output
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" \
                      --enrich-disease \
                      --disease-term "early-stage prostate cancer"

# Advanced usage with all options
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" \
                      --enrich-disease \
                      --enrich-source grok+opentargets \
                      --grok-api-key "your-grok-key" \
                      --enrich-profile strict \
                      --cache-ttl-days 7 \
                      --no-p-value-weight \
                      --no-q-value-weight \
                      --feature-types gene exon intron \
                      --group-by gene_name \
                      --min-k 20 \
                      --max-k 1000 \
                      --stability-threshold 5 \
                      --output-dir /custom/output/path
```

### For Azure SQL Database (Legacy)

```bash
# Configure Azure SQL connection
methyl_mapper --input dmps.csv --config db_config.json --sample-id 12345
```

## Tools Overview

### methyl_mapper_bedtools (Primary Tool)

**Features:**
- ⚡ **Fast local processing** using bedtools intersect
- 🧬 **Comprehensive feature mapping** (genes, transcripts, exons, introns, etc.)
- 📊 **Statistical weighting** by p-value, q-value, and effect size
- 🧪 **Gene-level aggregation** with weighted Stouffer p-values and gene importance
- 🏥 **Disease enrichment** via Grok API + Open Targets (optional DisGeNET)
- 🧪 **Enrichment profiles** for strict/balanced/permissive testing
- 💾 **Disk cache** for faster repeated runs
- 📈 **Progress indicators** for long-running operations
- 🔧 **Flexible configuration** via environment variables and CLI options

**Best for:** Research workflows, disease association studies, interactive analysis

### methyl_mapper (Azure SQL Database)

**Features:**
- 🏢 **Enterprise-scale** processing with Azure SQL stored procedures
- 🔄 **Batch processing** with database optimization
- 📋 **Structured output** with sample tracking
- ⚙️ **Configurable weighting** for different genomic regions

**Best for:** Production pipelines, large-scale batch processing, enterprise environments

## License

MIT License - see LICENSE file for details.
