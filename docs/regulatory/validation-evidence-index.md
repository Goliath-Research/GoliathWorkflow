# Validation Evidence Index

> Status: template and registry structure. Populate this file with real
> study/model entries as validation runs are completed and reviewed.

## Purpose

This index ties real results to exact software, configuration, workflow, data,
and model artifacts. It is the regulatory bridge between product controls and
clinical or analytical performance claims.

Architecture and release controls show that the product is controlled. This
index shows what evidence was produced by a specific controlled version.

## Evidence Principles

Each evidence package should be:

- version-bound: exact release bundle and component versions,
- configuration-bound: exact study, site, profile, and DomainProgram inputs,
- instance-bound: workflow instance IDs and node execution exports,
- data-bound: cohort/sample IDs and validation partitions,
- artifact-bound: model, panel, readiness, prediction, and metric outputs,
- limitation-aware: caveats and residual risks documented with the result.

## Evidence Package Template

Copy this template for each reviewed study/model.

```markdown
## Evidence Package: <Study / Model Name>

### Administrative Metadata

- Evidence package ID:
- Review status: draft | under review | approved | superseded
- Prepared by:
- Reviewers:
- Date:
- Intended use / claim:

### Software and Release

- MethylPipeline release bundle:
- MethylPipeline component version:
- MethylExtractor component version:
- Runtime bundle path:
- Release `manifest.json` path:
- Release manifest SHA256:
- Git tag / commit:
- CI run:
- Regression test results (JUnit):
- Coverage report:
- Real reference-sample(s) used (id / analyte / provenance):
- Real-data test run (JUnit):
- Deploy approval record:

### Configuration Inputs

- Study manifest path:
- Study manifest SHA256:
- Site manifest path:
- Site manifest SHA256:
- Pipeline profile:
- Pipeline profile SHA256:
- DomainProgram path:
- DomainProgram SHA256:
- Workflow version ID:
- Action catalog version/hash:
- JSON Schema export version/hash:

### Data and Cohorts

- Project/study:
- Analyte:
- Species/genome build:
- Control cohort:
- Disease cohort(s):
- Total samples:
- Exclusion criteria:
- QC pass/fail summary:
- Validation partitions:
  - development_train:
  - locked_test:
  - pivotal_validation:
  - post_market_monitoring:

### Workflow Instances

- SamplePrepPipeline instance ID:
- StudyValidationLifecycle instance ID:
- Holdout or blind prediction instance ID:
- Node execution export:
- Worker/action timeline export:
- Portal dashboard snapshot/export:

### Model Creation Artifacts

- Monte Carlo run root:
- Stability summary:
- Stable DMP panel:
- Production freeze project:
- Production summary:
- Biological readiness report:
- Classifier artifacts:
- Predictor artifacts:
- Model bundle:

### Validation Results

- Internal stability metrics:
- Frozen-model predictor metrics:
- True holdout metrics:
- Bootstrap confidence intervals:
- Blind prediction report:
- Calibration metrics:
- Confusion matrix:
- ROC-AUC / macro AUC:
- Sensitivity / specificity:
- Balanced accuracy:

### Traceability Artifacts

- Action result manifests:
- `action_run_log.jsonl`:
- `sample_prep_log.jsonl`:
- Node execution outputs:
- Idempotency signature records:
- Artifact hash manifest:

### Deviations and Limitations

- Known deviations:
- Failed or retried tasks:
- Missing artifacts:
- Data limitations:
- Statistical limitations:
- External validation status:
- Residual risk:

### Decision

- Verdict: accepted | accepted with risks | rejected | superseded
- Rationale:
- Required follow-up:
```

## Current Evidence Packages

| Evidence Package | Product Release | Study / Claim | Status | Primary Result Location |
|------------------|-----------------|---------------|--------|-------------------------|
| TBD | TBD | TBD | draft | TBD |

## Minimum Evidence Set For A Model Claim

Before a model claim is presented externally, the evidence package should include
at minimum:

- release manifest and deploy record,
- frozen study/profile/program/site inputs,
- sample prep and QC summary,
- stability summary and stable panel,
- production freeze summary,
- biological readiness report,
- final classifier and predictor artifacts,
- true holdout evaluation when available,
- bootstrap confidence intervals for primary metrics,
- node execution export and worker action timeline,
- documented limitations and decision rationale.

## Real Results vs Demonstrations

Smoke runs, synthetic fixtures, and development demos are useful engineering
evidence but should not be presented as clinical or analytical validation. They
belong in CI and development-readiness records.

Regulatory evidence requires real cohorts, declared partitions, locked outputs,
and traceability to the deployed product version that produced the results.

## Related Documents

- [`../theory/chapters/12-two-workflows.qmd`](../theory/chapters/12-two-workflows.qmd)
- [`../theory/chapters/15-model-creation-and-validation.qmd`](../theory/chapters/15-model-creation-and-validation.qmd)
- [`../usage/10-artifacts-and-qa-checks.qmd`](../usage/10-artifacts-and-qa-checks.qmd)
- [`deployment-and-supervision.md`](deployment-and-supervision.md)
- [`traceability-matrix.md`](traceability-matrix.md)
