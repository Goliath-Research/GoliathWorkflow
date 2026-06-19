# Portal staged study lifecycle

Staged orchestration for multi-group studies: **SamplePrep** completes, then the portal starts **StudyValidationLifecycle** with a pre-planned `context_json`.

## Instance 1 — SamplePrepPipeline

Start when FASTQs are ready. Each sample in `context_json.samples[]` runs download → Parabricks → QC (+ optional R2 trim remediation) → MethylExtractor.

### Option A — Gateway helper (recommended)

```http
POST /v1/studies/sample-prep/start
{
  "projectPath": "/work/.../project_Healthy_vs_PCa1-5-CG.json",
  "workflow_version_id": <sample_prep_version>,
  "fastqStorage": {
    "type": "s3",
    "bucket": "methyl-cohort",
    "region": "us-east-1",
    "credentials": { "authMode": "instance_profile" }
  },
  "sampleCsvs": ["/work/.../healthy.csv", "/work/.../pca.csv"]
}
```

Or pass explicit samples:

```http
POST /v1/studies/sample-prep/start
{
  "projectPath": "/work/.../project.json",
  "workflow_version_id": <sample_prep_version>,
  "samples": [
    { "sampleId": "S1", "sampleDir": "/work/samples/S1", "fastqPrefix": "plasma/S1/" }
  ]
}
```

See [`sample_prep_test_bed.md`](sample_prep_test_bed.md) for planner fields, smoke script, and QC disposition semantics.

### Option B — Manual context_json

```http
POST /v1/workflows/instances
{
  "workflow_version_id": <sample_prep_version>,
  "context_json": {
    "projectPath": "/work/.../project_Healthy_vs_PCa1-5-CG.json",
    "primaryAnalyte": "buffy_coat",
    "isCfdna": false,
    "referenceFasta": "/work/genomes/.../Homo_sapiens.GRCh38.dna.primary_assembly.fa",
    "samples": [
      { "sampleId": "S1", "sampleDir": "/work/samples/S1", "fastqPrefix": "plasma/S1/" }
    ]
  }
}
```

Poll `GET /v1/workflows/instances/{id}` until status is **COMPLETED** (all samples passed QC and have per-chromosome HDF5s).

`chrom_mapping` is derived from `project.chromosomes` at extract time (no shared-storage mapping file required). Optional overrides: `step_config.methyl_extract.contig_naming`, `chromosome_overrides`, or inline `chrom_mapping` object.

## Instance 2 — StudyValidationLifecycle

The portal **pre-plans** iterations before starting the workflow. Two equivalent paths:

### Option A — Gateway helper (recommended)

```http
POST /v1/studies/validation/start
{
  "projectPath": "/work/.../project_Healthy_vs_PCa1-5-CG.json",
  "workflow_version_id": <study_validation_version>,
  "featureIterations": 30,
  "seed": 42
}
```

Or register from a DomainProgram on the fly:

```http
POST /v1/studies/validation/start
{
  "projectPath": "/work/.../project_Healthy_vs_PCa1-5-CG.json",
  "program_path": "/work/.../study_validation_lifecycle.program.json"
}
```

Response:

```json
{
  "instance_id": 123,
  "workflow_version_id": 45,
  "context_json": { "...": "..." },
  "n_iterations": 30
}
```

### Option B — Manual plan + enrich + start

```http
POST /v1/validation/plan-iterations
{ "projectPath": "...", "featureIterations": 30 }
```

Merge planner output with enriched project fields (`comparisons`, `chromosomes`, `groups`, `contexts`) via `enrich_instance_context`, then:

```http
POST /v1/workflows/instances
{
  "workflow_version_id": <study_validation_version>,
  "context_json": {
    "projectPath": "...",
    "iterations": [ "... from plan-iterations ..." ],
    "monteCarloRunsRoot": "/work/.../monte_carlo_runs",
    "backends": ["ecdf", "tabular_sklearn", "generative_hybrid"],
    "comparisons": [ "..." ],
    "chromosomes": ["1", "2", "..."],
    "contexts": ["CG"],
    "groups": [ { "label": "healthy" }, { "label": "PCa1" } ]
  }
}
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

## Project defaults

Portal-facing validation defaults live in `step_config.validation`:

```json
"validation": {
  "feature_iterations": 30,
  "backends": ["ecdf", "tabular_sklearn", "generative_hybrid"],
  "selection_metric": "balanced_accuracy"
}
```

Parabricks alignment settings: `step_config.parabricks` (`image`, `bwa_threads`, `gpu_flags`, …) with task `input_json` overrides; env vars remain as fallback.

## Worker fleet and node prerequisites

Workers poll `POST /v1/workers/tasks/request` and must **not** connect to the database directly. Full details: [`workers/WORKER_PROTOCOL.md`](../../workers/WORKER_PROTOCOL.md).

**Install:** run [`scripts/install_all.sh`](../../scripts/install_all.sh) (or `setup_host.sh`) so all `packages/*` CLIs and validation handlers are on the node, then `pip install -e workers/`.

**Registration options:**

- **Per-capability workers** (recommended in production): register one worker ID per capability (`methyl-centroid`, `methyl-detector`, `validation.model-mc`, …).
- **Omnibus worker** (dev): omit `WORKER_CAPABILITY` so one process claims any task; the node must have GPU (Parabricks), `MethylExtractor`, and the full Python stack.

**External binaries:** Parabricks Docker image, `MethylExtractor` on `PATH`, cloud credentials for `sample.download-fastq` when using `s3://` or `az://` URIs.

**Data flow:** Instance 2 assumes Instance 1 wrote per-chromosome HDF5s under `samples_base_path`. Model MC and hold-out validation require stability + freeze artifacts on shared storage (`monte_carlo_runs/`).
