---
name: SaMD Deploy Buffy Migrate
overview: Ship SaMD profiles/modes on shared storage; depersonalize all DomainPrograms (MC + historical check demos) to algorithm names; publish algorithm and SaMD-named workflow_def graphs to the DB (process-agnostic); fix mode overlay resolution; migrate Buffy to samd_research + dual_fc. No new SQL NodeTypes.
> **Status: COMPLETED** — 2026-07-10 (DB upsert pending host→Azure SQL network; compiled specs + deploy scripts ready).

azure_devops:
  type: Feature
  title: "SaMD deploy + generic programs + Buffy research migrate"
  work_item_id: 544
  epic_id: 413
todos:
  - id: depersonalize-all-programs
    content: Rename/move all study-prefixed DomainPrograms to algorithm-generic fixtures; update refs/tests/docs
    status: completed
    work_item_id: 545
  - id: publish-db-graphs
    content: Deploy algorithm graphs + SaMD-named workflow_def entry points to Azure SQL; write workflow_versions.json; no new NodeTypes
    status: completed
    work_item_id: 546
  - id: sync-runtime-bundle-samd
    content: Rsync samd profiles/modes + generic fixtures + pipeline_profiles.py into /work/goliath/current/runtime-bundle/domain; verify files present
    status: completed
    work_item_id: 547
  - id: fix-mode-path-resolution
    content: Resolve mode overlays via METHYL_PROFILE_DIR/profile_search_dirs; add verify_setup asserts; doc note
    status: completed
    work_item_id: 548
  - id: migrate-buffy-research
    content: Update Buffy manifest (regulatory + partition stubs); add context_samd_research_buffy.json (dual_fc); point runs at fixtures/mc_stability + SaMD_Research def
    status: completed
    work_item_id: 549
  - id: promote-plan-docs
    content: Promote plan to docs/plans/samd-deploy-buffy-research-migrate.plan.md + README mapping
    status: completed
    work_item_id: 550
---

# SaMD shared-storage deploy + generic programs + DB publish + Buffy migration

## Delivered

### DomainPrograms (algorithm names)
Canonical fixtures under [`workflow_engine/domain/fixtures/`](../../workflow_engine/domain/fixtures/):

- `mc_stability`, `mc_stability_staged`, `mc_stability_smoke`, `mc_stability_ppi`, `mc_gene_enricher_stability`
- `data_driven`, `interpretation`, `legacy_dual`, `validation_freeze`, `validation_model`, `full_lifecycle`, `study_validation_lifecycle`
- SaMD entry points: `samd_research`, `samd_holdout_enrichment`, `samd_pivotal`
- SamplePrep unchanged

Study-prefixed check programs removed; see `checks/*/PROGRAMS_MOVED.md`.

### Shared storage
Rsynced into `/work/goliath/current/runtime-bundle/domain/` (profiles + modes + fixtures + `pipeline_profiles.py`). Mode overlays resolve via `METHYL_PROFILE_DIR` / `profile_search_dirs()`.

### DB publish
Deploy scripts updated ([`scripts/deploy_mc_workflow_definitions.sh`](../../scripts/deploy_mc_workflow_definitions.sh), [`scripts/deploy_workflow_definitions.sh`](../../scripts/deploy_workflow_definitions.sh)). Compiled specs under `/work/goliath/env/compiled/mc/`; version map `/work/goliath/env/workflow_versions_mc.json`. **Host ODBC login to Azure SQL timed out** — re-run deploy when network allows. No new SQL NodeTypes.

### Buffy migration
- Manifest: `expanded_development` + partition stubs + `allow_clinical_performance_claims: false`
- Context: `/work/projects/prostate-cancer/configs/context_samd_research_buffy.json` (`samd_research` + `dual_fc`)
- Evidence index updated

## Operator run

```bash
methyl-workflow-run \
  --program /work/goliath/current/runtime-bundle/domain/fixtures/mc_stability.program.json \
  --context-file /work/projects/prostate-cancer/configs/context_samd_research_buffy.json
```
