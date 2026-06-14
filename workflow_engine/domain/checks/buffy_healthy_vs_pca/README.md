# Buffy healthy vs PCa — DomainProgram architecture check

End-to-end fixture matching the cluster project at `/work/prostate-cancer/configs/project_Buffy_healthy_vs_PCa.json` (legacy alias: `Buffy_healthy_vs_PCa.json`). Use it to validate **DomainProgram → compiler → collection bindings → minimal instance context** before running workers on the cluster.

## Bundle layout

| Path | Role |
|------|------|
| `configs/project_Buffy_healthy_vs_PCa.json` | Workflow-ready project config (same as methyl-config-editor copy, with **explicit** `comparisons[]` array) |
| `configs/buffy_data_driven.program.json` | DomainProgram: comparisons × contexts × chromosomes → centroids + detector, then mapper + enricher |
| `instance/context.json` | Minimal instance payload `{ "projectPath": "…" }` |
| `data/healthy_b.csv`, `data/pca_b.csv` | Sample list stubs (15 healthy + 15 PCa buffy-coat folders) |
| `check_pipeline.py` | Validate project, compile program, optionally install/deploy |
| `compiled/compiled_workflow.json` | Generated `WorkflowDefinitionSpec` (after running check) |

**Note:** The editor config uses `"comparisons": "control_vs_each_disease"`. The workflow engine resolves collection bindings with plain `jsonPath` only, so this bundle expands that shorthand to:

```json
"comparisons": [
  { "control_group": "all", "disease_group": "PCa", "label": "PCa" }
]
```

## Quick validation (repo only)

```bash
source .venv/bin/activate
python workflow_engine/domain/checks/buffy_healthy_vs_pca/check_pipeline.py
```

Expected compile summary (24 chromosomes × 1 context × 1 comparison):

- **3** FOREACH nodes (comparisons, contexts, chromosomes)
- **74** leaf ACTION tasks (72 chr×ctx modeling + mapper + enricher)
- **4** collection bindings (`project`, `chromosomes`, `contexts`, `comparisons`)

## Install to `/work/` (cluster paths)

```bash
bash workflow_engine/domain/checks/buffy_healthy_vs_pca/install_to_work.sh
# or overwrite existing files:
bash workflow_engine/domain/checks/buffy_healthy_vs_pca/install_to_work.sh --force
```

Installs:

- `/work/prostate-cancer/configs/project_Buffy_healthy_vs_PCa.json`
- `/work/prostate-cancer/configs/Buffy_healthy_vs_PCa.json` → symlink to `project_…`
- `/work/prostate-cancer/configs/buffy_data_driven.program.json`
- `/work/prostate-cancer/configs/buffy_instance_context.json`
- `/work/prostate-cancer/data/healthy_b.csv`, `pca_b.csv`

Ensure sample HDF5 data exists under `/work/samples/` for the CSV entries before running workers.

## Deploy workflow + start instance (PostgreSQL)

Requires deployed `wf` schema (see `workflow_engine/sql_pg/`).

```bash
source .venv/bin/activate
python workflow_engine/domain/checks/buffy_healthy_vs_pca/check_pipeline.py \
  --install --force \
  --deploy \
  --dsn "$WF_PG_DSN"
```

This calls `wf_repo_create_workflow_graph`, creates an instance with minimal context, and runs `sp_start_workflow_instance` (scope init + collection binding resolution + graph activation).

## Smoke variant (single chromosome)

For faster DB/worker smoke tests without editing the full project:

```bash
python workflow_engine/domain/checks/buffy_healthy_vs_pca/check_pipeline.py \
  --program configs/buffy_data_driven_smoke.program.json \
  --project configs/project_Buffy_healthy_vs_PCa_smoke.json \
  --write-spec compiled/smoke
```

Expected: **5** leaf tasks (3 modeling on chr 21 + mapper + enricher).

## Manual worker steps (standalone CLIs)

Same analysis order as before the DomainProgram layer — useful to compare worker I/O against compiled `input_json`:

```bash
PROJ=/work/prostate-cancer/configs/project_Buffy_healthy_vs_PCa.json
methyl-centroid --project "$PROJ" --group all
methyl-detector --project "$PROJ"
methyl-mapper --project "$PROJ"
methyl-enricher --project "$PROJ"
```

Artifacts land under `/work/prostate-cancer/Buffy_healthy_vs_PCa/` (detections `all/PCa`, mapper `all/PCa`, enricher `all/PCa`).

## Related docs

- [`workflow_engine/docs/pipeline_architecture.md`](../../docs/pipeline_architecture.md) — Section 3.5 (DomainProgram + collection bindings)
- [`tools/methyl-config-editor/configs/README_Plasma_Buffy_analyte_comparison.md`](../../../tools/methyl-config-editor/configs/README_Plasma_Buffy_analyte_comparison.md) — original Buffy vs Plasma study notes
