# DomainProgram Language Reference

Authoring format for MethylPipeline workflows.

| Artifact | Schema | Location |
|----------|--------|----------|
| DomainProgram (authoring IR) | `schemas/domain/domain_program.schema.json` | Repo: `workflow_engine/domain/**/*.program.json` |
| Compiled engine graph | `schemas/workflow/workflow_definition.schema.json` | Generated at deploy; check harnesses write `compiled/compiled_workflow.json` |
| Study manifest | `schemas/config/project_config.schema.json` | `/work/<study>/configs/project_*.json` |
| Site manifest | `schemas/config/site_manifest.schema.json` | `/work/site/methyl_site.json` (or `METHYL_SITE_CONFIG`) |
| Instance payload | (context keys + profile) | API / `methyl-workflow-run --context` |
| Pipeline profile | `schemas/config/profile.schema.json` | Repo: `workflow_engine/domain/profiles/*.profile.json` |

Compiler: `workflow_engine/domain/compiler.py` → `WorkflowDefinitionSpec` (Pydantic: `workflow_engine/contract/workflow_definition_spec.py`).

**Architecture overview:** [`docs/architecture/index.md`](architecture/index.md)  
**Operator deployment:** [Usage ch.14](usage/14-deployment-and-distributed-workflow.qmd-and-distributed-workflow.qmd)

## Artifact ladder

```text
*.program.json          Authoring IR (versioned in repo)
       │
       ▼ compile_domain_program / compile_domain_program_file
WorkflowDefinitionSpec  Engine graph (nodes, FOREACH, templates, bindings)
       │
       ▼ POST /v1/workflows/definitions  OR  methyl-workflow-run (local)
Database + scheduler    Instance execution with context_json + collection bindings
       │
       ▼ worker poll/submit
methyl-worker           Executes catalog actions; writes artifacts on /work
```

### program.json vs project.json vs context

| File | Contains | Example path |
|------|----------|--------------|
| **`*.program.json`** | Control flow: `do`, `for`, `if`, action names | `workflow_engine/domain/fixtures/sample_prep.program.json` |
| **`project.json`** | Study manifest: cohorts, stages, comparisons, paths, regulatory | `/work/projects/prostate-cancer/configs/project_Buffy_healthy_vs_PCa.json` |
| **`context_json`** | Instance vars: `projectPath`, `pipelineProfile`, `samples[]` | API body or `--context '{...}'` |
| **Profile** | Scope booleans + `actionConfig` parameter packs | `workflow_engine/domain/profiles/staged_ovr_mc.profile.json` |
| **Site manifest** | Genomes, GTF, caches, cluster defaults | `/work/site/methyl_site.json` |

The compiler reads **`projectPath`** from context and inlines `project.chromosomes`, `project.comparisons`, etc. via collection bindings before FOREACH runs.

### Worked example: compile and run locally

```bash
source .venv/bin/activate

# Compile only (inspect graph)
python scripts/compile_workflow_program.py \
  workflow_engine/domain/checks/buffy_healthy_vs_pca/configs/buffy_mc_stability.program.json \
  --context-file workflow_engine/domain/profiles/discovery_gene_featurecuts.profile.json \
  --context '{"projectPath":"/work/projects/prostate-cancer/configs/project_Buffy_healthy_vs_PCa.json"}'

# Run in-process (stub external GPU tools)
methyl-workflow-run \
  --program workflow_engine/domain/checks/buffy_healthy_vs_pca/configs/buffy_mc_stability.program.json \
  --context-file workflow_engine/domain/profiles/discovery_gene_featurecuts.profile.json \
  --context '{"projectPath":"/work/projects/prostate-cancer/configs/project_Buffy_healthy_vs_PCa.json"}' \
  --stub-external
```

### Deploy to gateway

```bash
export GATEWAY_URL=https://your-gateway.example.com
export GATEWAY_ADMIN_BEARER_TOKEN='...'
bash scripts/deploy_workflow_definitions.sh
```

Writes `workflow_versions.json` with IDs for `POST /v1/workflows/instances` and study-start APIs.

## Constructs

| IR | Engine node | Semantics |
|----|-------------|-----------|
| `do` / `action` | `ACTION` | Run catalog action; `with` supplies parameters |
| `for` / `foreach` | `FOREACH` | Iterate collection; `parallel: true` fans out |
| `parallel: [...]` | `PARALLEL` | Run children concurrently |
| sequence of steps | `SEQUENCE` | Ordered execution |
| `if` / `then` / `else` | `IF` | Branch on scope variable truthiness |
| `switch` | `SWITCH` | Integer case selection |
| `while` | `WHILE` | Loop while condition var truthy |
| `repeat` | `REPEAT` | Fixed iteration count |

## Conditions (IF)

Conditions reference scope variables set by prior ACTION output bindings or instance `context_json`:

```json
{ "if": "${qcPass}", "then": [...], "else": [...] }
```

Example: `sample.methyl_qc` binds `qcPass` from `$.guardrails.overall_pass` (see `schemas/actions/catalog.json`).

## Result codes and branching

When a worker completes an ACTION, it submits **`result_code`** (integer) with typed **`output_json`**. The engine stores the code on `node_execution.result_code` and resolves it for control flow via `wf_try_task_result_code(workflow_instance_id, node_key)`.

| Code | Meaning |
|------|---------|
| `< 0` | Hard failure; workflow instance fails |
| `0` | Default success / false branch |
| `1` | True branch (e.g. remediation needed) |
| `2..N` | Multi-way SWITCH cases (per action) |

See also [`workers/WORKER_PROTOCOL.md`](../workers/WORKER_PROTOCOL.md) (worker contract) and the user manual [Artifacts and QA Checks — observability](usage/10-artifacts-and-qa-checks.qmd).

### Two branching styles

**1. Boolean scope bindings (preferred for readability)** — catalog `output_bindings` copy fields from `output_json` into scope variables. Use these in IF conditions:

```json
{ "if": "${qcPass}", "then": [...], "else": [...] }
```

`sample.methyl_qc` also binds `remediateAlignment`, trim counts, and `qcAttemptReason` so programs can loop on alignment remediation without reading `result_code` directly (see `workflow_engine/domain/fixtures/sample_prep.program.json`):

```json
{
  "if": "${remediateAlignment}",
  "then": [
    { "action": "sample.trim_fastq", "node_key": "trim_fastq" },
    { "action": "sample.parabricks_fq2bam", "node_key": "parabricks_realign" },
    { "action": "sample.methyl_qc", "node_key": "methyl_qc_retry" }
  ],
  "else": [{ "action": "sample.qc_failed", "node_key": "qc_failed" }]
}
```

**2. Integer `result_code` (SWITCH)** — reference the prior ACTION node by `node_key`. The engine returns that node's stored `result_code` as an integer for SWITCH case matching:

```json
{
  "switch": { "ref": "methyl_qc" },
  "cases": {
    "0": [{ "action": "sample.methyl_extract", "node_key": "methyl_extract" }],
    "1": [{ "action": "sample.trim_fastq", "node_key": "trim_fastq" }],
    "2": [{ "action": "sample.qc_failed", "node_key": "qc_failed" }]
  }
}
```

`sample.methyl_qc` branch codes: `0` = pass, `1` = realign/trim, `2` = permanent fail.

### Observability on `/work`

Workers and CLIs write trace artifacts under shared storage:

- **Per-action manifests:** `{output_dir}/.action_results/{action_name}.{run_key}.json` — full typed result snapshots from pipeline CLIs.
- **Sample prep timeline:** `{sampleDir}/{sampleId}.sample_prep_log.jsonl` — append-only audit log.
- **Validation / MC timeline:** `{monteCarloRunsRoot}/action_run_log.jsonl` — append-only log for validation-category actions.

Authors do not write these files; they are useful when debugging failed runs on `/work`.

## Idempotent action skip (signature-based)

By default, `execute_task()` **skips** an action when a prior successful manifest exists with matching signatures and verified output artifacts. This makes `methyl-workflow-run` safe to re-run after partial failure (e.g. MC iterations complete, stability failed).

| Field | Location | Purpose |
|-------|----------|---------|
| `action_revision` | `.action_results/*.json` | Invalidates skip when catalog or task schema changes |
| `input_signature` | manifest + `action_run_log.jsonl` | Hash of validated input + materialized `resolvedConfig` |
| `output_signature` | manifest + log | Hash of output artifact metadata (size/mtime; not full HDF5 contents) |

**Skip authority:** `{outputDir}/.action_results/{action_name}.{run_key}.json` (`ActionExecutionRecord`, schema 1.1).

**Audit:** validation actions also append `skipped: true` lines to `{monteCarloRunsRoot}/action_run_log.jsonl`.

**FOREACH iterations:** the scheduler always enters each iteration body; **each action** inside (centroid, detector, mapper, gene_select, …) skips independently when its manifest under `{runDir}/.action_results/` matches. No iteration-level marker is required.

**Force re-execute:**

```bash
methyl-workflow-run --program path/to/program.json --context-file ctx.json --force-rerun
```

Or set `"forceRerun": true` in instance context / per-action input. Environment: `METHYL_FORCE_RERUN=1`.

Enabled for `validation.plan_iterations`, `validation.stability`, `validation.stability_freeze_readiness`, `validation.prepare_freeze_project`, and all `pipeline.*` actions. Legacy coarse flags (`methyl-validation --skip-detection`, `--resume`) remain available.

## Action parameters

```json
{
  "do": "pipeline.detector",
  "with": {
    "chromosome": { "ref": "chromosome" },
    "stepOverride": { "detection_mode": "discovery_only" }
  }
}
```

Literal strings in `with` (e.g. `"mode": "full"`) are preserved; use `{ "ref": "..." }` for scope references. Refs like `iteration.runDir` compile to `${var.iteration.runDir}` for nested FOREACH scope.

## Instance context

Minimal validation instance:

```json
{
  "projectPath": "/work/study/configs/project.json",
  "pipelineProfile": "staged_ovr_mc"
}
```

Pass a profile file with `--context-file workflow_engine/domain/profiles/staged_ovr_mc.profile.json` (merges `actionConfig` and scope flags). Site defaults load from `METHYL_SITE_CONFIG` or `/work/site/methyl_site.json`.

Sample prep adds `samples[]`, `isCfdna`, storage profiles — see `workflow_engine/sql/instance_context_examples/`.

## Local execution

```bash
methyl-workflow-run --program path/to/program.json --context-file context.json --stub-external
methyl-validation run-workflow --program path/to/program.json --context-file context.json
```

## Collection bindings

Compiler emits bindings for `project.*` references. Engine resolves `projectPath` → inline `project` JSON → `chromosomes`, `comparisons`, etc. before FOREACH runs.

## Pipeline profiles and site manifest

### Four-layer authoring

New runs combine four artifacts (see [`reference/config-parameter-matrix.md`](reference/config-parameter-matrix.md)):

1. **Study manifest** — cohorts, stages, comparisons, `regulatory`, `validation_partitions`, `progression_order`
2. **DomainProgram** — topology and optional per-action `stepOverride`
3. **Profile** — reusable `actionConfig` packs and IF scope booleans
4. **Site manifest** — shared infra paths (genome, GTF, caches)

**Precedence:** program `with` / `stepOverride` → profile `actionConfig` → analyte defaults → site manifest → package defaults. Study manifests must not contain tool parameters.

### Profile presets

Named presets live in `workflow_engine/domain/profiles/*.profile.json`. Pass via `--context-file` or set `pipelineProfile` in instance context. The engine seeds IF-friendly booleans from the profile preset and from `actionConfig.validation` / `gene_selection` / `dmp_selection`.

| Profile | Detector | dmp_select | Mapper CSV | Stability / progression |
|---------|----------|------------|------------|-------------------------|
| `legacy_dual` | legacy inline FeatureCuts | off | discovery | DMP classifier panels |
| `discovery_interpretation` | discovery_only | off | discovery | single-run mapper/enricher |
| `gene_enricher_stability` | discovery_only | off | discovery | gene frequency from enricher |
| `dmp_panel_stability` | discovery_only | on | classifier-extended | DMP panel MC |
| `full_biomarker_gene_fc` | discovery + dmp_select | on | classifier-extended | DMP + gene FeatureCuts |
| `discovery_gene_featurecuts` | discovery + dmp_select | on | discovery | gene FeatureCuts on broad mapped pool |
| `structural_features` | discovery_only | off | discovery + intersections | gene×region ranked catalog |
| `staged_ovr_mc` | staged OvR + FeatureCuts | on | discovery | MC stability + progression |
| `staged_full_lifecycle` | staged OvR + FeatureCuts | on | discovery | MC + freeze + model lifecycle |
| `staged_progression_interpretation` | discovery_only | off | discovery | mapper/enricher + progression (no MC) |
| `mc_gene_fc` | Binary cohort MC + stability (analyte-agnostic; use manifest `regulatory`) | on | classifier-extended | gene FeatureCuts stability |
| `buffy_mc_gene_fc` | *(deprecated alias → `mc_gene_fc`)* | | | |

```json
{
  "if": "${runDmpSelection}",
  "then": [{ "do": "pipeline.dmp_select", "with": { "chromosome": { "ref": "chromosome" } } }],
  "else": []
}
```

Profile `actionConfig` example:

```json
{
  "pipelineProfile": "staged_ovr_mc",
  "runDmpSelection": true,
  "runProgressionAnalysis": true,
  "actionConfig": {
    "detection": { "alpha": 0.05, "detection_mode": "discovery_only" },
    "validation": { "n_iterations": 30, "run_stability": true },
    "progression": { "enabled": true, "report_md": true }
  }
}
```

Site manifest example: `workflow_engine/domain/profiles/site_grch38.example.json`.

Fixture programs under `workflow_engine/domain/fixtures/` (`detection_discovery_only`, `dmp_select_optional`, `mapper_per_comparison`, `enricher_with_overrides`) compose with study-specific programs.

Example:

```bash
methyl-workflow-run \
  --program workflow_engine/domain/checks/buffy_healthy_vs_pca/configs/buffy_interpretation.program.json \
  --context-file workflow_engine/domain/profiles/gene_enricher_single_run.context.json

methyl-validation run-workflow \
  --program workflow_engine/domain/checks/pca1_5_cg/configs/mc_gene_enricher_stability.program.json \
  --context-file workflow_engine/domain/profiles/gene_enricher_stability.profile.json
```

**Discovery DMPs → broad mapper → gene FeatureCuts (stable gene panel for model):**

```bash
methyl-validation run-workflow \
  --program workflow_engine/domain/checks/pca1_5_cg/configs/pca1_5_mc_stability.program.json \
  --context-file workflow_engine/domain/profiles/discovery_gene_featurecuts.profile.json
```

Uses `dmps-*-discovery.csv` for mapper (large gene pool), `pipeline.dmp_select` for classifier DMP exports required by `pipeline.gene_select`, and MC stability on gene classifier panels. Set `"runBiomarkerFilter": true` in context to add PPI/disease shrink before gene FeatureCuts (as in `full_biomarker_gene_fc`).

Stability summaries record active axes in `stability_summary.json` → `pipeline_axes` (`dmp_axis`: `none|discovery|classifier`, `gene_axis`: `enricher|classifier`).

## Related JSON schemas

- DomainProgram: `schemas/domain/domain_program.schema.json`
- WorkflowDefinitionSpec: `schemas/workflow/workflow_definition.schema.json`
- Action catalog: `schemas/actions/catalog.json`
- Task I/O: `schemas/tasks/*.schema.json` (regenerate: `methyl-export-task-schemas`)

## Sample prep reference

QC gates and Picard/Parabricks/extraction guardrails: [Usage ch.03](usage/03-sample-prep-and-qc.qmd), [`workflow_engine/sql/SamplePrepFlow.md`](../workflow_engine/sql/SamplePrepFlow.md).
