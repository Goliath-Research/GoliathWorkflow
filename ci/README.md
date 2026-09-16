# MethylPipeline CI

All CI is **GitHub Actions** under [`.github/workflows/`](../.github/workflows/).

## Workflows (this repo)

| Workflow | Trigger |
|----------|---------|
| [`.github/workflows/pr.yml`](../.github/workflows/pr.yml) | Pull requests — sync contracts, MkDocs, packaging smoke, full pytest + coverage, spine ratchet |
| [`.github/workflows/release.yml`](../.github/workflows/release.yml) | Tags `v*` — wheels to **pypi-goliath** (GitHub Packages) + `methyl-pipeline-release-*.tar.gz` GitHub Release asset |
| [`.github/workflows/release-assemble.yml`](../.github/workflows/release-assemble.yml) | Manual — GitHub Release `goliathomics-<version>` |
| [`.github/workflows/release-deploy.yml`](../.github/workflows/release-deploy.yml) | Manual + Environment `production-work` (self-hosted `production-work-agents`) |
| [`.github/workflows/db-parity.yml`](../.github/workflows/db-parity.yml) | Path-filtered push/PR |
| [`.github/workflows/real-data.yml`](../.github/workflows/real-data.yml) | Manual / weekly (`production-work-agents`, `/work` mounted) |
| [`.github/workflows/smoke.yml`](../.github/workflows/smoke.yml) | Nightly + manual (`production-work-agents`) |
| [`.github/workflows/sample-prep-canary.yml`](../.github/workflows/sample-prep-canary.yml) | Manual + monthly subset (`production-work-agents`, real GPU) |
| [`.github/workflows/methylgrapher-image.yml`](../.github/workflows/methylgrapher-image.yml) | Manual / path filter on `workers/docker/methylgrapher/**` — **image build only**, not deploy |

MethylExtractor: [`.github/workflows/build.yml`](https://github.com/Goliath-Research/MethylExtractor/blob/main/.github/workflows/build.yml) (PR) and [`.github/workflows/release.yml`](https://github.com/Goliath-Research/MethylExtractor/blob/main/.github/workflows/release.yml) (tags `v*`).

## Regression and coverage gate (PR)

`.github/workflows/pr.yml` runs **sync contracts** then the **full pytest suite** as a
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

The PR workflow builds a `.venv`, installs editable packages with
dependencies (`scripts/install_packages.sh --with-deps`, including a foundational
re-editable pass for `methylutils` / `methyldomain`), then runs
[`../scripts/run_tests_ci.sh`](../scripts/run_tests_ci.sh), which emits:

- `test-results/junit.xml` — uploaded as a workflow artifact (a failing test fails the PR)
- `coverage/coverage.xml` and `coverage/html/` — uploaded as artifacts

GPU tests are deselected (`-m "not gpu"`); database and `/work`-fixture tests
self-skip on the hosted runner. Coverage is **measure-and-report only**: there is
no `--cov-fail-under` gate yet. The baseline is recorded so the threshold can be
ratcheted up over time. Policy and rationale live in
[`../docs/regulatory/continuous-integration-and-regression-testing.md`](../docs/regulatory/continuous-integration-and-regression-testing.md).

### Spine coverage ratchet (branch, `fail_under`)

The global suite stays measure-and-report, but the PR workflow additionally runs
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

`.github/workflows/real-data.yml` runs the `@pytest.mark.real_data` tests against
designated **real** reference samples (per-analyte samples plus named groups such
as `healthy`/`PCa`) on the self-hosted `production-work-agents` runner, which mounts
`/work`. Hosted PR runners do not mount `/work`, so these tests self-skip there;
they only execute where a real sample is declared via the site manifest `testing`
block or `METHYL_TEST_DATA_CONFIG`. See
[`../docs/reference/test-data-registry.md`](../docs/reference/test-data-registry.md).

## SamplePrep real-data canary (self-hosted GPU)

`.github/workflows/sample-prep-canary.yml` runs one pinned public WGBS sample
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

## One-time setup

1. **Packages:** GitHub Packages Python index **pypi-goliath** (`https://pypi.pkg.github.com/Goliath-Research/simple/`). MethylExtractor tarballs are **GitHub Release** assets.
2. **Environment:** GitHub Environment `production-work` with required reviewers (deploy workflow).
3. **Runner labels:** `production-work-agents` (self-hosted, `/work/goliath` mounted).
4. **Secrets (optional):** NGC creds if deploy uses `pullParabricks: true`.
5. **SemVer tags only:** `v2026.6.1` (not `v2026.06.1`).

## Release flow

1. Tag MethylExtractor `v2026.5.2` → MethylExtractor **release** workflow (both arches).
2. Tag MethylPipeline `v2026.6.1` → **MethylPipeline release** (this repo).
3. Run **release-assemble** (`workflow_dispatch`) with version pins.
4. Approve **release-deploy**.

See [`docs/deployment/production_release.md`](../docs/deployment/production_release.md).
