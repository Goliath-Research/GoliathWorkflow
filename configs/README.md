# Pipeline configs

Repo-level configuration examples for the MethylPipeline unified project config.

## Unified project config

Use a **single project JSON** with `--project` so each tool derives its paths and (where applicable) sample lists from one place. Paths follow:

`{output_base}/{centroids|detection|mapper|enricher|classifier}`

- **Centroids**: `{output_base}/centroids/{group1.label}` and `{output_base}/centroids/{group2.label}`
- **Detection**: `{output_base}/detection`
- **Mapper**: `{output_base}/mapper`
- **Enricher**: `{output_base}/enricher`
- **Classifier**: `{output_base}/classifier`

### Example: `project_PCa_vs_Healthy_example.json`

Based on the latest PCa vs Healthy runs. Fields:

| Field | Description |
|-------|-------------|
| `project_name` | Project identifier (e.g. for metadata and naming). |
| `output_base` | Project root; all step outputs live under this directory. |
| `group1` / `group2` | Each has `label` (used in centroid subdir names) and `sample_paths`. |
| `sample_paths` | List of sample directories, or paths to files (one path per line or JSON array). |
| `chromosomes` | Optional; shared chromosome list for centroid/detector batches. |
| `contexts` | Optional; shared contexts (e.g. `["CG"]`). |
| `path_remap` | Optional; prefix replacement when sample paths move (e.g. NAS); longest match applied. |
| `step_config` | Optional; per-step defaults. Keys: `centroid`, `detection`, `mapper`, `enricher`, `classifier`. Each value is a JSON object merged into that step’s config. Override file (`--step-override`) and CLI args still override these. |

### Per-step configuration (`step_config`)

You can define defaults for each pipeline step in the project JSON under `step_config`:

```json
"step_config": {
  "centroid": {
    "base_config": { "min_coverage": 5, "use_gpu": true },
    "parallel_combinations": 4
  },
  "detection": { "min_pvalue": 0.01 },
  "mapper": { "csv_pattern": "/path/to/detection/dmps-*-3-optimized.csv" },
  "enricher": { "output_dir": "/custom/enricher" },
  "classifier": { "output_path": "/custom/classifier/results.csv" }
}
```

Resolution order: **project shared + derived paths → `step_config[step]` → `--step-override` file / CLI**. So you can set defaults in the project and still override per run.

### Usage

```bash
# Centroid for group1 (healthy)
methyl_centroid --project configs/project_PCa_vs_Healthy_example.json --group group1

# Centroid for group2 (pcancer)
methyl_centroid --project configs/project_PCa_vs_Healthy_example.json --group group2

# Detector (reads centroids, writes to detection)
methyl_detector --project configs/project_PCa_vs_Healthy_example.json

# Mapper bedtools (input from detection, output to mapper; still need --gtf)
methyl_mapper_bedtools --project configs/project_PCa_vs_Healthy_example.json --gtf /path/to/gencode.gtf

# Enricher (input = mapper combined CSV, output to enricher)
methyl_enricher --project configs/project_PCa_vs_Healthy_example.json

# Classifier (model from detection, centroid dirs from project, output to classifier)
methyl_classifier --project configs/project_PCa_vs_Healthy_example.json
```

Optional **step overrides** (e.g. `--step-override step.json`) can override specific fields per run without changing the project file.
