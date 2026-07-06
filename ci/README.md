# MethylPipeline Azure DevOps pipelines

Each YAML lives in **this repository** so Azure DevOps can point pipelines at local paths.

## MethylPipeline repo (this repo)

| YAML | Suggested pipeline name | Trigger |
|------|-------------------------|---------|
| [`azure-pipelines-pr.yml`](azure-pipelines-pr.yml) | MethylPipeline-PR | Pull requests |
| [`azure-pipelines-release.yml`](azure-pipelines-release.yml) | MethylPipeline-Release | Tags `v*` |
| [`azure-pipelines-release-assemble.yml`](azure-pipelines-release-assemble.yml) | Epimethyl-Release-Assemble | Manual |
| [`azure-pipelines-release-deploy.yml`](azure-pipelines-release-deploy.yml) | Epimethyl-Release-Deploy | Manual (+ approval) |
| [`azure-pipelines-real-data.yml`](azure-pipelines-real-data.yml) | MethylPipeline-RealData | Manual / scheduled (self-hosted) |

## Regression and coverage gate (PR pipeline)

`azure-pipelines-pr.yml` runs the **full pytest suite** as a regression gate on
every pull request, in addition to the doc/diagram/packaging guards. It builds a
`.venv`, installs the editable packages with dependencies
(`scripts/install_packages.sh --with-deps`), then runs
[`../scripts/run_tests_ci.sh`](../scripts/run_tests_ci.sh), which emits:

- `test-results/junit.xml` — published via `PublishTestResults@2` (a failing test fails the PR),
- `coverage/coverage.xml` — published via `PublishCodeCoverageResults@2` (Cobertura),
- `coverage/html/` — browsable HTML report.

GPU tests are deselected (`-m "not gpu"`); database and `/work`-fixture tests
self-skip on the hosted agent. Coverage is **measure-and-report only**: there is
no `--cov-fail-under` gate yet. The baseline is recorded so the threshold can be
ratcheted up over time. Policy and rationale live in
[`../docs/regulatory/continuous-integration-and-regression-testing.md`](../docs/regulatory/continuous-integration-and-regression-testing.md).

Run the same suite locally with `./scripts/run_tests_ci.sh` (or `./scripts/run_tests.sh`
for a plain run without coverage artifacts).

## Real reference-sample tests (self-hosted)

`azure-pipelines-real-data.yml` runs the `@pytest.mark.real_data` tests against
designated **real** reference samples (per-analyte samples plus named groups such
as `healthy`/`PCa`) on the self-hosted `production-work-agents` pool, which mounts
`/work`. Hosted PR agents do not mount `/work`, so these tests self-skip there;
they only execute where a real sample is declared via the site manifest `testing`
block or `METHYL_TEST_DATA_CONFIG`. See
[`../docs/reference/test-data-registry.md`](../docs/reference/test-data-registry.md).

## MethylExtractor repo (separate)

MethylExtractor pipelines are in **MethylExtractor** → `ci/` (`azure-pipelines-release-arm64.yml`, `azure-pipelines-release-x64.yml`, `azure-pipelines-pr.yml`).

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

1. Tag MethylExtractor `v2026.5.2` → **MethylExtractor-Release-ARM64** and **MethylExtractor-Release-x64** (ME repo).
2. Tag MethylPipeline `v2026.6.1` → **MethylPipeline-Release** (this repo).
3. Run **Epimethyl-Release-Assemble** (this repo) with version pins.
4. Approve **Epimethyl-Release-Deploy** (this repo).

See [`docs/deployment/production_release.md`](../docs/deployment/production_release.md).
