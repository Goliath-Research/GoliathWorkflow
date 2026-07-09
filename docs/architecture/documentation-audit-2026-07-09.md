# Documentation Audit — July 2026 (comprehensive)

> **Status:** IN PROGRESS (documentation-and-deployment-reliability plan, 2026-07-09).  
> Supersedes stale findings in [`integrity-and-design-review-2026-07-01.md`](integrity-and-design-review-2026-07-01.md) where noted below.

This audit covers **all project dimensions**: developer setup, production deployment, DomainProgram authoring, traceability, logging, idempotency, the database-resident agnostic workflow engine, worker-only gateway, Admin CLI, configuration layers, security, testing, release bundle, and operator workflows.

The July 2026 **config-not-code** refresh ([`documentation-audit-2026-07.md`](documentation-audit-2026-07.md)) remains valid for `step_config` / profile precedence. This report adds **gateway/admin removal**, **setup-path reliability**, and **operational contract** gaps.

## Canonical vs derived

| Layer | Examples | Rule |
|-------|----------|------|
| **Canonical** | `docs/index.md`, `docs/architecture/`, `docs/reference/`, `docs/implementation/`, Usage/Theory `.qmd`, `workflow_engine/contract/`, `contracts/openapi.yaml` | Edit here first |
| **Generated** | `docs/theory/_book/`, `docs/usage/_book/`, `workflow_engine/docs/pipeline_architecture.qmd`, `docs/diagrams/out/*` | Regenerate from source |
| **Historical** | `docs/plans/*.plan.md`, `docs/research/`, `docs/presentations/`, Delphi docs | Do not treat as operational truth |
| **Agent / dev tools** | Cursor MCP, `AGENTS.md` | Dev-only; not worker runtime |

## Coverage heatmap

| Dimension | Canonical home | Depth | Action |
|-----------|----------------|-------|--------|
| Dev setup | [`DEPLOYMENT.md`](../DEPLOYMENT.md), [`setup_host.sh`](../../scripts/setup_host.sh) | Medium | Fix manual path; document `setup_host.sh` as sole path |
| Production deploy | [`operator-journey.md`](../deployment/operator-journey.md), ch.14 | Medium | Remove gateway-deploy wording; fix release scripts |
| DomainProgram | [`domain-program-language.md`](../reference/domain-program-language.md) | High | Add end-to-end worked path + Admin CLI ref |
| DB workflow engine | [`workflow-engine.md`](../implementation/workflow-engine.md) | **Low** | **Primary expansion** |
| Gateway | [`component-boundaries.md`](component-boundaries.md), [`openapi.yaml`](../../contracts/openapi.yaml) | High intent | Purge stale `/v1/admin`, `/v1/actions` from active docs |
| Admin CLI | [`admin-cli-methyl-study-start.md`](../reference/admin-cli-methyl-study-start.md) | New | Dedicated reference |
| Traceability | [`traceability-provenance.md`](../reference/traceability-provenance.md) | New | Operator + regulatory bridge |
| Logging | [`logging-observability.md`](../reference/logging-observability.md) | New | JSONL, timing fields, gaps |
| Idempotency / lease | [`workflow-idempotency-retry-lease.md`](../architecture/workflow-idempotency-retry-lease.md) | New | Document gaps honestly |
| Recovery | Usage ch.11 | Low / legacy | Rewrite for distributed path |

## P0 — Active contradictions (fix in this plan)

| Issue | Stale locations | Canonical truth |
|-------|-----------------|-----------------|
| Gateway admin deploy | `operator-journey.md`, `production_release.md`, ch.14 | Direct DB: `deploy_workflow_definitions.sh`, `seed_action_catalog.py` |
| `GET /v1/actions` | `WORKER_PROTOCOL.md`, `workflow_engine/README.md`, `pipeline_architecture.md` | Worker-only gateway; catalog via git/DB/portal |
| `POST /v1/workflows/*` | Delphi docs, pipeline architecture | Portal SQL or `methyl-study-start` |
| `sample.upload_h5` | `production_runbook.md`, `pipeline_architecture.md` | `sample.archive_sample` |
| `step_config` survivors | `packages/methylclassifier/CONFIG_FILE_GUIDE.md`, `schemas/config/README.md` | `actionConfig.*` |
| PGHOST vs POSTGRES_* | `distributed-workers-bootstrap.md` | `POSTGRES_*` + `BACKEND_DB=postgres` |
| Missing `deploy/env/*.example` | ch.14, production runbook | Add committed templates |

## P1 — Setup / release script defects (fix in this plan)

| Defect | Fix |
|--------|-----|
| `build_release.sh` skips `workflow_engine` wheel (path under `packages/`) | Resolve package paths from `packages.list` |
| `install_release.sh` `--no-index` without third-party wheels | Document `--index-url` or hybrid install |
| `install_worker_systemd.sh` sed duplicates venv path | Use escaped path segments |
| `methyl-gateway.service` uses `venv` not `venv-<arch>` | Arch-aware unit template |
| `verify_setup.sh` checks removed docs; never fails | Runtime-bundle mode + exit on failure |
| `provision_worker_node.sh` calls `setup_host.sh` without source tree | Use `install_release.sh` on promoted bundle |

## P2 — Documentation gaps (new pages in this plan)

- [`docs/reference/admin-cli-methyl-study-start.md`](../reference/admin-cli-methyl-study-start.md)
- [`docs/reference/traceability-provenance.md`](../reference/traceability-provenance.md)
- [`docs/reference/logging-observability.md`](../reference/logging-observability.md)
- [`docs/architecture/workflow-idempotency-retry-lease.md`](workflow-idempotency-retry-lease.md)
- Expanded [`docs/implementation/workflow-engine.md`](../implementation/workflow-engine.md)

## Related

- Registry: [`DOCUMENTATION_AUDIT.md`](../DOCUMENTATION_AUDIT.md)
- Prior config audit: [`documentation-audit-2026-07.md`](documentation-audit-2026-07.md)
- Plan: [`documentation-and-deployment-reliability.plan.md`](../plans/documentation-and-deployment-reliability.plan.md)
