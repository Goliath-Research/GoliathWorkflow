---
name: Typed Action Observability
overview: Replace loose dict-based worker I/O with strict Pydantic models end-to-end, wire CLI tools to persist typed result manifests under /work, and have workers collect/validate those manifests so every successful action submits a traceable result_code plus a complete output_json (timing, files, counts).

> **Status: IMPLEMENTED.** Parent plan for typed worker I/O; follow-ups in [`optional-observability-follow-ups.plan.md`](optional-observability-follow-ups.plan.md) and [`finish-typed-follow-ups.plan.md`](finish-typed-follow-ups.plan.md).

azure_devops:
  type: Feature
  title: "Typed worker action observability"
  work_item_id: 444
  epic_id: 413
todos:
  - id: infra-action-result
    content: Add methyl_domain.action_result (ActionTelemetry, ArtifactRef, atomic write/read) and typed ActionBase.execute -> tuple[int, OutputModel]
    status: completed
    work_item_id: 445
  - id: runner-result-code
    content: Refactor WorkerRunner to validate InputModel, submit OutputModel.result_code, forbid dict boundaries
    status: completed
    work_item_id: 446
  - id: cli-manifest-dmp-detector-mapper
    content: Write typed manifests from run_dmp_selection, detector core, mapper.run; add worker collectors with legacy fallback
    status: completed
    work_item_id: 447
  - id: strict-pipeline-schemas
    content: Replace PipelineCliTaskInput/Output with per-action forbid-extra models; re-export schemas and CI drift check
    status: completed
    work_item_id: 448
  - id: validation-typed-outputs
    content: Replace ValidationTaskOutput summary dict with per-action OutputModels sourced from stability/planner return values
    status: completed
    work_item_id: 449
  - id: sample-prep-result-codes
    content: Strict QC nested models; methyl_qc result_code 0/1/2; align output_json with sample_prep_log
    status: completed
    work_item_id: 450
  - id: docs-observability
    content: Document manifest paths, result_code tables, and /work traceability in WORKER_PROTOCOL and user manual
    status: completed
    work_item_id: 451
---

# Typed action results and CLI observability

## Problem (current design gaps)

The worker contract *looks* typed (catalog → Pydantic schemas → JSON Schema export), but execution bypasses it:

| Layer | Today | Why observability is lost |
|-------|--------|---------------------------|
| Handler boundary | `HandlerResult = Dict[str, Any]` in [`workers/methyl_worker/actions/base.py`](workers/methyl_worker/actions/base.py) and [`handlers.py`](workers/methyl_worker/handlers.py) | No compile-time or runtime guarantee on shape |
| 8 pipeline CLIs | Share [`PipelineCliTaskOutput`](workers/methyl_worker/task_models.py) (`status`, `tool`, `stdout_tail`, `extra="allow"`) | Success submits almost nothing; [`pipeline_centroid.output.schema.json`](schemas/tasks/pipeline_centroid.output.schema.json) allows any extra field |
| CLI subprocess | [`CliAction.execute`](workers/methyl_worker/actions/base.py) returns generic dict after exit 0 | Core library already computed rich results but CLI only prints them (e.g. [`run_dmp_selection`](packages/methyldmpselect/methyl_dmp_select/core/runner.py) returns audit dict; [`DMPMapper.run`](packages/methylmapper/methyl_mapper/mapper.py) returns counts) |
| `result_code` | Worker always submits `0` or `-1` ([`runner.py`](workers/methyl_worker/runner.py)) | Engine supports `0..N` for IF/SWITCH via [`wf_try_task_result_code`](workflow_engine/sql/MethylPipelineDB_Script.sql), but actions never populate meaningful codes |
| Validation actions | [`ValidationTaskOutput`](workers/methyl_worker/task_models.py) with `summary: Dict[str, Any]` | Counts/paths stay opaque blobs |

**Good partial precedent:** [`split_detector_task_models.py`](workers/methyl_worker/split_detector_task_models.py) (`extra="forbid"`) + worker adapters that scrape `/work` audit files ([`dmp_select.py`](workers/methyl_worker/actions/dmp_select.py)). Sample prep uses [`sample_prep_log.jsonl`](workers/methyl_worker/sample_prep_log.py) for per-action traceability.

---

## Target contract

```mermaid
sequenceDiagram
  participant DB as WorkflowDB
  participant Worker as methyl_worker
  participant CLI as methyl_tool_CLI
  participant Work as SharedStorage_/work

  DB->>Worker: input_json (validated InputModel)
  Worker->>Worker: t0 = now()
  alt execution_mode cli
    Worker->>CLI: subprocess(argv from InputModel)
    CLI->>CLI: core.run_*() -> ResultModel
    CLI->>Work: write action_result.json (atomic)
    CLI-->>Worker: exit code
    Worker->>Work: read + validate ResultModel (collector fallback)
  else in_process
    Worker->>Worker: handler(InputModel) -> ResultModel
  end
  Worker->>Worker: OutputModel.validate; result_code from OutputModel
  Worker->>DB: submit(result_code, output_json)
  DB->>DB: wf_apply_output_bindings
```

### Rules (non-negotiable)

1. **No dict at boundaries** — `ActionBase.execute(input: InputModel) -> tuple[int, OutputModel]`. Internal dicts may exist inside packages but must be converted before crossing the worker boundary.
2. **Pydantic strict** — all task I/O models use `model_config = ConfigDict(extra="forbid")`. Nested structures are nested models, not `Dict[str, Any]` (replace `guardrails`, `summary`, `iterations`, `stepOverride` blobs incrementally).
3. **`result_code` semantics** (aligned with DB engine):
   - `< 0` — hard failure (workflow instance fails)
   - `0` — default success / false branch
   - `1` — true branch (boolean SWITCH)
   - `2..N` — multi-way SWITCH cases (document per action)
   - Stored on `node_execution.result_code`; IF/SWITCH reads it via `wf_try_task_result_code`.
4. **Every success is observable** — each `OutputModel` includes a shared telemetry base (see below) plus action-specific fields (paths, counts, durations).

### Shared telemetry base (new module)

Add [`packages/methyldomain/methyl_domain/action_result.py`](packages/methyldomain/methyl_domain/action_result.py):

```python
class ActionTelemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = "1.0"
    action_name: str
    capability: str
    started_at_utc: datetime
    finished_at_utc: datetime
    duration_ms: int
    result_code: int = 0          # branch code for engine
    exit_code: int = 0            # CLI/process exit code
    manifest_path: str | None     # path under /work
    artifacts: list[ArtifactRef]  # {path, kind, bytes?, sha256?}

class ArtifactRef(BaseModel): ...
```

Helpers: `atomic_write_action_result(path, model)`, `read_action_result(path) -> model`.

**Manifest location convention:** `{resolved_output_dir}/.action_results/{action_name}.{node_key_or_run_id}.json` (hidden dir avoids cluttering science outputs). Worker collectors know `resolved_output_dir` via the same project resolvers the CLI uses.

---

## Hybrid CLI strategy (your choice)

Many CLIs already call a core method that builds the answer; the fix is to **persist that answer**, not re-invent it in the worker.

### Phase A — Extract + write in packages

For each `methyl-*` tool:

1. Define `{Tool}ActionResult(OutputModel)` in the package (or re-use/extend worker task model via import to avoid duplication).
2. At end of `core.run_*()` (or CLI `main` after run): build `ResultModel`, call `atomic_write_action_result`.
3. Map process exit code: `0` → write manifest + exit 0; non-zero → write failure manifest with `result_code < 0` optional, then exit 1.

**First migrations (highest workflow volume):**

| Action | Core return today | Manifest source |
|--------|-------------------|-----------------|
| `pipeline.dmp_select` | `run_dmp_selection` dict + audit file | Promote audit to `DmpSelectTaskOutput` + telemetry; CLI writes manifest (worker collector reads same file) |
| `pipeline.detector` | Rich result object, printed only | Add `DetectorActionResult` (n_stat_dmps, n_bio_dmps, csv paths, per-comparison timings) |
| `pipeline.mapper` | `mapper.run()` dict | `n_input_dmps`, `n_output_genes`, csv/json paths |
| `pipeline.centroid` | HDF5 + logs only | Add result builder: n_samples, n_positions, centroid paths |
| `pipeline.enricher` | completeness manifest exists ([`write_project_completeness_manifest`](packages/methylenricher/methyl_enricher/ensure_complete.py)) | Wrap/enrich into typed output |

### Phase B — Worker collectors (fallback + enrichment)

Refactor [`CliAction`](workers/methyl_worker/actions/base.py):

```python
class CliAction:
    output_model: type[OutputModel]
    collector: ArtifactCollector | None

    def execute(self, input: InputModel) -> tuple[int, OutputModel]:
        t0 = ...
        proc = subprocess.run(...)
        manifest = self.collector.collect(input, work_root)  # reads .action_results/ or legacy paths
        out = self.output_model.model_validate(manifest)
        return out.result_code, out
```

- **Primary:** read typed manifest written by CLI.
- **Fallback:** collector reconstructs from legacy artifacts (current `dmp_select` / `gene_select` logic) until CLI is migrated.
- **Enrichment:** worker always sets `duration_ms`, `exit_code` from subprocess (CLI cannot lie about wall time).

In-process handlers return `OutputModel` directly (no manifest required), but should still write optional manifests under `/work` for operator debugging.

---

## Worker layer refactor

### 1. Typed execution pipeline

[`workers/methyl_worker/runner.py`](workers/methyl_worker/runner.py):

```python
input_model = load_input_model(action_name).model_validate(claim.input_json)
result_code, output_model = action.execute(input_model)
validate_task_output(...)  # already typed
self.client.submit_result(..., result_code, output_model.model_dump(mode="json"))
```

Remove bare `Dict` from `ActionBase`, `InProcessCallable`, `execute_task`.

### 2. Replace generic pipeline schemas

Retire `_PIPELINE_IN` / `_PIPELINE_OUT` from [`action_catalog.py`](workers/methyl_worker/action_catalog.py) for:

- `pipeline.centroid`, `pipeline.detector`, `pipeline.mapper`, `pipeline.enricher`, `pipeline.progression`, `pipeline.classifier`, `pipeline.predictor`, `pipeline.cluster`

Add per-action modules mirroring [`split_detector_task_models.py`](workers/methyl_worker/split_detector_task_models.py) (or split into `workers/methyl_worker/task_models/pipeline/`).

### 3. Tighten validation actions

Replace shared loose [`ValidationTaskOutput`](workers/methyl_worker/task_models.py) with one output model per validation action (e.g. `ValidationStabilityOutput` with typed stability counts, tier breakdown, output paths — sourced from [`run_stability_analysis`](packages/methylvalidation/methyl_validation/stability.py) return value, not `summary: dict`).

### 4. Tighten sample prep nested dicts

Promote QC sub-objects to models (`GuardrailsOutput`, `ScreeningOutput`, `QcHistoryEntry`). Keep `sample_prep_log.jsonl` as append-only audit; **`output_json` submitted to DB must mirror the same fields** (today they diverge for some handlers).

### 5. `result_code` mapping for branching actions

Document and implement per action, e.g. `sample.methyl_qc`:

| Code | Meaning | Today |
|------|---------|-------|
| 0 | QC pass, continue | `remediateAlignment=false` |
| 1 | Needs realign/trim | `remediateAlignment=true` |
| 2 | Permanent fail → mark_failed | manual IF on flags |

Worker sets `result_code` from `OutputModel.result_code`; workflows can migrate from boolean scope vars to `wf_try_task_result_code` over time.

---

## Observability beyond DB payload

| Mechanism | Purpose |
|-----------|---------|
| `output_json` on `node_execution` | Portal/API query, output_bindings |
| `.action_results/*.json` on `/work` | Operator inspection, re-validation, replay |
| `sample_prep_log.jsonl` (sample stage) | Append-only timeline (extend pattern to MC run dirs as `action_run_log.jsonl`) |
| JSON Schema artifacts | [`methyl-export-task-schemas`](workers/methyl_worker/task_schema_export.py) CI check — fail if drift |

Add CI test: for each catalog action, golden fixture input → execute (or mock collector) → output validates against exported JSON Schema with `additionalProperties: false`.

---

## Rollout phases

### Phase 0 — Infrastructure (1 PR)
- `methyl_domain.action_result` telemetry base + atomic write/read
- Typed `ActionBase` + runner submit `result_code` from output model
- `extra="forbid"` policy + export schemas with `additionalProperties: false`

### Phase 1 — Split pipeline actions (2–3 PRs)
- Migrate `dmp_select`, `gene_select`, `gene_feature_select` to manifest-first (CLI writes; worker reads)
- Add strict models + collectors for `detector`, `mapper`, `centroid`
- Delete `PipelineCliTaskOutput` usage for migrated actions

### Phase 2 — Remaining pipeline + validation (2 PRs)
- enricher, progression, classifier, predictor, cluster
- Replace `ValidationTaskOutput` with per-action typed outputs

### Phase 3 — Sample prep strict models + result_code branching (1 PR)
- Nested Pydantic for QC outputs
- `methyl_qc` emits `result_code` 0/1/2; update sample prep program IF nodes

### Phase 4 — Docs + portal
- Update [`workers/WORKER_PROTOCOL.md`](workers/WORKER_PROTOCOL.md) and [`docs/reference/domain-program-language.md`](docs/reference/domain-program-language.md) with result_code table and manifest convention
- Usage manual: where to find `.action_results/` and `action_run_log.jsonl` on `/work`

---

## Success criteria

- No `HandlerResult = Dict[str, Any]` at worker boundaries
- No task I/O model with `extra="allow"` (except deprecated aliases during migration, marked for removal)
- Every catalog action has exported input/output JSON Schema with `additionalProperties: false`
- CLI-backed success path: `output_json` contains `duration_ms`, `manifest_path`, and all fields defined in the action output schema (counts, paths, branch code)
- Worker never submits `{status: ok, stdout_tail: ...}` as the sole success payload for pipeline actions
