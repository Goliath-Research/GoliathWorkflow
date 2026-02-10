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
