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
