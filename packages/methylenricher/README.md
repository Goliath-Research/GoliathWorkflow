# MethylEnricher

A command-line tool for gene enrichment analysis of Differentially Methylated Positions (DMPs) from methylation studies. MethylEnricher performs Over-Representation Analysis (ORA) using Enrichr databases to identify significantly enriched pathways, ontologies, and gene sets.

## Features

- **Multiple Database Support**: Query KEGG, Reactome, GO, MSigDB Hallmark, WikiPathways, and more
- **Batch Processing**: Analyze multiple gene lists simultaneously
- **Flexible Input**: Accept gene lists from DMP analysis or any gene symbol list
- **Comprehensive Output**: Per-library results plus merged summaries
- **FDR Filtering**: Automatic filtering of significant hits (q-value ≤ 0.05)
- **Easy Integration**: Works seamlessly with MethylDetector DMP outputs

## Installation

### Prerequisites

MethylEnricher requires Python 3.8+ and internet access (to query Enrichr databases).

### Install MethylEnricher

```bash
cd /home/ubuntu/MethylEnricher
pip install -e .
```

This will install all dependencies including `gseapy`.

## Usage

### Basic Usage

```bash
# Run enrichment analysis on a gene list
methylenricher --input genes.txt --outdir enrichment_results
```

### Advanced Options

```bash
# Analyze top 100 genes from multiple libraries
methylenricher --input genes.txt \
               --outdir results \
               --top 100 \
               --libraries KEGG_2021_Human GO_Biological_Process_2023

# Use custom libraries
methylenricher --input genes.txt \
               --outdir results \
               --libraries MSigDB_Hallmark_2020 Reactome_2022 \
               --top 200
```

### From DMP Results

```bash
# Extract gene symbols from DMP CSV (assuming 'gene' column exists)
cut -d',' -f gene biological_dmps-chr1-CG.csv | tail -n +2 > genes_for_enrichment.txt

# Run enrichment
methylenricher --input genes_for_enrichment.txt --outdir enrichment_chr1_CG
```

## Command-Line Arguments

### Required Arguments
- `--input, -i`: Path to input file containing gene symbols (one per line)

### Optional Arguments
- `--outdir, -o`: Output directory for results (default: `results`)
- `--top, -t`: Use only top N genes from the list (default: `200`)
- `--libraries, -l`: Enrichr libraries to query (see Libraries section)
- `--cutoff, -c`: Adjusted p-value cutoff for filtering (default: `0.05`)
- `--organism`: Organism for analysis (default: `Human`)

## Enrichr Libraries

### Default Libraries

MethylEnricher queries these libraries by default:

- **KEGG_2021_Human**: KEGG pathway database
- **Reactome_2022**: Reactome pathway database
- **GO_Biological_Process_2023**: Gene Ontology Biological Processes
- **GO_Molecular_Function_2023**: Gene Ontology Molecular Functions
- **GO_Cellular_Component_2023**: Gene Ontology Cellular Components
- **MSigDB_Hallmark_2020**: MSigDB Hallmark gene sets
- **WikiPathway_2023_Human**: WikiPathways database

### Available Libraries

To see all available Enrichr libraries:

```python
import gseapy as gp
gp.get_library_name(organism='Human')
```

Popular additional libraries:
- `GWAS_Catalog_2023`
- `DisGeNET`
- `DrugMatrix`
- `ENCODE_and_ChEA_Consensus_TFs_from_ChIP-X`
- `Human_Phenotype_Ontology`
- `UK_Biobank_GWAS_v1`

## Input Format

### Gene List Format

Simple text file with one gene symbol per line:

```
TP53
BRCA1
EGFR
KRAS
PTEN
```

### From DMP CSV

If your DMP results include gene annotations, extract them first:

```bash
# If 'gene_symbol' column exists
awk -F',' 'NR>1 {print $gene_column}' dmps.csv > genes.txt

# Or using pandas in Python
python -c "import pandas as pd; df = pd.read_csv('dmps.csv'); df['gene_symbol'].dropna().drop_duplicates().to_csv('genes.txt', index=False, header=False)"
```

## Output Files

MethylEnricher generates several output files:

### Per-Library Results

- `enrich_KEGG_2021_Human.csv`
- `enrich_Reactome_2022.csv`
- `enrich_GO_Biological_Process_2023.csv`
- etc.

Each file contains enrichment results for that specific library.

### Merged Results

- `enrichment_merged.csv`: All results from all libraries combined and sorted by adjusted p-value
- `enrichment_top_q0.05.csv`: Top 200 significant hits (q-value ≤ 0.05)

### Output Columns

- **Term**: Pathway/gene set name
- **Overlap**: Genes in your list that are in this term (format: k/K where k=overlap, K=term size)
- **P-value**: Unadjusted p-value from Fisher's exact test
- **Adjusted P-value**: FDR-adjusted p-value (Benjamini-Hochberg)
- **Odds Ratio**: Enrichment odds ratio
- **Combined Score**: Enrichr combined score (log(p-value) × odds ratio)
- **Genes**: Comma-separated list of overlapping genes
- **library**: Source database name

## Example Workflow

### Complete DMP to Enrichment Pipeline

```bash
# 1. Run MethylDetector to get DMPs
cd /home/ubuntu/MethylDetector
python -m methyl_detector configs/cancer_vs_healthy.json

# 2. Extract gene symbols from top DMPs (if gene annotation available)
python -c "
import pandas as pd
df = pd.read_csv('output/biological_dmps-chr1-CG.csv')
# Assuming you have gene annotations
genes = df['gene_symbol'].dropna().drop_duplicates().head(200)
genes.to_csv('top_genes.txt', index=False, header=False)
"

# 3. Run enrichment analysis
cd /home/ubuntu/MethylEnricher
methylenricher --input top_genes.txt \
               --outdir enrichment_results \
               --top 200

# 4. View results
ls -lh enrichment_results/
cat enrichment_results/enrichment_top_q0.05.csv
```

## Integration with MethylDetector Workflow

MethylEnricher is part of the methylation analysis workflow:

1. **MethylDetector**: Identify DMPs from methylation data
2. **Gene Annotation**: Map DMPs to genes (external tool or database)
3. **MethylEnricher**: Perform pathway enrichment analysis
4. **Interpretation**: Identify biological processes affected by methylation changes

## Requirements

- Python 3.8+
- gseapy >= 1.1.0
- pandas >= 1.3.0
- numpy >= 1.20.0
- Internet connection (to query Enrichr APIs)

## Troubleshooting

### Import Error: gseapy not found

```bash
pip install gseapy
```

### Connection Errors

Enrichr queries require internet access. If you encounter connection errors:
- Check your internet connection
- Try again later (Enrichr servers may be temporarily unavailable)
- Use a different Enrichr mirror if available

### Empty Results

If no significant results are found:
- Try increasing `--top` parameter to include more genes
- Check that gene symbols are correctly formatted (HUGO gene symbols)
- Try different Enrichr libraries
- Consider using a less stringent cutoff

## Citation

If you use MethylEnricher in your research, please cite:

```
MethylEnricher: Gene Enrichment Analysis for Methylation Studies
[Your citation information here]
```

Also cite the underlying tools:
- **Enrichr**: Chen et al. (2013) BMC Bioinformatics
- **GSEApy**: Zhuoqing Fang et al. (2023) Bioinformatics

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support

For issues, questions, or suggestions:
- Open an issue on GitHub
- Contact the MethylDetector team

## Related Tools

- **MethylDetector**: DMP detection and analysis
- **MethylTrainer**: Classifier training from methylation data
- **MethylClassifier**: Sample classification using trained models
