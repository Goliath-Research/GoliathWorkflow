---
name: Effective Monte Carlo Config
overview: Remove legacy Monte Carlo parameters from the core model/schema as an intentional breaking change, then add a compact human-facing configuration that nests dependent parameters under their enabling feature. Existing snapshots require the old release; no compatibility adapter or automatic migration will be retained.

> **Status: IMPLEMENTED.** Canonical `MonteCarloConfig` rejects removed keys; planners write `mc_config.json` + informational `mc_config.effective.json`. Resume old snapshots on the release that created them. **DB sync (2026-07-16):** Azure SQL + PostgreSQL `cfg.pipeline_profile` and `wf` action catalog re-seeded via [`scripts/sync_cfg_profiles_and_action_catalog.py`](../../scripts/sync_cfg_profiles_and_action_catalog.py).

azure_devops:
  type: Feature
  title: "Effective Monte Carlo configuration"
  work_item_id: null
  epic_id: 413
todos:
  - id: legacy-inventory-removal
    content: Remove legacy fields, aliases, runtime mirrors, and compatibility validators from MonteCarloConfig and migrate all in-repository consumers to canonical APIs.
    status: completed
  - id: canonical-schemas-configs
    content: Regenerate canonical schemas and update repository profiles, fixtures, tests, and documentation so no removed parameter remains.
    status: completed
  - id: effective-schema-writer
    content: Add the typed activation-aware effective configuration and write it beside the canonical resolved snapshot.
    status: completed
  - id: breaking-change-verification
    content: Add rejection, projection, integration, and clean-repository scans; document the breaking release and old-run boundary.
    status: completed
  - id: db-config-sync
    content: Re-sync cfg.pipeline_profile + wf action catalog/schemas to Azure SQL and PostgreSQL after legacy-parameter removal; leave a reusable sync script and plan note.
    status: completed
---

# Effective Monte Carlo Configuration

## Breaking-change boundary
- Remove legacy parameters from the core model, generated schemas, runtime snapshots, profiles, fixtures, and documentation. Old snapshots/configs are intentionally unsupported and must be run with the old release.
- Do not add an automatic upgrader, compatibility adapter, or silent key drop. Unknown removed keys must fail with a concise breaking-change error.
- Keep the resulting canonical `mc_config.json` as the complete resolved machine snapshot; generate `mc_config.effective.json` beside it for operators.

## Legacy inventory and removal
- Remove cohort aliases `healthy_csv` / `disease_csv` and `_synthesize_cohorts_from_legacy`; require canonical `cohorts`.
- Remove explicitly deprecated stability/workflow fields `stability_min_selected_dmps`, `run_mapper_and_enricher`, and `skip_enricher`; use `stability_min_core_dmps` and DomainProgram topology.
- Remove the embedded `validation` compatibility field from `MonteCarloConfig`.
- Remove flat backend compatibility fields declared on `MonteCarloConfig`, `_sync_runtime_backend_fields`, and flat-key serialization exclusions. Migrate internal consumers to `backend_profiles`, `get_backend_params()`, and explicit backend selection.
- Also remove the runtime-mirror duplicates that still serialize beside `backend_profiles`: `chromosome_*`, `ecdf_aggregated_enabled`, and `ecdf_aggregated_n_bins`.
- Remove legacy modeling-mode/token aliases from [`modeling_modes.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/modeling_modes.py) and observed-feature normalization after converting all repository configs to canonical values.
- Retain the offline legacy backend migration utility only if it can operate without importing legacy fields into the runtime model; otherwise remove it with the compatibility surface.
- Keep `run_stability`; audit confirms it is a canonical orchestration flag, not a legacy alias.
- Before removing freeze-side `skip_enricher` behavior, move enricher skip policy into DomainProgram / `actionConfig.enricher`.
- Before removing `MonteCarloConfig.validation`, fix [`locked_model_spec.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/locked_model_spec.py) so it no longer depends on embedded `step_config.validation`.

## Conditional representation
Represent feature switches as nested sections so dependencies are unambiguous:

```json
"early_stopping": {
  "enabled": false
}
```

When enabled:

```json
"early_stopping": {
  "enabled": true,
  "minimum_qualifying_iterations": 20,
  "comparison_window": 5,
  "minimum_jaccard_similarity": 0.98,
  "maximum_relative_size_change": 0.02,
  "required_consecutive_passes": 3
}
```

Apply the same pattern to dual cutoffs, stability tiers, biomarker filtering, holdout evaluation, freeze/model stages, and backend profiles. Disabled backends retain only `enabled: false`; ECDF includes only parameters relevant to `raw_gene` and configured covariates.

## Clarity and provenance
- Add derived explanatory fields where behavior is not obvious, such as ECDF `second_stage_active`, `include_covariates`, and `include_observed_hybrid`.
- Separate settings consumed by `mc_stability.program.json` from settings merely carried forward for later model training.
- Use canonical field names only; no legacy alternatives may appear in either resolved or effective snapshots.
- Document that the effective file is informational and source profiles/context remain the editable configuration.

## Verification
- Add strict tests proving every removed key is rejected and absent from `MonteCarloConfig.model_json_schema()`.
- Scan versioned profiles, programs, fixtures, docs, examples, and tests for removed names and legacy value aliases.
- Update all runtime consumers that currently read synchronized flat backend attributes.
- Test disabled and enabled forms for every conditional section.
- Test that the new canonical snapshot round-trips on the new release; do not assert compatibility with old snapshots.
- Test the current ECDF/covariate configuration: ten iterations, no early stopping, ECDF only, strict six-cell-type covariate join.
- Test planner/worker integration writes and consumes the new canonical snapshot and also writes the informational effective snapshot.
- Run focused methylvalidation/workflow/worker tests plus schema exporters and repository legacy-name checks.

## Documentation and traceability
- Mark the change as breaking: existing Monte Carlo runs remain tied to the release that created their snapshots.
- Document canonical replacements and the release boundary; do not promise transparent resume across the boundary.
- After approval, promote this plan to `docs/plans/effective-monte-carlo-config.plan.md`, add AB#413 Feature metadata, and update `docs/plans/README.md` as required by repository conventions.

## Database propagation (Azure SQL + PostgreSQL)

Repo JSON is not enough for distributed runs: operators also need published rows in `cfg.pipeline_profile` and seeded `wf.workflow_action` / `wf.workflow_action_schema`.

**Reusable sync (commit this with the feature):**

```bash
source .venv/bin/activate
# Azure SQL: AZURE_SQL_* (or DB_* from local mssql-mcp .env)
python scripts/sync_cfg_profiles_and_action_catalog.py --backend mssql
# PostgreSQL: POSTGRES_* (URL-encode @ in AAD usernames as %40)
python scripts/sync_cfg_profiles_and_action_catalog.py --backend postgres
```

### Sync log — 2026-07-16

| Target | Profiles | Catalog | Verification |
|--------|----------|---------|--------------|
| Azure SQL (`em-maindb`) | Upserted `staged_ovr_mc`, `staged_full_lifecycle` from repo (`stability_min_selected_dmps` → `stability_min_core_dmps`) | Seeded 46 actions / 92 schemas | No removed key; biomarker output has `empty_reason` |
| PostgreSQL (`epimethyl`) | Renamed legacy key on the same two profiles | Seeded 46 actions / 92 schemas | Same checks |

Old Monte Carlo `mc_config.json` snapshots remain bound to the release that wrote them; this sync only refreshes registry/catalog rows.