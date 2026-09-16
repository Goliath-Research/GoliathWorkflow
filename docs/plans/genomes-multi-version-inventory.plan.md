---
name: Genomes multi-version inventory
overview: Company myQNAPcloud holds a multi-version genome inventory under goliath/genomes/ using a role-based tree (linear / annotation / pangenome). Site/cfg pins exact selected versions; provision syncs from goliath-genomes to /work/genomes.

> **Status: IMPLEMENTED.** Canonical tree + site `reference_selection`, `goliath-genomes` endpoint, reference_asset fixtures/SQL seeds, `s3_sync` provision, Phase 0 `scripts/provision_selected_genomes.sh`.

azure_devops:
  type: Feature
  title: "Genomes multi-version inventory + pinned selection"
  work_item_id: null
  epic_id: 413
todos:
  - id: layout-and-selection
    content: "Update site examples/schema + sync script for tree: linear/GRCh38/ensembl-114, annotation/gencode/v49, pangenome/GRCh38/d9/1.70"
    status: completed
  - id: qnap-reorganize-cli
    content: QNAP goliath/genomes/ reorganized to canonical tree (operator complete)
    status: completed
  - id: confirm-gap-docs
    content: Document Phase 0 sync from goliath/genomes/ inventory + site pins selected versions
    status: completed
  - id: seed-genomes-endpoint
    content: Seed/publish cfg storage_endpoint goliath-genomes (bucket goliath, prefixBase genomes/) reusing archive credential
    status: completed
  - id: reference-asset-recipes
    content: Publish versioned cfg.reference_asset per role + site reference_selection mapping
    status: completed
  - id: provision-s3-sync
    content: Bulk S3 sync inventory to /work/genomes; materialize site paths from selected asset versions
    status: completed
  - id: phase0-hook
    content: "Phase 0: ensure selected versions present under /work/genomes before extract/align"
    status: completed
---

# Genomes: multi-version inventory + pinned selection

## Canonical tree

```
goliath/genomes/   ↔   /work/genomes/
  linear/GRCh38/ensembl-114/
  annotation/gencode/v49/
  pangenome/GRCh38/d9/1.70/
```

## Advantages

- Role separation (linear / GENCODE / pangenome version independently)
- Assembly-first under `linear/` and `pangenome/`
- Clear site pins via `reference_selection`
- Pangenome index nesting `d9/1.70/`

## Implementation artifacts

| Area | Location |
|------|----------|
| Site schema + examples | [`schemas/config/site_manifest.schema.json`](../../schemas/config/site_manifest.schema.json), [`site_grch38.example.json`](../../tools/methyl-config-editor/configs/site_grch38.example.json) |
| Sync script | [`scripts/sync_genomes_to_s3.sh`](../../scripts/sync_genomes_to_s3.sh) (`--only linear\|annotation\|pangenome`) |
| Phase 0 helper | [`scripts/provision_selected_genomes.sh`](../../scripts/provision_selected_genomes.sh) |
| Endpoint seed | [`portal_resource_profile.sql`](../../workflow_engine/sql_mssql/portal_resource_profile.sql) → `goliath-genomes` |
| Asset seed | [`cfg_reference_assets_seed.sql`](../../workflow_engine/sql_mssql/cfg_reference_assets_seed.sql) + fixtures under `workflow_engine/domain/fixtures/reference_assets/` |
| Provision | [`workflow_engine/cfg/provision.py`](../../workflow_engine/cfg/provision.py) (`s3_sync`, `--selected-only`) |
| Selection helper | [`workflow_engine/cfg/reference_selection.py`](../../workflow_engine/cfg/reference_selection.py) |
| Docs | [`production-platform.md`](../deployment/production-platform.md) Phase 0, [`config-registry.md`](../architecture/config-registry.md) |
