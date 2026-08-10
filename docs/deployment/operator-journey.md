# Operator journey (day-1 → day-N)

Single navigation page for production operators. Each step links to the canonical deep-dive runbook — this file does not duplicate them.

**Start here for a full production platform:** [production-platform.md](production-platform.md) (release → DB → gateway → Arc workers → portal enroll).

## Prerequisites

| Step | Action | Deep dive |
|------|--------|-----------|
| 1 | Mount shared storage at `/work/epimethyl` and study trees under `/work/projects/<study>/` | [Production platform — Phase 0](production-platform.md#phase-0-shared-storage-and-site) |
| 2 | Install site manifest at `/work/site/methyl_site.json` (`METHYL_SITE_CONFIG`) | [Layer model](../architecture/layer-model.md) |
| 3 | Production DB = Azure SQL (portal); PostgreSQL for parity/CI | [Usage ch.14](../usage/14-deployment-and-distributed-workflow.md) |

## Greenfield control plane

| Step | Script / command | Deep dive |
|------|------------------|-----------|
| 4 | Promote MethylPipeline + MethylExtractor (+ Parabricks) | [production_release.md](production_release.md) |
| 5 | Deploy DB schema + catalog + workflows | `bash scripts/bootstrap_distributed_workers.sh` |
| 6 | Verify bootstrap (read-only) | `bash scripts/bootstrap_distributed_workers.sh --verify` |
| 7 | Start gateway (systemd + nginx TLS + Arc attest) | [production-platform.md — Phase 3](production-platform.md#phase-3-single-gateway-vm) |
| 8 | Portal-preregister IP → prepare → Arc approve → finish-enroll → systemd | [Lambda worker join](lambda_worker_join.md) · [Phase 4](production-platform.md#phase-4-each-gpu-worker-arc-enroll) |

See [Lambda worker join](lambda_worker_join.md) (Azure vs QNAP vs NGC vs Arc), [Distributed workers bootstrap](distributed-workers-bootstrap.md), [arc_worker_runbook.md](arc_worker_runbook.md), and [GPU worker runbook](gpu_worker_runbook.md).

## Release promote

| Step | Script / pipeline | Deep dive |
|------|-------------------|-----------|
| 9 | Tag release build | Azure DevOps `ci/azure-pipelines-release.yml` (`v*`) |
| 10 | Assemble MP + MethylExtractor | `ci/azure-pipelines-release-assemble.yml` → `scripts/assemble_release.sh` |
| 11 | Promote to `/work/epimethyl/current` | `ci/azure-pipelines-release-deploy.yml` → `scripts/promote_release.sh` |
| 12 | Post-promote verify | `scripts/verify_setup.sh` (deploy pipeline); optional `scripts/verify_e2e_node.sh` on GPU worker |

See [Production release](production_release.md).

## Study execution (canonical)

| Step | Entry | Deep dive |
|------|-------|-----------|
| 13 | Sample prep (FASTQ → HDF5) | Portal SQL or `methyl-study-start` | [SamplePrepFlow](../../workflow_engine/sql_mssql/SamplePrepFlow.md), [Usage ch.03](../usage/03-sample-prep-and-qc.md) |
| 14 | Staged validation | `methyl-workflow-run` + DomainProgram + profile | [Usage ch.04 orchestration](../usage/04-orchestration-workflow-run.md) |
| 15 | Monitor instances | Gateway poll + DB `wf.workflow_instance` | [Distributed runtime](../architecture/distributed-runtime.md) |

**Presets:** copy-ready program/profile/context combos — `bash scripts/workflow_presets.sh list`.

## Smoke and rollback

| Step | Script | When |
|------|--------|------|
| Smoke (stub worker) | `WORKER_STUB_EXTERNAL=1 bash scripts/smoke_sample_prep.sh` | After bootstrap |
| Smoke (lifecycle) | `bash scripts/smoke_study_lifecycle.sh` | After workflow deploy |
| Nightly CI smoke | `ci/azure-pipelines-smoke.yml` | Scheduled on `production-work-agents` |
| Rollback release | Re-run deploy pipeline with previous `releaseVersion` | [Production release — rollback](production_release.md#rollback) |

## Script catalog (operator)

| Script | Purpose |
|--------|---------|
| `bootstrap_distributed_workers.sh` | DDL + catalog seed + workflow deploy (+ `--verify`) |
| `assemble_release.sh` | Bundle MethylPipeline + MethylExtractor artifacts |
| `promote_release.sh` | Flip `/work/epimethyl/current`, refresh venv, worker env |
| `deploy_workflow_definitions.sh` | Compile + deploy DomainPrograms via direct DB (`methyl-study-start` / `ops`) |
| `install_gateway_systemd.sh` | Install arch-aware gateway unit (`venv-<arch>`) |
| `preflight_worker_join.sh` | QNAP `/work` + `current/manifest` join checks |
| `provision_worker_node.sh` | Join-only prepare / finish-enroll (host/Docker + gateway enroll + systemd) |
| `register_worker.sh` | Gateway enroll (no DB env) or **dev** direct-DB register |
| `verify_setup.sh` | Release layout + script presence |
| `verify_e2e_node.sh` | GPU worker verify (Parabricks, HDF5 plugin, venv) |
| `verify_work_layout.sh` | Four-layer path and env sanity |
| `smoke_sample_prep.sh` | End-to-end SamplePrep instance smoke |
| `smoke_study_lifecycle.sh` | Validation lifecycle smoke |
| `workflow_presets.sh` | Print canonical `methyl-workflow-run` command lines |

## Legacy paths (transitional only)

| Path | Use when |
|------|----------|
| `methyl-validation --stability/--freeze/--model` | Unmigrated shell scripts only |
| `methyl-validation plan-runs` / `run-task` | File-queue MC not yet on gateway workers |

See [Usage ch.13](../usage/13-distributed-methyl-validation.md).

## Related

- [Production runbook](production_runbook.md)
- [Usage ch.14 — Deployment and distributed workflow](../usage/14-deployment-and-distributed-workflow.md)
- [Operator DB canvas](../canvas/README.md#methylpipeline-db-runbook) (Cursor; sync with `bash scripts/sync_cursor_canvases.sh`)
