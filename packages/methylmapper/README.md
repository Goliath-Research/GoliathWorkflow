# MethylMapper

## Overview

A command-line tool and Python library for mapping Differentially Methylated Positions (DMPs) to genes using Azure SQL Database and STRING-DB. MethylMapper integrates with the MethylDetector pipeline to provide gene-level interpretation of methylation analysis results.

## Features

- Azure SQL Integration: Direct connection to Azure SQL Database
- STRING-DB Mapping: Leverages STRING-DB for DMP-to-gene mapping
- Flexible Weighting: Customizable weights for different genomic regions (promoter, exon, intron, etc.)
- Batch Processing: Efficient bulk upload and processing of DMPs
- Dual Output: CSV for full results, JSON for gene lists
- CLI and API: Use as command-line tool or Python library
- Configuration Management: JSON-based configuration for database and parameters

## Installation

```bash
poetry install
```

## Usage

### Command Line

```bash
methylmapper --input biological_dmps.csv --config db_config.json --sample-id 12345
```

### Python API

```python
from methylmapper import DMPMapper, MethylMapperConfig

config = MethylMapperConfig.parse_file("db_config.json")
mapper = DMPMapper(config)
results = mapper.run(input_csv="biological_dmps.csv", sample_id=12345)
```

## Configuration

See example_config.json in the original content.

## Output

- mapped_genes.csv: Full gene mapping results
- mapped_genes.json: Ordered list of unique gene names

## Integration

Works with MethylDetector outputs for gene mapping, then feed to MethylEnricher.

## Troubleshooting

- Connection errors: Verify Azure SQL credentials and firewall
- Missing columns: Ensure input CSV has required fields

## License

MIT License - see LICENSE file for details.
