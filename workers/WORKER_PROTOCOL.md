# Remote Worker Protocol

Language-neutral contract for HPC/cloud workers executing workflow ACTION nodes.
Workers **must not** connect to the database directly; they use the REST API defined in
[`../contracts/openapi.yaml`](../contracts/openapi.yaml).

## Flow

```mermaid
sequenceDiagram
  participant Worker
  participant API as MiddleTier_REST
  participant DB as Database

  loop poll
    Worker->>API: POST /workers/tasks/request
    API->>DB: sp_worker_request_task
    DB-->>API: task row or empty
    API-->>Worker: WorkerTaskClaimResponse
  end
  Worker->>Worker: Run capability tool
  Worker->>API: POST /workers/tasks/{id}/submit
  API->>DB: sp_worker_submit_result
  opt long running
    Worker->>API: POST /workers/tasks/{id}/heartbeat
  end
```

## Capability strings

Map to `wf.workflow_action.capability` (e.g. `methyl-centroid`, `methyl-detector`).
The reference worker dispatches via **ActionBase** (`CliAction` / `InProcessAction`) using metadata from `schemas/actions/catalog.json` (`execution_mode`, `cli_tool`, `argv_map`). Fetch live metadata with `GET /v1/actions`.

## Result codes

Branch codes are stored on `node_execution.result_code` and drive IF/SWITCH via `wf_try_task_result_code`:

| Code | Meaning |
|------|---------|
| `< 0` | Hard failure; workflow instance fails |
| `0` | Default success / false branch |
| `1` | True branch (e.g. `sample.methyl_qc` needs realign/trim) |
| `2..N` | Multi-way SWITCH cases (document per action) |

Every successful submit includes a **typed** `output_json` (Pydantic `extra="forbid"`, exported under `schemas/tasks/`). Each output carries telemetry: `started_at_utc`, `finished_at_utc`, `duration_ms`, `exit_code`, `manifest_path`, and `artifacts[]`.

### Action result manifests on `/work`

CLI tools write JSON manifests under `{output_dir}/.action_results/{action_name}.{run_key}.json` (see `methyl_domain.action_result`). The worker reads and validates these after subprocess exit; legacy artifact scraping remains as fallback until all tools emit manifests.

Sample prep also appends `{sampleDir}/{sampleId}.sample_prep_log.jsonl` for an operator-visible timeline.

### `sample.methyl_qc` branch codes

| Code | Meaning |
|------|---------|
| `0` | QC pass |
| `1` | Needs realign/trim (`remediateAlignment`) |
| `2` | Permanent fail → `sample.qc_failed` |

## Implementing a worker in any language

1. Load OpenAPI spec from `contracts/openapi.yaml`
2. Poll `POST /workers/tasks/request` with `worker_id`, `worker_token`, optional `capability`
3. Parse `input_json` from the claim response
4. Execute domain logic
5. `POST /workers/tasks/{nodeExecutionId}/submit` with `output_json`
6. Optionally heartbeat during long jobs

## Reference implementation

Python package [`methyl_worker/`](methyl_worker/):

```bash
source .venv/bin/activate
pip install -e workers/

# Poll for methyl-qc tasks (credentials from portal worker registration)
export WORKER_ID=1 WORKER_TOKEN='...' WORKER_CAPABILITY=methyl-qc
methyl-worker --api-base http://localhost:8080/v1

# Dry-run external capabilities (download, Parabricks, extract, delete)
export WORKER_STUB_EXTERNAL=1
methyl-worker --capability sample.download-fastq

# Monte Carlo planner (local CLI, no workflow poll)
methyl-worker plan-iterations --plan-input /path/to/plan_request.json

# Register worker with capability validation.plan-iterations to run planner as a workflow ACTION
export WORKER_CAPABILITY=validation.plan-iterations
methyl-worker --api-base http://localhost:8080/v1

# One-shot claim (debug)
methyl-worker --once
```

Modules:

| Module | Role |
|--------|------|
| [`methyl_worker/client.py`](methyl_worker/client.py) | REST client (`request`, `submit`, `heartbeat`, `fail`) |
| `methyl_worker/handlers.py` | Capability dispatch to methyl-* CLIs, sample-prep handlers, and **`validation.plan-iterations`** (Monte Carlo planner) |
| [`methyl_worker/runner.py`](methyl_worker/runner.py) | Poll loop with background heartbeat |

Legacy shim: [`reference_rest_worker.py`](reference_rest_worker.py) delegates to `methyl-worker`.

## Full staged pipeline (SamplePrep + StudyValidation)

The reference worker can execute **every action** in both workflow instances when the node environment is provisioned correctly. See [`../workflow_engine/docs/portal_study_lifecycle.md`](../workflow_engine/docs/portal_study_lifecycle.md) for portal orchestration.

### Install (not `pip install -e workers/` alone)

Handlers import the full monorepo (`methyl_alignment_qc`, `methyl_fragmentomics`, `methyl_validation`, …). Production nodes need editable installs of all packages:

```bash
source .venv/bin/activate
./scripts/install_all.sh    # or scripts/setup_host.sh on a fresh HPC image
pip install -e workers/
```

Console scripts on `PATH` must include: `methyl-centroid`, `methyl-detector`, `methyl-mapper`, `methyl-enricher`, `methyl-disease-progression`, `methyl-qc`, `methyl-extraction-qc`, plus native **`MethylExtractor`** and Docker **Parabricks** for sample prep.

### Capability fleet

`WorkerRunner` filters tasks when `WORKER_CAPABILITY` is set. For the full lifecycle, either:

| Approach | When to use |
|----------|-------------|
| **One worker, no `WORKER_CAPABILITY`** | Dev / small cluster; single process polls any task (must have full stack + GPU for Parabricks tasks) |
| **Per-capability workers** | Production; register multiple worker IDs, each with one capability |

| Stage | Capability | Execution |
|-------|------------|-----------|
| Sample prep | `sample.download-fastq`, `parabricks.fq2bam`, `sample.trim-fastq`, `sample.delete-fastqs`, `methyl-qc`, `methyl-fragmentomics`, `methyl-extract`, `methyl-extraction-qc`, `sample.upload-h5`, `sample.delete-bam`, `sample.mark-failed` | in-process / external GPU |
| Feature MC / freeze | `methyl-centroid`, `methyl-detector` | CLI subprocess |
| Biological | `methyl-mapper`, `methyl-enricher`, `methyl-disease-progression` | CLI (`--project`) |
| Validation | `validation.plan-iterations`, `validation.stability`, `validation.prepare-freeze-project`, `validation.stability-freeze-readiness`, `validation.model-mc`, `validation.select-best-model`, `validation.post-model-validation` | in-process |

`pipeline.detector` uses **`DetectorCliAction`**: workflow `comparison` → `--group`; `chromosome`, `context`, `fixedDmpPanel`, and `outputDir` are folded into `--step-override` JSON (methyl-detector has no per-chromosome CLI flags).

### Dry-run

`WORKER_STUB_EXTERNAL=1` fakes download, Parabricks, extract, and delete only. It does **not** stub pipeline CLI or validation actions.

## Database contract (middle-tier only)

If implementing a new middle-tier language, call the same DB objects documented in
[`../workflow_engine/contract/db_objects.yaml`](../workflow_engine/contract/db_objects.yaml)
rather than duplicating SQL in application code.
