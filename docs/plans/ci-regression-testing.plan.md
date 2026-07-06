---
name: CI Regression Testing
overview: Add a Continuous Integration regression + coverage stage to the Azure DevOps PR pipeline (measure-and-report first, no failing threshold), fix the coverage/testpaths gaps in the root pytest config, author missing tests so every used package covers its most important classes/features, and document CI/regression testing as a first-class regulatory control alongside Traceability, Validation, Deployment, and Change Management.
todos:
  - id: pytest-config
    content: "Fix root pyproject.toml: drop unconditional --cov-report from addopts, broaden testpaths (scripts/tests + nested package tests), and expand coverage source to packages/workers/workflow_engine."
    status: completed
  - id: ci-script
    content: Add scripts/run_tests_ci.sh emitting JUnit XML + Cobertura coverage XML, running with -m 'not gpu' and no --cov-fail-under.
    status: completed
  - id: test-gap-analysis
    content: Rank packages/classes by import frequency across the repo and produce a prioritized per-package list of the most-used untested classes/features to cover.
    status: completed
  - id: author-missing-tests
    content: Author unit tests for the highest-priority untested classes/features per used package, starting with zero-test (methylcluster, methylgenefeatureselect) and thin packages (methylderivedmeasures, methylfragmentomics, methylgeneselect, methyldiseaseprogression, methyldomain).
    status: completed
  - id: azure-pipeline
    content: Extend ci/azure-pipelines-pr.yml with a full-suite regression + coverage step and PublishTestResults@2 / PublishCodeCoverageResults@2.
    status: completed
  - id: ci-readme
    content: Update ci/README.md to describe the regression + coverage stage and baseline-only policy.
    status: completed
  - id: regulatory-doc
    content: Author docs/regulatory/continuous-integration-and-regression-testing.md as a new regulatory pillar.
    status: completed
  - id: regulatory-wiring
    content: Wire the new doc into docs/regulatory/README.md, change-management-plan.md, traceability-matrix.md, and validation-evidence-index.md.
    status: completed
  - id: verify
    content: Run scripts/run_tests_ci.sh in .venv to confirm full collection and artifact generation with no import collisions or new failures.
    status: completed
---

# Continuous Integration and Regression Testing

> **Status: implemented.** Functional CI regression + coverage stage, root
> pytest/coverage config fixes, new package tests, and the regulatory control
> document are in place. Pre-existing test failures surfaced by broadening
> collection are recorded as follow-ups for their code/fixture owners.

Add automated regression testing (run the whole suite on every change) plus
coverage measurement, wired into CI, and give it a regulatory-facing document so
it stands beside Traceability / Validation / Deployment / Change Management.

Decisions (confirmed): host on **Azure DevOps** (extend
`ci/azure-pipelines-pr.yml`); coverage is **measure-and-report only** at first
(record a baseline, no build-failing threshold yet).

## Functional changes

1. **Root pytest + coverage config** ([`../../pyproject.toml`](../../pyproject.toml)):
   removed the unconditional `--cov-report=*` from `addopts` (so subset/local runs
   do not require pytest-cov), broadened `testpaths` to include `scripts/tests` and
   the nested `packages/methylcentroid/methyl_centroid/tests` and
   `packages/methylutils/methyl_utils/tests` dirs, and expanded
   `[tool.coverage.run] source` to `packages/`, `workers/`, `workflow_engine/`.
   Verified there are no duplicate test basenames after adding new tests, so the
   default (prepend) import mode collects the whole tree cleanly.
2. **CI test runner** ([`../../scripts/run_tests_ci.sh`](../../scripts/run_tests_ci.sh)):
   runs the full suite with `-m "not gpu"`, emitting `test-results/junit.xml`,
   `coverage/coverage.xml`, and `coverage/html/`; no `--cov-fail-under`.
3. **Azure PR pipeline** ([`../../ci/azure-pipelines-pr.yml`](../../ci/azure-pipelines-pr.yml)):
   added a venv build (editable packages + deps), a full regression step, and
   `PublishTestResults@2` / `PublishCodeCoverageResults@2`.
4. **CI README** ([`../../ci/README.md`](../../ci/README.md)): documents the
   regression + coverage stage and baseline-only policy.

## Filling test gaps (frequently-used classes)

Ranked packages by import breadth across the repo and prioritized the
zero-test and thin packages. New suites added:

| Package | Prior state | New tests |
|---------|-------------|-----------|
| `methylcluster` | no tests | `test_cluster_config.py`, `test_utils.py` |
| `methylgenefeatureselect` | no tests | `test_gene_feature_runner.py` |
| `methyldomain` | thin (22 import breadth) | `test_helpers.py` |
| `methylgeneselect` | thin (7 import breadth) | `test_caps.py` |
| `methyldiseaseprogression` | thin | `test_gene_set_coverage.py` |
| `methylderivedmeasures` | thin | `test_genome_measures_stats.py` |
| `methylfragmentomics` | thin | `test_fragmentomics_summaries.py` |

New tests assert behavior/contracts and follow `config-not-code` (missing tunable
caps resolve to unset, not invented defaults).

## Regulatory documentation changes

- New pillar: [`../regulatory/continuous-integration-and-regression-testing.md`](../regulatory/continuous-integration-and-regression-testing.md).
- Wired into [`../regulatory/README.md`](../regulatory/README.md),
  [`../regulatory/change-management-plan.md`](../regulatory/change-management-plan.md),
  [`../regulatory/traceability-matrix.md`](../regulatory/traceability-matrix.md), and
  [`../regulatory/validation-evidence-index.md`](../regulatory/validation-evidence-index.md).

## Verification results

- Full CI run via `scripts/run_tests_ci.sh`: 1272 passed, 2 skipped, 16 failed;
  total coverage 59%; artifacts written.
- All 58 newly authored tests pass.
- The 16 failures are pre-existing and not caused by this work: 12 fail under the
  old `testpaths` too (methylvalidation schema-export/tabular-backend drift and 8
  missing worker golden fixtures that need `scripts/generate_golden_fixtures.py`);
  4 more are in dirs that were previously never collected (methylcentroid CLI stale
  mock, methylutils ECDF statistical assertion, scripts `parse_chromosome_list`
  case-normalization). Broadening collection surfaced them rather than hiding them.

## Out of scope

- No hard coverage threshold / build-failing gate (deferred until a baseline exists).
- Not exhaustive 100% coverage: the aim is the most-used classes/features per package.
- No changes to the release/assemble/deploy pipelines.
- Fixing the pre-existing failures above (owned by the respective code/fixtures).
