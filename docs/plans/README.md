# Implementation plans (Azure DevOps traceability)

Plans in this folder are the **source of truth** for large features. Each plan maps to Azure DevOps work items under Epic **[AB#413 MethylPipeline platform](https://dev.azure.com/EpiMethyl/Development/_workitems/edit/413)**.

**Cursor Plan Mode:** When you finish planning in Cursor, copy the plan here (kebab-case filename, e.g. `my-feature.plan.md`). Do not rely on `~/.cursor/plans/` or `.cursor/plans/` alone — those are not committed unless promoted to this folder. See [`.cursor/rules/plan-mode-docs-plans.mdc`](../../.cursor/rules/plan-mode-docs-plans.mdc).

**Historical backlog:** Epic [#283 MethylPipeline](https://dev.azure.com/EpiMethyl/Development/_workitems/edit/283) (package-era Features such as MethylUtils / MethylCentroid) is retained for history and is **Related** to AB#413. New work goes under AB#413.

**Seed tooling:** [`scripts/ado_traceability/`](../../scripts/ado_traceability/) — generate manifest, idempotent Boards seed, backfill plan IDs, link commits (`link_commits.py --apply`).

Commits are attached as **Fixed in Commit** artifact links (no git history rewrite). Open a work item → **Development** to see them.

## Work item mapping

Hierarchy (EpiMethyl Agile): **Epic (AB#413) → Feature (one per plan) → User Story (one per plan todo)**.

| Plan file | ADO Feature | Title | Child User Stories (todo ids) |
|-----------|-------------|-------|-------------------------------|
| [`production-gpu-worker-layout.plan.md`](production-gpu-worker-layout.plan.md) | **AB#414** | Production GPU worker layout | `define-layout`, `extractor-ci`, `pipeline-ci`, `install-release`, `gpu-node-runbook`, `docker-shared`, `worker-provision` |
| [`devops-ci-cd-release.plan.md`](devops-ci-cd-release.plan.md) | **AB#422** | DevOps CI/CD release pipeline | `me-release-ci`, `mp-release-ci`, `assemble-script`, `assemble-pipeline`, `deploy-pipeline`, `docs-ci-cd` |
| [`alignment-qc-screening.plan.md`](alignment-qc-screening.plan.md) | **AB#429** | Alignment QC screening and remediation | `screening-core`, `guardrail-enhance`, `cohort-report`, `trim-action`, `workflow-remediation`, `validate-docs` |
| [`composable-pipeline-flexibility.plan.md`](composable-pipeline-flexibility.plan.md) | **AB#436** | Composable pipeline profiles and MC paths | `profiles-config`, `scope-if-fix`, `programs-gene-enricher`, `programs-composable`, `validation-alignment`, `tests-docs`, `phase2-structural` |
| [`typed-action-observability.plan.md`](typed-action-observability.plan.md) | **AB#444** | Typed worker action observability | `infra-action-result`, `runner-result-code`, `cli-manifest-dmp-detector-mapper`, `strict-pipeline-schemas`, `validation-typed-outputs`, `sample-prep-result-codes`, `docs-observability` |
| [`finish-typed-follow-ups.plan.md`](finish-typed-follow-ups.plan.md) | **AB#452** | CLI manifests + typed in-process handlers | `deps-methyl-domain`, `detector-manifest`, `centroid-manifest`, `enricher-manifest-collector`, `handlers-sample-prep`, `handlers-validation`, `inprocess-strict`, `tests-manifest-collectors` |
| [`optional-observability-follow-ups.plan.md`](optional-observability-follow-ups.plan.md) | **AB#461** | Observability follow-ups (golden fixtures, CI, MC log) | `doc-result-code-dpl`, `golden-fixtures-test`, `ci-worker-tests`, `mc-action-run-log`, `handler-input-model` |
| [`gene-feature-effect-size.plan.md`](gene-feature-effect-size.plan.md) | **AB#467** | Biology-weighted gene/feature importance | `biology-weight-matrix`, `remove-legacy-mapper`, `canonical-gene-feature-formulas`, `fix-downstream-consumers`, `doc-biological-model` |
| [`simplify-study-config.plan.md`](simplify-study-config.plan.md) | **AB#473** | Simplify study config (four-layer model) | `contract-docs`, `site-resolver`, `profiles-progression`, `materialize-input`, `purge-step-config`, `migrate-manifests`, `editor-manual` |
| [`streamline-action-parameters.plan.md`](streamline-action-parameters.plan.md) | **AB#481** | Streamline workflow action parameters | `contract-audit-ci`, `canonical-config-keys`, `retire-mc-sidecars`, `slim-sample-prep-inputs`, `slim-pipeline-inputs`, `slim-validation-inputs`, `slim-implementations`, `docs-promote-plan` |
| [`parallel-mc-centroid-seed.plan.md`](parallel-mc-centroid-seed.plan.md) | **AB#490** | Parallel MC centroid seed | `typed-models`, `planner-models`, `handler-output`, `centroid-worker`, `domain-programs`, `schema-export`, `tests`, `db-catalog-seed`, `db-workflow-deploy`, `docs-plan-promote` |
| [`docs-refresh-and-guardrails.plan.md`](docs-refresh-and-guardrails.plan.md) | **AB#501** | Documentation refresh and CI guardrails | `audit-report`, `fix-precedence`, … |
| [`documentation-and-deployment-reliability.plan.md`](documentation-and-deployment-reliability.plan.md) | **AB#517** | Documentation and deployment reliability | `canonical-map`, `setup-reliability`, `domain-program-guide`, `engine-reference`, `operational-contracts`, `stale-cleanup`, `docs-guardrails` |
| [`typed-assign-domain-program.plan.md`](typed-assign-domain-program.plan.md) | **AB#525** | Typed assign DomainProgram language | `lang-doc-v2`, `ir-schema`, `compiler-control-assign`, `compute-actions`, `fixtures-tests`, `docs-align` |
| [`samd-study-profile-ladder.plan.md`](samd-study-profile-ladder.plan.md) | **AB#532** | SaMD study profile ladder | `sop-doc`, `samd-profiles`, `study-scaffold`, `presets-cli-docs`, `examples-evidence`, `promote-plan` |
| [`samd-follow-on-assign-evidence-modes.plan.md`](samd-follow-on-assign-evidence-modes.plan.md) | **AB#539** | SaMD follow-on (assign → evidence → fold mc_*) | `phase-a-sampleprep-assign`, `phase-b-evidence-packages`, `phase-c-fold-mc-modes`, `promote-follow-on-plan` |
| [`samd-deploy-buffy-research-migrate.plan.md`](samd-deploy-buffy-research-migrate.plan.md) | **AB#544** | SaMD deploy + generic programs + Buffy research migrate | `depersonalize-all-programs`, `publish-db-graphs`, `sync-runtime-bundle-samd`, `fix-mode-path-resolution`, `migrate-buffy-research`, `promote-plan-docs` |
| [`agnostic-gateway-and-boundaries.plan.md`](agnostic-gateway-and-boundaries.plan.md) | **AB#551** | Agnostic gateway and documented boundaries | `resolve-at-config`, `gateway-claim-clean`, `gateway-catalog-clean`, `move-lifecycle-out`, `repoint-callers`, `docs-boundaries`, `promote-plan`, `verify` |
| [`db-config-registry.plan.md`](db-config-registry.plan.md) | **AB#560** | Database configuration registry + shared-storage materialization | `phase1-cfg-ddl`, `phase1-methyl-cfg-cli`, `phase1-roundtrip-tests`, `phase2-publish-program`, `phase2-sync-actions`, `phase3-storage-credentials`, `phase3-assets-storage`, `phase4-bidirectional-scaffold`, `phase5-cutover-docs` |
| [`cfg-study-sample-mapping.plan.md`](cfg-study-sample-mapping.plan.md) | **AB#570** | cfg study membership from portal.Samples | `ddl-study-groups`, `procs-materialize`, `cli-portal-api`, `docs-user-manual` |
| [`action-provider-registry.plan.md`](action-provider-registry.plan.md) | **AB#575** | Action provider registry (process pack) | `phase1-registry`, `phase2-compiler`, `docs` |
| [`read-level-info-measures.plan.md`](read-level-info-measures.plan.md) | **AB#580** | Read-level information-theoretic measures | `contract-loader`, `extractor-flags`, `package-core`, `outputs`, `action-registration`, `covariate-list`, `config-program-wiring`, `regen-seed`, `tests`, `plan-promotion` |
| [`ci-regression-testing.plan.md`](ci-regression-testing.plan.md) | **AB#591** | CI regression testing and coverage | `pytest-config`, `ci-script`, `test-gap-analysis`, `author-missing-tests`, `azure-pipeline`, `ci-readme`, `regulatory-doc`, `regulatory-wiring`, `verify` |
| [`regression-protection-test-coverage.plan.md`](regression-protection-test-coverage.plan.md) | **AB#604** | Regression-protection test coverage | `p1-resolver-merge`, `p1-workflow-merge`, `p2-task-schema-drift-pytest`, `p3-cli-resolved-config`, `p4-action-result`, `p5-resolver-model-handshake`, `p6-ratchet-scope` |
| [`hyperparameter-result-versioning.plan.md`](hyperparameter-result-versioning.plan.md) | **AB#612** | Hyperparameter result versioning (CAAS) | `record-schema`, `content-store`, `content-key`, `skip-reuse`, `execute-orchestrate`, `hpset-id`, `tests`, `docs` |
| [`workflow-engine-sql-design.plan.md`](workflow-engine-sql-design.plan.md) | **AB#621** | Workflow engine SQL design | (see plan frontmatter) |
| [`alignment-derived-guardrails.plan.md`](alignment-derived-guardrails.plan.md) | **AB#628** | Alignment-derived guardrails | (see plan frontmatter) |
| [`dmp_gene_modeling_modes_c0d0bad6.plan.md`](dmp_gene_modeling_modes_c0d0bad6.plan.md) | **AB#635** | DMP/gene modeling modes (historical) | Superseded by composable-pipeline + docs refresh |
| [`chromosome_sample_derived_measures_a9b33eac.plan.md`](chromosome_sample_derived_measures_a9b33eac.plan.md) | **AB#644** | Chromosome sample derived measures | (see plan frontmatter) |
| [`ising_mrf_v2_gpu_5f06ccb7.plan.md`](ising_mrf_v2_gpu_5f06ccb7.plan.md) | **AB#653** | Ising MRF v2 GPU | (see plan frontmatter) |
| [`buffy-cell-deconvolution.plan.md`](buffy-cell-deconvolution.plan.md) | _(pending ADO)_ | Buffy-coat cell deconvolution (Houseman / FlowSorted) | `pkg-qp-core`, `flowsorted-basis-asset`, `action-wiring`, `program-profile`, `tests`, `docs-plan-promote` |
| [`hitimed-hierarchical-deconvolution.plan.md`](hitimed-hierarchical-deconvolution.plan.md) | _(pending ADO)_ | HiTIMED hierarchical cell-type deconvolution | `hierarchy-core`, `config-method`, `runner-dispatch`, `bases-build`, `schema-export`, `profile-covariates`, `tests`, `docs-promote` |
| [`hitimed-theory-docs.plan.md`](hitimed-theory-docs.plan.md) | _(pending ADO)_ | HiTIMED + analyte actions in Theory and end-to-end docs | `e2e-hitimed`, `theory-deconv-chapter`, `theory-analyte-actions`, `limitations-analyte-sync`, `promote-plan` |
| [`typed-composition-alr.plan.md`](typed-composition-alr.plan.md) | _(pending ADO)_ | Typed composition (simplex) ALR covariates | `composition-group-model`, `preprocessor-multi-alr`, `ecdf-prob-alr-default`, `profile-migrate`, `tests-docs-promote` |
| [`fix-tabular-alr-routing.plan.md`](fix-tabular-alr-routing.plan.md) | _(pending ADO)_ | Fix tabular ALR routing | `fix-resolve-attr`, `add-regression-test`, `run-pytest`, `promo-plan`, `operator-rerun` |
| [`unify-model-bundle-datasets.plan.md`](unify-model-bundle-datasets.plan.md) | _(pending ADO)_ | Unify model_bundle train/test datasets (Parquet) | `shared-writer`, `tabular-rename`, `ecdf-parquet`, `generative-export`, `tests-docs` |
| [`fix-tabular-test-dataset-export.plan.md`](fix-tabular-test-dataset-export.plan.md) | _(pending ADO)_ | Fix tabular test_dataset export (test_groups.json) | `fix-tabular-export`, `regression-test`, `docs-promo`, `operator-rerun` |
| [`gene-scored-dmp-analogs.plan.md`](gene-scored-dmp-analogs.plan.md) | _(pending ADO)_ | Gene-level analogs of dmp_scored features | `gene-centroid-compute`, `wire-observed-hybrid`, `tests`, `docs-promo` |
| [`omega-cluster-detection.plan.md`](omega-cluster-detection.plan.md) | _(pending ADO)_ | Ω-cluster cancer detection (research) | `omega-cluster-script`, `pairwise-eval`, `research-note`, `pipeline-gate` |
| [`ecdf-covariate-support.plan.md`](ecdf-covariate-support.plan.md) | _(pending ADO)_ | ECDF optional covariates (second-stage stacker) | `typed-second-stage-params`, `stack-covariates`, `trainer-gate-all-modes`, `profiles-docs-schema`, `tests` |
| [`effective-monte-carlo-config.plan.md`](effective-monte-carlo-config.plan.md) | _(pending ADO)_ | Effective Monte Carlo configuration | `legacy-inventory-removal`, `canonical-schemas-configs`, `effective-schema-writer`, `breaking-change-verification`, `db-config-sync` |
| [`cell-fraction-group-column.plan.md`](cell-fraction-group-column.plan.md) | _(pending ADO)_ | Cell fraction group column | `propagate-group-label`, `verify-group-column` |
| [`post-model-output-layout.plan.md`](post-model-output-layout.plan.md) | _(pending ADO)_ | Post-model validation output layout | `fix-output-root`, `update-contracts-tests`, `document-layout` |
| [`strict-reuse-model-mc.plan.md`](strict-reuse-model-mc.plan.md) | _(pending ADO)_ | Strict Reuse Model MC | `strict-reuse-contract`, `slim-program`, `tests-schemas`, `docs-plan` |
| [`model-mc-train-test.plan.md`](model-mc-train-test.plan.md) | _(pending ADO)_ | Model MC Train Test | `bind-test-partition`, `separate-ecdf-phases`, `aggregate-test-only`, `verify-document` |
| [`unified-model-mc-partitions.plan.md`](unified-model-mc-partitions.plan.md) | _(pending ADO)_ | Unified Model-MC Partitions | `predict-partition-api`, `trainer-orchestration`, `fail-closed-all-backends`, `train-membership-assert`, `tests-docs-plan` |
| [`independent-lr-stack-features.plan.md`](independent-lr-stack-features.plan.md) | _(pending ADO)_ | Independent LR Stack Features | `typed-transform-contract`, `fit-apply-independent-features`, `persist-exact-design-matrices`, `verify-document-contract` |
| [`ecdf-dmp-and-gene-models.plan.md`](ecdf-dmp-and-gene-models.plan.md) | _(pending ADO)_ | ECDF DMP and gene models | `dmp-context`, `dmp-freeze-model`, `gene-project-context`, `gene-mc-run`, `promote-plan-docs` |
| [`buffy-ecdf-gene-tier-a.plan.md`](buffy-ecdf-gene-tier-a.plan.md) | _(pending ADO)_ | Buffy gene Tier-A | `buffy-project-holdout`, `buffy-gene-context`, `buffy-tier-a-grid`, `buffy-plan-docs`, `buffy-vm-runbook` |
| [`pca-application-deep-dive.plan.md`](pca-application-deep-dive.plan.md) | _(pending ADO)_ | Prostate Cancer application deep-dive | `draft-deep-dive`, `index-links`, `claim-boundary-pass` |
| [`ecdf-studies-cross-vm.plan.md`](ecdf-studies-cross-vm.plan.md) | _(pending ADO)_ | ECDF studies cross-VM | `fix-buffy-context`, `fix-hpca-context`, `buffy-archive-rerun`, `hpca-other-vm-runbook`, `promote-plan-docs` |
| [`buffy-clean-pipeline.plan.md`](buffy-clean-pipeline.plan.md) | _(pending ADO)_ | Buffy clean stability→model pipeline | `fix-readiness-ready`, `emit-holdout-eval-artifacts`, `post-model-fallback`, `buffy-context-second-stage`, `promote-plan-docs`, `launch-buffy-freeze` |
| [`universal-caas-idempotency.plan.md`](universal-caas-idempotency.plan.md) | _(pending ADO)_ | Universal worker-side CAAS idempotency (+ FOREACH) | `phase0-substrate`, `phase1-validation-caas`, `phase2-foreach-bundle`, `phase3-consolidate-reuse`, `phase4-sample-caas` |
| [`release-stable-tier-a-ops.plan.md`](release-stable-tier-a-ops.plan.md) | _(pending ADO)_ | Release-stable Tier-A experimentation | `docs-release-boundary`, `docs-hyperparam-gene-fc`, `ops-release-pin` |
| [`portal-multi-instance-hpo.plan.md`](portal-multi-instance-hpo.plan.md) | _(pending ADO)_ | Portal multi-instance hyperparameter grid | `rename-wf-execution-scope`, `typed-hpo-schemas`, `cfg-search-ledger`, `grid-expander`, `score-promote`, `legacy-bridge-docs`, `tests-promote-plan` |
| [`di_action-agnostic_assessment_0d376284.plan.md`](di_action-agnostic_assessment_0d376284.plan.md) | **AB#664** | DI action-agnostic assessment | (see plan frontmatter) |
| [`methylit-standalone-doc.plan.md`](methylit-standalone-doc.plan.md) | **AB#668** | MethylIT Standalone Doc | (see plan frontmatter) |
| [`worker-transport-security.plan.md`](worker-transport-security.plan.md) | **AB#672** | Worker Transport Security | (see plan frontmatter) |
| [`ado-boards-traceability.plan.md`](ado-boards-traceability.plan.md) | _(meta)_ | ADO Boards Traceability (seed tooling) | `manifest`, `seed-script`, `ado-create`, `backfill-docs`, `promote-plan` |
| [`ci-dev-deploy-sync.plan.md`](ci-dev-deploy-sync.plan.md) | _(pending ADO)_ | CI / Dev / Deploy synchronization contracts | `immediate-ci-fixes`, `sync-matrix`, `install-contract`, `catalog-fixture-contract`, `local-mirrors-ci`, `precommit-expand`, `editable-hygiene`, `promote-plan-docs` |
| [`sync-genomes-to-qnap.plan.md`](sync-genomes-to-qnap.plan.md) | _(ops)_ | Sync /work/genomes to myQNAPcloud | `sync-script`, `doc-note` |
| [`genomes-multi-version-inventory.plan.md`](genomes-multi-version-inventory.plan.md) | _(pending ADO)_ | Genomes multi-version inventory + pinned selection | `layout-and-selection`, `qnap-reorganize-cli`, `confirm-gap-docs`, `seed-genomes-endpoint`, `reference-asset-recipes`, `provision-s3-sync`, `phase0-hook` |
| [`reference-inventory-audit.plan.md`](reference-inventory-audit.plan.md) | _(pending ADO)_ | Reference inventory propagation audit | `inventory-doc`, `pin-to-prefix`, `sql-parity`, `cred-example`, `verify-genomes`, `legacy-hygiene` |
| [`storage-transfer-hardening.plan.md`](storage-transfer-hardening.plan.md) | _(ops)_ | Storage transfer hardening (+ historical credential refs; superseded delivery in storage-db-sot) | `cloud-transfer-module`, `transfer-config-schema`, `cred-auth-modes`, `tests-docs` |
| [`storage-db-sot.plan.md`](storage-db-sot.plan.md) | _(ops)_ | Storage accounts DB SoT + dumb workers | `portal-storage-procs`, `unify-archive-cfg`, `expand-content-hash`, `worker-node-cache`, `arc-prod-boundary`, `dev-prod-docs`, `tests-promote-plan` |
| [`storage-sot-consistency-fixes.plan.md`](storage-sot-consistency-fixes.plan.md) | _(ops)_ | Storage SoT consistency (token fields + schema/docs) | `models-accept-tokens`, `regen-reconcile-schema`, `mssql-pg-parity`, `regression-tests`, `docs-destale` |
| [`worker-gateway-enroll.plan.md`](worker-gateway-enroll.plan.md) | _(ops)_ | Worker gateway enroll (IP preregistration) | `schema-enrollment`, `gateway-enroll-api`, `worker-enroll-client`, `provision-docs`, `tests-promote` |
| [`methylpipeline-platform-overview.plan.md`](methylpipeline-platform-overview.plan.md) | _(docs)_ | MethylPipeline platform overview | `outline-source-map`, `platform-capabilities`, `samd-evidence`, `extension-example`, `docs-canvas`, `verify-promote` |
| [`regulatory-pitch-presentation.plan.md`](regulatory-pitch-presentation.plan.md) | _(docs)_ | Regulatory-ready pitch presentation (Marp) | `author-deck`, `render-pipeline`, `index-docs`, `verify-shareable` |
| [`rna-seq-process-pack.plan.md`](rna-seq-process-pack.plan.md) | _(pending ADO)_ | RNA-Seq transcriptomics process pack | `modality-refs`, `quant-actions`, `rna-qc-express`, `downstream-model`, `programs-profiles`, `register-deploy-docs` |
| [`alzheimer-cfdna-disease-pack.plan.md`](alzheimer-cfdna-disease-pack.plan.md) | _(pending ADO)_ | Alzheimer cfDNA methylation disease pack | `study-scaffold`, `preset-registry`, `neuro-preset`, `disease-overlay`, `ci-fixture`, `docs-guide`, `regulatory-update`, `promote-plan` |
| [`plant-abiotic-stress-pack.plan.md`](plant-abiotic-stress-pack.plan.md) | _(pending ADO)_ | Plant abiotic stress methylation trait pack | `analyte-plant-tissue`, `site-tair10`, `lifecycle-no-deconv`, `preset-plant-stress`, `study-scaffold`, `ci-fixture`, `docs-regulatory` |
| [`multi-crop-plant-expansion.plan.md`](multi-crop-plant-expansion.plan.md) | _(pending ADO)_ | Multi-crop plant sites + plant trait priors | `crop-site-recipes`, `crop-overlays`, `plant-traits-source`, `ci-tests-docs` |
| [`plant-deconv-epigbs-seams.plan.md`](plant-deconv-epigbs-seams.plan.md) | _(pending ADO)_ | Plant deconv + epi-GBS platform seams | `eval-decisions`, `deconv-runtime-seams`, `deconv-cfg-asset`, `protocol-split-sampleprep`, `docker-align-demux`, `qc-presets-docs` |
| [`generic-application-pack-pattern.plan.md`](generic-application-pack-pattern.plan.md) | _(pending ADO)_ | Generic methylation application-pack pattern | `app-pack-guide`, `reframe-instances`, `hub-docs`, `promote-plan` |
| [`assay-procedure-packs.plan.md`](assay-procedure-packs.plan.md) | _(pending ADO)_ | Assay procedure packs for methylation analytes | `taxonomy-docs`, `procedure-json-resolver`, `ship-buffy-cfdna`, `emseq-seam`, `retarget-app-packs` |
| [`wgbs-pangenome-sample-prep.plan.md`](wgbs-pangenome-sample-prep.plan.md) | _(pending ADO)_ | WGBS pangenome SamplePrep (methylGrapher) | `typed-bs-assets`, `worker-dual-align`, `worker-graph-extract`, `sampleprep-routing`, `idempotency-validation`, `docs-release` |
| [`sampleprep-pangenome-documentation.plan.md`](sampleprep-pangenome-documentation.plan.md) | _(pending ADO)_ | SamplePrep pangenome documentation + extraction-QC contract | `traceability`, `manifest-contract`, `primary-diagram`, `canonical-docs`, `sync-references`, `validate` |
| [`sampleprep-real-data-canary.plan.md`](sampleprep-real-data-canary.plan.md) | _(pending ADO)_ | SamplePrep real-data canary (GSE261315 / three modes) | `pin-canary-data`, `typed-canary-config`, `real-canary-runner`, `canary-validation`, `scheduled-pipeline`, `catalog-contract`, `canary-docs`, `validate-canary` |
| [`linear-vs-wgbs-sampleprep-compare.plan.md`](linear-vs-wgbs-sampleprep-compare.plan.md) | _(pending ADO)_ | Linear vs pangenome_wgbs SamplePrep comparison | `layout-runner`, `cpg-time-report`, `execute-two-samples`, `docs-no-archive` |
| [`ds20m-dual-graph-finish.plan.md`](ds20m-dual-graph-finish.plan.md) | _(pending ADO)_ | DS20M dual-graph MethylCall finish | `restore-wl-gfa`, `clean-quarantine`, `run-methylcall`, `project-linear`, `compare-gono` |
| [`wgbs-alignment-decision.plan.md`](wgbs-alignment-decision.plan.md) | _(pending ADO)_ | WGBS alignment decision (linear vs pangenome_wgbs) | `interim-linear`, `fix-ds20m-concordance`, `code-acceptance-gate`, `ds20m-gate`, `buffy-confirm`, `final-reco` |
| [`methylgrapher-mojo-cutover.plan.md`](methylgrapher-mojo-cutover.plan.md) | _(pending ADO)_ | methylGrapher-mojo cutover (performance successor) | `phase0-bootstrap`, `phase1-mcall-parity`, `phase1-mcall-perf`, `phase2-mergecpg-align`, `phase3-dual-ship`, `phase4-cutover-gate` |
| [`pangenome-wgbs-methyl-qc.plan.md`](pangenome-wgbs-methyl-qc.plan.md) | _(pending ADO)_ | Mode-aware methyl_qc + MethylCall Mojo cutover | `detect-metrics-family`, `optional-models`, `wgbs-guardrails`, `tests-schemas`, `operator-rerun`, `mcall-native-hot-loop`, `mcall-fullsample-gate`, `mcall-cutover-flip`, `docs-promote` |
| [`extend-former-out-of-scope.plan.md`](extend-former-out-of-scope.plan.md) | _(pending ADO)_ | WGBS Picard metrics + Mojo MergeCpG/ConversionRate; Buffy 238 gated on missing25 | `picard-wgbs-worker`, `native-mergecpg`, `native-conversionrate`, `gate-buffy238`, `docs-split-oos` |
| [`gh200-wgbs-dual-graph-align.plan.md`](gh200-wgbs-dual-graph-align.plan.md) | _(pending ADO)_ | GH200 Mojo dual-graph Align (GAF); Parabricks GAF NO-GO | `phase0-gh200-spike`, `phase1-mojo-align`, `phase2-worker-site`, `phase3-perf-science-gate` |
| [`mojo-gpu-giraffe-gaf.plan.md`](mojo-gpu-giraffe-gaf.plan.md) | _(pending ADO)_ | Mojo GPU Giraffe GAF (portable NVIDIA/AMD); replace vg-only gpu_giraffe | `phase-a-spec-fixtures`, `phase-b-cpu-parity`, `phase-c-nvidia-gpu`, `phase-d-amd-bakeoff`, `phase-e-wire-docs` |
| [`gbz-native-mojo-giraffe.plan.md`](gbz-native-mojo-giraffe.plan.md) | _(pending ADO)_ | GBZ-native Mojo Giraffe for pangenome_wgbs (drop GFA size-cap) | `phase1-index-contract`, `phase2-cpu-gbz-parity`, `phase3-gpu-wall`, `phase4-cutover-docs` |
| [`prostate-study-alignment-update.plan.md`](prostate-study-alignment-update.plan.md) | _(pending ADO)_ | Prostate study alignment update (buffy pangenome_wgbs) | `materialize-procedures`, `verify-site-catalog`, `wire-buffy-context`, `wire-plasma-context`, `emit-realign-commands`, `acceptance-gate`, `emit-downstream-commands`, `docs` |
| [`deploy-remote-gateway.plan.md`](deploy-remote-gateway.plan.md) | _(ops)_ | Deploy gateway.epimethyl.com + worker cutover | `inventory-remote`, `install-gateway`, `nginx-tls`, `verify-health`, `worker-cutover`, `rotate-creds` |
| [`proteomics-process-pack.plan.md`](proteomics-process-pack.plan.md) | _(pending ADO)_ | Proteomics GPU process pack | `modality-generalize`, `diann-ingest`, `qc-abundance`, `downstream`, `programs-profiles-config`, `gpu-provisioning`, `panel-ingest`, `prosit-rescore`, `casanovo-denovo`, `register-deploy-docs-tests` |
| [`proteomics-sage-dda.plan.md`](proteomics-sage-dda.plan.md) | _(pending ADO)_ | Proteomics DDA via Sage (open MSFragger alternative) | `sage-runner`, `sage-ingest-source`, `program-config`, `provisioning`, `register-tests-docs` |
| [`config-propagation-analysis.plan.md`](config-propagation-analysis.plan.md) | _(pending ADO)_ | Config propagation analysis (methylation) | `analysis-doc`, `fix-prepare-freeze-bind`, `regression-tests`, `docs-wire-plan` |
| [`production-config-enforcement.plan.md`](production-config-enforcement.plan.md) | _(pending ADO)_ | Production config enforcement | `deep-merge-null-delete`, `full-lifecycle-model-mc`, `study-owned-analyte`, `pack-boundaries`, `scenario-experiments`, `docs-promote` |
| [`collapse-frozen-gene-features.plan.md`](collapse-frozen-gene-features.plan.md) | _(pending ADO)_ | Collapse frozen gene-feature panel | `collapse-groupby`, `tests-isoform`, `docs-contract`, `promote-plan` |
| [`methylsample-bp-ranged-io.plan.md`](methylsample-bp-ranged-io.plan.md) | _(pending ADO)_ | MethylSample bp-ranged H5 I/O | `range-resolve`, `load-api`, `shard-iter`, `tests`, `docs-plans` |

Create each **User Story** under its Feature in Azure DevOps Boards. Copy the story title from the plan `todos[].content` field (seed prefixes `[todo-id]`). Mark stories **Closed** when the corresponding code is merged; close the Feature when all child stories are done.

Smaller fixes (single script, doc tweak) can be a **User Story** under the nearest Feature (or a new Feature under AB#413) without a plan file.

## Commit message convention

Link commits to work items so Azure DevOps auto-updates state:

```
<imperative summary> (AB#<work-item-id>)

Optional body: what changed and why.
```

Examples:

```
Add assemble_release.sh and release assemble pipeline (AB#424)

Implements devops-ci-cd-release plan todo assemble-script.
Part of Feature AB#422 (DevOps CI/CD release); Epic AB#413.
```

```
Document production release layout on /work/epimethyl (AB#415)

Implements production-gpu-worker-layout plan todo define-layout.
```

### Multiple work items

```
Refactor CI YAML per repo (AB#423 AB#424)
```

Or reference the Feature only when the commit completes several stories:

```
Complete GPU worker production layout (AB#414)
```

## Branch and PR workflow

1. Create **User Story** or **Feature** under Epic AB#413 (or use existing IDs from plan frontmatter).
2. Branch: `feature/AB1234-assemble-release` or `task/1101-release-docs`.
3. Implement; reference plan file in PR description.
4. PR title: `Add assemble release pipeline (AB#1234)`.
5. Enable **Automatically link work items** in Azure DevOps repo settings (Boards → Project settings → Git → Mention tracking).
6. Close User Story when PR completes; close Feature when all child stories are done.

## Plan file format

Plans use YAML frontmatter (`name`, `overview`, `todos`) plus markdown body. Include:

```yaml
azure_devops:
  type: Feature
  title: "…"
  work_item_id: <Feature id>
  epic_id: 413
todos:
  - id: my-todo
    content: …
    status: completed
    work_item_id: <User Story id>
```

Update `status: completed` in the plan when merging if you use plans as living records.

Filename convention: `kebab-case-from-plan-name.plan.md` in this directory (not the Cursor hash suffix from `~/.cursor/plans/`).

## Related docs

- [`../deployment/production_release.md`](../deployment/production_release.md) — operational release guide
- [`../deployment/production_runbook.md`](../deployment/production_runbook.md) — operator runbook (includes alignment QC remediation)
- [`../../packages/methylalignmentqc/docs/USAGE.md`](../../packages/methylalignmentqc/docs/USAGE.md) — MethylAlignmentQC usage
- [`../../ci/README.md`](../../ci/README.md) — pipeline registration
- [`../../scripts/ado_traceability/README.md`](../../scripts/ado_traceability/README.md) — Boards seed / backfill
