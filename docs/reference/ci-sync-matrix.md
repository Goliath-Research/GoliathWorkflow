# CI sync matrix (dev ↔ PR ↔ deploy)

Paired artifacts that must stay synchronized. If a source changes without its companion, a gate must fail **before** merge.

Local mirror of PR guards: [`scripts/ci_preflight.sh`](../../scripts/ci_preflight.sh). Plan: [`../plans/ci-dev-deploy-sync.plan.md`](../plans/ci-dev-deploy-sync.plan.md).

| Source | Companion | Gate | Pre-commit | PR CI |
|--------|-----------|------|:----------:|:-----:|
| `docs/diagrams/src/*.mmd` | `docs/diagrams/out/*.{svg,png,mmd.sha256}` | `scripts/render_diagrams.sh --check` | yes | yes |
| Active docs (`docs/**`, package READMEs, …) | No retired patterns (`step_config`, old profiles, …) | `scripts/check_doc_freshness.sh` | yes | yes |
| Doc internal links | Resolvable paths | `scripts/check_doc_links.sh` | yes | yes |
| `deploy/env/*.example` | Files exist; not ignored by root `env/` | freshness + install-contract | yes | yes |
| `packages/*/pyproject.toml` | Dist name ↔ path-dep keys; declared README exists | `scripts/check_package_install_contract.py` | yes | yes |
| `scripts/packages.list` | Topological order vs bare/path local deps | same | yes | yes |
| Foundational packages after `--with-deps` | Editable `methylutils` / `methyldomain` | `install_packages.sh` re-editable pass | n/a | yes |
| `schemas/actions/catalog.json` | `schemas/tasks/*` refs + golden I/O JSON | `scripts/check_catalog_fixture_contract.py` + pytest golden/catalog | yes | yes |
| Pydantic config / task / domain models | Committed JSON Schema under `schemas/` | `methyl-export-*-check` exporters | partial | yes |
| Study `project_*.json` | No `step_config` | `scripts/check_no_step_config.py` | yes | yes |
| `workflow_engine/rest/db/mssql.py` | `json.dumps` only inside `_json_text()` | `test_mssql_json_binding_policy` | no | yes (full suite) |
| DomainProgram / profiles | Compiler + composable program tests | pipeline profile tests | no | yes |

## How to use

```bash
# Before push — same cheap guards as PR (no full pytest)
./scripts/ci_preflight.sh

# Full regression mirror (coverage artifacts)
./scripts/run_tests_ci.sh
```

## Failure-mode cheat sheet

| Symptom | Likely sync break |
|---------|-------------------|
| `FAIL: missing deploy/env/*.example` | Gitignore / untracked env templates |
| `STALE: docs/diagrams/out/...` | Hash sidecar or render out of date — run `scripts/render_diagrams.sh` |
| `inconsistent name: expected '…'` (pip) | Path-dep key ≠ distribution `name` |
| `No matching distribution found for omics_features` | `packages.list` order (bare PEP 621 local dep) |
| `Readme path … does not exist` | Missing package README |
| `missing golden input/output` | Catalog action without fixtures — update `golden_fixtures_data.py` + generate |
| `missing schema artifact` under `.venv/lib/schemas` | Non-editable install broke path walk — re-editable foundations / `METHYL_REPO_ROOT` |
