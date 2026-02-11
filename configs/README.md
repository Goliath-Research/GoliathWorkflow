# Pipeline configs

Repo-level configuration examples for the MethylPipeline unified project config.

## Unified project config

Use a **single project JSON** with `--project` so each tool derives its paths and (where applicable) sample lists from one place. `output_base` is a global folder; each project uses a subfolder `{output_base}/{project_name}`. Paths follow:

- **Project root**: `{output_base}/{project_name}`
- **Centroids**: `{project_root}/centroids/{group1.label}` and `{project_root}/centroids/{group2.label}`
- **Detection**: `{project_root}/detection`
- **Mapper**: `{project_root}/mapper`
- **Enricher**: `{project_root}/enricher`
- **Classifier**: `{project_root}/classifier`
- **Alignment QC**: `{project_root}/alignment_qc`

### Example: `project_PCa_vs_Healthy_example.json`

Based on the latest PCa vs Healthy runs. Fields:

| Field | Description |
|-------|-------------|
| `project_name` | Project identifier (e.g. for metadata and naming). |
| `output_base` | Global output directory; step outputs live under `{output_base}/{project_name}`. |
| `group1` / `group2` | Each has `label` (used in centroid subdir names) and `sample_paths`. |
| `sample_paths` | List of sample directories, or paths to files (one path per line or JSON array). |
| `chromosomes` | Optional; shared chromosome list for centroid/detector batches. |
| `contexts` | Optional; shared contexts (e.g. `["CG"]`). |
| `path_remap` | Optional; prefix replacement when sample paths move (e.g. NAS); longest match applied. |
| `step_config` | Optional; per-step defaults. Keys: `centroid`, `detection`, `mapper`, `enricher`, `classifier`, `alignment_qc`. Each value is a JSON object merged into that step’s config. Override file (`--step-override`) and CLI args still override these. |

### Per-step configuration (`step_config`)

You can define defaults for each pipeline step in the project JSON under `step_config`:

```json
"step_config": {
  "centroid": {
    "base_config": { "min_coverage": 5, "use_gpu": true },
    "parallel_combinations": 4
  },
  "detection": { "min_pvalue": 0.01 },
  "mapper": { "csv_filename_pattern": "dmps-*.csv", "gtf": "/path/to/gencode.gtf" },
  "enricher": { "output_dir": "/custom/enricher" },
  "classifier": { "output_path": "/custom/classifier/results.csv" }
}
```

Resolution order: **project shared + derived paths → `step_config[step]` → `--step-override` file / CLI**. So you can set defaults in the project and still override per run.

**Mapper** and **enricher** defaults come from the same keys as their standalone configs: see `packages/methylmapper/configs/PCa_vs_Healthy_mapper_config.json` and `packages/methylenricher/configs/PCa_vs_Healthy_enricher_config.json`. When you run with `--project`, those step_config entries are applied automatically (e.g. `gtf`, `disease_term`, `enrich_*` for mapper; `gene_column`, `libraries`, `disease_only`, etc. for enricher). For mapper, set `grok_api_key` via environment or `--step-override` rather than in the project file.

### Usage

All pipeline CLIs use hyphens: `methyl-centroid`, `methyl-detector`, `methyl-mapper`, `methyl-enricher`, `methyl-classifier`, `methyl-qc`.

```bash
# Centroid for group1 (healthy)
methyl-centroid --project configs/project_PCa_vs_Healthy_example.json --group group1

# Centroid for group2 (pcancer)
methyl-centroid --project configs/project_PCa_vs_Healthy_example.json --group group2

# Detector (reads centroids, writes to detection)
methyl-detector --project configs/project_PCa_vs_Healthy_example.json

# Mapper (input from detection, output to mapper; gtf in step_config or --gtf)
methyl-mapper --project configs/project_PCa_vs_Healthy_example.json

# Enricher (input = mapper combined CSV, output to enricher)
methyl-enricher --project configs/project_PCa_vs_Healthy_example.json

# Classifier (model from detection, centroid dirs from project, output to classifier)
methyl-classifier --project configs/project_PCa_vs_Healthy_example.json

# Alignment QC (one JSON per sample to alignment_qc dir)
methyl-qc --project configs/project_PCa_vs_Healthy_example.json
```

Optional **step overrides** (e.g. `--step-override step.json`) can override specific fields per run without changing the project file.
