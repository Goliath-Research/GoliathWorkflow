# MethylMapper Quick Start Guide

## Installation

```bash
cd /home/ubuntu/MethylMapper
pip install -e .
```

## Configuration

1. Copy example config:
```bash
cp example_config.json my_config.json
```

2. Edit with your Azure SQL credentials:
```json
{
  "database": {
    "server": "your-server.database.windows.net",
    "database": "your_database",
    "username": "your_username",
    "password": "your_password",
    "driver": "ODBC Driver 17 for SQL Server",
    "port": 1433
  }
}
```

## Usage

### Basic Command

```bash
methyl_mapper --input biological_dmps.csv \
             --config my_config.json \
             --sample-id 12345
```

### With MethylModeler Output

```bash
# After running MethylModeler
methyl_mapper --input /home/ubuntu/MethylModeler/output/biological_dmps-chr1-CG.csv \
             --config my_config.json \
             --sample-id 12345 \
             --output-csv chr1_CG_genes.csv \
             --output-json chr1_CG_genes.json
```

### Python API

```python
from methyl_mapper import DMPMapper, MethylMapperConfig

config = MethylMapperConfig.parse_file("my_config.json")
mapper = DMPMapper(config)

results = mapper.run(
    input_csv="biological_dmps.csv",
    output_csv="genes.csv",
    output_json="genes.json",
    sample_id=12345
)

print(f"Mapped {results['output_genes']} genes")
```

## Output Files

- **CSV**: Full gene mapping results with scores
- **JSON**: Ordered list of gene names for enrichment analysis

## Integration with Pipeline

```bash
# Complete workflow
cd /home/ubuntu/MethylModeler
python -m methyl_modeler config.json

cd /home/ubuntu/MethylMapper
methyl_mapper --input ../MethylModeler/output/biological_dmps-*.csv \
             --config db_config.json \
             --sample-id 12345

cd /home/ubuntu/MethylEnricher
methylenricher --input ../MethylMapper/mapped_genes.json \
               --outdir enrichment_results
```

## Troubleshooting

**Connection Failed?**
- Check Azure SQL firewall rules
- Verify credentials in config file
- Test with: `sqlcmd -S server.database.windows.net -U username -P password`

**Missing Columns?**
- Ensure CSV is from MethylModeler with effect_size
- Check column names (case-sensitive)

**No Results?**
- Verify stored procedure exists: `spMapDMP2Genes`
- Check sample data uploaded correctly
- Verify chromosome/context match database

For more help, see INSTALLATION.md and README.md

