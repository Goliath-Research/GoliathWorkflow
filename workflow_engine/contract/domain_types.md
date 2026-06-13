# Domain types for workflow scope variables

The workflow engine stores **opaque JSON** in `wf.scope_variable.value_json`. The **domain layer** (`packages/methyldomain`) defines typed objects that clients, compilers, and workers agree on.

## Tagged JSON convention

Every domain value is a JSON object with a **`"$type"`** discriminator:

```json
{
  "$type": "MethylSampleRef",
  "sampleId": "DPLST-001",
  "sampleDir": "/work/samples/DPLST-001",
  "bamPath": "/work/samples/DPLST-001/DPLST-001.bam"
}
```

- Pydantic models use `Field(alias="$type")` for serialization.
- Use `parse_domain_value()` / `to_tagged_json()` from `methyl_domain.types`.
- JSON Schemas live under `schemas/domain/` (export via `methyl-export-domain-schemas`).

FOREACH flattening and `${var.*}` templates work unchanged: domain objects are ordinary JSON objects in scope.

## Type catalog

| `$type` | Purpose |
|---------|---------|
| `MethylIngestRef` | Pre-download URIs / file count |
| `MethylSampleRef` | Sample lifecycle handle (grows through prep) |
| `AlignmentQcRef` | QC JSON path + pass gate |
| `FragmentomicsRef` | cfDNA fragmentomics artifacts |
| `MethylationMatrixRef` | Post-extract HDF5 matrix handles |
| `MethylGroup` | Cohort (static project group or MC train/val draw) |
| `MethylCentroidRef` | Centroid HDF5 per group × chr × ctx |
| `ComparisonSpec` | Control vs disease pair |
| `MethylDetectionRef` | Detector run summary (paths, not full DMP table) |
| `StratifiedCohortDraw` | One Monte Carlo stratified subsample iteration |

See `schemas/domain/registry.json` for schema file names.

## Sample prep state machine

Actions in `workers/methyl_worker/action_catalog.py` declare **`domain_effects`** (exported to `schemas/actions/catalog.json`):

| Action | Reads | Writes on scope |
|--------|-------|-----------------|
| `sample.download_fastq` | `MethylIngestRef` | `MethylSampleRef.fastqFiles` |
| `sample.parabricks_fq2bam` | `MethylSampleRef` | `bamPath`, `metricsJson` |
| `sample.methyl_qc` | `MethylSampleRef` | `alignmentQc`; binds `qcPass` bool |
| `sample.fragmentomics` | `MethylSampleRef` | `fragmentomics` |
| `sample.methyl_extract` | `MethylSampleRef` | `methylation` |
| `pipeline.centroid` | `MethylGroup` | `MethylCentroidRef` |
| `pipeline.detector` | `ComparisonSpec` + centroids | `MethylDetectionRef` |
| `validation.plan_iterations` | project groups | `iterations[]` as `StratifiedCohortDraw` |

Optional worker adapter: `methyl_domain.helpers.enrich_sample_prep_output()` merges handler `output_json` into a `MethylSampleRef`.

## DomainProgram IR and compiler

**IR schema:** `schemas/domain/domain_program.schema.json`

Clients author a declarative **DomainProgram** (phases, `foreach`, `if`, typed `action` steps). The compiler lowers it to engine artifacts:

```
DomainProgram  →  compile_domain_program()
                    ├─ WorkflowDefinitionSpec  (POST /v1/workflows/definitions)
                    ├─ context_json            (initial scope / instance context)
                    └─ variable_output_bindings (e.g. qcPass from methyl_qc)
```

Implementation: `workflow_engine/domain/compiler.py`

Example fixture: `workflow_engine/domain/fixtures/sample_prep.program.json` compiles to a graph equivalent to `workflow_engine/sql/wf_sample_prep_pipeline_seed.sql`.

## Monte Carlo iterations

`methyl_validation.workflow_planner` emits each `context_json.iterations[]` element as a tagged **`StratifiedCohortDraw`**, retaining flat keys (`runId`, `phase`, `projectPath`, `taskConfig`) for backward compatibility.

Helpers:

- `groups_from_mc_run_dir()` — train/val CSV paths per cohort for a run directory
- `build_stratified_cohort_draw()` — assemble tagged iteration object
- `MethylGroup_from_project()` — resolve a static group from `project.json`

## Invariants

1. **Engine agnostic** — no domain types in SQL schema or CHECK constraints.
2. **Storage authoritative** — HDF5/JSON on `/work/`; scope holds references only.
3. **Backward compatible** — flat scope vars (`sampleId`, `qcPass`, …) remain during migration; compiler may emit dual bindings.
