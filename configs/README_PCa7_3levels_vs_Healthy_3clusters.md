# PCa7 3 levels vs Healthy 3 clusters – pipeline commands

This project uses **N-group** config: one healthy cohort (clustered into up to 3 groups) and one PCa cohort split into 3 levels (early / medium / late) via `level_labels_path`.

- **Config**: `configs/project_PCa7_3levels_vs_Healthy_3clusters.json`
- **PCa levels CSV**: `configs/pca7_levels.csv` (path → level: early, medium, late). Replace with real Gleason/staging when available.
- **Project root**: `{output_base}/{project_name}` = `/work/david-gladys/all-prostate/PCa7_3levels_vs_Healthy_3clusters`

Resolved groups from the config: `healthy`, `pca_early`, `pca_medium`, `pca_late` (4 groups). Health discovery adds `healthy_level1`, `healthy_level2`, `healthy_level3` (up to 3).

Run all commands from the **MethylPipeline repository root** so `configs/pca7_levels.csv` resolves.

---

## 1. Build PCa level centroids (3 groups)

Build centroids for the three PCa levels (pca_early, pca_medium, pca_late) from the project config and `level_labels_path`:

```bash
python -m methyl_centroid.cli --project configs/project_PCa7_3levels_vs_Healthy_3clusters.json --group 1
```

Output: `{project_root}/centroids/pca_early`, `pca_medium`, `pca_late`.

---

## 2. Build single “healthy” centroid (for binary detection)

Build the overall healthy centroid so detection has a valid reference (optional if you only care about 6-class later):

```bash
python -m methyl_centroid.cli --project configs/project_PCa7_3levels_vs_Healthy_3clusters.json --group 0
```

Output: `{project_root}/centroids/healthy`.

---

## 3. Health discovery: cluster healthy into up to 3 groups

Cluster the healthy cohort and build one centroid dir per cluster (healthy_level1, healthy_level2, healthy_level3):

```bash
python -m methyl_utils.health_discovery configs/project_PCa7_3levels_vs_Healthy_3clusters.json \
  --force-k 3 \
  --label-prefix healthy_level \
  --group group1
```

- Assignments and cluster JSON: `{project_root}/health_discovery/`
- Centroid dirs: `{project_root}/centroids/healthy_level1`, `healthy_level2`, `healthy_level3` (if k=3).

Use `--no-centroid` to only run clustering and write the assignments CSV without building centroid dirs.

---

## 4. Detection (binary: healthy vs pca_early)

Run MethylDetector with the project config (uses first two resolved groups: healthy, pca_early):

```bash
python -m methyl_detector.cli.main --project configs/project_PCa7_3levels_vs_Healthy_3clusters.json
```

Output: `{project_root}/detection/` (DMPs, model, etc.).

---

## 5. Classifier (binary validation)

Run the classifier with the project config (centroid validation: healthy vs pca_early):

```bash
python -m methyl_classifier.cli.main --project configs/project_PCa7_3levels_vs_Healthy_3clusters.json
```

Output: `{project_root}/classifier/classification_results.csv` (and optional classifier .pkl / sample list if configured).

---

## 6. (Optional) Multiclass with 6 groups

To use all 6 centroid dirs (healthy_level1, healthy_level2, healthy_level3, pca_early, pca_medium, pca_late), you need a merged DMP list (e.g. from one-vs-rest or pairwise detection runs) and a multiclass config.

Build a multiclass config from the project (expects a DMP CSV under detection_dir; adjust if you merged DMPs elsewhere):

```bash
cd /home/dizada/MethylPipeline
python -c "
from pathlib import Path
from methyl_classifier.project_resolver import build_multiclass_config_from_project
import json
cfg = build_multiclass_config_from_project(
    'configs/project_PCa7_3levels_vs_Healthy_3clusters.json',
    dmps_csv=None,
    output_model=None,
    weights_column='importance',
)
# Override classes to the 6 discovered + level groups (replace with your actual centroid paths)
project_root = '/work/david-gladys/all-prostate/PCa7_3levels_vs_Healthy_3clusters'
cfg['classes'] = [
    {'name': 'healthy_level1', 'centroid_dir': f'{project_root}/centroids/healthy_level1'},
    {'name': 'healthy_level2', 'centroid_dir': f'{project_root}/centroids/healthy_level2'},
    {'name': 'healthy_level3', 'centroid_dir': f'{project_root}/centroids/healthy_level3'},
    {'name': 'pca_early', 'centroid_dir': f'{project_root}/centroids/pca_early'},
    {'name': 'pca_medium', 'centroid_dir': f'{project_root}/centroids/pca_medium'},
    {'name': 'pca_late', 'centroid_dir': f'{project_root}/centroids/pca_late'},
]
Path('configs/multiclass_6groups_config.json').write_text(json.dumps(cfg, indent=2))
print('Wrote configs/multiclass_6groups_config.json')
"
```

Then build the multiclass model (after you have a DMP CSV that spans the 6 classes, e.g. merged from multiple runs):

```bash
python packages/methylclassifier/build_multiclass_model.py configs/multiclass_6groups_config.json
```

---

## Short test sequence (binary path)

Minimal test of the new pipeline (binary detection/classifier):

```bash
# From MethylPipeline repo root
export PYTHONPATH="packages/methylutils:packages/methylcentroid:packages/methyldetector:packages/methylclassifier:packages/methylcluster:$PYTHONPATH"

# 1. PCa level centroids
python -m methyl_centroid.cli --project configs/project_PCa7_3levels_vs_Healthy_3clusters.json --group 1

# 2. Healthy centroid (for detection)
python -m methyl_centroid.cli --project configs/project_PCa7_3levels_vs_Healthy_3clusters.json --group 0

# 3. Health discovery (3 healthy clusters)
python -m methyl_utils.health_discovery configs/project_PCa7_3levels_vs_Healthy_3clusters.json --force-k 3 --group group1

# 4. Detection
python -m methyl_detector.cli.main --project configs/project_PCa7_3levels_vs_Healthy_3clusters.json

# 5. Classifier
python -m methyl_classifier.cli.main --project configs/project_PCa7_3levels_vs_Healthy_3clusters.json
```

If the environment uses the monorepo layout (e.g. `pip install -e packages/methylutils` etc.), you can omit `PYTHONPATH` and run the same commands.
