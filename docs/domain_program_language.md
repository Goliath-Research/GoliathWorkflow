# DomainProgram Language Reference

Authoring format for MethylPipeline workflows. Schema: `schemas/domain/domain_program.schema.json`.  
Compiler: `workflow_engine/domain/compiler.py` → `WorkflowDefinitionSpec`.

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

See also [`workers/WORKER_PROTOCOL.md`](../workers/WORKER_PROTOCOL.md) (worker contract) and the user manual [Artifacts and QA Checks — observability](user-manual/09-artifacts-and-qa-checks.qmd).

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

- **Per-action manifests:** `{output_dir}/.action_results/{action_name}.{run_key}.json` — typed result snapshots from pipeline CLIs.
- **Sample prep timeline:** `{sampleDir}/{sampleId}.sample_prep_log.jsonl` — append-only audit log.
- **Validation / MC timeline:** `{monteCarloRunsRoot}/action_run_log.jsonl` — append-only log for validation-category actions.

Authors do not write these files; they are useful when debugging failed runs on `/work`.

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

Literal strings in `with` (e.g. `"mode": "full"`) are preserved; use `{ "ref": "..." }` for scope references.

## Instance context

Minimal validation instance:

```json
{ "projectPath": "/work/study/configs/project.json" }
```

Sample prep adds `samples[]`, `isCfdna`, storage profiles — see `workflow_engine/sql/instance_context_examples/`.

## Local execution

```bash
methyl-workflow-run --program path/to/program.json --context-file context.json --stub-external
methyl-validation run-workflow --program path/to/program.json --context-file context.json
```

## Collection bindings

Compiler emits bindings for `project.*` references. Engine resolves `projectPath` → inline `project` JSON → `chromosomes`, `comparisons`, etc. before FOREACH runs.

## Pipeline profiles (composable paths)

Named presets live in `workflow_engine/domain/profiles/*.profile.json`. Pass via `--context-file` or set `pipelineProfile` in instance context. The engine seeds IF-friendly booleans (`runDmpSelection`, `runGeneFeaturecuts`, `runBiomarkerFilter`, `runGeneFeatureSelect`, `stabilityFeaturecutsEnabled`, …) from the profile and from `step_config.validation` / `gene_selection` / `dmp_selection`.

| Profile | Detector | dmp_select | Mapper CSV | Stability focus |
|---------|----------|------------|------------|-----------------|
| `legacy_dual` | legacy inline FeatureCuts | off | discovery | DMP classifier panels |
| `discovery_interpretation` | discovery_only | off | discovery | single-run mapper/enricher |
| `gene_enricher_stability` | discovery_only | off | discovery | **gene frequency from enricher** (no DMP FC) |
| `dmp_panel_stability` | discovery_only | on | classifier-extended | DMP panel MC |
| `full_biomarker_gene_fc` | discovery + dmp_select | on | classifier-extended | DMP + gene FeatureCuts |
| `discovery_gene_featurecuts` | discovery + dmp_select | on | **discovery** | gene FeatureCuts on **broad mapped gene pool** |
| `structural_features` | discovery_only | off | discovery + intersections | gene×region ranked catalog |

```json
{
  "if": "${runDmpSelection}",
  "then": [{ "do": "pipeline.dmp_select", "with": { "chromosome": { "ref": "chromosome" } } }],
  "else": []
}
```

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
