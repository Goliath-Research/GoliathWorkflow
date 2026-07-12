---
name: DB Config Registry
overview: Make the database the authoritative store for all workflow-execution configuration (sites, reference assets and their provision recipes, sample origins, profiles, studies, DomainProgram source, and action schemas), with bidirectional authoring for DomainPrograms and actions, and a deploy path that materializes those objects onto shared `/work` storage for cluster workers.
todos:
  - id: phase1-cfg-ddl
    content: Add cfg schema + registry tables/procs (MSSQL + PG); wire deploy_azure.sh
    status: completed
  - id: phase1-methyl-cfg-cli
    content: Implement methyl-cfg import-fs / upsert / materialize for site, profiles, DomainProgram IR, studies
    status: completed
  - id: phase1-roundtrip-tests
    content: "Round-trip tests: import → materialize → existing loaders resolve"
    status: completed
  - id: phase2-publish-program
    content: "publish-program: compile DomainProgram from cfg → wf graph deploy + bundle materialize"
    status: completed
  - id: phase2-sync-actions
    content: "sync-actions: cfg ↔ wf.workflow_action/schema ↔ client catalog; bootstrap integration"
    status: completed
  - id: phase3-storage-credentials
    content: "cfg.storage_endpoint + cfg.credential: provider-discriminated locations (S3/Azure/GCS/file) and secrets; extend JSON Schema with Azure SAS + GCS; never materialize secrets to /work"
    status: completed
  - id: phase3-assets-storage
    content: reference_asset recipes + provision runner; storage_profile refs endpoints; site refs expand on materialize; planner injects credentials into task input only
    status: completed
  - id: phase4-bidirectional-scaffold
    content: DB→client action scaffold CLI; portal cfg DomainProgram tree API; config-editor catalog rewire
    status: completed
  - id: phase5-cutover-docs
    content: DB-first admin create paths; update layer-model, work-config-paths, distributed-runtime, docs/plans
    status: completed
---

# Database configuration registry and shared-storage materialization

> **Status: Implemented (spine)** — `cfg` DDL (MSSQL+PG), `methyl-cfg` CLI + file store, materialize, storage credentials (SAS/GCS), provision recipes, action scaffold, portal API, docs.

See [docs/architecture/config-registry.md](../architecture/config-registry.md) and [docs/usage/19-config-registry.qmd](../usage/19-config-registry.qmd) for the operator path. Original design notes live in the Cursor plan; this file is the repo-local epic record.
