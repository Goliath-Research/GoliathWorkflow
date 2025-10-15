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

## Enrichment Analysis Workflow

### Step-by-Step Process

1. **Gene List Preparation**: Extract gene symbols from DMP analysis or provide custom list
2. **Database Query**: Query Enrichr databases via API
3. **Statistical Testing**: Perform Fisher's exact test for over-representation
4. **Multiple Testing Correction**: Apply Benjamini-Hochberg FDR correction
5. **Results Filtering**: Filter by adjusted p-value (q-value ≤ 0.05)
6. **Output Generation**: Create per-library and merged result files
7. **Interpretation**: Identify significantly enriched pathways and processes

### Over-Representation Analysis (ORA)

MethylEnricher uses the **hypergeometric test** (Fisher's exact test) to assess enrichment:

**Contingency table**:
```
                In Gene Set    Not in Gene Set    Total
In Input List        k              n-k              n
Not in Input         K-k            N-K-n+k         N-n
Total                K              N-K              N
```

Where:
- **k**: Genes in both your list and the gene set
- **n**: Total genes in your input list
- **K**: Total genes in the gene set
- **N**: Total genes in the background (genome)

**P-value calculation**:
```
P = Σ[i=k to min(n,K)] [C(K,i) * C(N-K,n-i)] / C(N,n)
```

**FDR correction** (Benjamini-Hochberg):
```
q-value = P * (m / rank)
```
where m = total number of tests

### Statistical Methods Explained

#### Enrichment Score Metrics

**Odds Ratio**:
```
OR = (k / (n-k)) / ((K-k) / (N-K-n+k))
```
- OR > 1: Over-representation (enrichment)
- OR = 1: No enrichment
- OR < 1: Under-representation (depletion)

**Combined Score** (Enrichr-specific):
```
CS = log(P-value) × Z-score
```
- Combines statistical significance with effect size
- Higher scores = more significant enrichment

**Z-score**:
```
Z = (observed - expected) / √expected
```
- Standardized measure of deviation from expected

## Configuration Parameters

### Input Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--input` | str | Required | Path to gene list file |
| `--outdir` | str | `results` | Output directory |
| `--top` | int | `200` | Number of top genes to use |
| `--libraries` | list | Default set | Enrichr libraries to query |
| `--cutoff` | float | `0.05` | Q-value threshold for filtering |
| `--organism` | str | `Human` | Organism for analysis |

### Default Libraries Explained

#### KEGG_2021_Human
- **Content**: Kyoto Encyclopedia of Genes and Genomes pathways
- **Use case**: Metabolic and signaling pathways
- **Gene sets**: ~300 pathways
- **Update frequency**: Annual

#### Reactome_2022
- **Content**: Curated biological pathways
- **Use case**: Cellular processes and reactions
- **Gene sets**: ~2,000 pathways
- **Update frequency**: Quarterly

#### GO_Biological_Process_2023
- **Content**: Gene Ontology biological processes
- **Use case**: Broad biological functions
- **Gene sets**: ~15,000 terms
- **Update frequency**: Continuous

#### GO_Molecular_Function_2023
- **Content**: Molecular-level activities
- **Use case**: Protein and enzyme functions
- **Gene sets**: ~4,000 terms
- **Update frequency**: Continuous

#### GO_Cellular_Component_2023
- **Content**: Cellular locations
- **Use case**: Subcellular localization
- **Gene sets**: ~1,500 terms
- **Update frequency**: Continuous

#### MSigDB_Hallmark_2020
- **Content**: Well-defined biological states/processes
- **Use case**: High-level biological themes
- **Gene sets**: 50 hallmark gene sets
- **Update frequency**: Infrequent (curated)

#### WikiPathway_2023_Human
- **Content**: Community-curated pathways
- **Use case**: Disease and drug pathways
- **Gene sets**: ~600 pathways
- **Update frequency**: Continuous

## Output Interpretation

### Understanding Enrichment Results

#### Significance Thresholds

- **Highly significant**: q-value < 0.001
  - Very strong evidence of enrichment
  - High confidence in biological relevance
  
- **Significant**: 0.001 ≤ q-value ≤ 0.01
  - Strong evidence of enrichment
  - Reliable for interpretation
  
- **Marginally significant**: 0.01 < q-value ≤ 0.05
  - Moderate evidence
  - Consider in context of other results
  
- **Not significant**: q-value > 0.05
  - Insufficient evidence
  - May be false positives

#### Overlap Interpretation

**Example**: `5/120` means:
- **5**: Genes from your list in this pathway
- **120**: Total genes in this pathway
- **Percentage**: 5/120 = 4.2% overlap

**Guidelines**:
- High overlap (>10%): Strong pathway involvement
- Medium overlap (5-10%): Moderate involvement
- Low overlap (<5%): Weak involvement, may be spurious

#### Combined Score Interpretation

- **Very high**: >100
  - Exceptionally strong enrichment
  - Top priority for follow-up
  
- **High**: 50-100
  - Strong enrichment
  - High confidence
  
- **Moderate**: 20-50
  - Reasonable enrichment
  - Consider in biological context
  
- **Low**: <20
  - Weak enrichment
  - Lower priority

### Result Files Explained

#### Per-Library Files

Each library gets its own file: `enrich_KEGG_2021_Human.csv`

**Columns**:
- `Term`: Pathway/gene set name
- `Overlap`: Format "k/K" (your genes / total genes)
- `P-value`: Raw p-value from Fisher's exact test
- `Adjusted P-value`: FDR-corrected q-value
- `Odds Ratio`: Enrichment ratio
- `Combined Score`: Enrichr's combined metric
- `Genes`: Comma-separated list of overlapping genes

#### Merged Results File

`enrichment_merged.csv`: All libraries combined, sorted by q-value

**Use cases**:
- Compare enrichment across different databases
- Identify pathways detected by multiple libraries
- Comprehensive overview of all results

#### Top Results File

`enrichment_top_q0.05.csv`: Top 200 significant hits (q ≤ 0.05)

**Use cases**:
- Quick summary of most significant findings
- Publication-ready results table
- Focus on high-confidence hits

## Common Use Cases

### 1. DMP-Associated Gene Enrichment

```bash
# Starting from MethylDetector output
cd /home/ubuntu/MethylDetector
python -m methyl_detector configs/cancer_vs_healthy.json

# Extract genes from biological DMPs
cd /home/ubuntu/MethylEnricher
python -c "
import pandas as pd
df = pd.read_csv('../MethylDetector/output/biological_dmps-chr1-CG.csv')
# Assuming gene_symbol column exists from MethylMapper
if 'gene_symbol' in df.columns:
    genes = df['gene_symbol'].dropna().drop_duplicates()
    genes.to_csv('dmp_genes.txt', index=False, header=False)
    print(f'Extracted {len(genes)} unique genes')
"

# Run enrichment
methylenricher --input dmp_genes.txt --outdir enrichment_chr1_CG --top 200
```

### 2. Comparing Multiple Conditions

```bash
# Enrichment for different comparisons
for comparison in healthy_vs_cancer treatment_vs_control responder_vs_nonresponder; do
    # Extract genes for this comparison
    python extract_genes.py ${comparison}_dmps.csv > ${comparison}_genes.txt
    
    # Run enrichment
    methylenricher \
      --input ${comparison}_genes.txt \
      --outdir enrichment_${comparison} \
      --top 300
done

# Compare results
python compare_enrichments.py enrichment_*/enrichment_merged.csv
```

### 3. Tissue-Specific Enrichment

```bash
# Analyze tissue-specific DMPs
methylenricher \
  --input liver_specific_genes.txt \
  --outdir enrichment_liver \
  --libraries KEGG_2021_Human Reactome_2022 GO_Biological_Process_2023 \
  --top 500
```

### 4. Time-Course Enrichment Analysis

```bash
# Analyze each timepoint
for timepoint in day0 day1 day3 day7 day14 day28; do
    echo "Analyzing ${timepoint}..."
    methylenricher \
      --input genes_${timepoint}.txt \
      --outdir enrichment_timecourse/${timepoint} \
      --top 200
done

# Track pathway dynamics over time
python analyze_temporal_enrichment.py enrichment_timecourse/*/enrichment_merged.csv
```

## Advanced Usage

### Custom Library Selection

```bash
# Focus on specific biological aspects
methylenricher \
  --input genes.txt \
  --outdir enrichment_cancer \
  --libraries \
    "KEGG_2021_Human" \
    "Reactome_2022" \
    "GWAS_Catalog_2023" \
    "DisGeNET" \
    "UK_Biobank_GWAS_v1" \
  --top 300
```

### Adjusting Stringency

```bash
# More stringent (fewer false positives)
methylenricher --input genes.txt --outdir strict_enrichment --cutoff 0.01 --top 100

# Less stringent (more exploratory)
methylenricher --input genes.txt --outdir exploratory_enrichment --cutoff 0.1 --top 500
```

### Programmatic Usage

```python
from methylenricher import run_enrichment
import pandas as pd

# Read gene list
with open('genes.txt', 'r') as f:
    genes = [line.strip() for line in f]

# Run enrichment
results = run_enrichment(
    genes=genes,
    libraries=[
        'KEGG_2021_Human',
        'Reactome_2022',
        'GO_Biological_Process_2023'
    ],
    outdir='programmatic_results',
    top=200,
    cutoff=0.05
)

# Process results
for library, df in results.items():
    sig_terms = df[df['Adjusted P-value'] <= 0.01]
    print(f"\n{library}: {len(sig_terms)} significant terms")
    print(sig_terms[['Term', 'Adjusted P-value', 'Overlap']].head())
```

## Integration Examples

### Complete MethylPipeline Workflow

```bash
#!/bin/bash
# complete_methylation_analysis.sh

# 1. Generate centroids
echo "Step 1: Generate centroids..."
cd /home/ubuntu/MethylCentroid
python -m methylcentroid.cli --config configs/healthy_config.json
python -m methylcentroid.cli --config configs/disease_config.json

# 2. Detect DMPs
echo "Step 2: Detect DMPs..."
cd /home/ubuntu/MethylDetector
python -m methyl_detector configs/healthy_vs_disease.json

# 3. Map DMPs to genes
echo "Step 3: Map DMPs to genes..."
cd /home/ubuntu/MethylMapper
python -m methylmapper \
  --dmps ../MethylDetector/output/biological_dmps-chr1-CG.csv \
  --output dmp_gene_mapping.csv

# 4. Extract gene symbols
echo "Step 4: Extract genes..."
python -c "
import pandas as pd
df = pd.read_csv('dmp_gene_mapping.csv')
genes = df['gene_symbol'].dropna().drop_duplicates()
genes.to_csv('mapped_genes.txt', index=False, header=False)
print(f'Extracted {len(genes)} genes')
"

# 5. Run enrichment analysis
echo "Step 5: Enrichment analysis..."
cd /home/ubuntu/MethylEnricher
methylenricher \
  --input ../MethylMapper/mapped_genes.txt \
  --outdir enrichment_healthy_vs_disease \
  --top 200

# 6. Summarize results
echo "Step 6: Generate summary..."
python -c "
import pandas as pd
df = pd.read_csv('enrichment_healthy_vs_disease/enrichment_top_q0.05.csv')
print(f'\nTop 10 enriched pathways:')
print(df[['Term', 'Adjusted P-value', 'Overlap']].head(10).to_string(index=False))
"

echo "\nAnalysis complete!"
```

### Integration with R for Visualization

```bash
# Export results for R visualization
methylenricher --input genes.txt --outdir enrichment_results

# In R
Rscript - <<'EOF'
library(ggplot2)
library(dplyr)

# Read results
df <- read.csv('enrichment_results/enrichment_top_q0.05.csv')

# Create dot plot
p <- df %>%
  head(20) %>%
  mutate(Term = reorder(Term, -log10(Adjusted.P.value))) %>%
  ggplot(aes(x = -log10(Adjusted.P.value), y = Term)) +
  geom_point(aes(size = Odds.Ratio, color = Combined.Score)) +
  scale_color_gradient(low = "blue", high = "red") +
  theme_minimal() +
  labs(title = "Top 20 Enriched Pathways",
       x = "-log10(Q-value)",
       y = "")

ggsave('enrichment_dotplot.pdf', p, width = 10, height = 8)
EOF
```

## Troubleshooting

### Issue: "No significant results found"

**Possible causes**:
1. Gene list too small (<10 genes)
2. Genes not annotated in selected databases
3. No biological enrichment (random gene set)
4. Cutoff too stringent

**Solutions**:
```bash
# Use more genes
methylenricher --input genes.txt --outdir results --top 500

# Relax cutoff
methylenricher --input genes.txt --outdir results --cutoff 0.1

# Try different libraries
methylenricher --input genes.txt --outdir results \
  --libraries KEGG_2021_Human GO_Biological_Process_2023
```

### Issue: "Connection timeout / API errors"

**Possible causes**:
- Enrichr servers temporarily unavailable
- Network connectivity issues
- Too many rapid requests

**Solutions**:
```bash
# Wait and retry
sleep 60
methylenricher --input genes.txt --outdir results

# Check Enrichr status: https://maayanlab.cloud/Enrichr/
```

### Issue: "Gene symbols not recognized"

**Problem**: Non-standard gene naming

**Solutions**:
```python
# Convert to HUGO gene symbols
import pandas as pd

# Example: Convert Ensembl to HUGO
genes = pd.read_csv('genes.txt', header=None, names=['gene_id'])

# Use biomaRt or mygene to convert
from mygene import MyGeneInfo
mg = MyGeneInfo()

results = mg.querymany(genes['gene_id'].tolist(), 
                      scopes='ensembl.gene',
                      fields='symbol',
                      species='human')

symbols = [r.get('symbol') for r in results if 'symbol' in r]

# Save converted symbols
pd.Series(symbols).drop_duplicates().to_csv('genes_hugo.txt', 
                                            index=False, 
                                            header=False)
```

### Issue: "Results seem biased/incomplete"

**Possible causes**:
- Background gene set not appropriate
- Library versions outdated
- Gene list biased (e.g., only well-studied genes)

**Solutions**:
- Use multiple libraries and compare
- Check library update dates
- Consider background correction methods
- Review gene list for technical biases

## Performance Considerations

### Speed

- **Small lists (<100 genes)**: <30 seconds
- **Medium lists (100-500 genes)**: 1-2 minutes
- **Large lists (>500 genes)**: 2-5 minutes

**Factors affecting speed**:
- Number of libraries queried
- Enrichr server load
- Network latency

### Best Practices

1. **Gene list size**: 50-500 genes optimal
   - Too few: Limited statistical power
   - Too many: Diluted signal

2. **Library selection**: Choose relevant databases
   - Start with default set for broad overview
   - Focus on specific databases for targeted analysis

3. **Multiple testing**: Always use FDR correction
   - Default q-value threshold (0.05) is appropriate
   - For exploratory analysis, consider 0.1

4. **Validation**: Cross-check results
   - Use multiple databases
   - Verify top hits manually
   - Consider biological plausibility

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
- **MethylMapper**: DMP-to-gene mapping
- **MethylTrainer**: Classifier training from methylation data
- **MethylClassifier**: Sample classification using trained models
