# Implementation plans (Azure DevOps traceability)

Plans in this folder are the **source of truth** for large features. Each plan maps to Azure DevOps work items.

**Cursor Plan Mode:** When you finish planning in Cursor, copy the plan here (kebab-case filename, e.g. `my-feature.plan.md`). Do not rely on `~/.cursor/plans/` or `.cursor/plans/` alone — those are not committed unless promoted to this folder. See [`.cursor/rules/plan-mode-docs-plans.mdc`](../../.cursor/rules/plan-mode-docs-plans.mdc).

## Work item mapping

| Plan file | ADO type | Suggested title | Child tasks (from plan frontmatter) |
|-----------|----------|-----------------|-------------------------------------|
| [`production-gpu-worker-layout.plan.md`](production-gpu-worker-layout.plan.md) | **Epic** | Production GPU worker layout | `define-layout`, `extractor-ci`, `pipeline-ci`, `install-release`, `gpu-node-runbook`, `docker-shared`, `worker-provision` |
| [`devops-ci-cd-release.plan.md`](devops-ci-cd-release.plan.md) | **Epic** | DevOps CI/CD release pipeline | `me-release-ci`, `mp-release-ci`, `assemble-script`, `assemble-pipeline`, `deploy-pipeline`, `docs-ci-cd` |
| [`alignment-qc-screening.plan.md`](alignment-qc-screening.plan.md) | **Epic** | Alignment QC screening and remediation | `screening-core`, `guardrail-enhance`, `cohort-report`, `trim-action`, `workflow-remediation`, `validate-docs` |
| [`composable-pipeline-flexibility.plan.md`](composable-pipeline-flexibility.plan.md) | **Epic** | Composable pipeline profiles and MC paths | `profiles-config`, `scope-if-fix`, `programs-gene-enricher`, `programs-composable`, `validation-alignment`, `tests-docs`, `phase2-structural` |
| [`typed-action-observability.plan.md`](typed-action-observability.plan.md) | **Epic** | Typed worker action observability | `infra-action-result`, `runner-result-code`, `cli-manifest-dmp-detector-mapper`, `strict-pipeline-schemas`, `validation-typed-outputs`, `sample-prep-result-codes`, `docs-observability` |
| [`finish-typed-follow-ups.plan.md`](finish-typed-follow-ups.plan.md) | **Task** | CLI manifests + typed in-process handlers | `deps-methyl-domain`, `detector-manifest`, `centroid-manifest`, `enricher-manifest-collector`, `handlers-sample-prep`, `handlers-validation`, `inprocess-strict`, `tests-manifest-collectors` |
| [`optional-observability-follow-ups.plan.md`](optional-observability-follow-ups.plan.md) | **Task** | Observability follow-ups (golden fixtures, CI, MC log) | `doc-result-code-dpl`, `golden-fixtures-test`, `ci-worker-tests`, `mc-action-run-log`, `handler-input-model` |
| [`gene-feature-effect-size.plan.md`](gene-feature-effect-size.plan.md) | **Epic** | Biology-weighted gene/feature importance | `biology-weight-matrix`, `remove-legacy-mapper`, `canonical-gene-feature-formulas`, `fix-downstream-consumers`, `doc-biological-model` |
| [`simplify-study-config.plan.md`](simplify-study-config.plan.md) | **Epic** | Simplify study config (four-layer model) | `contract-docs`, `site-resolver`, `profiles-progression`, `materialize-input`, `purge-step-config`, `migrate-manifests`, `editor-manual` |
| [`streamline-action-parameters.plan.md`](streamline-action-parameters.plan.md) | **Epic** | Streamline workflow action parameters | `contract-audit-ci`, `canonical-config-keys`, `retire-mc-sidecars`, `slim-sample-prep-inputs`, `slim-pipeline-inputs`, `slim-validation-inputs`, `slim-implementations`, `docs-promote-plan` |
| [`parallel-mc-centroid-seed.plan.md`](parallel-mc-centroid-seed.plan.md) | **Epic** | Parallel MC centroid seed | `typed-models`, `planner-models`, `handler-output`, `centroid-worker`, `domain-programs`, `schema-export`, `tests`, `db-catalog-seed`, `db-workflow-deploy`, `docs-plan-promote` |
| [`docs-refresh-and-guardrails.plan.md`](docs-refresh-and-guardrails.plan.md) | **Epic** | Documentation refresh and CI guardrails | `audit-report`, `fix-precedence`, … |
| [`documentation-and-deployment-reliability.plan.md`](documentation-and-deployment-reliability.plan.md) | **Epic** | Documentation and deployment reliability | `canonical-map`, `setup-reliability`, `domain-program-guide`, `engine-reference`, `operational-contracts`, `stale-cleanup`, `docs-guardrails` |
| [`typed-assign-domain-program.plan.md`](typed-assign-domain-program.plan.md) | **Epic** | Typed assign DomainProgram language | `lang-doc-v2`, `ir-schema`, `compiler-control-assign`, `compute-actions`, `fixtures-tests`, `docs-align` |
| [`samd-study-profile-ladder.plan.md`](samd-study-profile-ladder.plan.md) | **Epic** | SaMD study profile ladder | `sop-doc`, `samd-profiles`, `study-scaffold`, `presets-cli-docs`, `examples-evidence`, `promote-plan` |
| [`samd-follow-on-assign-evidence-modes.plan.md`](samd-follow-on-assign-evidence-modes.plan.md) | **Epic** | SaMD follow-on (assign → evidence → fold mc_*) | `phase-a-sampleprep-assign`, `phase-b-evidence-packages`, `phase-c-fold-mc-modes`, `promote-follow-on-plan` |
| [`samd-deploy-buffy-research-migrate.plan.md`](samd-deploy-buffy-research-migrate.plan.md) | **Epic** | SaMD deploy + generic programs + Buffy research migrate | `depersonalize-all-programs`, `publish-db-graphs`, `sync-runtime-bundle-samd`, `fix-mode-path-resolution`, `migrate-buffy-research`, `promote-plan-docs` |
| [`agnostic-gateway-and-boundaries.plan.md`](agnostic-gateway-and-boundaries.plan.md) | **Epic** | Agnostic gateway and documented boundaries | `resolve-at-config`, `gateway-claim-clean`, `gateway-catalog-clean`, `move-lifecycle-out`, `repoint-callers`, `docs-boundaries`, `promote-plan`, `verify` |
| [`action-provider-registry.plan.md`](action-provider-registry.plan.md) | **Task** | Action provider registry (process pack) | `phase1-registry`, `phase2-compiler`, `docs` |
| [`read-level-info-measures.plan.md`](read-level-info-measures.plan.md) | **Epic** | Read-level information-theoretic measures | `contract-loader`, `extractor-flags`, `package-core`, `outputs`, `action-registration`, `covariate-list`, `config-program-wiring`, `regen-seed`, `tests`, `plan-promotion` |
| [`ci-regression-testing.plan.md`](ci-regression-testing.plan.md) | **Epic** | CI regression testing and coverage | `pytest-config`, `ci-script`, `test-gap-analysis`, `author-missing-tests`, `azure-pipeline`, `ci-readme`, `regulatory-doc`, `regulatory-wiring`, `verify` |
| [`regression-protection-test-coverage.plan.md`](regression-protection-test-coverage.plan.md) | **Epic** | Regression-protection test coverage | `p1-resolver-merge`, `p1-workflow-merge`, `p2-task-schema-drift-pytest`, `p3-cli-resolved-config`, `p4-action-result`, `p5-resolver-model-handshake`, `p6-ratchet-scope` |
| [`hyperparameter-result-versioning.plan.md`](hyperparameter-result-versioning.plan.md) | **Epic** | Hyperparameter result versioning (CAAS) | `record-schema`, `content-store`, `content-key`, `skip-reuse`, `execute-orchestrate`, `hpset-id`, `tests`, `docs` |
| [`workflow-engine-sql-design.plan.md`](workflow-engine-sql-design.plan.md) | **Epic** | Workflow engine SQL design | (see plan frontmatter) |
| [`alignment-derived-guardrails.plan.md`](alignment-derived-guardrails.plan.md) | **Task** | Alignment-derived guardrails | (see plan frontmatter) |
| [`dmp_gene_modeling_modes_c0d0bad6.plan.md`](dmp_gene_modeling_modes_c0d0bad6.plan.md) | **Task** | DMP/gene modeling modes (historical) | Superseded by composable-pipeline + docs refresh |
| [`chromosome_sample_derived_measures_a9b33eac.plan.md`](chromosome_sample_derived_measures_a9b33eac.plan.md) | **Task** | Chromosome sample derived measures | (see plan frontmatter) |
| [`ising_mrf_v2_gpu_5f06ccb7.plan.md`](ising_mrf_v2_gpu_5f06ccb7.plan.md) | **Task** | Ising MRF v2 GPU | (see plan frontmatter) |

Create each **Task** under its Epic in Azure DevOps Boards. Copy the task title from the plan `todos[].content` field. Mark tasks **Closed** when the corresponding code is merged.

Smaller fixes (single script, doc tweak) can be a **Task** without a plan file.

## Commit message convention

Link commits to work items so Azure DevOps auto-updates state:

```
<imperative summary> (AB#<work-item-id>)

Optional body: what changed and why.
```

Examples:

```
Add assemble_release.sh and release assemble pipeline (AB#1234)

Implements devops-ci-cd-release plan task assemble-script.
Part of Epic AB#1200 (DevOps CI/CD release).
```

```
Document production release layout on /work/epimethyl (AB#1101)

Implements production-gpu-worker-layout plan task define-layout.
```

### Multiple work items

```
Refactor CI YAML per repo (AB#1234 AB#1235)
```

Or reference the Epic only when the commit completes several tasks:

```
Complete GPU worker production layout (AB#1100)
```

## Branch and PR workflow

1. Create **Task** or **Epic** in Azure DevOps (or use existing).
2. Branch: `feature/AB1234-assemble-release` or `task/1101-release-docs`.
3. Implement; reference plan file in PR description.
4. PR title: `Add assemble release pipeline (AB#1234)`.
5. Enable **Automatically link work items** in Azure DevOps repo settings (Boards → Project settings → Git → Mention tracking).
6. Close Task when PR completes; close Epic when all child tasks are done.

## Plan file format

Plans use YAML frontmatter (`name`, `overview`, `todos`) plus markdown body. The `todos` list mirrors Azure DevOps Tasks. Update `status: completed` in the plan when merging if you use plans as living records.

Filename convention: `kebab-case-from-plan-name.plan.md` in this directory (not the Cursor hash suffix from `~/.cursor/plans/`).

## Related docs

- [`../deployment/production_release.md`](../deployment/production_release.md) — operational release guide
- [`../deployment/production_runbook.md`](../deployment/production_runbook.md) — operator runbook (includes alignment QC remediation)
- [`../../packages/methylalignmentqc/docs/USAGE.md`](../../packages/methylalignmentqc/docs/USAGE.md) — MethylAlignmentQC usage
- [`../../ci/README.md`](../../ci/README.md) — pipeline registration
