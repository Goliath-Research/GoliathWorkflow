# MethylPipeline Azure DevOps pipelines

Each YAML lives in **this repository** so Azure DevOps can point pipelines at local paths.

## MethylPipeline repo (this repo)

| YAML | Suggested pipeline name | Trigger |
|------|-------------------------|---------|
| [`azure-pipelines-pr.yml`](azure-pipelines-pr.yml) | MethylPipeline-PR | Pull requests |
| [`azure-pipelines-release.yml`](azure-pipelines-release.yml) | MethylPipeline-Release | Tags `v*` |
| [`azure-pipelines-release-assemble.yml`](azure-pipelines-release-assemble.yml) | Epimethyl-Release-Assemble | Manual |
| [`azure-pipelines-release-deploy.yml`](azure-pipelines-release-deploy.yml) | Epimethyl-Release-Deploy | Manual (+ approval) |

## MethylExtractor repo (separate)

MethylExtractor pipelines are in **MethylExtractor** → `ci/` ([`azure-pipelines-release.yml`](https://dev.azure.com/EpiMethyl/Development/_git/MethylExtractor?path=/ci)).

## Register a pipeline in Azure DevOps

1. **Pipelines** → **New pipeline** → select the **repository** (MethylPipeline or MethylExtractor).
2. **Existing Azure Pipelines YAML file**.
3. Branch: `main` (or your default).
4. Path: e.g. `/ci/azure-pipelines-release.yml`.
5. Save; rename pipeline to match the suggested name above.

Pipeline **definition names** must match assemble/deploy parameters (`methylPipelinePipelineName`, `assemblePipelineName`).

## One-time setup

1. **Feeds:** `methyl-extractor` (Universal), `pypi-epimethyl` (Python) — build service **Contributor** on both.
2. **Environment:** `production-work` with approvers (deploy pipeline).
3. **Agent pool:** `production-work-agents` (self-hosted, `/work/epimethyl` mounted).
4. **Variable group (optional):** NGC creds if deploy uses `pullParabricks: true`.
5. **SemVer tags only:** `v2026.6.1` (not `v2026.06.1`).

## Release flow

1. Tag MethylExtractor `v2026.5.2` → **MethylExtractor-Release** (ME repo pipeline).
2. Tag MethylPipeline `v2026.6.1` → **MethylPipeline-Release** (this repo).
3. Run **Epimethyl-Release-Assemble** (this repo) with version pins.
4. Approve **Epimethyl-Release-Deploy** (this repo).

See [`docs/deployment/production_release.md`](../docs/deployment/production_release.md).
