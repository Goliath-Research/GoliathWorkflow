# Agent guide (MethylPipeline)

Principles for AI agents and contributors working in this repository.

## Disease-agnostic, deployment-configurable

MethylPipeline is **not** tied to one disease or study. Cohorts and paths live on `/work/projects/<study>/`; pipeline structure and profiles live in the **git repo** (or the promoted **runtime-bundle** on `/work/epimethyl/current/`). Do not hard-code study names, paths, or operational science parameters in Python.

## Database backends (operator)

| Backend | Typical use | Populate reference data |
|---------|-------------|-------------------------|
| Azure SQL | Production gateway, portal | Already populated; refresh catalog via `seed_action_catalog.py` or MCP |
| PostgreSQL | Parity, dev gateway, CI | Schema via `sql_pg/deploy_azure.sh`; **data** via [`scripts/populate_postgres_reference_data.py`](scripts/populate_postgres_reference_data.py) |

When assisting with DB tasks:

1. **Azure SQL** — use Cursor MCP `user-azure-sql-dev` (`mcp_SQL_execute_query`, `mcp_SQL_discover_tables`) for inspection and surgical SQL when available.
2. **PostgreSQL** — use PostgreSQL MCP (`pgsql_query`) when `pgsql_list_connection_profiles` returns profiles; otherwise require `POSTGRES_*` env and `psql` / `populate_postgres_reference_data.py`.
3. **Catalog source of truth** — git (`schemas/actions/catalog.json` + `seed_action_catalog.py`), not necessarily production MSSQL rows (may include retired actions like `sample.upload_h5`).
4. **Shell bootstrap** — `scripts/bootstrap_distributed_workers.sh` for full DDL + seed + workflow deploy; use MCP for verification and incremental fixes.

## Four-layer configuration

| Layer | Artifact | Docs |
|-------|----------|------|
| Study manifest | `/work/projects/<study>/configs/project_*.json` | [Project config (usage)](docs/usage/02-project-config-and-layout.qmd) |
| Pipeline profile | `workflow_engine/domain/profiles/*.profile.json` | [Domain program language](docs/reference/domain-program-language.md) |
| Site manifest | `/work/site/methyl_site.json` (`METHYL_SITE_CONFIG`) | [Layer model](docs/architecture/layer-model.md) |
| DomainProgram | `workflow_engine/domain/**/*.program.json` | [Layer model](docs/architecture/layer-model.md) |

**Precedence (highest wins):** program/instance override → profile `actionConfig` → analyte defaults → site `actionConfig` → *(no Python fallback for tunable science knobs)*.

Study manifests must **not** contain `step_config` or tool parameters. See [config parameter matrix](docs/reference/config-parameter-matrix.md).

## Config not code

**Cursor rule:** [`.cursor/rules/config-not-code.mdc`](.cursor/rules/config-not-code.mdc) (`alwaysApply`).

- Do **not** add `DEFAULT_*` constants or Pydantic `Field(default=…)` for tunable operational parameters (caps, thresholds, iteration counts meant for operators).
- Code **resolves** merged config (`resolve_action_config`, `resolve_for_project`, `materialize_action_input`) and **validates** types/bounds only.
- New tunable knobs: JSON schema + site/profile examples — not package defaults.

**Repo vs `/work`:** [`.cursor/rules/work-config-paths.mdc`](.cursor/rules/work-config-paths.mdc).

## Database workflows

Gateway instances store enriched `context_json` (`projectPath`, `pipelineProfile`, merged `actionConfig`) in `wf.workflow_instance`. Workers consume `resolvedConfig` on tasks; MC runs snapshot resolved validation config to `monte_carlo_runs/queue/mc_config.json`. Operators view and override parameters at the **instance** and **profile** layers, not by changing code.

## Runtime environment

- Use the repo virtualenv: `source .venv/bin/activate` before `python`, `pytest`, or `methyl-*` CLIs.
- Production workers use `/work/epimethyl/current/runtime-bundle/` for profiles and programs, not a git checkout.

## Example: gene FeatureCuts caps

Set at **site** (deployment-wide) and/or **profile** (procedure pack):

```json
"actionConfig": {
  "validation": {
    "stability_gene_featurecuts_max_dmps": 1000,
    "stability_gene_featurecuts_max_genes": 200
  },
  "gene_selection": {
    "max_dmps": 1000,
    "max_genes": 200
  }
}
```

Resolution: `packages/methylgeneselect/methyl_gene_select/caps.py` (no hardcoded fallbacks).
