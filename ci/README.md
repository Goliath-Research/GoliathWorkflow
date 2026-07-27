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
| [`azure-pipelines-smoke.yml`](azure-pipelines-smoke.yml) | MethylPipeline-Distributed-Smoke | Nightly + manual (`production-work-agents`) |
| [`azure-pipelines-sample-prep-canary.yml`](azure-pipelines-sample-prep-canary.yml) | MethylPipeline-SamplePrep-Canary | Manual + monthly subset (`production-work-agents`, real GPU) |
| [`azure-pipelines-methylgrapher-image.yml`](azure-pipelines-methylgrapher-image.yml) | MethylPipeline-MethylGrapher-Image | Manual / path filter on `workers/docker/methylgrapher/**` (`build-arm64`) — **image build only**, not deploy |

## Regression and coverage gate (PR pipeline)

`azure-pipelines-pr.yml` runs **sync contracts** then the **full pytest suite** as a
regression gate on every pull request. Sync contracts catch the deployment
whack-a-mole class of failures (package install metadata, catalog/golden drift,
docs/diagrams) before the long suite.

### Local commands (mirror CI)

```bash
# Cheap sync guards — same scripts as PR (run before push)
./scripts/ci_preflight.sh

# Full regression + coverage artifacts (hosted PR suite)
./scripts/run_tests_ci.sh

# Narrow spine coverage ratchet
./scripts/run_spine_coverage_ratchet.sh
```

Contract map: [`../docs/reference/ci-sync-matrix.md`](../docs/reference/ci-sync-matrix.md).
Plan: [`../docs/plans/ci-dev-deploy-sync.plan.md`](../docs/plans/ci-dev-deploy-sync.plan.md).

`azure-pipelines-pr.yml` builds a `.venv`, installs editable packages with
dependencies (`scripts/install_packages.sh --with-deps`, including a foundational
re-editable pass for `methylutils` / `methyldomain`), then runs
[`../scripts/run_tests_ci.sh`](../scripts/run_tests_ci.sh), which emits:

- `test-results/junit.xml` — published via `PublishTestResults@2` (a failing test fails the PR),
- `coverage/coverage.xml` — published via `PublishCodeCoverageResults@2` (Cobertura),
- `coverage/html/` — browsable HTML report.

GPU tests are deselected (`-m "not gpu"`); database and `/work`-fixture tests
self-skip on the hosted agent. Coverage is **measure-and-report only**: there is
no `--cov-fail-under` gate yet. The baseline is recorded so the threshold can be
ratcheted up over time. Policy and rationale live in
[`../docs/regulatory/continuous-integration-and-regression-testing.md`](../docs/regulatory/continuous-integration-and-regression-testing.md).

### Spine coverage ratchet (branch, `fail_under`)

The global suite stays measure-and-report, but the PR pipeline additionally runs
[`../scripts/run_spine_coverage_ratchet.sh`](../scripts/run_spine_coverage_ratchet.sh),
a **narrow, branch-aware gate** on the shared config-resolution "spine"
(`methyl_utils/action_config_resolver.py`, `methyl_utils/cli_resolved_config.py`,
`methyl_domain/action_result.py`). These modules sit upstream of every typed
action, so a regression is high-blast-radius yet invisible to the Pydantic
boundary (values stay type-valid but wrong). Config is in
[`coveragerc-spine`](coveragerc-spine) with `branch = True` and a real
`fail_under` on just these files, so the GPU-depressed global number does not
force a meaningless whole-repo threshold. Run it locally with
`./scripts/run_spine_coverage_ratchet.sh`.

## Real reference-sample tests (self-hosted)

`azure-pipelines-real-data.yml` runs the `@pytest.mark.real_data` tests against
designated **real** reference samples (per-analyte samples plus named groups such
as `healthy`/`PCa`) on the self-hosted `production-work-agents` pool, which mounts
`/work`. Hosted PR agents do not mount `/work`, so these tests self-skip there;
they only execute where a real sample is declared via the site manifest `testing`
block or `METHYL_TEST_DATA_CONFIG`. See
[`../docs/reference/test-data-registry.md`](../docs/reference/test-data-registry.md).

## SamplePrep real-data canary (self-hosted GPU)

`azure-pipelines-sample-prep-canary.yml` runs one pinned public WGBS sample
(`GSE261315` / `SRR28293403`) through SamplePrep for `linear`, stock `pangenome`
(engineering comparator), and `pangenome_wgbs` (methylGrapher). Default tier is
the deterministic **subset**; pass `tier=full` for periodic qualification.
Requires provisioned FASTQs in `fastqStorage`, `WORKER_STUB_EXTERNAL` unset, and
site `testing.sample_prep_canary` (or `METHYL_SAMPLE_PREP_CANARY_CONFIG`).

```bash
# Local / operator
bash scripts/provision_sample_prep_canary.sh --subset-pairs 2000000
scripts/sync_genomes_to_s3.sh --only pangenome/canary
unset WORKER_STUB_EXTERNAL
bash scripts/smoke_sample_prep_real.sh --tier subset
```

Docs: [`../workflow_engine/docs/sample_prep_test_bed.md`](../workflow_engine/docs/sample_prep_test_bed.md),
[`../workers/tests/test_methylgrapher_wgbs_canary.md`](../workers/tests/test_methylgrapher_wgbs_canary.md).

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

## GitHub Actions (supplementary)

The root [`.github/workflows/db-parity.yml`](../.github/workflows/db-parity.yml) runs PostgreSQL parity and worker schema drift on path-filtered changes. **Full regression remains on Azure DevOps** (`MethylPipeline-PR`). Configure branch policies to require the ADO build on merge, or add a mirror workflow if GitHub-only forks must gate without ADO.
