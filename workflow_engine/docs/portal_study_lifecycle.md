# Portal staged study lifecycle

Staged orchestration for multi-group studies: **SamplePrep** completes, then the portal starts **StudyValidationLifecycle** with a pre-planned `context_json`.

## Architecture (three paths)

| Actor | Transport | Purpose |
|-------|-----------|---------|
| **EpiPortal** | **Azure SQL direct** | Plan context, create/start instances, monitor (`portal.sp_*` procs) |
| **Workers** | Gateway `/v1/workers/*` | Execute READY action tasks |
| **CI / operators** | Admin CLI + direct DB scripts | `methyl-study-start`, `seed_action_catalog.py`, `deploy_workflow_definitions.sh` |

The portal **never** calls the REST gateway. The gateway is **worker-only**. Study compile/plan/start for CI and Cursor developer mode uses **`methyl-study-start`** (backend-agnostic DB client); production uses portal SQL.

Deploy portal SQL API: [`../sql/portal_workflow_api.sql`](../sql/portal_workflow_api.sql) (Azure SQL) or [`../sql_pg/portal_workflow_api.sql`](../sql_pg/portal_workflow_api.sql) (PostgreSQL).

## Instance 1 — SamplePrepPipeline

Start when FASTQs are ready. Each sample in `context_json.samples[]` runs download → Parabricks → QC (+ optional remediation) → MethylExtractor → extraction QC → archive.

### Option A — Portal database (recommended for EpiPortal)

Middle-tier runs the sample prep planner in-process, then:

```sql
-- After planning context_json and resolving workflow_version_id:
EXEC portal.sp_create_and_start_instance
  @workflow_version_id = @sample_prep_version_id,
  @context_json = @planned_context_json;
```

Read `portal.resource_profile` for archive defaults when building context (same rules as [`archive_profile_resolver.py`](../portal/archive_profile_resolver.py)).

Monitor:

```sql
EXEC portal.sp_get_instance_tasks @workflow_instance_id = @instance_id;
```

### Option B — Admin CLI (CI / Cursor developer mode)

**`fastqStorage` is always required** — initial FASTQs come from **laboratory-owned** storage.

```bash
methyl-study-start sample-prep-start request.json
# request.json: projectPath, workflow_version_id, fastqStorage, sampleCsvs, ...
```

See [`sample_prep_test_bed.md`](sample_prep_test_bed.md) for smoke scripts and QC semantics.

## Instance 2 — StudyValidationLifecycle

The portal **pre-plans** iterations before starting the workflow. Two equivalent paths:

### Option A — Admin CLI (recommended for CI)

```bash
methyl-study-start validation-start request.json
# request.json: projectPath, workflow_version_id, featureIterations, seed, ...
```

Or register from a DomainProgram on the fly (include `program_path` in the JSON body).

Response (stdout JSON):

```json
{
  "instance_id": 123,
  "workflow_version_id": 45,
  "context_json": { "...": "..." },
  "n_iterations": 30
}
```

### Option B — Manual plan + enrich + portal SQL

Plan iterations with `methyl_validation.workflow_planner.plan_validation_context`, merge via `finalize_instance_context`, then:

```sql
EXEC portal.sp_create_and_start_instance
  @workflow_version_id = @study_validation_version_id,
  @context_json = @planned_context_json;
```

`chrom_mapping` is derived from `project.chromosomes` at extract time (no shared-storage mapping file required). Optional overrides: profile/site `actionConfig.methyl_extract.contig_naming`, `chromosome_overrides`, inline `chrom_mapping` in instance `context_json`, or program `stepOverride`.

## Deploy system graphs

```bash
export BACKEND_DB=mssql   # or postgres
# AZURE_SQL_* or POSTGRES_*
bash scripts/deploy_workflow_definitions.sh
python workflow_engine/sql_mssql/seed_action_catalog.py --use-db
```

## StudyValidationLifecycle phases

| Phase | Action(s) |
|-------|-----------|
| Feature MC | `validation.plan_iterations` + FOREACH iteration → centroids + detectors |
| Stability | `validation.stability` |
| Freeze readiness | `validation.stability_freeze_readiness` |
| Freeze panel | `validation.prepare_freeze_project` → binds `fixedDmpPanel` |
| Freeze re-run | FOREACH groups/comparisons/chromosomes with `${var.fixedDmpPanel}` |
| Biological | `pipeline.mapper`, `pipeline.enricher`, `pipeline.progression` |
| Model MC | `validation.model_mc` (shared runs + per-backend loops) |
| Selection | `validation.select_best_model` → binds `selectedBackend` |
| Hold-out | `validation.post_model_validation` |

DomainProgram: `workflow_engine/domain/checks/pca1_5_cg/configs/study_validation_lifecycle.program.json`

Compiler output bindings (scope write-back on task complete):

| Action | Scope variable | JSON path |
|--------|----------------|-----------|
| `validation.plan_iterations` | `iterations` | `$.iterations` |
| `validation.prepare_freeze_project` | `fixedDmpPanel` | `$.fixedDmpPanel` |
| `validation.select_best_model` | `selectedBackend` | `$.selectedBackend` |

## Project defaults (four-layer config)

Tool parameters are **not** in the study manifest. Portal-facing validation defaults live in **pipeline profile** and/or **site** `actionConfig.validation` (merged into instance `context_json` at start):

```json
"actionConfig": {
  "validation": {
    "feature_iterations": 30,
    "backends": ["ecdf", "tabular_sklearn", "generative_hybrid"],
    "selection_metric": "balanced_accuracy"
  }
}
```

Pass `pipelineProfile` (e.g. `mc_gene_fc`) in `context_json` or `--context-file` when starting runs.

Parabricks alignment settings: profile/site `actionConfig.parabricks` (`image`, `bwa_threads`, `gpu_flags`, …) with task `input_json` / `resolvedConfig` overrides; env vars remain as fallback when config is absent.

## Worker fleet and node prerequisites

Workers poll `POST /v1/workers/tasks/request` and must **not** connect to the database directly. Full details: [`workers/WORKER_PROTOCOL.md`](../../workers/WORKER_PROTOCOL.md).

**Install:** run [`scripts/install_all.sh`](../../scripts/install_all.sh) (or `setup_host.sh`) so all `packages/*` CLIs and validation handlers are on the node, then `pip install -e workers/`.

**Registration options:**

- **Per-capability workers** (recommended in production): register one worker ID per capability (`methyl-centroid`, `methyl-detector`, `validation.model-mc`, …).
- **Omnibus worker** (dev): omit `WORKER_CAPABILITY` so one process claims any task; the node must have GPU (Parabricks), `MethylExtractor`, and the full Python stack.

**External binaries:** Parabricks Docker image, `MethylExtractor` on `PATH`, cloud credentials for `sample.download-fastq` when using `s3://` or `az://` URIs.

**Data flow:** Instance 2 assumes Instance 1 wrote per-chromosome HDF5s under `samples_base_path`. Model MC and hold-out validation require stability + freeze artifacts on shared storage (`monte_carlo_runs/`).
