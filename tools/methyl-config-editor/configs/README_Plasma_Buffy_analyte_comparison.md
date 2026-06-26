# Plasma vs buffy-coat paired analyte comparison

Binary **healthy vs PCa** projects (~15 samples per arm, paired subjects) for cross-analyte discovery comparison. No stability or model training — single full-cohort run feeding MethylMapper and MethylEnricher.

## Project configs

| File | Analyte | Sample lists |
|------|---------|----------------|
| `project_Plasma_healthy_vs_PCa.json` | `cfdna` (fragmentomics on) | `/work/projects/prostate-cancer/data/healthy_p.csv`, `/work/projects/prostate-cancer/data/pca_p.csv` |
| `project_Buffy_healthy_vs_PCa.json` | `buffy_coat` (fragmentomics off) | `/work/projects/prostate-cancer/data/healthy_b.csv`, `/work/projects/prostate-cancer/data/pca_b.csv` |

Cluster copies: `/work/projects/prostate-cancer/configs/` (same content).

Comparison resolved: **all vs PCa** → artifacts under `detections/all/PCa/` and `mapper/all/PCa/`.

Mapper uses **discovery** DMPs (`dmps-*-discovery.csv`) for broad/raw biology.

## Run workflow (standalone CLIs)

Activate the repo venv first:

```bash
source /path/to/MethylPipeline/.venv/bin/activate
```

### Plasma

```bash
PROJ=/work/projects/prostate-cancer/configs/project_Plasma_healthy_vs_PCa.json

# One command builds both cohort centroids (healthy + PCa):
methyl-centroid --project "$PROJ" --group all

# Or run each cohort separately (group1/group2, 0/1, or project labels all/PCa):
# methyl-centroid --project "$PROJ" --group group1
# methyl-centroid --project "$PROJ" --group PCa

methyl-detector --project "$PROJ"
methyl-mapper --project "$PROJ"
methyl-enricher --project "$PROJ"
methyl-fragmentomics --project "$PROJ"
methyl-qc --project "$PROJ"
```

### Buffy-coat

```bash
PROJ=/work/projects/prostate-cancer/configs/project_Buffy_healthy_vs_PCa.json

methyl-centroid --project "$PROJ" --group all

methyl-detector --project "$PROJ"
methyl-mapper --project "$PROJ"
methyl-enricher --project "$PROJ"
```

Do **not** run `methyl-validation --stability`, `--freeze`, or `--model` for these small-N discovery runs.

## Key artifact paths

For each project `{output_base}/{project_name}/` (default `/work/projects/prostate-cancer/Plasma_healthy_vs_PCa/`):

| Artifact | Path |
|----------|------|
| Raw DMPs | `detections/all/PCa/dmps-*-discovery.csv` |
| Mapper genes | `mapper/all/PCa/all-gene_name-combined.csv` |
| Enricher | `enricher/all/PCa/` |

## Cross-analyte comparison

After both projects finish, compare overlap with:

```bash
# Discovery DMPs (default; broad biology panel)
python tools/compare_analyte_outputs.py \
  --plasma-root /work/projects/prostate-cancer/Plasma_healthy_vs_PCa \
  --buffy-root /work/projects/prostate-cancer/Buffy_healthy_vs_PCa \
  --comparison all/PCa \
  --out /work/projects/prostate-cancer/analyte_comparison/all_vs_PCa/discovery

# Classifier DMPs (model candidates; same methyl-detector run, no re-run)
python tools/compare_analyte_outputs.py \
  --plasma-root /work/projects/prostate-cancer/Plasma_healthy_vs_PCa \
  --buffy-root /work/projects/prostate-cancer/Buffy_healthy_vs_PCa \
  --comparison all/PCa \
  --dmp-source classifier \
  --out /work/projects/prostate-cancer/analyte_comparison/all_vs_PCa/classifier
```

`--dmp-source` accepts `discovery` (default), `classifier`, or `classifier-extended`.

### Classifier-based gene overlap (optional re-map)

Detection does not need re-running. Re-map from classifier DMPs into a **separate** mapper directory so discovery mapper output is preserved.

**Do not reuse a shared `$ROOT` between plasma and buffy** — if you forget to change it, both runs write to the same folder. Use **per-project override JSON** (paths baked in) or derive the project output root from each `--project` config:

```bash
source .venv/bin/activate

# Project config JSON (not the output directory)
PLASMA_PROJ=/work/projects/prostate-cancer/configs/project_Plasma_healthy_vs_PCa.json
BUFFY_PROJ=/work/projects/prostate-cancer/configs/project_Buffy_healthy_vs_PCa.json

# Optional: derive output root from config (unique per analyte)
# PLASMA_ROOT=$(python -c "from methyl_utils import load_project; print(load_project('$PLASMA_PROJ').get_derived_paths().output_base)")
```

**Recommended:** per-analyte step overrides in `configs/` (no shared shell variables):

```bash
methyl-mapper --project "$PLASMA_PROJ" \
  --step-override tools/methyl-config-editor/configs/mapper_classifier_plasma.json

methyl-mapper --project "$BUFFY_PROJ" \
  --step-override tools/methyl-config-editor/configs/mapper_classifier_buffy.json
```

Each override file sets `csv_pattern` and `output_dir`. For a single comparison, `output_dir` may be the full path (`.../mapper_classifier/all/PCa`). For projects with multiple comparisons, set `output_dir` to the mapper base (`.../mapper_classifier`); the resolver appends `{control}/{disease}` per comparison.

If you prefer explicit CLI paths, use the **full detection glob** (not a bare filename) and a **project-specific** output dir:

```bash
methyl-mapper --project "$PLASMA_PROJ" \
  --csv-pattern "/work/projects/prostate-cancer/Plasma_healthy_vs_PCa/detections/all/PCa/dmps-*-classifier.csv" \
  --output-dir "/work/projects/prostate-cancer/Plasma_healthy_vs_PCa/mapper_classifier/all/PCa"
```

Compare genes:

```bash
python tools/compare_analyte_outputs.py \
  --plasma-root /work/projects/prostate-cancer/Plasma_healthy_vs_PCa \
  --buffy-root /work/projects/prostate-cancer/Buffy_healthy_vs_PCa \
  --comparison all/PCa \
  --dmp-source classifier \
  --mapper-subdir mapper_classifier \
  --out /work/projects/prostate-cancer/analyte_comparison/all_vs_PCa/classifier
```

### Enricher on classifier mapper genes (optional)

`methyl-enricher` reads the mapper combined CSV. Use per-analyte override files so plasma and buffy do not share paths:

```bash
methyl-enricher --project "$PLASMA_PROJ" \
  --step-override tools/methyl-config-editor/configs/enricher_classifier_plasma.json

methyl-enricher --project "$BUFFY_PROJ" \
  --step-override tools/methyl-config-editor/configs/enricher_classifier_buffy.json
```

Use enricher outputs under `enricher_classifier/` for pathway/module differences; gene overlap for cross-analyte comparison still comes from mapper `all-gene_name-combined.csv`.

Outputs: `dmp_overlap_summary.json`, `gene_overlap_summary.json`, and CSV lists of shared/private DMP loci and genes.

### Pre-flight QC (paired cohort)

Verify 1:1 patient pairing across analytes before interpreting biology, e.g. a manifest at `/work/projects/prostate-cancer/data/plasma_buffy_pairing.csv` with columns `patient_id`, `plasma_sample`, `buffy_sample`, `group`.

## Config validation

```bash
python -c "
from methyl_utils import load_project
p = load_project('tools/methyl-config-editor/configs/project_Plasma_healthy_vs_PCa.json')
print(p.get_detection_output_dir('all', 'PCa'))
print(p.get_mapper_output_dir('all', 'PCa'))
"
```
