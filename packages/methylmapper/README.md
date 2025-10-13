# MethylMapper

A command-line tool and Python library for mapping Differentially Methylated Positions (DMPs) to genes using Azure SQL Database and STRING-DB. MethylMapper integrates with the MethylDetector pipeline to provide gene-level interpretation of methylation analysis results.

## Features

- **Azure SQL Integration**: Direct connection to Azure SQL Database
- **STRING-DB Mapping**: Leverages STRING-DB for DMP-to-gene mapping
- **Flexible Weighting**: Customizable weights for different genomic regions (promoter, exon, intron, etc.)
- **Batch Processing**: Efficient bulk upload and processing of DMPs
- **Dual Output**: CSV for full results, JSON for gene lists
- **CLI and API**: Use as command-line tool or Python library
- **Configuration Management**: JSON-based configuration for database and parameters

## Installation

### Prerequisites

- Python 3.8+
- Azure SQL Database access
- ODBC Driver 17 for SQL Server (or compatible driver)

### Install MethylMapper

```bash
cd /home/ubuntu/MethylMapper
pip install -e .
```

### Install ODBC Driver (if not already installed)

#### Ubuntu/Debian
```bash
curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add -
curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list > /etc/apt/sources.list.d/mssql-release.list
apt-get update
ACCEPT_EULA=Y apt-get install -y msodbcsql17
```

#### macOS
```bash
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
brew update
brew install msodbcsql17
```

## Configuration

### Create Configuration File

Create a JSON configuration file with your Azure SQL connection details:

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

See `example_config.json` for a template.

## Usage

### Command-Line Interface

#### Basic Usage

```bash
methylmapper --input biological_dmps.csv \
             --config db_config.json \
             --sample-id 12345
```

#### Specify Output Files

```bash
methylmapper --input biological_dmps.csv \
             --config db_config.json \
             --sample-id 12345 \
             --output-csv results.csv \
             --output-json genes.json
```

#### Override Chromosome/Context

```bash
methylmapper --input biological_dmps.csv \
             --config db_config.json \
             --sample-id 12345 \
             --chromosome chr1 \
             --context CG
```

#### Customize Region Weights

```bash
methylmapper --input biological_dmps.csv \
             --config db_config.json \
             --sample-id 12345 \
             --w-promoter 3.0 \
             --w-exon 2.0 \
             --upstream-size 10000
```

### Python API

```python
from pathlib import Path
from methylmapper import DMPMapper, MethylMapperConfig

# Load configuration
config = MethylMapperConfig.parse_file("db_config.json")

# Create mapper
mapper = DMPMapper(config)

# Run pipeline
results = mapper.run(
    input_csv=Path("biological_dmps.csv"),
    output_csv=Path("mapped_genes.csv"),
    output_json=Path("genes.json"),
    sample_id=12345,
    chromosome="chr1",
    context="CG"
)

print(f"Mapped {results['output_genes']} genes")
```

### Step-by-Step API

```python
from methylmapper import DMPMapper, MethylMapperConfig, StoredProcedureConfig

# Load configuration
config = MethylMapperConfig.parse_file("db_config.json")

# Create mapper
mapper = DMPMapper(config)

# Step 1: Load DMPs
dmps_df = mapper.load_dmps("biological_dmps.csv")

# Step 2: Map to genes
genes_df = mapper.map_dmps_to_genes(
    sample_id=12345,
    chromosome="chr1",
    context="CG"
)

# Step 3: Save results
stats = mapper.save_results(
    output_csv="results.csv",
    output_json="genes.json"
)
```

## Input Format

### DMP CSV Requirements

The input CSV must contain these columns:

- `position`: Genomic position (integer)
- `chromosome`: Chromosome identifier (e.g., "chr1", "1")
- `context`: Methylation context (e.g., "CG", "CHG", "CHH")
- `q_value`: Adjusted p-value (float)
- `delta_mean`: Mean methylation difference (float)
- `overlap`: Bhattacharyya Coefficient / overlap measure (float, 0-1)
- `effect_size`: Variance-weighted effect size (float)

Example from MethylDetector output:

```csv
position,chromosome,context,q_value,delta_mean,overlap,effect_size,mean1,mean2,...
12345,chr1,CG,0.001,0.45,0.15,125.3,0.75,0.30,...
12346,chr1,CG,0.002,0.38,0.20,98.7,0.68,0.30,...
```

## Output Format

### CSV Output (Full Results)

Complete gene mapping results including:
- Gene identifiers
- Importance scores
- Region types (promoter, exon, intron, etc.)
- Weighted contributions
- All fields from stored procedure

### JSON Output (Gene List)

Ordered list of unique gene names:

```json
[
  "TP53",
  "BRCA1",
  "EGFR",
  ...
]
```

Genes are sorted by importance/score if available.

## Database Requirements

### Staging Table

MethylMapper requires a staging table in your Azure SQL Database:

```sql
CREATE TABLE dmp_staging (
    SampleID INT NOT NULL,
    position BIGINT NOT NULL,
    chromosome VARCHAR(10) NOT NULL,
    context VARCHAR(3) NOT NULL,
    q_value FLOAT NULL,
    delta_mean FLOAT NULL,
    overlap FLOAT NULL,
    effect_size FLOAT NULL
);
```

The table is automatically created if it doesn't exist.

### Stored Procedure

The `spMapDMP2Genes` stored procedure must exist in your database:

```sql
CREATE PROCEDURE spMapDMP2Genes
    @SampleID INT,
    @chromosome VARCHAR(10),
    @context VARCHAR(3),
    @upstream_size INT = 5000,
    @downstream_size INT = 2000,
    @min_intron_size INT = 0,
    @w_promoter FLOAT = 2.0,
    @w_terminator FLOAT = 0.5,
    @w_gene_body FLOAT = 1.0,
    @w_exon FLOAT = 1.5,
    @w_intron FLOAT = 0.7,
    @w_unknown FLOAT = 1.0
AS
BEGIN
    -- Your DMP-to-gene mapping logic using STRING-DB
    -- Should return gene mappings with importance scores
END
```

## Integration with MethylDetector

MethylMapper is designed to work seamlessly with MethylDetector:

```bash
# Step 1: Run MethylDetector
cd /home/ubuntu/MethylDetector
python -m methyl_detector config.json

# Output: biological_dmps-chr1-CG.csv

# Step 2: Map DMPs to genes
cd /home/ubuntu/MethylMapper
methylmapper --input ../MethylDetector/output/biological_dmps-chr1-CG.csv \
             --config db_config.json \
             --sample-id 12345

# Output: mapped_genes.csv, mapped_genes.json

# Step 3: Run enrichment analysis
cd /home/ubuntu/MethylEnricher
methylenricher --input ../MethylMapper/mapped_genes.json \
               --outdir enrichment_results
```

## Command-Line Options

### Required Arguments

- `--input, -i`: Input DMP CSV file path
- `--config, -c`: JSON configuration file with database details
- `--sample-id, -s`: Sample ID for database tracking

### Output Options

- `--output-csv`: Output CSV file path (default: `mapped_genes.csv`)
- `--output-json`: Output JSON file path (default: `mapped_genes.json`)

### Data Options

- `--chromosome`: Override chromosome from CSV
- `--context`: Override methylation context from CSV

### Stored Procedure Parameters

- `--upstream-size`: Upstream region size for promoter (bp, default: 5000)
- `--downstream-size`: Downstream region size for terminator (bp, default: 2000)
- `--min-intron-size`: Minimum intron size (bp, default: 0)
- `--w-promoter`: Weight for promoter DMPs (default: 2.0)
- `--w-terminator`: Weight for terminator DMPs (default: 0.5)
- `--w-gene-body`: Weight for gene body DMPs (default: 1.0)
- `--w-exon`: Weight for exon DMPs (default: 1.5)
- `--w-intron`: Weight for intron DMPs (default: 0.7)
- `--w-unknown`: Weight for unknown region DMPs (default: 1.0)

### Other Options

- `--verbose, -v`: Enable verbose logging
- `--version`: Show version and exit

## Troubleshooting

### Connection Errors

**Issue**: Cannot connect to Azure SQL Database

**Solutions**:
- Verify server name, database name, username, and password
- Check firewall rules allow your IP address
- Ensure ODBC driver is installed correctly
- Try connection string directly with `sqlcmd` or other SQL client

### Missing Columns

**Issue**: Missing required columns in CSV

**Solutions**:
- Ensure input CSV is from MethylDetector or has required columns
- Check column names match exactly (case-sensitive)
- Verify CSV is not corrupted

### Stored Procedure Not Found

**Issue**: Stored procedure does not exist

**Solutions**:
- Verify `spMapDMP2Genes` exists in your database
- Check you have EXECUTE permission on the procedure
- Ensure you're connected to the correct database

### No Results Returned

**Issue**: Stored procedure returns empty results

**Solutions**:
- Check sample data was uploaded correctly
- Verify chromosome and context values match your database
- Check stored procedure logic and STRING-DB data

## Architecture

### Workflow

1. **Load DMPs**: Read CSV file with DMP data
2. **Connect to Database**: Establish Azure SQL connection
3. **Upload to Staging**: Bulk insert DMPs to `dmp_staging` table
4. **Execute Mapping**: Call `spMapDMP2Genes` stored procedure
5. **Retrieve Results**: Fetch gene mappings from procedure
6. **Save Outputs**: Write CSV (full) and JSON (gene names)

### Components

- **Config**: Pydantic models for configuration validation
- **Database**: SQLAlchemy-based Azure SQL connection manager
- **Mapper**: Core DMP-to-gene mapping orchestration
- **CLI**: Command-line interface with argparse

## Performance

- Bulk insert for efficient DMP upload (1000 rows/batch)
- Connection pooling disabled for Azure SQL compatibility
- Streaming results for large gene sets
- Typical processing time: < 1 minute for 1000 DMPs

## Security

- Passwords stored in configuration files (use secure storage in production)
- SSL/TLS encryption enabled by default
- Server certificate validation
- Consider using Azure Key Vault for credentials in production

## Related Tools

- **MethylDetector**: DMP detection and analysis (`/home/ubuntu/MethylDetector`)
- **MethylEnricher**: Gene enrichment analysis (`/home/ubuntu/MethylEnricher`)
- **MethylTrainer**: Classifier training (`/home/ubuntu/MethylTrainer`)
- **MethylClassifier**: Sample classification (`/home/ubuntu/MethylClassifier`)
- **MethylUtils**: Core utilities (`/home/ubuntu/MethylUtils`)

## Citation

If you use MethylMapper in your research, please cite:

```
MethylMapper: DMP-to-Gene Mapping for Methylation Analysis
[Your citation information here]
```

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support

For issues, questions, or suggestions:
- Open an issue on GitHub
- Contact the MethylDetector team
- Check INSTALLATION.md for setup help

## Version History

- **0.1.0** (2025-01-13): Initial release
  - Azure SQL integration
  - STRING-DB mapping support
  - CLI and Python API
  - Configurable region weights
