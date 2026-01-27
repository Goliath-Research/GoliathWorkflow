# MethylMapper Quick Start Guide

**Choose the right tool for your workflow**

MethylMapper offers two complementary tools for DMP-to-gene mapping:

## 🏥 methyl_mapper_bedtools (Recommended for Research)

**For disease enrichment and interactive analysis**

### Installation

```bash
# Install bedtools
conda install -c bioconda bedtools

# Install MethylMapper
cd /home/ubuntu/MethylPipeline/packages/methylmapper
pip install -e .
```

### Download Reference Data

```bash
# Download GENCODE annotation (recommended)
wget https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_44/gencode.v44.annotation.gtf.gz
gunzip gencode.v44.annotation.gtf.gz

# Set as default
export GENE_GTF="/path/to/gencode.v44.annotation.gtf"
```

### Basic Usage

```bash
# Map DMPs to genes
cd /path/to/methylmodeler/output
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv"
```

### Advanced Options

```bash
# Disease enrichment with multiple sources (default: Grok + Open Targets)
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" \
                      --enrich-disease \
                      --enrich-source grok+opentargets \
                      --disease-term "early-stage prostate cancer" \
                      --grok-api-key "your-grok-key"

# Use only Open Targets (no API key needed)
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" \
                      --enrich-disease \
                      --enrich-source opentargets

# Use only DisGeNET (optional)
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" \
                      --enrich-disease \
                      --enrich-source disgenet \
                      --disgenet-api-key "your-disgenet-key"

# Custom weighting and filtering
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" \
                      --no-p-value-weight \
                      --no-q-value-weight \
                      --feature-types gene exon \
                      --group-by transcript_id

# DMP optimization control
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" \
                      --enrich-disease \
                      --enrich-profile strict \
                      --cache-ttl-days 7 \
                      --min-k 20 \
                      --max-k 1000 \
                      --stability-threshold 5 \
                      --unrelated-growth-threshold 0.15

# Disable DMP optimization (use all DMPs)
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" \
                      --no-optimize-dmps
```

### Output Files

```
mapped_features/
├── dmps-chr1-3-optimized-features-gene_name.csv    # Per-chromosome results
├── dmps-chr1-3-optimized-intersections.csv         # Detailed intersections
├── all-gene_name-combined.csv                      # Combined across chromosomes
└── all-gene_name-combined-enriched.csv             # With disease enrichment
```

Per-gene outputs include aggregated `gene_p_value`, `gene_q_value`, and `gene_importance` (sum of DMP importance).

### Python API

```python
from pathlib import Path
from methyl_mapper import BedtoolsMapper

mapper = BedtoolsMapper(
    gene_gtf=Path("/path/to/gencode.v44.annotation.gtf"),
    enrich_disease=True,
    disease_term="early-stage prostate cancer"
)

results = mapper.map_csv_files(
    csv_pattern="dmps-*-3-optimized.csv",
    output_dir=Path("mapped_features")
)
```

## 🏢 methyl_mapper (Azure SQL Database)

**For enterprise-scale batch processing**

### Installation

```bash
cd /home/ubuntu/MethylPipeline/packages/methylmapper
pip install -e .
```

### Configuration

1. Install ODBC driver:
```bash
# Ubuntu/Debian
curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
curl https://packages.microsoft.com/config/ubuntu/20.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql17 unixodbc-dev
```

2. Create config file:
```json
{
  "database": {
    "server": "your-server.database.windows.net",
    "database": "your_database",
    "username": "your_username",
    "password": "your_password",
    "driver": "ODBC Driver 17 for SQL Server"
  }
}
```

### Usage

```bash
methyl_mapper --input biological_dmps.csv \
             --config db_config.json \
             --sample-id 12345
```

## 🔄 Complete Pipeline Workflow

```bash
# 1. Run MethylModeler
cd /home/ubuntu/MethylPipeline/packages/methylmodeler
python -c "from methyl_modeler import run_methyl_modeler; run_methyl_modeler('config.json')"

# 2. Map DMPs to genes with enrichment
cd /path/to/methylmodeler/output
export GENE_GTF="/path/to/gencode.v44.annotation.gtf"
export GROK_API_KEY="your-key"

methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" \
                      --enrich-disease \
                      --disease-term "early-stage prostate cancer"

# 3. Results in: mapped_features/all-gene_name-combined-enriched.csv
```

## 🏥 Disease Enrichment Details

### Data Sources

- **Grok API**: Biomedical knowledge queries with evidence levels
- **Open Targets**: Public target-disease association database (no API key)
- **DisGeNET**: Curated disease-gene association database (optional)
- **Combined**: Best available evidence from enabled sources

### Added Columns

| Column | Description |
|--------|-------------|
| `disease_associated` | Boolean: gene associated with disease |
| `disease_association_type` | Type: direct, indirect, predicted, none |
| `disease_evidence_level` | Evidence: high, medium, low, none |
| `disease_description` | Association description |
| `disease_publications` | Number of supporting publications |
| `disease_functional_role` | Gene's role in disease |
| `disease_source` | Data source: grok_api, open_targets, disgenet, none |
| `disease_associated_raw` | Unfiltered association flag from source |
| `disease_score` | Source score (Open Targets / DisGeNET) |

### Progress Tracking

Real-time progress indicators show:
- Batch processing for Grok API (10 genes per batch)
- Individual gene processing for Open Targets
- Individual gene processing for DisGeNET
- Success/error counts and ETA

## 🐛 Troubleshooting

### For methyl_mapper_bedtools

**"bedtools not found"**
```bash
conda install -c bioconda bedtools
```

**"No CSV files found"**
```bash
ls dmps-*-3-optimized.csv  # Check file pattern matches
```

**Disease enrichment fails**
```bash
export GROK_API_KEY="your-key"  # Set Grok key
# Or use Open Targets only (no key)
methyl_mapper_bedtools --csv-pattern "dmps-*.csv" \
                      --enrich-disease \
                      --enrich-source opentargets
# Or use DisGeNET only
methyl_mapper_bedtools --csv-pattern "dmps-*.csv" \
                      --enrich-disease \
                      --enrich-source disgenet \
                      --disgenet-api-key "your-key"
```

### For methyl_mapper

**ODBC connection failed**
```bash
odbcinst -q -d  # Check ODBC drivers
sqlcmd -S server.database.windows.net -U username -P password  # Test connection
```

**Missing stored procedure**
- Ensure `spMapDMP2Genes` exists in your Azure SQL database
- Check user permissions: `GRANT EXECUTE ON dbo.spMapDMP2Genes TO your_username`

## 📚 API Keys Setup

### Grok API Key
1. Visit https://x.ai/
2. Create account with X/Twitter
3. Generate API key
4. Set: `export GROK_API_KEY="your-key"`

### DisGeNET API Key
1. Visit https://www.disgenet.org/
2. Free registration
3. Get API key
4. Set: `export DISGENET_API_KEY="your-key"`

### Open Targets
No API key required. Open Targets is enabled by default when `--enrich-disease` is used.

## 📖 Next Steps

- **BEDTOOLS_MAPPER_README.md**: Comprehensive bedtools guide
- **INSTALLATION.md**: Detailed setup instructions
- **README.md**: Tool comparison and overview

