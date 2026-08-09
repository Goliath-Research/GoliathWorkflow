# Implementation Guide

Developer-facing documentation for the workflow engine, workers, DomainProgram compiler, and package code paths.

| Document | Topic |
|----------|-------|
| [Sample preparation flow](sample-preparation-flow.md) | download → three-mode align (native-Mojo / explicit Parabricks) → mode-aware alignment QC → remediation → extract → extraction QC |
| [Workflow engine](workflow-engine.md) | local engine, REST gateway, SQL schema |
| [Workers and gateway](workers-and-gateway.md) | poll/submit protocol, capabilities |
| [DomainProgram compiler](domain-program-compiler.md) | compile, bind, deploy |
| [Packages index](packages/index.md) | links to `packages/*/docs/IMPLEMENTATION.md` |

**Engine deep dive:** [`workflow_engine/docs/pipeline_architecture.md`](../../workflow_engine/docs/pipeline_architecture.md) — DB tables, hyperparameter sets, CAAS, portal lifecycle.

**Also:** [`workflow_engine/docs/IMPLEMENTATION.md`](../../workflow_engine/docs/IMPLEMENTATION.md) — gateway, DB client, scheduler internals.

**Architecture (system design):** [../architecture/](../architecture/index.md). **Operator runbooks:** [../usage/](../usage/index.qmd).

## When to update

- Action catalog or compiler changes → this guide + affected package `IMPLEMENTATION.md`
- Worker protocol changes → `workers/WORKER_PROTOCOL.md` + OpenAPI + this guide
- Schema export → `methyl-export-task-schemas`, `methyl-export-action-catalog`
