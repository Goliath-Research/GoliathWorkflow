# Traceability Matrix

> Status: starter matrix. Expand rows as product requirements, hazards, and
> validation claims are formalized.

## Purpose

This matrix maps product claims and operational controls to design documents,
schemas, tests, and runtime evidence. It is intended to support design review,
release readiness, and regulatory evidence assembly.

## Matrix

| Claim / Control | Design Control | Implementation / Source | Schema / Contract | Verification Evidence | Runtime Evidence |
|-----------------|----------------|-------------------------|-------------------|-----------------------|------------------|
| Study workflow is configuration-driven, not hard-coded | Four-layer model: study, site, profile, DomainProgram | [`../architecture/layer-model.md`](../architecture/layer-model.md), [`../reference/domain-program-language.md`](../reference/domain-program-language.md) | `schemas/config/`, `schemas/domain/domain_program.schema.json` | config schema export checks, domain schema export checks | `context_json`, `resolvedConfig`, workflow version |
| Tool parameters are not stored in study manifests | Config-not-code boundary | [`../reference/action-parameter-contract.md`](../reference/action-parameter-contract.md) | config schemas, task schemas | `scripts/check_task_input_config_boundary.py`, no-step-config guard | task `input_json` plus resolved action config |
| Workflow topology is explicit and monitorable | DomainProgram compile to graph nodes and edges | [`../implementation/workflow-engine.md`](../implementation/workflow-engine.md) | workflow deploy schemas | compile/deploy smoke tests | workflow instance, node execution, scope variables |
| Portal can show Gantt-style instance execution | Node status and dependency graph stored in DB | [`../../workflow_engine/docs/portal_study_lifecycle.md`](../../workflow_engine/docs/portal_study_lifecycle.md) | portal SQL API, workflow DB contract | portal procedure smoke tests | instance task query, node status, timings |
| Workers cannot claim unsupported work | Capability-based worker registration and dispatch | [`../../workers/WORKER_PROTOCOL.md`](../../workers/WORKER_PROTOCOL.md) | OpenAPI, action catalog capabilities | worker runner tests | worker ID, capability, task lease |
| Workers do not connect directly to DB | Gateway-mediated worker protocol | [`../implementation/workers-and-gateway.md`](../implementation/workers-and-gateway.md) | [`../../contracts/openapi.yaml`](../../contracts/openapi.yaml) | gateway/worker tests | gateway logs, task request/submit records |
| Every action returns typed outputs | Pydantic task outputs and JSON Schema export | [`../reference/schema-index.md`](../reference/schema-index.md) | `schemas/tasks/*.json`, DB `workflow_action_schema` | `methyl-export-task-schemas --check` | `node_execution.output_json` |
| Action execution is auditable on shared storage | Action result manifest convention | [`../../workers/WORKER_PROTOCOL.md`](../../workers/WORKER_PROTOCOL.md) | `ActionExecutionRecord` / action output models | action manifest tests, collector tests | `.action_results/*.json` |
| Workflow action timeline is append-only | Unified action run log | [`../usage/10-artifacts-and-qa-checks.qmd`](../usage/10-artifacts-and-qa-checks.qmd) | JSONL action log record shape | action log tests | `action_run_log.jsonl` |
| Sample prep has per-sample traceability | Sample prep JSONL lifecycle log | [`../../workers/WORKER_PROTOCOL.md`](../../workers/WORKER_PROTOCOL.md) | sample prep output schemas | sample prep worker tests | `{sampleId}.sample_prep_log.jsonl` |
| Idempotent replay requires matching signatures | Input/output signatures and artifact verification | [`../../workers/WORKER_PROTOCOL.md`](../../workers/WORKER_PROTOCOL.md) | action manifest schema | action skip tests | `input_signature`, `output_signature`, `skipped`, `skip_reason` |
| Production workers use versioned releases, not git checkouts | Runtime-bundle release layout | [`../deployment/production_release.md`](../deployment/production_release.md) | release manifest schema | release script checks, packaging smoke | `/work/epimethyl/current`, `manifest.json` |
| Release artifacts are hash-checked | Manifest SHA256 fields and promote verification | [`../deployment/production_release.md`](../deployment/production_release.md) | `schemas/deployment/epimethyl_release_manifest.schema.json` | assemble/promote script checks | release manifest, deploy logs |
| Deployment is gated and rollbackable | Assemble and deploy pipelines with approval | [`../../ci/README.md`](../../ci/README.md) | pipeline YAML, release manifest | CI run, deploy approval | deployed release version, rollback record |
| Gateway can avoid stored SQL passwords | Managed identity database access | [`../deployment/production_runbook.md`](../deployment/production_runbook.md) | gateway env contract | health checks | gateway health, DB audit |
| Production worker security is supervised | Worker tokens, TLS, optional Arc/Defender/Sentinel | [`../deployment/production_runbook.md`](../deployment/production_runbook.md) | worker registration schema / DB tables | registration and security verification | worker registration, cluster status |
| Stable panel is selected by recurrence | Monte Carlo stability and freeze workflow | [`../theory/chapters/12-two-workflows.qmd`](../theory/chapters/12-two-workflows.qmd) | validation config schema | validation tests | `stable_dmps_production.csv`, `stability_summary.json` |
| Frozen model is built from fixed panel | Freeze stage injects fixed panel and reruns production analysis | [`../theory/chapters/15-model-creation-and-validation.qmd`](../theory/chapters/15-model-creation-and-validation.qmd) | project/config schemas | model creation tests | `production/project.json`, classifier artifacts |
| Biological readiness is reviewed before model use | Readiness gate checks stability, freeze, enrichment, progression | [`../../packages/methylvalidation/docs/STABILITY_FREEZE_READINESS.md`](../../packages/methylvalidation/docs/STABILITY_FREEZE_READINESS.md) | readiness output JSON | readiness CLI tests | `readiness/readiness.json`, `readiness.md` |
| True holdout evaluation can exclude samples from training | Validation partitions and holdout manifest | [`../theory/chapters/12-two-workflows.qmd`](../theory/chapters/12-two-workflows.qmd) | validation config schema | holdout evaluation tests | `production/holdout_manifest.json`, `holdout_batch/` metrics |
| Real claims require version-bound evidence | Evidence package registry | [`validation-evidence-index.md`](validation-evidence-index.md) | evidence package template | review checklist | approved evidence package |

## Evidence Collection Checklist

For each release or model review, collect:

- release manifest and checksums,
- CI and deploy approval records,
- study/site/profile/program hashes,
- workflow version and instance IDs,
- node execution export,
- worker registration snapshot,
- action result manifests,
- action timeline logs,
- stability/freeze/model/readiness outputs,
- validation metrics and confidence intervals,
- deviation and limitation records.

## Open Traceability Gaps To Review

The following should be resolved or explicitly accepted before formal submission:

- exact portal export format for Gantt-style workflow-instance evidence,
- canonical hash procedure for study/site/profile/program artifacts on `/work`,
- formal link between Azure DevOps work items and change records,
- signed approval workflow for validation evidence packages,
- retention period and archive location for node execution exports and action logs.
