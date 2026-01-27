# MethylMapper Installation Guide

**Complete setup for both mapping tools**

## Overview

MethylMapper provides two tools with different installation requirements:

- **`methyl_mapper_bedtools`** - Local processing with bedtools (Recommended for research)
- **`methyl_mapper`** - Azure SQL Database integration (For enterprise environments)

## Prerequisites

- **Python 3.8+**
- **pip** package manager

## methyl_mapper_bedtools Installation (Recommended)

### Install System Dependencies

```bash
# Install bedtools (required)
conda install -c bioconda bedtools

# Or on Ubuntu/Debian:
sudo apt-get update
sudo apt-get install bedtools

# Or on macOS:
brew install bedtools

# Verify installation
bedtools --version
```

### Install Python Package

```bash
cd /home/ubuntu/MethylPipeline/packages/methylmapper
pip install -e .
```

### Download Reference Data

```bash
# Download GENCODE annotation (recommended for human)
wget https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_44/gencode.v44.annotation.gtf.gz
gunzip gencode.v44.annotation.gtf.gz

# Set as environment variable
export GENE_GTF="/path/to/gencode.v44.annotation.gtf"

# Or Ensembl annotation
wget https://ftp.ensembl.org/pub/release-110/gtf/homo_sapiens/Homo_sapiens.GRCh38.110.gtf.gz
gunzip Homo_sapiens.GRCh38.110.gtf.gz
```

### Optional: API Keys for Disease Enrichment

```bash
# Grok API key (recommended)
export GROK_API_KEY="your-grok-api-key"

# Open Targets uses a public API (no key required)

# DisGeNET API key (free registration, optional)
export DISGENET_API_KEY="your-disgenet-api-key"
```

### Test Installation

```bash
# Test CLI
methyl_mapper_bedtools --help

# Test Python import
python -c "from methyl_mapper import BedtoolsMapper; print('✓ BedtoolsMapper installed')"

# Test credential management
methyl_mapper_credentials save --credential-type grok --api-key "test-key"
methyl_mapper_credentials test --credential-type grok
```

## methyl_mapper Installation (Azure SQL Database)

### Install System Dependencies

```bash
# Install ODBC drivers
# Ubuntu/Debian:
curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
curl https://packages.microsoft.com/config/ubuntu/20.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql17 unixodbc-dev

# macOS:
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
brew update
brew install msodbcsql17

# Windows: Download from Microsoft website

# Verify ODBC installation
odbcinst -j
```

### Install Python Package

```bash
cd /home/ubuntu/MethylPipeline/packages/methylmapper
pip install -e .
```

### Test Installation

```bash
# Test CLI
methyl_mapper --help

# Test Python import
python -c "from methyl_mapper import DMPMapper, MethylMapperConfig; print('✓ DMPMapper installed')"

# Test ODBC driver
python -c "import pyodbc; print('Available drivers:', pyodbc.drivers())"
```

## Configuration

### For methyl_mapper_bedtools

**Environment Variables:**
```bash
export GENE_GTF="/path/to/gencode.v44.annotation.gtf"    # Required
export GROK_API_KEY="your-key"                          # Optional (for Grok enrichment)
export DISGENET_API_KEY="your-key"                      # Optional (for DisGeNET enrichment)
```

### For methyl_mapper (Azure SQL)

**Create Configuration File:**
```bash
cp example_config.json my_config.json
```

**Edit my_config.json:**
```json
{
  "database": {
    "server": "your-server.database.windows.net",
    "database": "your_database",
    "username": "your_username",
    "password": "your_password",
    "driver": "ODBC Driver 17 for SQL Server",
    "port": 1433
  },
  "stored_procedure": {
    "upstream_size": 5000,
    "downstream_size": 2000,
    "min_intron_size": 0,
    "w_promoter": 2.0,
    "w_terminator": 0.5,
    "w_gene_body": 1.0,
    "w_exon": 1.5,
    "w_intron": 0.7,
    "w_unknown": 1.0
  }
}
```

## Testing

### Test methyl_mapper_bedtools

```bash
# Create test DMP file
cat > test_dmps.csv << 'EOF'
position,chromosome,context,q_value,delta_mean,overlap,effect_size
12345,chr1,CG,0.001,0.45,0.15,125.3
12346,chr1,CG,0.002,0.38,0.20,98.7
12347,chr1,CG,0.003,0.42,0.18,110.5
EOF

# Test mapping
methyl_mapper_bedtools --csv-pattern "test_dmps.csv" --gtf $GENE_GTF

# Test with enrichment (if API keys set)
methyl_mapper_bedtools --csv-pattern "test_dmps.csv" \
                      --gtf $GENE_GTF \
                      --enrich-disease \
                      --disease-term "test disease"
```

### Test methyl_mapper (Azure SQL)

```bash
# Test database connection
python -c "
from methyl_mapper import MethylMapperConfig, AzureSQLConnection
config = MethylMapperConfig.parse_file('my_config.json')
with AzureSQLConnection(config.database) as db:
    print('✓ Database connection successful')
"

# Test mapping
methyl_mapper --input test_dmps.csv --config my_config.json --sample-id 99999
```

## API Key Setup

### Grok API Key

1. **Sign up**: Visit https://x.ai/ (requires X/Twitter account)
2. **Generate key**: Navigate to API settings
3. **Set environment variable**:
   ```bash
   export GROK_API_KEY="your-generated-key"
   ```
4. **Test key**:
   ```bash
   methyl_mapper_credentials save --credential-type grok --api-key "your-key"
   methyl_mapper_credentials test --credential-type grok
   ```

### DisGeNET API Key

1. **Register**: Visit https://www.disgenet.org/ (free)
2. **Get API key**: After registration, access your profile
3. **Set environment variable**:
   ```bash
   export DISGENET_API_KEY="your-api-key"
   ```
4. **Test key**:
   ```bash
   methyl_mapper_credentials save --credential-type disgenet --api-key "your-key"
   methyl_mapper_credentials test --credential-type disgenet
   ```

### Open Targets
Open Targets uses a public GraphQL endpoint and does not require an API key.

### Optional: Azure Key Vault Integration

For enterprise environments, you can store API keys securely in Azure Key Vault:

```bash
# Set Key Vault URL
export AZURE_KEY_VAULT_URL="https://your-vault.vault.azure.net/"

# Save keys to Key Vault (requires Azure authentication)
methyl_mapper_credentials save --credential-type grok --api-key "your-key" --use-azure
methyl_mapper_credentials save --credential-type disgenet --api-key "your-key" --use-azure

# Test retrieval from Key Vault
methyl_mapper_credentials test --credential-type grok --azure-key-vault-url "https://your-vault.vault.azure.net/"
```

**Note**: Azure Key Vault integration requires:
- Azure CLI authentication (`az login`)
- Appropriate Key Vault permissions
- Azure Identity package (`pip install azure-identity`)

## Troubleshooting

### Common Issues

#### "bedtools not found"
```bash
# Install bedtools
conda install -c bioconda bedtools
# Verify: bedtools --version
```

#### "ODBC Driver not found"
```bash
# Check installed drivers
odbcinst -q -d

# Reinstall ODBC (Ubuntu)
sudo apt-get purge msodbcsql17
sudo apt-get install msodbcsql17
```

#### "Cannot connect to Azure SQL"
```bash
# Test connection
sqlcmd -S your-server.database.windows.net -U username -P password -d database

# Check firewall rules in Azure Portal
# Add your IP to SQL Server firewall rules
```

#### "Grok API key invalid"
```bash
# Check key format (should be xai-...)
echo $GROK_API_KEY

# Test API access
curl -X POST "https://api.x.ai/v1/chat/completions" \
     -H "Authorization: Bearer $GROK_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model": "grok-4-latest", "messages": [{"role": "user", "content": "test"}]}'
```

#### "DisGeNET API key invalid"
```bash
# Test API access
curl -H "Authorization: Bearer $DISGENET_API_KEY" \
     "https://www.disgenet.org/api/gda/gene/BRCA1"
```

### Azure SQL Database Setup

#### Create Staging Table
```sql
-- Run in your Azure SQL database
CREATE TABLE dmp_staging (
    SampleID INT NOT NULL,
    position BIGINT NOT NULL,
    chromosome VARCHAR(10) NOT NULL,
    context VARCHAR(3) NOT NULL,
    q_value FLOAT NULL,
    delta_mean FLOAT NULL,
    overlap FLOAT NULL,
    effect_size FLOAT NULL,
    INDEX IX_dmp_staging_SampleID (SampleID)
);
```

#### Verify Stored Procedure
```sql
-- Check if spMapDMP2Genes exists
SELECT OBJECT_ID('dbo.spMapDMP2Genes', 'P');

-- Grant permissions if needed
GRANT EXECUTE ON dbo.spMapDMP2Genes TO your_username;
```

### Performance Tips

#### For Large Datasets
- **Use methyl_mapper_bedtools** for better performance
- **Set appropriate batch sizes** in Azure SQL
- **Use environment variables** instead of config files

#### Memory Usage
- **Monitor RAM usage** during large mappings
- **Use smaller chunks** for very large datasets
- **Clear cache** between runs if needed

## Next Steps

### Complete Pipeline Setup

```bash
# 1. Install all components
cd /home/ubuntu/MethylPipeline
pip install ./packages/methylutils ./packages/methylcentroid ./packages/methylcluster ./packages/methylmodeler ./packages/methylclassifier ./packages/methylmapper

# 2. Set environment variables
export GENE_GTF="/path/to/gencode.v44.annotation.gtf"
export GROK_API_KEY="your-grok-key"

# 3. Test complete workflow
# Run MethylModeler → MethylMapper → Results
```

### Integration Examples

```bash
# Research workflow (recommended)
methyl_mapper_bedtools --csv-pattern "dmps-*-3-optimized.csv" \
                      --enrich-disease \
                      --disease-term "early-stage prostate cancer"

# Enterprise workflow
methyl_mapper --input dmps.csv --config azure_config.json --sample-id 12345
```

## Support

- **Documentation**: See README.md, QUICK_START.md, BEDTOOLS_MAPPER_README.md
- **Issues**: Check error messages, verify configurations
- **API Keys**: Test with provided credential management commands
- **Performance**: Use bedtools version for research, Azure SQL for production

