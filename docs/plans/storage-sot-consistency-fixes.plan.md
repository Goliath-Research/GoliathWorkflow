---
name: Storage SoT Consistency Fixes
azure_devops:
  type: Feature
  title: "Storage SoT consistency fixes"
  work_item_id: null
  epic_id: 413
overview: "Reconcile the storage DB SoT changes: make the typed storage/credential Pydantic models accept the expand-injected change tokens (scope, credentialName, credentialVersion, contentHash) so the archive-default and worker paths actually work end-to-end, regenerate/reconcile the domain schema, close the MSSQL/PG parity gap, add regression coverage, and de-stale the docs."
> **Status: COMPLETED** — models accept tokens; schemas regenerated; MSSQL provider parity; regression tests; docs de-staled.
todos:
  - id: models-accept-tokens
    content: Add optional scope/credentialName/credentialVersion/contentHash to storage + credential Pydantic models (fastq_storage.py, sample_storage.py); propagate in merge_* helpers
    status: completed
  - id: regen-reconcile-schema
    content: Regenerate fastq_storage/sample schema via methyl-export-domain-schemas; reconcile hand-written storage_location.schema.json; --check passes
    status: completed
  - id: mssql-pg-parity
    content: MSSQL cfg_repo_upsert storage_endpoint provider derives from location JSON type (match PG)
    status: completed
  - id: regression-tests
    content: "Add tests: expanded dict validates through planner + worker input models; contentHash reaches resolve_secret_payload/node cache"
    status: completed
  - id: docs-destale
    content: Fix stale storage-credential docs (platform overview, transfer-hardening plan pointer, resource_profile->cfg endpoint, methyl-cfg vs portal, schema-index/audit gaps, WORKER_PROTOCOL comment)
    status: completed
---

# Storage SoT consistency fixes

## Root cause (verified P0)

Expand now injects `scope` + `credentialName` / `credentialVersion` / `contentHash` (top-level and nested in `credentials`) in [`workflow_engine/cfg/storage_expand.py`](../../workflow_engine/cfg/storage_expand.py) (`assemble_storage_location`), but the models these dicts pass through are `extra="forbid"`. Broken end-to-end path: archive defaults → `SamplePrepPlanRequest.model_validate` → **ValidationError**. Workers fail identically on task input validation.

## Delivered

1. **Models** — optional change tokens on storage + credential Pydantic models; `merge_*` helpers propagate them.
2. **Schemas** — regenerated `fastq_storage.schema.json`; reconciled `storage_location.schema.json` / `sample_storage.schema.json`; `methyl-export-domain-schemas --check` passes.
3. **MSSQL/PG parity** — `cfg_repo_upsert` storage_endpoint `provider` derives from location JSON `$.type`.
4. **Regression tests** — expanded dicts validate through planner + worker input models; `contentHash` reaches secret resolution / node cache.
5. **Docs** — platform overview, transfer-hardening superseded pointer, resource_profile→cfg endpoint, methyl-cfg vs portal, schema-index, DOCUMENTATION_AUDIT, WORKER_PROTOCOL, sample-prep auth-mode table.

## Non-goals

- No change to the DB SoT authority model or the dumb-worker/node-cache design.
- No EpiPortal UI work.
- Historical/problem-statement text inside completed plans stays (only add superseded pointers).
