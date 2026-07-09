# Configurable Methylation Pipeline — Architecture

Presentation-oriented overview of how a **project configuration** (JSON), a **schema-validated portal editor**, a **workflow database** (including **scoped variables**), a **stateless middle-tier**, and **remote workers** cooperate to run a configurable methylation pipeline on a shared-storage cluster.

**Audience:** engineers and stakeholders reviewing the company portal, backend database, middle-tier, and compute workers.

**Related code:** [`schemas/config/`](/home/ubuntu/MethylPipeline/schemas/config/), [`tools/methyl-config-editor/`](/home/ubuntu/MethylPipeline/tools/methyl-config-editor/), [`workflow_engine/`](/home/ubuntu/MethylPipeline/workflow_engine/)

**Other formats (HTML / PDF):** Quarto source is [`pipeline_architecture.qmd`](pipeline_architecture.qmd), generated from this file.

**Local HTML (diagrams need a live preview server — do not open `pipeline_architecture.html` directly in the browser or in the IDE preview):**

```bash
python workflow_engine/docs/build_pipeline_architecture_qmd.py
quarto preview workflow_engine/docs/pipeline_architecture.qmd
```

Quarto serves the page at `http://localhost:…` and Mermaid renders in your normal browser. See [Rendering](#rendering-this-document) at the end of the `.qmd` for PDF commands.

---

## Presentation map (four layers)

Two workflow definitions run in sequence for production studies: **SamplePrepPipeline** (per-sample FASTQ → HDF5), then **StudyValidationLifecycle** (MC stability → freeze → biological outputs → model MC → selection → hold-out). **DataDrivenPipeline** remains the single-pass centroid → enricher path for ad-hoc analysis.

**Staged portal contract:** [`portal_study_lifecycle.md`](portal_study_lifecycle.md) — `methyl-study-start validation-start` (or portal SQL) after SamplePrep completes.

```mermaid
flowchart TB
  subgraph portal ["Company Portal"]
    editor["Schema-driven config editor<br/>(methyl-config-editor Web)"]
    runPrep["Start SamplePrepPipeline"]
    runDdp["Start DataDrivenPipeline"]
  end
  subgraph database ["Backend Database"]
    wfPrep["SamplePrepPipeline"]
    wfDef["DataDrivenPipeline"]
    inst["workflow_instance<br/>+ context_json"]
    nexec["node_execution<br/>+ scope_variable"]
  end
  subgraph mt ["Internal Middle-Tier"]
    rest["WfEngine REST API<br/>:8080"]
    engine["Workflow engine<br/>(T-SQL / PL/pgSQL procs)"]
  end
  subgraph workers ["Remote Workers / Cluster"]
    w0["download / Parabricks / methyl-qc / extract"]
    w1["methyl-centroid"]
    w2["methyl-detector"]
    w3["methyl-mapper / enricher / progression"]
  end
  storage[("Shared storage<br/>NFS / Azure Files<br/>/work/...")]

  editor -->|"validated project.json"| runPrep
  runPrep --> wfPrep
  wfPrep -->|"all samples HDF5 ready"| runDdp
  runDdp --> wfDef
  wfDef --> inst
  inst --> nexec
  rest --> engine
  engine --> nexec
  w0 -->|"poll / submit"| rest
  w1 -->|"poll / submit"| rest
  w2 -->|"poll / submit"| rest
  w3 -->|"poll / submit"| rest
  w0 --> storage
  w1 --> storage
  w2 --> storage
  w3 --> storage
  nexec -.->|"input_json paths"| storage
```

| Layer | Technology | Responsibility |
|-------|------------|----------------|
| Portal | uniGUI web app (`MethylConfigEditorWeb`) | Edit `project.json` against JSON Schema; start runs |
| Database | Azure SQL or Azure PostgreSQL (`wf` schema) | Store workflow tree, instances, executions, leases |
| Middle-tier | Python `methyl-gateway` on Linux + REST (`/v1/*`, uvicorn) | Stateless HTTP proxy; invokes engine stored procedures (Delphi `WfEngineSrv` frozen) |
| Workers | Python/CLI on cluster nodes | Poll tasks by capability; read/write shared paths |

---

## 0. Per-sample upstream preprocessing (SamplePrepPipeline)

The analysis pipeline ([Section 1](#1-project-configuration) onward) assumes per-chromosome methylation HDF5 files already exist under `samples_base_path`. **SamplePrepPipeline** orchestrates ingest, alignment, QC gating, optional cfDNA fragmentomics, methylation extraction, and cleanup **per sample** before **DataDrivenPipeline** runs.

**Workflow definition:** [`workflow_engine/domain/fixtures/sample_prep.program.json`](/home/ubuntu/MethylPipeline/workflow_engine/domain/fixtures/sample_prep.program.json) — deploy with `bash scripts/deploy_workflow_definitions.sh`.

Legacy SQL seed [`workflow_engine/sql_mssql/deprecated/wf_sample_prep_pipeline_seed.sql`](workflow_engine/sql_mssql/deprecated/wf_sample_prep_pipeline_seed.sql) is **deprecated**.

**Operator guide:** [`workflow_engine/sql_mssql/SamplePrepFlow.md`](/home/ubuntu/MethylPipeline/workflow_engine/sql_mssql/SamplePrepFlow.md)  
**Worker contract:** [`workflow_engine/contract/sample_prep_capabilities.md`](/home/ubuntu/MethylPipeline/workflow_engine/contract/sample_prep_capabilities.md)  
**Analyte profiles:** [`docs/ANALYTE_PROFILES.md`](/home/ubuntu/MethylPipeline/docs/ANALYTE_PROFILES.md)

### Step order

```mermaid
flowchart TD
  subgraph perSample [FOREACH sample parallel]
    dl[download_FASTQs]
    align[Parabricks_fq2bam GPU]
    qc[methyl_qc alignment guardrail]
    gateQc{qcPass}
    delFq[delete_FASTQs after final align QC]
    frag[methyl_fragmentomics if isCfdna]
    ext[MethylExtractor GPU]
    extQc[extraction_qc post-extract guardrail]
    gateExt{extractionQcPass}
    upload[archive_sample optional]
    delBam[delete_BAM]
    trim[trim_fastq fastp]
    align2[Parabricks forceRealign]
    qc2[methyl_qc retry]
    fail[sample_qc_failed]
  end
  dl --> align --> qc --> gateQc
  gateQc -->|pass| delFq --> frag --> ext --> extQc --> gateExt
  gateExt -->|pass| upload --> delBam
  gateExt -->|fail| fail
  gateQc -->|fail| trim --> align2 --> qc2 --> delFq
  delBam --> h5["chrom-CG.h5 in sample dir"]
  h5 --> ddp[DataDrivenPipeline]
```

| Step | Capability | Owner | Primary outputs |
|------|------------|-------|-----------------|
| Download FASTQs | `sample.download-fastq` | In-process | `*.fastq.gz` in `/work/samples/{id}/` |
| Parabricks fq2bam | `parabricks.fq2bam` | External GPU | `{id}.bam`, `{id}.json`, `*.qc-metrics.tar` |
| methyl-qc | `methyl-qc` | In-repo | V2 QC JSON; `qcPass`, remediation scope vars |
| Trim FASTQ | `sample.trim-fastq` | In-process fastp | Trimmed FASTQs (remediation branch) |
| Delete FASTQs | `sample.delete-fastqs` | In-process | FASTQs removed after final alignment QC |
| methyl-fragmentomics | `methyl-fragmentomics` | In-repo (cfDNA only) | `{project}/fragmentomics/{id}/` |
| MethylExtractor | `methyl-extract` | External GPU | `{chrom}-{ctx}.h5`, extraction manifest |
| Extraction QC | `methyl-extraction-qc` | In-repo | `{id}.extraction_qc.json`; `extractionQcPass` |
| Archive HDF5 | `sample.upload-h5` | In-process | Optional remote copy |
| Delete BAM | `sample.delete-bam` | In-process | BAM removed after extraction QC pass |

**Ordering:** Run **methyl-qc before methyl-fragmentomics** so failed samples do not scan BAMs. **extraction_qc** runs after extract and before upload/delete. When `primary_analyte` is `cfdna`, fragmentomics runs; `buffy_coat` skips it.

### Storage contract (`/work/samples`)

```
/work/samples/{sample_id}/
  *.fastq.gz              (transient; deleted after align)
  {sample_id}.bam         (transient; deleted after extract)
  {sample_id}.json        (Parabricks metrics; retained)
  *.qc-metrics.tar        (optional; retained)
  bisulfite_conversion.json  (optional sidecar)
  1-CG.h5 … Y-CG.h5       (retained; consumed by methyl-centroid)
```

Project [`path_remap`](/home/ubuntu/MethylPipeline/packages/methylutils/methyl_utils/pipeline_config.py) bridges NAS paths to `/work/samples`. Sample list CSVs in `project.json` resolve via [`load_and_resolve_sample_paths`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/split.py).

### QC gate semantics

- **`methyl-qc`** reads Parabricks/Picard metrics from the sample directory and writes alignment QC JSON ([`methyl_alignment_qc`](/home/ubuntu/MethylPipeline/packages/methylalignmentqc/)).
- **`guardrails.overall_pass`** (bound to scope variable `qcPass` after the QC action) drives the workflow **IF** node. Failed samples run `sample.qc_failed` and skip extraction.
- cfDNA samples additionally get insert-size guardrails via [`fragmentomics.py`](/home/ubuntu/MethylPipeline/packages/methylalignmentqc/methyl_alignment_qc/core/fragmentomics.py) when the analyte profile applies.

### Portal handoff

1. Start **SamplePrepPipeline** when FASTQs are ready (`context_json.samples[]` lists each sample).
2. On instance **COMPLETED** (all samples have HDF5 + passed QC), start **DataDrivenPipeline** with the same `projectPath`, `comparisons`, and `chromosomes`.

Example instance payload: [`workflow_engine/sql_mssql/instance_context_examples/sample_prep_plasma.json`](/home/ubuntu/MethylPipeline/workflow_engine/sql_mssql/instance_context_examples/sample_prep_plasma.json).

---

## 1. Project configuration

A **project config** (study manifest) is a single JSON file that describes *what* to run: cohorts, comparisons, chromosomes, and contexts. Tool parameters live in **pipeline profile** and **site** `actionConfig`; instance **`context_json`** carries `pipelineProfile`, merged `actionConfig`, and planner fields. It is the scientific contract for one methylation study.

**Canonical schema:** [`schemas/config/project_config.schema.json`](/home/ubuntu/MethylPipeline/schemas/config/project_config.schema.json)  
**Pydantic model:** [`packages/methylutils/methyl_utils/pipeline_config.py`](/home/ubuntu/MethylPipeline/packages/methylutils/methyl_utils/pipeline_config.py)  
**In-repo examples:** [`tools/methyl-config-editor/configs/`](/home/ubuntu/MethylPipeline/tools/methyl-config-editor/configs/)

### Top-level structure

Only **`project_name`** and **`output_base`** are required. Everything else is optional and validated by schema.

| Field | Role |
|-------|------|
| `project_name` | Identifier; output lives under `{output_base}/{project_name}/` |
| `output_base` | Global output root (e.g. `/work/projects/prostate-cancer`) |
| `controls` / `disease` | Two-sided layout: control vs disease cohorts |
| `comparisons` | Shorthand string or explicit list of control vs disease pairs |
| `chromosomes` | Shared list (`"1"`…`"22"`, `"X"`, `"Y"`) |
| `contexts` | Methylation contexts: `CG`, `CHG`, `CHH` |
| `path_remap` | Prefix replacement when sample paths moved (e.g. NAS → cluster mount) |
| `progression_order` | Optional ordered comparison labels for progression (study-only) |
| `regulatory` / `validation_partitions` | Study metadata (not tool knobs) |

Per-step tool parameters (`centroid`, `detection`, `mapper`, `enricher`, `validation`, …) belong in **profile/site `actionConfig`**, merged into instance `context_json` at workflow start — not in the study manifest.

### Cohort hierarchy

```mermaid
flowchart TD
  root["ProjectConfig"]
  root --> meta["Metadata\nproject_name, laboratory, batch"]
  root --> paths["Paths\noutput_base, samples_base_path, path_remap"]
  root --> ctrl["control\n(ControlDiseaseSide)"]
  root --> dis["disease\n(ControlDiseaseSide)"]
  root --> cmp["comparisons"]
  root --> chr["chromosomes[]"]
  root --> ctx["contexts[]"]
  root --> po["progression_order / regulatory"]
  ctrl --> g1["groups[]\nlabel, sample_paths"]
  dis --> g2["groups[]"]
  g2 --> stages["stages[]\noptional nesting"]
  stages --> leaf["Resolved label:\n{parent}_{stage}\ne.g. PCa_PCa1"]
```

**Control side** (`controls`): one or more groups, e.g. `all` with a CSV of healthy sample paths.

**Disease side** (`diseases`): groups may nest **`stages`** (e.g. Gleason PCa1–PCa4 under parent `PCa`). Resolved centroid labels become `{parent}_{stage}` → `PCa_PCa1`.

### Comparisons

`comparisons` can be:

| Form | Behavior |
|------|----------|
| `"control_vs_each_disease"` | First control group vs **each** resolved disease leaf |
| `"all_pairs"` | Every control leaf × every disease leaf |
| `[{control_group, disease_group, comparison_label?}, …]` | Explicit list |

Detection output paths follow: `detections/{control_group}/{disease_group}/`.

### Example snippet (two-group OvR style)

External reference project (not in repo): `project_PCa3.json` with one control (`all`) and two disease stages (`PCa_Low`, `PCa_High`). In-repo analogue with four stages:

```json
{
  "project_name": "Healthy_vs_PCa1-4-CG",
  "output_base": "/work/projects/prostate-cancer",
  "controls": {
    "label": "healthy",
    "groups": [{ "label": "all", "sample_paths": ["/work/projects/prostate-cancer/data/healthy.csv"] }]
  },
  "diseases": {
    "label": "cancer",
    "groups": [{
      "label": "PCa",
      "stages": [
        { "label": "PCa1", "description": "Gleason Score 3+3", "sample_paths": ["..."] },
        { "label": "PCa2", "description": "Gleason Score 3+4", "sample_paths": ["..."] }
      ]
    }]
  },
  "comparisons": "control_vs_each_disease",
  "chromosomes": ["1", "2", "...", "22", "X", "Y"],
  "contexts": ["CG"],
  "progression_order": ["PCa1", "PCa2", "PCa3", "PCa4"]
}
```

Centroid, detection, and other tool knobs come from a **pipeline profile** (e.g. `mc_dmp_gene_fc.profile.json` → `actionConfig`) and/or site manifest (`/work/site/methyl_site.json`), passed via instance `context_json` (`pipelineProfile`, merged `actionConfig`).

For a **two-group OvR** study (one control vs two disease stages), use `"comparisons": "control_vs_each_disease"` with two disease leaves (`PCa_Low`, `PCa_High`) — see [Section 5](#5-two-group-example-config--workflow-tree).

---

## 2. JSON Schema hierarchy

Schemas are **JSON Schema draft 2020-12**. The top-level document is generated from Pydantic (`ProjectConfig`) and kept in sync via `methyl-export-config-schemas` ([`packages/methylvalidation/methyl_validation/config_schema_registry.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/config_schema_registry.py)).

### Reference tree

```mermaid
flowchart LR
  pcs["project_config.schema.json"]
  pcs --> cds["$defs/ControlDiseaseSide"]
  pcs --> gc["$defs/GroupConfig\n(recursive: stages)"]
  pcs --> cs["$defs/ComparisonSpec"]
  pcs --> sub["$defs/SubclusterRequest"]
  pcs --> prof["profile / site actionConfig"]
  prof --> cent["centroid.schema.json"]
  prof --> det["detection.schema.json"]
  prof --> map["mapper.schema.json"]
  prof --> enr["enricher.schema.json"]
  prof --> cls["classifier.schema.json"]
  prof --> val["validation.schema.json"]
  prof --> prog["progression.schema.json"]
  prof --> aqc["alignment_qc.schema.json"]
```

### `$defs` in `project_config.schema.json`

| Definition | Required fields | Purpose |
|--------------|-------------------|---------|
| `ComparisonSpec` | `control_group`, `disease_group` | One pairwise comparison |
| `ControlDiseaseSide` | `label` | Control or disease side with `groups[]` |
| `GroupConfig` | `label` | Cohort or stage; optional `stages[]`, `subcluster`, `level_labels_path` |
| `SubclusterRequest` | (none) | Optional MethylCluster pre-centroid clustering |

### Per-step schemas (`schemas/config/`)

| File | Step |
|------|------|
| `centroid.schema.json` | MethylCentroid |
| `detection.schema.json` | MethylDetector |
| `mapper.schema.json` | MethylMapper |
| `enricher.schema.json` | MethylEnricher |
| `classifier.schema.json` | MethylClassifier |
| `predictor.schema.json` | MethylPredictor |
| `validation.schema.json` | MethylValidation (+ nested `validation_monte_carlo`, `validation_regulatory`, `validation_backend_profiles`, …) |
| `progression.schema.json` | MethylDiseaseProgression |
| `alignment_qc.schema.json` | Alignment QC |

Per-step schemas validate **profile/site `actionConfig`** slices and optional program `stepOverride` overlays. At runtime, `resolve_action_config` merges profile → site → analyte defaults into task `resolvedConfig`; workers and CLI may still override with flags or `stepOverride`.

### Action payload schemas (`schemas/tasks/`)

Workflow **actions** (not project config steps) have separate input/output JSON Schemas stored in `wf.workflow_action_schema` and exported to `schemas/tasks/`:

```mermaid
flowchart LR
  PM[Pydantic task models]
  EXP[methyl-export-task-schemas]
  DB[wf.workflow_action_schema]
  CAT[schemas/actions/catalog.json]
  ED[Config Editor]
  WK[Worker runtime]
  PM --> EXP --> DB
  CAT --> WK
  PM --> WK
  DB --> ED
```

| Artifact | Role |
|----------|------|
| `workers/methyl_worker/task_models.py` | Source-of-truth Pydantic I/O models |
| `methyl-export-task-schemas` | Writes `schemas/tasks/<action>.input\|output.schema.json` |
| `workflow_engine/sql_mssql/seed_action_schemas.py` | Upserts schemas into the database |
| `schemas/actions/catalog.json` | Git catalog; Config Editor filesystem mode |
| Worker `validate_task_input/output` | Enforces resolved payloads at claim/submit |

> **Note:** The production gateway is **worker-only** (`/v1/workers/*`). Catalog HTTP routes were removed; use `schemas/actions/catalog.json` or DB seed. Instance lifecycle uses portal SQL or `methyl-study-start` (direct DB).

Template documents (`workflow_input_template.template_json`) may contain `${var.*}` placeholders. The Config Editor treats `${...}` strings as wildcards during validation; workers validate fully resolved JSON.

### Constraint enforcement

- **Portal editor:** loads `*.schema.json` and blocks invalid types, missing required fields, and bad enums at edit time ([Section 3](#3-portal-config-editor)).
- **Python runtime:** `ProjectConfig.model_validate()` on `load_project()` enforces the same rules before any pipeline step runs.
- **Comparisons resolution:** `get_comparisons()` in `pipeline_config.py` expands shorthands and validates that `control_group` / `disease_group` labels exist in resolved cohort leaves.

---

## 3. Portal config editor

There is **no separate React/TypeScript portal** in this repository. JSON editing is provided by **methyl-config-editor**: a schema-driven Delphi application with a **web port** suitable for embedding in a company portal.

| Component | Path |
|-----------|------|
| Desktop (VCL) | [`tools/methyl-config-editor/MethylConfigEditor.dproj`](/home/ubuntu/MethylPipeline/tools/methyl-config-editor/MethylConfigEditor.dproj) |
| Web (uniGUI) | [`tools/methyl-config-editor/MethylConfigEditorWeb.dproj`](/home/ubuntu/MethylPipeline/tools/methyl-config-editor/MethylConfigEditorWeb.dproj) — default port **8077** |
| Schema loader | [`src/Schema/JsonSchemaLoader.pas`](/home/ubuntu/MethylPipeline/tools/methyl-config-editor/src/Schema/JsonSchemaLoader.pas) |
| Web property grid | [`src/Web/SchemaPropertyGrid.pas`](/home/ubuntu/MethylPipeline/tools/methyl-config-editor/src/Web/SchemaPropertyGrid.pas) |

### Editor flow

```mermaid
flowchart LR
  user["Portal user\n(browser)"]
  web["MethylConfigEditorWeb\n:8077"]
  schemas["schemas/config/\n*.schema.json"]
  loader["JsonSchemaLoader\n→ TSchemaNode meta-tree"]
  grid["TSchemaPropertyGrid\ninline scalars"]
  nested["NestedEditorForm /\nWebArrayEditorForm"]
  json["project.json\n(upload / download)"]

  user -->|"Upload"| web
  schemas --> loader
  loader --> grid
  loader --> nested
  grid --> json
  nested --> json
  json -->|"Download"| user
```

**Behavior:**

1. Administrator points the web app at `schemas/config` (`Paths.SchemasRoot` in `methyl-config-editor-web.ini`).
2. User selects schema **`project_config.schema.json`**, uploads or creates JSON.
3. **Scalars** edit inline in `TUniPropertyGrid`; **objects/arrays** open modal nested editors.
4. `$ref` to sibling files (e.g. `centroid.schema.json`) resolves at load time — no code generation.
5. User downloads validated JSON.

### From project JSON to workflow run

The portal (or a separate **planner service**) maps a validated project config into a **`workflow_instance.context_json`** — runtime variables for the workflow engine, not a copy of the full project file.

Typical mapping:

| Project config | `context_json` |
|----------------|----------------|
| Resolved comparisons | `comparisons[]` with `label`, `centroid2Dir`, `detectOutDir`, … |
| `chromosomes` | `chromosomes[]` |
| `contexts` | `contexts[]` |
| `output_base` + paths | `centroid1Dir`, `projectPath`, tool name strings |
| `progression_order` or profile `actionConfig.progression.ordered_comparison_labels` | `orderedComparisonLabels` |
| Pipeline profile name | `pipelineProfile` |
| Profile + site `actionConfig` | Merged `actionConfig` / per-task `resolvedConfig` |

**Alternative (DomainProgram + collection bindings):** pass only `{ "projectPath": "…" }`; the engine resolves `chromosomes`, `contexts`, and `comparisons` from the project JSON at instance start ([Section 3.5](#35-domain-program-language-and-workflow-compilation)). Pre-expanded arrays in `context_json` remain supported for hand-written seeds such as **DataDrivenPipeline**.

Example instance payload: [`workflow_engine/sql_mssql/instance_context_examples/pca_ovr.json`](/home/ubuntu/MethylPipeline/workflow_engine/sql_mssql/instance_context_examples/pca_ovr.json).

Starting a run (portal SQL or Admin CLI — not gateway HTTP):

```bash
methyl-study-start validation-start - <<'JSON'
{ "projectPath": "/work/projects/.../configs/project_*.json", "pipelineProfile": "mc_gene_fc" }
JSON
```

Or portal: `portal.sp_start_workflow_instance` with `workflow_version_id` + `context_json`.

---

## 3.5 Domain program language and workflow compilation

Hand-written SQL seeds (`wf_data_driven_pipeline_seed.sql`, `wf_sample_prep_pipeline_seed.sql`) define fixed workflow graphs. The **domain program layer** lets clients describe *any* pipeline in a small declarative language, compile it to a **`WorkflowDefinitionSpec`**, and deploy via **`scripts/deploy_workflow_definitions.sh`** or **`methyl-study-start`** (direct DB) — without per-study node explosion in the database.

**Package:** [`packages/methyldomain/`](/home/ubuntu/MethylPipeline/packages/methyldomain/)  
**Compiler:** [`workflow_engine/domain/compiler.py`](/home/ubuntu/MethylPipeline/workflow_engine/domain/compiler.py)  
**WorkflowContext:** [`workflow_engine/domain/workflow_context.py`](/home/ubuntu/MethylPipeline/workflow_engine/domain/workflow_context.py) — instance `context_json` enrichment, template resolution helpers, and resolved-payload validation (see [`domain_types.md`](/home/ubuntu/MethylPipeline/workflow_engine/contract/domain_types.md))  
**Schemas:** [`schemas/domain/`](/home/ubuntu/MethylPipeline/schemas/domain/), [`schemas/workflow/workflow_definition.schema.json`](/home/ubuntu/MethylPipeline/schemas/workflow/workflow_definition.schema.json)

### Three-layer split

| Layer | Knows about | Produces |
|-------|-------------|----------|
| **DomainProgram (client language)** | Actions, control flow, `project.chromosomes`, typed domain refs | JSON IR (`for`, `parallel`, `do`/`with`, `if`) |
| **Compiler** | Action catalog templates, FOREACH/PARALLEL lowering | `WorkflowDefinitionSpec` + `collection_bindings` |
| **Workflow engine (DB)** | JSON arrays, scope vars, `${var.*}` only | One `node_execution` per concrete unit of work |

The engine never parses methylation semantics. It iterates JSON arrays and resolves templates. Domain types (`MethylSampleRef`, `MethylGroup`, `StratifiedCohortDraw`, …) are **authoring and validation** concerns; runtime scope holds flat JSON.

**Schema boundary:** Domain configuration (archive storage profiles, portal RBAC, cohort metadata) belongs in **`portal`**, **`Meta`**, or **`RBAC`** schemas — not in **`wf`**. The engine stores opaque `context_json` with already-resolved action inputs (e.g. `fastqStorage`, `h5Storage`); middle-tier planners read `portal.resource_profile` before instance creation. See [`docs/deployment/portal_resource_profile.md`](/home/ubuntu/MethylPipeline/docs/deployment/portal_resource_profile.md).

### Statement-shaped IR (v2)

Programs use statement nodes (JSON AST), not opaque nested config:

```json
{
  "programVersion": 2,
  "name": "TwoGroupComparison",
  "projectPath": "/work/study/configs/project.json",
  "body": [
    {
      "for": { "in": { "ref": "project.comparisons" }, "as": "comparison", "parallel": true },
      "do": [
        {
          "for": { "in": { "ref": "project.contexts" }, "as": "context", "parallel": true },
          "do": [
            {
              "for": { "in": { "ref": "project.chromosomes" }, "as": "chromosome", "parallel": true },
              "do": [
                {
                  "parallel": [
                    { "do": "pipeline.centroid", "with": { "group": { "ref": "comparison.control_group" }, "chromosome": { "ref": "chromosome" }, "context": { "ref": "context" } }, "node_key": "centroid_g1" },
                    { "do": "pipeline.centroid", "with": { "group": { "ref": "comparison.disease_group" }, "chromosome": { "ref": "chromosome" }, "context": { "ref": "context" } }, "node_key": "centroid_g2" }
                  ]
                },
                { "do": "pipeline.detector", "with": { "chromosome": { "ref": "chromosome" }, "context": { "ref": "context" } }, "node_key": "detect" }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

Example fixture: [`workflow_engine/domain/fixtures/two_group_comparison.program.json`](/home/ubuntu/MethylPipeline/workflow_engine/domain/fixtures/two_group_comparison.program.json). Sample prep equivalent: [`sample_prep.program.json`](/home/ubuntu/MethylPipeline/workflow_engine/domain/fixtures/sample_prep.program.json).

The compiler lowers each construct 1:1 to engine node types:

| IR statement | Engine node | Edge `branch_kind` from parent |
|--------------|-------------|--------------------------------|
| `for … in project.X` | `FOREACH` on scope var `X` | `SEQUENCE` or `BODY` |
| `parallel: [ … ]` | `PARALLEL` + child ACTIONs | `PARALLEL` for all direct children |
| `do action(with: …)` | `ACTION` + `input_template` | `SEQUENCE` or `PARALLEL` |
| `if` | `IF` + THEN/ELSE | `SEQUENCE` |

### Deploy and run

```text
DomainProgram JSON
  → compile_domain_program()
      → WorkflowDefinitionSpec (nodes, edges, templates, collection_bindings)
      → context_json { "projectPath": "..." }   // minimal instance payload

deploy_workflow_definitions.sh / methyl-study-start  → wf.wf_repo_create_workflow_graph
methyl-study-start / portal.sp_*                     → sp_start_workflow_instance
  → wf_init_instance_scope_from_context
  → wf_resolve_collection_bindings   // populate chromosomes, contexts, comparisons, …
  → graph activation → READY tasks with concrete input_json
```

Workers receive fully bound payloads (e.g. `"chromosome": "7"`, `"context": "CG"`, `"group": "healthy"`) — not a “run whole project” meta-task.

### Collection bindings (engine-side array expansion)

Previously, `chromosomes[]`, `contexts[]`, and `comparisons[]` had to be copied into `context_json` by a portal planner before instance start. **Collection bindings** move that expansion into the **generic engine**, keeping the workflow definition reusable across projects.

**Table:** `wf.workflow_collection_binding` (per `workflow_version_id`, ordered by `bind_order`)

| `source_kind` | Meaning |
|---------------|---------|
| `jsonFile` | Read JSON document from filesystem path in scope var `path_var` (typically `projectPath` → scope var `project`); falls back to inline `project` in `context_json` if the file is unreadable |
| `jsonPath` | Extract fragment from scope var `base_var` at `json_path` (e.g. `$.chromosomes`) into `scope_var` |

**Procedure:** `wf.wf_resolve_collection_bindings` — invoked from `sp_start_workflow_instance` immediately after `wf_init_instance_scope_from_context`, before graph activation.

**SQL:** [`workflow_engine/sql_pg/wf_sql_collection_bindings.sql`](/home/ubuntu/MethylPipeline/workflow_engine/sql_pg/wf_sql_collection_bindings.sql)

Compiler emits bindings automatically for every `project.*` reference in `for` loops:

```json
{
  "collection_bindings": [
    { "scope_var": "project", "kind": "jsonFile", "path_var": "projectPath", "bind_order": 0 },
    { "scope_var": "chromosomes", "kind": "jsonPath", "base_var": "project", "json_path": "$.chromosomes", "bind_order": 1 },
    { "scope_var": "contexts", "kind": "jsonPath", "base_var": "project", "json_path": "$.contexts", "bind_order": 2 },
    { "scope_var": "comparisons", "kind": "jsonPath", "base_var": "project", "json_path": "$.comparisons", "bind_order": 3 }
  ]
}
```

```mermaid
sequenceDiagram
  participant Client
  participant DB as Engine (DB)
  participant Worker

  Client->>DB: create instance { projectPath, pipelineProfile }
  Client->>DB: sp_start_workflow_instance
  DB->>DB: init scope from context_json
  DB->>DB: resolve collection_bindings (project → chromosomes, contexts, comparisons)
  DB->>DB: FOREACH / PARALLEL activate graph
  Worker->>DB: sp_worker_request_task(capability)
  DB-->>Worker: input_json with concrete chr, ctx, group
```

**Instance `context_json` (minimal):**

```json
{ "projectPath": "/work/study/configs/project_Healthy_vs_PCa.json" }
```

The full project file remains authoritative for cohorts and study layout; **tool parameters** resolve from profile/site `actionConfig` (enriched into `context_json` at instance start). The engine only materializes **iteration arrays** needed by FOREACH nodes.

**Note:** `jsonFile` uses PostgreSQL `pg_read_file` when the DB host can read the shared `/work/` mount. If not (e.g. Azure SQL without file access), include `"project": { … }` in `context_json` as a snapshot; `jsonPath` bindings still apply.

---

## 4. Workflow database model

The workflow engine stores **definitions** (reusable trees) and **runtime** (instances, executions, leases). The same logical model deploys to **Azure SQL Database** (T-SQL, `json` columns) or **Azure PostgreSQL** (`jsonb`). Stored procedure names are contractually identical ([`workflow_engine/contract/db_objects.yaml`](/home/ubuntu/MethylPipeline/workflow_engine/contract/db_objects.yaml)).

Deploy scripts:

- SQL Server: bundled [`workflow_engine/sql_mssql/MethylPipeline.sql`](/home/ubuntu/MethylPipeline/workflow_engine/sql_mssql/MethylPipeline.sql) + parity scripts
- PostgreSQL: [`workflow_engine/sql_pg/`](/home/ubuntu/MethylPipeline/workflow_engine/sql_pg/) (`00_schema.sql` … `07_scope_encoding_parity.sql`)

### Tables by layer

| Layer | Tables |
|-------|--------|
| **Definition** | `workflow_def`, `workflow_version`, `workflow_node`, `workflow_edge`, `workflow_action`, `workflow_input_template`, `workflow_input_binding`, `variable_output_binding`, `node_scope_default`, **`workflow_collection_binding`** |
| **Runtime** | `workflow_instance`, `node_execution`, `task_lease`, `loop_state`, `execution_context`, `scope_variable`, `instance_cursor`, **`hyperparameter_set`**, **`hyperparameter_set_action_entry`** (`workflow_instance.hyperparameter_set_id` FK, nullable) |
| **Workers / cluster** | `worker`, `worker_token`, `cluster` |

### Control-flow node types

`workflow_node.node_type` CHECK constraint:

```
ACTION | SEQUENCE | PARALLEL | IF | SWITCH | REPEAT | WHILE | FOREACH
```

| Type | Role |
|------|------|
| `ACTION` | Leaf task; bound to `workflow_action`; becomes `READY` for workers |
| `SEQUENCE` | Run children in `child_order` |
| `PARALLEL` | Run all children concurrently; complete when all succeed |
| `FOREACH` | Iterate a JSON array from `context_json` (`foreach_collection_var`); `foreach_parallel=1` fans out all iterations at once |
| `IF` / `SWITCH` | Branch on scope variable or prior task result |
| `REPEAT` / `WHILE` | Fixed-count or condition loops |

`workflow_edge.branch_kind`: `SEQUENCE`, `PARALLEL`, `THEN`, `ELSE`, `CASE`, `DEFAULT`, `BODY`.

### Entity relationship (simplified)

```mermaid
erDiagram
  workflow_def ||--o{ workflow_version : has
  workflow_version ||--o{ workflow_node : contains
  workflow_node ||--o{ workflow_edge : links
  workflow_node ||--o| workflow_input_template : template
  workflow_version ||--o{ workflow_instance : runs
  workflow_instance ||--o{ node_execution : executes
  node_execution ||--o| task_lease : lease
  workflow_action ||--o{ workflow_node : action
  cluster ||--o{ worker : registers
  worker ||--o{ worker_token : auth
```

### Hyperparameter sets and CAAS

When operators experiment with the **same** workflow (site/study/profile/DomainProgram) under varied config, the Content-Addressed Action Store (CAAS) versions idempotent action results by cumulative input signature and reuses identical intermediate outputs across workflow instances. The database mirrors on-disk CAAS identity and ledger for portal queries and cross-instance comparison.

**Process-agnostic design:** these objects are **additive** — they do not alter the core workflow-engine tables or procedures. Identity is a generic `set_key` hash of merged `resolvedConfig__*` slices; `config_json` is opaque JSON; the ledger keys on `action_name`, `run_key`, and `content_key`. There are no disease, study, or process-specific columns. The FK `workflow_instance.hyperparameter_set_id` is **nullable**; instances that do not opt into CAAS behave as before.

| Object | Role |
|--------|------|
| `wf.hyperparameter_set` | Registry of unique config combinations (`set_key`, optional `display_name`, `config_json`) |
| `wf.workflow_instance.hyperparameter_set_id` | Links each run to its hyperparameter set |
| `wf.hyperparameter_set_action_entry` | Queryable ledger: `(set, action_name, run_key) → content_key` |

**Procedures** (deployed from [`workflow_engine/sql_pg/wf_hyperparameter_set.sql`](/home/ubuntu/MethylPipeline/workflow_engine/sql_pg/wf_hyperparameter_set.sql); parity in `sql_mssql/`):

- `wf_apply_hyperparameter_set` — called at instance creation when `hyperparamSetId` is present in `context_json`
- `wf_repo_upsert_hyperparameter_action_entry` — called after successful task submit when CAAS is enabled

On-disk CAAS (`.caas/` under `{project_root}`) remains the execution store; the database mirrors identity and ledger only.

```mermaid
erDiagram
  hyperparameter_set ||--o{ workflow_instance : "labels runs"
  hyperparameter_set ||--o{ hyperparameter_set_action_entry : "ledger"
  workflow_instance ||--o{ hyperparameter_set_action_entry : "records"
  hyperparameter_set {
    bigint id PK
    text set_key "hash of resolvedConfig slices"
    text display_name "optional"
    jsonb config_json "opaque merged config"
  }
  workflow_instance {
    bigint id PK
    bigint hyperparameter_set_id FK "nullable"
    jsonb context_json
  }
  hyperparameter_set_action_entry {
    bigint hyperparameter_set_id FK
    bigint workflow_instance_id FK
    text action_name
    text run_key
    text content_key "sha256(action_revision|input_signature)"
  }
```

**See also:** [Usage ch.17 — Content-Addressed Action Store](/home/ubuntu/MethylPipeline/docs/usage/17-content-addressed-action-store.qmd), [hyperparameter-result-versioning plan](/home/ubuntu/MethylPipeline/docs/plans/hyperparameter-result-versioning.plan.md).

### Scoped variables — declaration, assignment, and use

Scoped variables are a first-class workflow feature: they carry **instance parameters**, **loop indices**, **FOREACH item fields**, and **outputs from prior worker actions** through the execution tree. The engine resolves them when building `input_json` and when choosing IF / SWITCH / WHILE branches.

**Why they exist:**

1. **Complex control flow** — conditions that are too rich for a static workflow definition (QC gates, pagination, model-quality thresholds, custom business rules) can be evaluated inside a worker ACTION; the worker writes an integer or JSON fragment back into scope, and downstream IF / SWITCH / WHILE nodes read that value.
2. **Validation / Monte Carlo iterations** — each iteration needs a **fresh stratified train/validation partition**. A **domain planner** (outside the engine) materializes partition descriptors into `context_json.iterations[]`; FOREACH flattens each element into scope and templates reference `${var.taskConfig}` directly.

#### Storage model

| Object | Layer | Role |
|--------|-------|------|
| `wf.scope_variable` | Runtime | `(workflow_instance_id, scope_node_execution_id, var_name) → value_json` |
| `wf.node_scope_default` | Definition | Variables declared when a composite scope **opens** (`var_name`, `default_expr`) |
| `wf.variable_output_binding` | Definition | Maps ACTION **output** → scope variable (`result_code` or `output_path` into `output_json`) |
| `workflow_node.condition_var` / `switch_var` | Definition | IF / SWITCH / WHILE read these names from scope |

**Scope identity:** `scope_node_execution_id = 0` is the **instance root** (global scope). Each composite node (SEQUENCE, PARALLEL, REPEAT, WHILE, FOREACH, IF, SWITCH) opens a child scope tied to its `node_execution.id`. Lookup walks **up the parent chain** until a name is found (`wf.wf_get_scope_variable_json`).

```mermaid
flowchart TD
  ctx["context_json\n(instance start)"]
  root["scope id = 0\nprojectPath, comparisons[], iterations[]"]
  fecp["FOREACH scope\nvar.label, var.chromosome"]
  seq["SEQUENCE scope\ncopied from parent"]
  act["ACTION scope\noutput bindings write here"]
  ctx -->|"wf_init_instance_scope_from_context"| root
  root --> fecp
  fecp --> seq
  seq --> act
  act -->|"variable_output_binding\non submit"| act
  act -.->|"visible to siblings\nvia parent walk"| seq
```

#### Declaration (definition-time)

**`node_scope_default`** declares variables that appear when a node’s scope opens. Values are **expressions**, not literals: the engine resolves `${...}` placeholders against the current scope before assignment.

Example from per-comparison nodes in legacy PCa seeds: `centroid2Dir`, `detectOutDir`, and `comparisonLabel` are seeded as defaults on each comparison subtree so the workflow definition stays generic while paths vary by comparison label.

#### Assignment (runtime)

| Mechanism | When | Example |
|-----------|------|---------|
| Instance bootstrap | `StartInstance` | Every top-level key in `context_json` → scope `0` |
| **Collection bindings** | **`StartInstance` (after bootstrap)** | **`projectPath` → load `project`; `$.chromosomes` → `chromosomes[]` for FOREACH** |
| Scope open | Composite activation | Copy parent scope + apply `node_scope_default` |
| FOREACH iteration | Each loop body activation | Bind `foreach_item_var` fields and flatten object keys (`runId`, `taskConfig`, …) |
| REPEAT / WHILE | Loop body | `${ctx.iterationNo}` in `execution_context` |
| ACTION complete | Worker submit | `variable_output_binding`: `result_code` or JSON path from `output_json` |
| Domain planner (optional) | Before instance start | Populates `context_json.iterations[]`; may audit via `wf.instance_extension` |

Engine write-path: [`wf_sql_scope_writepath_parity.sql`](/home/ubuntu/MethylPipeline/workflow_engine/sql_mssql/wf_sql_scope_writepath_parity.sql) (`wf_set_scope_variable`, `wf_open_scope`, `wf_apply_output_bindings`).

#### Use (read-path)

**Input templates and bindings** resolve placeholders at task claim time in the SQL engine. **`resolvedConfig`** is baked into instance scope at configuration time (`resolvedConfig__*` vars via `finalize_instance_context`); the agnostic gateway does not merge config on claim.

| Token family | Example | Source |
|--------------|---------|--------|
| Scope variable | `${var.chromosome}` | Scope chain walk |
| Indexed array in scope | `${var.orderedComparisonLabels[0]}` | JSON array element |
| FOREACH context | `${ctx.item}`, `${ctx.index}` | Current iteration |
| Loop context | `${ctx.iterationNo}`, `${ctx.parallelIndex}` | `execution_context` |
| Prior task | `${ctx.task.detect.resultCode}` | Latest terminal execution of `detect` |

The resolver does **not** evaluate arithmetic or boolean expressions in placeholders. Any logic beyond simple lookup must run in a worker (or in the planner before the instance starts) and **publish** a scalar or JSON value into scope.

**Control-flow reads:** IF, SWITCH, and WHILE nodes specify `condition_var` / `switch_var`. The engine reads an **integer** from scope (`0` = false / exit loop; non-zero = true / continue). If the variable is absent, it falls back to `condition_ref_node_key` / `switch_ref_node_key` (prior ACTION `result_code`). See [`WORKFLOW_ENGINE_DELPHI.md`](/home/ubuntu/MethylPipeline/workflow_engine/delphi/WORKFLOW_ENGINE_DELPHI.md) and [`wf_sql_branch_parity.sql`](/home/ubuntu/MethylPipeline/workflow_engine/sql_mssql/wf_sql_branch_parity.sql).

### Worker-driven conditions and branching

For conditions that depend on **data-dependent computation**, the workflow pattern is:

```mermaid
sequenceDiagram
  participant E as Workflow engine
  participant W as Worker ACTION
  participant S as scope_variable

  E->>W: input_json (paths, params)
  Note over W: Run analysis, QC, or rule engine
  W->>E: submit result_code + output_json
  E->>S: variable_output_binding writes e.g. shouldRunQc, hasMorePages, mode
  E->>E: IF / SWITCH / WHILE reads condition_var
  E->>E: Activate THEN, ELSE, CASE, or next loop body
```

**Example tree** (from Delphi reference seed `DelphiTreeFlow`):

- `GateIf` — `condition_var = shouldRunQc`: worker sets `1` to run QC, `0` to skip.
- `ModeSwitch` — `switch_var = mode`: worker chooses normalization branch (`1`, `2`, or default).
- `PollWhile` — `condition_var = hasMorePages`: pagination worker sets `1` until no pages remain, then `0`.

This keeps the **workflow graph static** while allowing arbitrarily complex predicates inside workers. Bindings can take either:

- **`source_kind = result_code`** — worker returns a signed integer directly.
- **`source_kind = output_path`** — worker returns JSON; engine extracts a field (e.g. `$.gate.passed`) into scope.

### Extension pattern: validation and Monte Carlo

Monte Carlo validation ([`packages/methylvalidation`](/home/ubuntu/MethylPipeline/packages/methylvalidation/)) repeats analysis on many **independent random splits** of the same cohorts. That domain logic stays **outside** the workflow engine core:

| Layer | Responsibility |
|-------|----------------|
| **Engine** | Static graph; `FOREACH` over `context_json.iterations[]`; `${var.taskConfig}` in `workflow_input_template` |
| **Planner worker** | Capability `validation.plan-iterations`; materializes `monte_carlo_runs/run_*` + returns `iterations[]` ([`workflow_planner.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/workflow_planner.py)) |
| **Optional audit** | `wf.instance_extension` keyed e.g. `methylvalidation.plan`; apply via `wf.wf_apply_validation_plan` |

Each planner-produced iteration typically:

1. Draws a **stratified partition** per cohort (`train_fraction`, e.g. `0.8`).
2. Materializes a run-specific project under `monte_carlo_runs/run_XXXX/`.
3. Emits an object with `runId`, `phase`, `projectPath`, and opaque `taskConfig` JSON.

Stratified split: [`methyl_validation/split.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/split.py). Planner contract: [`contract/validation_planner_capabilities.md`](/home/ubuntu/MethylPipeline/workflow_engine/contract/validation_planner_capabilities.md).

#### Example workflow topology (`ValidationPipeline`)

Seed: [`wf_validation_pipeline_seed.sql`](/home/ubuntu/MethylPipeline/workflow_engine/sql_mssql/wf_validation_pipeline_seed.sql)

```mermaid
flowchart TD
  root["SEQUENCE root"]
  root --> fe["FOREACH iterations"]
  root --> fin["SEQUENCE final_sequence"]
  fe --> seq["SEQUENCE one_iteration"]
  seq --> fc["ACTION centroid\n${var.taskConfig}"]
  seq --> fd["ACTION detector\n${var.taskConfig}"]
  fin --> map["mapper"]
  fin --> enr["enricher"]
  fin --> prog["progression"]
```

FOREACH flattening copies each `iterations[]` element's fields into scope, so templates embed `taskConfig` without hidden engine injection. The **final sequence** runs mapper → enricher → progression on the base `projectPath` after all iterations complete.

**Composition:** outer `FOREACH iterations` × inner `FOREACH comparisons/chromosomes` (DataDrivenPipeline pattern) — see [`wf_foreach_design.md`](/home/ubuntu/MethylPipeline/workflow_engine/sql_mssql/wf_foreach_design.md).

Example `context_json` fragment:

```json
{
  "projectPath": "/work/study/Plasma_healthy_vs_PCa",
  "iterations": [
    {
      "runId": "feature_run_0001",
      "phase": "feature",
      "projectPath": "/work/study/.../monte_carlo_runs/run_0001",
      "taskConfig": { "runId": "feature_run_0001", "phase": "feature", "iteration": 1 }
    }
  ]
}
```

Full example: [`validation_mc.json`](/home/ubuntu/MethylPipeline/workflow_engine/sql_mssql/instance_context_examples/validation_mc.json).

Legacy `MethylValidationFlow` + `context_json.monteCarlo` + `wf.monte_carlo_*` tables are **deprecated**. See [`packages/methylvalidation/docs/USAGE.md`](/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/USAGE.md) for CLI/filesystem-first validation.

Monte Carlo parameters (`train_fraction`, `n_iterations`, stability axes, backends, …) live in **profile/site `actionConfig.validation`** (schema: [`validation.schema.json`](/home/ubuntu/MethylPipeline/schemas/config/validation.schema.json) / `validation_monte_carlo`). The planner and gateway merge them into `context_json`; cohort CSVs and regulatory metadata stay in the study manifest.

### Cluster metadata in DB

```sql
wf.cluster (
  cluster_key, name, provider,
  shared_storage_uri,    -- e.g. file://share or https://...
  worker_mount_path,     -- default '/work'
  status
)
```

Workers register against a cluster; capabilities are stored on `wf.worker.capabilities` (JSON).

---

## 5. Two-group example: config → workflow tree

This section ties **one control vs two disease groups** (OvR-style) to the **`DataDrivenPipeline`** workflow definition and a concrete `context_json`.

### 5.1 Project intent (PCa3-style)

| Item | Value |
|------|--------|
| Control | `controls.all` |
| Disease stages | e.g. `PCa_Low`, `PCa_High` (two comparisons) |
| Context | `CG` |
| Chromosomes | 24 (`1`–`22`, `X`, `Y`) |
| Comparisons shorthand | `control_vs_each_disease` |

Resolved directories (under `/work/projects/prostate-cancer/PCa3/`):

- Centroids control: `centroids/controls/healthy/all`
- Centroids disease: `centroids/diseases/cancer/{PCa_Low|PCa_High}`
- Detections: `detections/all/{PCa_Low|PCa_High}`

### 5.2 Instance `context_json` (runtime)

From [`workflow_engine/sql_mssql/instance_context_examples/pca_ovr.json`](/home/ubuntu/MethylPipeline/workflow_engine/sql_mssql/instance_context_examples/pca_ovr.json):

```json
{
  "projectPath": "/work/projects/prostate-cancer/configs/project_PCa3.json",
  "context": "CG",
  "centroid1Dir": "/work/projects/prostate-cancer/PCa3/centroids/controls/healthy/all",
  "group1Label": "group1",
  "orderedComparisonLabels": ["PCa_Low", "PCa_High"],
  "chromosomes": ["1", "2", "...", "22", "X", "Y"],
  "comparisons": [
    {
      "label": "PCa_Low",
      "centroid2Dir": "/work/projects/prostate-cancer/PCa3/centroids/diseases/cancer/PCa_Low",
      "detectOutDir": "/work/projects/prostate-cancer/PCa3/detections/all/PCa_Low",
      "group2Label": "group2"
    },
    {
      "label": "PCa_High",
      "centroid2Dir": "/work/projects/prostate-cancer/PCa3/centroids/diseases/cancer/PCa_High",
      "detectOutDir": "/work/projects/prostate-cancer/PCa3/detections/all/PCa_High",
      "group2Label": "group2"
    }
  ]
}
```

No per-chromosome nodes are stored in the DB — only **~15 static nodes** in `DataDrivenPipeline`; fan-out is entirely data-driven. The same topology can be **compiled** from a DomainProgram ([Section 3.5](#35-domain-program-language-and-workflow-compilation)) instead of maintained as a SQL seed.

### 5.3 Workflow tree (`DataDrivenPipeline`)

Seed: [`workflow_engine/sql_mssql/wf_data_driven_pipeline_seed.sql`](/home/ubuntu/MethylPipeline/workflow_engine/sql_mssql/wf_data_driven_pipeline_seed.sql)

```mermaid
flowchart TD
  root["SEQUENCE root"]
  root --> fecp["FOREACH foreach_comparisons\nparallel, var: comparisons"]
  root --> post["SEQUENCE post_pipeline"]
  fecp --> seqcmp["SEQUENCE one_comparison"]
  seqcmp --> fechr["FOREACH foreach_chromosomes\nparallel, var: chromosomes"]
  fechr --> seqchr["SEQUENCE one_chromosome"]
  seqchr --> par["PARALLEL centroids"]
  seqchr --> det["ACTION detect"]
  par --> c1["ACTION centroid_g1"]
  par --> c2["ACTION centroid_g2"]
  post --> mapper["ACTION mapper"]
  post --> enricher["ACTION enricher"]
  post --> prog["ACTION progression"]
```

### 5.4 Per-chromosome dependency (one comparison)

```text
one_chromosome (SEQUENCE)
├─ PARALLEL centroids
│  ├─ centroid_g1  (methyl-centroid → centroid1Dir)
│  └─ centroid_g2  (methyl-centroid → centroid2Dir)
└─ detect         (methyl-detector → detectOutDir)
```

`detect` runs only after **both** centroids for that chromosome succeed (PARALLEL parent must complete first).

### 5.5 Execution scale (PCa OvR example)

| Phase | Count |
|-------|------:|
| Comparisons (parallel) | 2 |
| Chromosomes per comparison | 24 |
| Actions per chromosome | 3 (2 centroids + 1 detect) |
| **Subtotal ACTION tasks** | **2 × 24 × 3 = 144** |
| Post-pipeline (sequential) | mapper + enricher + progression = **3** |
| **Total ACTION executions** | **147** |

Post steps run only after **all** comparison branches complete (root `SEQUENCE`: fan-out then post_pipeline).

### 5.6 Input templates (resolved at claim time in SQL; config baked at instance create)

| Node | Resolved `input_json` fields |
|------|---------------------------|
| `centroid_g1` | `project`, `group`, `chromosome`, `context`, `comparison`, `outputDir` → `centroid1Dir` |
| `centroid_g2` | same with `centroid2Dir` |
| `detect` | `project`, `chromosome`, `centroid1Dir`, `centroid2Dir`, `outputDir` |
| `mapper` / `enricher` | `project` only (reads detection outputs from shared storage) |
| `progression` | `project`, `orderedComparisonLabels` |

Worker contracts: [`workflow_engine/sql_mssql/wf_worker_contracts_pca_ovr.md`](/home/ubuntu/MethylPipeline/workflow_engine/sql_mssql/wf_worker_contracts_pca_ovr.md)

---

## 6. Worker protocol and middle-tier

Workers **never connect to the database directly**. They use the REST API (or an equivalent gateway) documented in [`contracts/openapi.yaml`](/home/ubuntu/MethylPipeline/contracts/openapi.yaml) and [`workflow_engine/WORKER_PROTOCOL.md`](/home/ubuntu/MethylPipeline/workflow_engine/WORKER_PROTOCOL.md).

### REST endpoints (worker-only gateway)

| Method | Path | Caller |
|--------|------|--------|
| `GET` | `/v1/health` | Load balancer / monitoring |
| `POST` | `/v1/workers/claim` | Worker poll loop |
| `POST` | `/v1/workers/submit` | Task completion |
| `POST` | `/v1/workers/heartbeat` | Long-running jobs (optional) |

Instance create/start: **portal SQL** or **`methyl-study-start`** (direct DB). See [`docs/reference/admin-cli-methyl-study-start.md`](/home/ubuntu/MethylPipeline/docs/reference/admin-cli-methyl-study-start.md).

Production implementation: Python [`workflow_engine/rest/gateway.py`](/home/ubuntu/MethylPipeline/workflow_engine/rest/gateway.py) (`methyl-gateway`, uvicorn, systemd on Linux). Frozen Delphi reference: [`WfEngine.GatewayService.pas`](/home/ubuntu/MethylPipeline/workflow_engine/delphi/src/WfEngine.GatewayService.pas) / `WfEngineSrv` (see [`DELPHI_GATEWAY_STATUS.md`](/home/ubuntu/MethylPipeline/workflow_engine/delphi/DELPHI_GATEWAY_STATUS.md)).

### Request / submit sequence

```mermaid
sequenceDiagram
  participant W as Worker
  participant MT as Middle-Tier REST
  participant DB as Database wf schema

  W->>MT: POST /v1/workers/tasks/request
  Note over W,MT: worker_id, token, capability filter
  MT->>DB: sp_worker_request_task
  DB-->>MT: 0 or 1 row READY to RUNNING plus lease
  MT-->>W: has_task, input_json, node_execution_id

  Note over W: Run methyl-centroid / methyl-detector / ...

  W->>MT: POST /v1/workers/tasks/id/submit
  MT->>DB: sp_worker_submit_result
  DB->>DB: wf_engine_on_action_complete
  Note over DB: apply output bindings to scope_variable
  Note over DB: activate next READY nodes (IF/SWITCH use scope)
  MT-->>W: accepted, instance_status
```

### Middle-tier responsibilities

| Component | Role |
|-----------|------|
| **`WfEngine.Mvc.*Controller` (DMVC / HTTP.sys)** | Declarative routes → `IGatewayService`; hosted by Windows service `MethylWfGateway` |
| **`IGatewayService` / `TGatewayService`** | One method per OpenAPI operation; calls `wf` contract procs |
| **`WfEngine.GatewayDb` / SQL procs** | Create/start instances; activate graph, resolve templates, advance control flow |
| **`WfEngine.WorkerApiAdapter`** | Worker authenticate, claim, submit, heartbeat, fail |

**State:** All workflow progress lives in the database (`node_execution.status`, `task_lease`, `scope_variable`). The middle-tier is **stateless** between HTTP calls.

### Capability matching

| `workflow_action` | Capability string | Worker advertises |
|-------------------|-------------------|-------------------|
| `pipeline.centroid` | `methyl-centroid` | `methyl-centroid` |
| `pipeline.detector` | `methyl-detector` | `methyl-detector` |
| `pipeline.mapper` | `methyl-mapper` | `methyl-mapper` |
| `pipeline.enricher` | `methyl-enricher` | `methyl-enricher` |
| `pipeline.progression` | `methyl-disease-progression` | `methyl-disease-progression` |

`sp_worker_request_task` claims the oldest `READY` row matching the worker’s capability (optional filter), using `FOR UPDATE SKIP LOCKED` on PostgreSQL for safe concurrent polling.

---

## 7. Cluster and shared storage model

Distributed processing assumes **all worker nodes see the same filesystem** at a common mount point, conventionally **`/work`**, recorded in `wf.cluster.worker_mount_path` and optionally `shared_storage_uri`.

### Assumptions

1. **Shared storage:** NFS, Azure Files, or equivalent mounted at `/work` on every compute node.
2. **Path contract:** `input_json` carries absolute paths under that mount (`centroid1Dir`, `detectOutDir`, …). Workers read and write files directly; the DB stores paths, not file bytes.
3. **No worker-to-worker RPC:** Dependencies are enforced only by the workflow tree (e.g. `detect` after both centroids for the same chromosome).
4. **Maximize parallelism:** Outer `FOREACH` over comparisons and inner `FOREACH` over chromosomes both use **`foreach_parallel = 1`**, so up to `len(comparisons) × len(chromosomes)` centroid pairs and detections can run concurrently, bounded by worker count.
5. **Serialization within a chromosome:** For each `(comparison, chromosome)`, detect waits for both centroids — the only mandatory per-chromosome barrier.
6. **Post-pipeline barrier:** Mapper, enricher, and progression run only after **all** detection tasks complete (second child of root `SEQUENCE`).

### Architecture diagram

```mermaid
flowchart LR
  subgraph cluster [Compute cluster]
    n1["Worker A\nmethyl-centroid"]
    n2["Worker B\nmethyl-centroid"]
    n3["Worker C\nmethyl-detector"]
    n4["Worker D\nmethyl-mapper"]
  end
  subgraph storage [Shared storage /work]
    c1["centroids/controls/.../*.h5"]
    c2["centroids/diseases/.../*.h5"]
    d1["detections/.../dmps-*.csv"]
    m1["mapper/ enricher/ progression/"]
  end
  MT["Middle-tier REST"]
  DB[("Azure SQL or PostgreSQL")]

  n1 --> c1
  n2 --> c2
  n3 --> c1
  n3 --> c2
  n3 --> d1
  n4 --> d1
  n4 --> m1
  n1 & n2 & n3 & n4 --> MT
  MT --> DB
```

### Minimizing total processing time

| Technique | Effect |
|-----------|--------|
| Per-chromosome parallelism | 24 chromosomes per comparison run concurrently |
| Per-comparison parallelism | Multiple disease groups run concurrently |
| Capability-specific workers | Centroid-heavy and detector-heavy nodes scale independently |
| `SKIP LOCKED` task claim | Many workers poll without blocking each other |
| Shared output paths | Centroid output for chr *N* is input to detect for chr *N* on the same mount — no data shipping between nodes |

### Portal + planner + engine (end-to-end)

```text
1. User edits project.json in portal (schema-validated)
2. Planner builds context_json (comparisons[], chromosomes[], dirs)
   — OR compile DomainProgram and pass { projectPath } with collection_bindings
3. Portal or `methyl-study-start` creates instance { workflow_version_id, context_json }
4. Engine resolves collection bindings (if defined) → activates graph → READY rows
5. Workers on cluster pull tasks, read/write /work/..., submit results
6. Instance status → COMPLETED when root SEQUENCE finishes
```

---

## Further reading

| Document | Topic |
|----------|--------|
| [`workflow_engine/contract/domain_types.md`](/home/ubuntu/MethylPipeline/workflow_engine/contract/domain_types.md) | Domain types, `$type` convention, compiler pipeline |
| [`workflow_engine/sql_mssql/DataDrivenPipeline.md`](/home/ubuntu/MethylPipeline/workflow_engine/sql_mssql/DataDrivenPipeline.md) | FOREACH workflow, deploy order |
| [`workflow_engine/sql_pg/wf_sql_collection_bindings.sql`](/home/ubuntu/MethylPipeline/workflow_engine/sql_pg/wf_sql_collection_bindings.sql) | Collection binding table and resolver |
| [`workflow_engine/delphi/WORKFLOW_ENGINE_DELPHI.md`](/home/ubuntu/MethylPipeline/workflow_engine/delphi/WORKFLOW_ENGINE_DELPHI.md) | Scope variables, IF/SWITCH/WHILE, Monte Carlo bridge |
| [`workflow_engine/CAPABILITY_CHECK.md`](/home/ubuntu/MethylPipeline/workflow_engine/CAPABILITY_CHECK.md) | Engine capabilities vs gaps |
| [`docs/theory/chapters/05-methylpredictor-and-validation.qmd`](/home/ubuntu/MethylPipeline/docs/theory/chapters/05-methylpredictor-and-validation.qmd) | Theory: Monte Carlo splits and validation |
| [`docs/theory/chapters/11-project-configuration.qmd`](/home/ubuntu/MethylPipeline/docs/theory/chapters/11-project-configuration.qmd) | Theory: project configuration |
| [`tools/methyl-config-editor/README.md`](/home/ubuntu/MethylPipeline/tools/methyl-config-editor/README.md) | Config editor setup |
| [`workflow_engine/README.md`](/home/ubuntu/MethylPipeline/workflow_engine/README.md) | SQL deploy order |

---

*Document version: aligns with `DataDrivenPipeline` seed, `FOREACH` engine support, scoped-variable write-path parity, Monte Carlo plan/run tables, **DomainProgram IR + compiler**, and **workflow_collection_binding** resolution at instance start.*
