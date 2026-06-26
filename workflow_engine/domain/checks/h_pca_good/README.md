# H_PCa_good — MC stability (healthy vs PCa, good cohort)

Buffy-coat **healthy vs PCa** using `healthy_good.csv` / `pca_good.csv`. Same MC design as Buffy (10 iterations, FeatureCuts BA tuning) with **biomarker filter** enabled.

## What lives where

| Location | Artifacts |
|----------|-----------|
| **Repo** (this bundle) | `configs/h_pca_good_mc_stability.program.json`, smoke `project_H_PCa_good.json` |
| **Repo** (`workflow_engine/domain/profiles/`) | `full_biomarker_gene_fc.profile.json` |
| **`/work/projects/prostate-cancer/`** | `configs/project_H_PCa_good.json`, `data/healthy_good.csv`, `pca_good.csv`, run outputs |

| Repo path | Role |
|-----------|------|
| `configs/h_pca_good_mc_stability.program.json` | MC DomainProgram |
| `../profiles/full_biomarker_gene_fc.profile.json` | Profile (DMP + gene FeatureCuts + biomarker filter) |

| `/work` path | Role |
|--------------|------|
| `configs/project_H_PCa_good.json` | Study manifest (cohorts, `step_config`, `n_iterations`) |
| `data/healthy_good.csv`, `data/pca_good.csv` | Sample lists |

The `configs/project_H_PCa_good.json` in this folder is a **reference / CI mirror** only; edit production JSON on `/work`.

## Run

From repo root with `.venv` activated:

```bash
methyl-workflow-run \
  --program workflow_engine/domain/checks/h_pca_good/configs/h_pca_good_mc_stability.program.json \
  --context-file workflow_engine/domain/profiles/full_biomarker_gene_fc.profile.json \
  --context '{"projectPath":"/work/projects/prostate-cancer/configs/project_H_PCa_good.json"}' \
  --parallel-workers 1
```

Outputs: `/work/projects/prostate-cancer/H_PCa_good/monte_carlo_runs/`.

## Config notes (on `/work` project JSON)

- Use canonical `stability_*` keys under `step_config.validation` (not legacy `stability_dmps_*` names)
- DMP FeatureCuts: `step_config.dmp_selection`
- `enricher.sort_by`: `gene_importance`
- `n_iterations`: 10 for the standard MC stability run
