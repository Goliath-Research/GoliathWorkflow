---
name: Reference inventory audit
overview: Audit shows the human GRCh38 reference inventory (QNAP ↔ cfg ↔ /work) is mostly implemented end-to-end, but several parity gaps, hardcoded pin→asset maps, missing operator upload docs, and legacy leftovers can leave operators or fresh DBs orphaned. This plan documents the exact myQNAPcloud upload layout and closes those gaps so SQL, deploy scripts, fixtures, and docs stay consistent.

> **Status: IMPLEMENTED.** Operator map [`docs/deployment/reference-inventory-qnap.md`](../deployment/reference-inventory-qnap.md); pin→`inventoryPrefix` resolution in `cfg/reference_selection.py`; MSSQL/PG deconv-role migrations; credential example fixture; `verify_work_layout.sh` genome checks; legacy path hygiene.

azure_devops:
  type: Feature
  title: "Reference inventory propagation audit"
  epic_id: 413
todos:
  - id: inventory-doc
    content: Add docs/deployment/reference-inventory-qnap.md with QNAP upload map + Phase 0; cross-link production-platform, config-registry, end-to-end-workflow
    status: completed
  - id: pin-to-prefix
    content: Resolve provision --selected-only via inventoryPrefix matching pin paths; tests for match/miss
    status: completed
  - id: sql-parity
    content: MSSQL asset_role CHECK migration twin; README/AGENTS clarify sql_pg + populate_postgres vs genome seeds
    status: completed
  - id: cred-example
    content: Add credentials/*.example.json + document upsert before provision-assets
    status: completed
  - id: verify-genomes
    content: Extend verify_work_layout.sh to assert pinned genome files when site present
    status: completed
  - id: legacy-hygiene
    content: Normalize stale /home/ubuntu/Work example paths; document deprecated SQL + dual site examples
    status: completed
---

# Reference inventory propagation audit and remediation

See the original plan body in the Cursor plan history. Deliverables:

| Todo | Result |
|------|--------|
| inventory-doc | [`docs/deployment/reference-inventory-qnap.md`](../deployment/reference-inventory-qnap.md) + cross-links |
| pin-to-prefix | [`workflow_engine/cfg/reference_selection.py`](../../workflow_engine/cfg/reference_selection.py) matches pin path → `inventoryPrefix` |
| sql-parity | [`sql_mssql/migrations/20260721_…`](../../workflow_engine/sql_mssql/migrations/20260721_site_reference_asset_deconv_roles.sql); README/AGENTS clarifications |
| cred-example | [`fixtures/credentials/goliath-archive-keys.example.json`](../../workflow_engine/domain/fixtures/credentials/) |
| verify-genomes | [`scripts/verify_work_layout.sh`](../../scripts/verify_work_layout.sh) |
| legacy-hygiene | Instance examples under `/work/projects/…`; `sql_mssql/deprecated/README.md`; dual site `_docs` |
