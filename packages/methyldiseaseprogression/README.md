# MethylDiseaseProgression

Aggregate per-comparison MethylMapper/MethylEnricher outputs into a single
disease-stage progression report.

## CLI

```bash
methyl-disease-progression --project /path/to/project.json
```

Optional flags:

- `--output-dir`: override default progression output directory.
- `--ordered-comparison-labels`: explicit disease-group order (comma-separated).
- `--strict-missing`: fail if any stage output is missing.
- `--report-md`: also write a human-readable markdown report.

## Project settings (`step_config.progression`)

The CLI can be configured via project JSON:

```json
"step_config": {
  "progression": {
    "enabled": true,
    "ordered_comparison_labels": ["pca_pca1", "pca_pca2", "pca_pca3", "pca_pca4"],
    "strict_missing": false,
    "report_md": true
  }
}
```

## Inputs

For each project comparison (`control_group`, `disease_group`), the tool reads:

- Mapper combined genes: `mapper/<control>/<disease>/all-gene_name-combined.csv`
  (or `step_config.enricher.combined_csv_name`).
- Enrichment table: `enricher/<control>/<disease>/enrichment_merged.csv`.
- Optional modules table: `enricher/<control>/<disease>/modules_ranked.csv`.

## Outputs

Default output directory: `<project_root>/progression`.

- `genes_long.csv`
- `pathways_long.csv`
- `modules_long.csv` (empty if no module files found)
- `entities_progression_labels.csv`
- `summary.json`
- optional `report.md`
