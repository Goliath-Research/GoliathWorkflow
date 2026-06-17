# Azure DevOps CI/CD pipelines

Register these pipelines in the **Development** project (EpiMethyl org).

## MethylPipeline repo

| YAML | ADO pipeline name (suggested) | Trigger |
|------|-------------------------------|---------|
| [`azure-pipelines-pr.yml`](azure-pipelines-pr.yml) | MethylPipeline-PR | Pull requests |
| [`azure-pipelines-methyl-pipeline-release.yml`](azure-pipelines-methyl-pipeline-release.yml) | MethylPipeline-Release | Tags `v*` |
| [`azure-pipelines-release-assemble.yml`](azure-pipelines-release-assemble.yml) | Epimethyl-Release-Assemble | Manual |
| [`azure-pipelines-release-deploy.yml`](azure-pipelines-release-deploy.yml) | Epimethyl-Release-Deploy | Manual (+ optional assemble trigger) |

## MethylExtractor repo

Copy or reference from MethylPipeline `ci/`:

| YAML | ADO pipeline name (suggested) | Trigger |
|------|-------------------------------|---------|
| [`azure-pipelines-methyl-extractor-pr.yml`](azure-pipelines-methyl-extractor-pr.yml) | MethylExtractor-PR | Pull requests |
| [`azure-pipelines-methyl-extractor-release.yml`](azure-pipelines-methyl-extractor-release.yml) | MethylExtractor-Release | Tags `v*` |

The MethylExtractor release pipeline checks out **MethylPipeline** for `package_methyl_extractor.sh`.

## One-time Azure DevOps setup

1. **Feeds:** `methyl-extractor` (Universal), `pypi-epimethyl` (Python) — grant build service Contributor.
2. **Environments:** `production-work` with required approvers.
3. **Agent pool:** `production-work-agents` — self-hosted agent with `/work/epimethyl` mounted.
4. **Variable group (optional):** NGC credentials for Parabricks pull during deploy.
5. **Pipeline names** must match parameters in assemble/deploy YAML (`methylPipelinePipelineName`, `assemblePipelineName`).

## Release flow

1. Tag `v2026.5.2` on MethylExtractor → **MethylExtractor-Release** publishes Universal Packages.
2. Tag `v2026.6.1` on MethylPipeline → **MethylPipeline-Release** publishes wheels + `methyl-pipeline-release-2026.6.1` artifact.
3. Run **Epimethyl-Release-Assemble** with `releaseVersion=2026.6.1`, `methylPipelineVersion=2026.6.1`, `methylExtractorVersion=2026.5.2`.
4. Approve **Epimethyl-Release-Deploy** with `releaseVersion=2026.6.1`.

See [`docs/deployment/production_release.md`](../docs/deployment/production_release.md) for operational detail.
