---
name: Documentation and Deployment Reliability
overview: Make documentation a trustworthy, role-based map of the complete MethylPipeline system and repair deployment/runtime paths so setup instructions are executable. Align canonical docs with worker-only gateway, backend-agnostic Admin CLI, database workflow engine, and current action/config contracts; enforce in CI.
> **Status: COMPLETED** — 2026-07-09.

azure_devops:
  type: Feature
  title: "Documentation and deployment reliability"
  work_item_id: 517
  epic_id: 413
todos:
  - id: canonical-map
    content: Publish the comprehensive audit, refresh canonical navigation, and label historical/derived documentation
    status: completed
    work_item_id: 518
  - id: setup-reliability
    content: Repair and document executable developer, database bootstrap, release, gateway, and worker setup paths
    status: completed
    work_item_id: 519
  - id: domain-program-guide
    content: Document DomainProgram authoring, compilation, deployment, and Admin CLI workflows end to end
    status: completed
    work_item_id: 520
  - id: engine-reference
    content: Expand the database-resident agnostic workflow engine and dual-backend contract documentation
    status: completed
    work_item_id: 521
  - id: operational-contracts
    content: Add canonical traceability, logging, idempotency/retry/lease, and distributed recovery documentation
    status: completed
    work_item_id: 522
  - id: stale-cleanup
    content: Remove stale gateway routes, retired actions/config surfaces, and conflicting generated documentation
    status: completed
    work_item_id: 523
  - id: docs-guardrails
    content: Extend documentation freshness checks and validate all canonical and generated artifacts
    status: completed
    work_item_id: 524
---

# Documentation and Deployment Reliability

See attached implementation plan in Cursor for full section breakdown. This file is the committed plan register; do not edit the Cursor-only plan copy.

## Delivery structure

```mermaid
flowchart LR
  audit["Audit and canonical map"] --> setup["Executable setup and deployment"]
  setup --> authoring["DomainProgram authoring guide"]
  authoring --> engine["Agnostic engine reference"]
  engine --> ops["Traceability, logging, idempotency, recovery"]
  ops --> cleanup["Stale surface cleanup"]
  cleanup --> gates["CI freshness and reliability gates"]
```
