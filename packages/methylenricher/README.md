# MethylEnricher

## Overview

A command-line tool for gene enrichment analysis of Differentially Methylated Positions (DMPs) from methylation studies. MethylEnricher performs Over-Representation Analysis (ORA) using Enrichr databases to identify significantly enriched pathways, ontologies, and gene sets.

## Features

- Multiple Database Support: Query KEGG, Reactome, GO, MSigDB Hallmark, WikiPathways, and more
- Batch Processing: Analyze multiple gene lists simultaneously
- Flexible Input: Accept gene lists (TXT) or MethylMapper CSV/TSV outputs
- Comprehensive Output: Per-library results plus merged summaries
- FDR Filtering: Automatic filtering of significant hits (q-value ≤ 0.05)
- Easy Integration: Works seamlessly with MethylMapper outputs

## Installation

```bash
pip install -e .
```

## Usage

### Command Line

CLI: **methyl-enricher**. With pipeline project config: `methyl-enricher --project configs/project.json`.

```bash
methyl-enricher --input genes.txt --outdir enrichment_results
```

### Using MethylMapper Output

```bash
# Use the combined MethylMapper CSV directly
methyl_enricher --input mapped_features/all-gene_name-combined.csv \
               --gene-column gene_name

# Optional: enrich only disease-associated genes (if present)
methyl_enricher --input mapped_features/all-gene_name-combined.csv \
               --gene-column gene_name \
               --disease-only

# Sort by a weight/score column before selecting top genes
methyl_enricher --input mapped_features/all-gene_name-combined.csv \
               --gene-column gene_name \
               --sort-by total_weight \
               --top 200
```

**Note:** When input is CSV/TSV, the tool auto-sorts by `total_weight` if present (unless `--sort-by` is provided).

### Focusing on important genes (MethylMapper CSV)

When the input is MethylMapper’s `all-gene_name-combined.csv`, you can filter to disease-relevant and high-signal genes before running pathway enrichment:

| Filter | CLI option | Description |
|--------|------------|-------------|
| Disease-associated only | `--disease-only` | Keep rows with `disease_associated == True` |
| Association type | `--disease-association-type direct indirect` | Keep only these `disease_association_type` values |
| Min evidence level | `--min-disease-evidence-level medium` | `disease_evidence_level`: high, medium, or low |
| Min publications | `--min-disease-publications 2` | Minimum `disease_publications` |
| Min disease score | `--min-disease-score 0.2` | Minimum Open Targets `disease_score` |
| Min DMP count | `--min-dmp-count 2` | Minimum `dmp_count` per gene |
| Min unique DMPs | `--min-unique-dmps 1` | Minimum `unique_dmps` |
| Max gene q-value | `--max-gene-q-value 0.05` | Keep genes with `gene_q_value` ≤ this |
| Min effect size | `--min-mean-effect-size 0.3` | Minimum `mean_effect_size` / weight |
| Min \|gene_z\| | `--min-gene-z 1.5` | Minimum absolute `gene_z` |
| Min gene importance | `--min-gene-importance 0.5` | Minimum `gene_importance` / weight |
| Feature types | `--feature-types gene exon` | Keep only these `feature_type` values |

**Example: PCa-focused enrichment**

```bash
methyl_enricher --input /work/data/.../PCa_vs_Healthy/mapped_features/all-gene_name-combined.csv \
  --gene-column gene_name \
  --disease-only \
  --disease-association-type direct indirect \
  --min-disease-evidence-level medium \
  --min-disease-score 0.2 \
  --min-dmp-count 2 \
  --max-gene-q-value 0.05 \
  --top 150 \
  --outdir enricher_pca
```

### Python API

```python
from methyl_enricher import run_enrichment

results = run_enrichment(
    input_file="mapped_features/all-gene_name-combined.csv",
    output_dir="enrichment_results",
    gene_column="gene_name",
    disease_only=True,
    sort_by="total_weight",
    top_n=200
)
```

## Configuration file

You can put all options in a JSON config and run with a single `--config` argument. CLI options override config.

**Example `enricher_config.json`:**

```json
{
  "input": "/path/to/all-gene_name-combined.csv",
  "outdir": "enricher_pca",
  "gene_column": "gene_name",
  "disease_only": true,
  "disease_association_type": ["direct", "indirect"],
  "min_disease_evidence_level": "medium",
  "min_disease_score": 0.2,
  "min_dmp_count": 2,
  "max_gene_q_value": 0.05,
  "sort_by": "total_weight",
  "top": 150,
  "cutoff": 0.05,
  "organism": "Human"
}
```

**Run with config:**

```bash
methyl_enricher --config enricher_config.json
# Override specific options
methyl_enricher --config enricher_config.json --top 100 --outdir other_results
```

Config keys use underscores (e.g. `disease_association_type`, `min_disease_score`). Optional keys can be omitted; see `configs/enricher_config_example.json` for a full example.

## Output

- **Per-library**: `enrich_<LibraryName>.csv` — full Enrichr results per database.
- **Merged**: `enrichment_merged.csv` — all libraries combined, with a `library` column.
- **Top hits**: `enrichment_top_q0.05.csv` (or your `--cutoff`) — significant terms only (q ≤ cutoff), up to 200.

See **[docs/MethylEnricher_after_MethylMapper.md](docs/MethylEnricher_after_MethylMapper.md)** for full functionality, expected input (MethylMapper combined CSV), filter/sort options, and output file descriptions.

## Integration

Use with gene lists from MethylMapper in MethylPipeline, including CSV/TSV outputs (e.g. `mapped_features/all-gene_name-combined.csv`). For a full description of MethylEnricher’s role after MethylMapper and expected outputs, see [docs/MethylEnricher_after_MethylMapper.md](docs/MethylEnricher_after_MethylMapper.md).

## Troubleshooting

- No results: Increase top genes or relax cutoff
- Connection errors: Check internet and retry

## License

MIT License - see LICENSE file for details.
