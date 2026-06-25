# PCa1-5 CG workflow check bundle

DomainProgram fixtures and harness for `Healthy_vs_PCa1-5-CG` (hierarchical multiclass, buffy coat, CG context).

**Layout:** `configs/*.program.json` and profiles under `workflow_engine/domain/profiles/` are **repo** artifacts. Production `project_*.json` and sample CSVs live on **`/work/prostate-cancer/`** only; smoke copies here are for CI.

## Contents

| Path | Purpose |
|------|---------|
| `configs/project_Healthy_vs_PCa1-5-CG.json` | Full project config (24 chr, 30 MC iterations) |
| `configs/project_Healthy_vs_PCa1-5-CG_smoke.json` | Smoke config (chr 21, 2 iterations) |
| `configs/pca1_5_mc_stability*.program.json` | MC + stability workflows |
| `configs/pca1_5_freeze.program.json` | Production freeze (granular centroids/detectors) |
| `configs/pca1_5_model.program.json` | Model selection + post-model validation |
| `configs/pca1_5_full_lifecycle.program.json` | End-to-end composed pipeline |
| `instance/context*.json` | Workflow instance payloads |
| `check_pipeline.py` | Validate project, compile program, check templates |

## Quick check

```bash
source .venv/bin/activate
python workflow_engine/domain/checks/pca1_5_cg/check_pipeline.py
python workflow_engine/domain/checks/pca1_5_cg/check_pipeline.py \
  --program workflow_engine/domain/checks/pca1_5_cg/configs/pca1_5_mc_stability_smoke.program.json
```

## Centroid efficiency

`validation.plan_iterations` enriches each iteration with per-group `addSamples` / `removeSamples` and copies baseline HDF5 when incremental updates are needed. `pipeline.centroid` passes these via `stepOverride`; MethylCentroid owns all statistics.
