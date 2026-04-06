---
name: Probabilistic V2 Roadmap
overview: Create a phased plan to convert the current strong ECDF pipeline into a statistically coherent end-to-end probabilistic system while preserving current performance and deployment safety.
todos:
  - id: phase0-baseline
    content: Define fixed baseline datasets, splits, seeds, and unified metric schema for binary and multiclass evaluation.
    status: pending
  - id: phase1-contract
    content: Formalize binary inference contract (likelihood, priors, posterior, calibration separation) in docs and metadata requirements.
    status: pending
  - id: phase2-design
    content: Select and specify coherent multiclass posterior strategy with backward-compatible inference mode versioning.
    status: pending
  - id: phase3-dependence
    content: Design block-level dependence-aware extension and benchmark protocol against independent-loci baseline.
    status: pending
  - id: phase4-calibration
    content: Define calibration governance policy, diagnostics, and split-safe fitting requirements.
    status: pending
  - id: phase5-rollout
    content: Prepare dual-run migration and production promotion/rollback criteria.
    status: pending
isProject: false
---

# Probabilistic V2 Roadmap

## Scope and Success Definition

This plan addresses the main issues raised in the review: mixed score scales, heuristic multiclass fusion, implicit independence assumptions, and calibration acting as a patch.

Success means:
- binary and multiclass outputs both have a clear probabilistic interpretation,
- calibration is optional and governance-controlled (not foundational),
- robustness and calibration improve without harming core accuracy,
- rollout is backward-compatible and low risk.

## Current-State Anchors (What We Keep)

- Keep ECDF-derived per-feature density modeling in [`/home/ubuntu/MethylPipeline/packages/methylutils/methyl_utils/ecdf_classifier.py`](/home/ubuntu/MethylPipeline/packages/methylutils/methyl_utils/ecdf_classifier.py).
- Keep detector-side statistical/biological separation and effect-size ranking in [`/home/ubuntu/MethylPipeline/packages/methyldetector/methyl_detector/core/methyldetector.py`](/home/ubuntu/MethylPipeline/packages/methyldetector/methyl_detector/core/methyldetector.py).
- Use existing limitations documentation as baseline truth in [`/home/ubuntu/MethylPipeline/docs/theory/chapters/10-limitations-and-open-questions.qmd`](/home/ubuntu/MethylPipeline/docs/theory/chapters/10-limitations-and-open-questions.qmd).
- Treat OvR fusion and geometric aggregation paths in [`/home/ubuntu/MethylPipeline/packages/methylclassifier/methyl_classifier/core/multiclass_ovr.py`](/home/ubuntu/MethylPipeline/packages/methylclassifier/methyl_classifier/core/multiclass_ovr.py) as target areas for formalization.

## Phase 0: Baseline Lock and Evaluation Harness

### Objective
Freeze a reproducible baseline so future changes can be proven, not argued.

### Work
- Define fixed datasets/splits/seeds for binary and multiclass runs.
- Standardize reporting for discrimination, calibration, and stability.
- Capture baseline for both calibrated and uncalibrated outputs.

### Deliverables
- Baseline metric artifacts and run manifests.
- One canonical comparison report schema for all later phases.

### Exit Gate
- Repeated baseline runs are deterministic and within agreed variance tolerance.

## Phase 1: Binary Probabilistic Contract

### Objective
Formalize the binary model as one coherent likelihood-prior-posterior contract.

### Work
- Explicitly define: `log p(X|c) = Σ w_i log p_i(x_i|c)` and `p(c|X) ∝ p(X|c)p(c)`.
- Add explicit class-prior handling policy and metadata serialization.
- Clarify weight semantics (`w_i` are reliability/information weights, not probabilities).
- Separate core posterior from optional calibration in docs and outputs.

### Deliverables
- Updated theory text in [`/home/ubuntu/MethylPipeline/packages/methylclassifier/docs/THEORY.md`](/home/ubuntu/MethylPipeline/packages/methylclassifier/docs/THEORY.md) and [`/home/ubuntu/MethylPipeline/docs/theory/chapters/04-methylclassifier.qmd`](/home/ubuntu/MethylPipeline/docs/theory/chapters/04-methylclassifier.qmd).
- Updated implementation contract notes in [`/home/ubuntu/MethylPipeline/packages/methylpredictor/docs/IMPLEMENTATION.md`](/home/ubuntu/MethylPipeline/packages/methylpredictor/docs/IMPLEMENTATION.md).

### Exit Gate
- Binary inference is fully explainable as likelihood + prior (+ optional calibration), with no undocumented transformations.

## Phase 2: Coherent Multiclass Inference (Critical Phase)

### Objective
Replace heuristic multiclass fusion with one mathematically coherent posterior layer.

### Work
- Design and choose one multiclass probabilistic strategy:
  - direct K-class likelihood model, or
  - principled coupling over pairwise/OvR evidence.
- Remove score-scale mixing across ECDF probabilities, logits, and fused heuristics.
- Define strict missing-evidence semantics (head missing vs low evidence).
- Preserve backward compatibility by versioning inference mode metadata.

### Deliverables
- New multiclass inference contract and package versioning strategy in [`/home/ubuntu/MethylPipeline/packages/methylclassifier/methyl_classifier/core/classifier.py`](/home/ubuntu/MethylPipeline/packages/methylclassifier/methyl_classifier/core/classifier.py) and [`/home/ubuntu/MethylPipeline/packages/methylclassifier/methyl_classifier/core/multiclass_ovr.py`](/home/ubuntu/MethylPipeline/packages/methylclassifier/methyl_classifier/core/multiclass_ovr.py).
- Migration notes for legacy OvR artifacts.

### Exit Gate
- Multiclass outputs are generated from one explicit posterior rule and outperform or match baseline on macro-F1 while improving NLL/ECE.

## Phase 3: Dependence-Aware Modeling

### Objective
Reduce overconfidence from independence assumptions among correlated CpGs.

### Work
- Introduce block/region-level aggregation (DMR/local cluster level).
- Apply shrinkage/regularization to avoid overfitting at block level.
- Keep independent-loci mode as fallback and benchmark both paths.

### Deliverables
- Dependence-aware model mode specification and metadata fields.
- Comparative benchmark report (independent vs block-aware).

### Exit Gate
- Dependence-aware mode shows improved calibration and shift robustness on held-out cohort-style splits.

## Phase 4: Calibration Governance

### Objective
Ensure calibration is controlled, auditable, and never masking core model inconsistency.

### Work
- Enforce split-safe calibration fitting policy.
- Always report calibrated and uncalibrated metrics side-by-side.
- Add calibration diagnostics (ECE, reliability curves, Brier).
- Define policy on when calibration can be enabled for production.

### Deliverables
- Calibration governance section in docs and report schema updates in predictor/validation outputs.
- Calibration provenance metadata for each model artifact.

### Exit Gate
- Calibration improves reliability metrics without hidden leakage and without being required for baseline validity.

## Phase 5: Production Migration and Rollout

### Objective
Ship the new probabilistic stack safely with rollback-ready controls.

### Work
- Dual-run v1 and v2 in parallel for a probation window.
- Define promotion thresholds (accuracy + calibration + robustness).
- Version model artifacts and inference semantics explicitly.
- Keep legacy loaders active until migration KPI is reached.

### Deliverables
- Rollout playbook, deprecation timeline, rollback protocol.
- Final decision report with go/no-go criteria.

### Exit Gate
- v2 meets promotion criteria and legacy path is reduced to compatibility mode.

## Validation Matrix (Used in Every Phase)

- Discrimination: balanced accuracy, macro-F1, per-class recall.
- Calibration: ECE, Brier, NLL, reliability diagnostics.
- Stability: bootstrap variance, seed variance, DMP-set sensitivity.
- Shift robustness: cohort/site/time split performance, not only random split.
- Operational behavior: missing-data handling, no-evidence scenarios, class-prior sensitivity.

## Architecture Progression

```mermaid
flowchart LR
    p0[Phase0_Baseline] --> p1[Phase1_BinaryContract]
    p1 --> p2[Phase2_MulticlassCoherence]
    p2 --> p3[Phase3_DependenceAware]
    p3 --> p4[Phase4_CalibrationGovernance]
    p4 --> p5[Phase5_ProductionRollout]
```

## Recommended Execution Order and Ownership

- Start with documentation + evaluation harness (Phases 0-1).
- Prioritize Phase 2 as architectural bottleneck before deeper modeling.
- Run Phase 3 only after Phase 2 inference semantics are stable.
- Keep MLOps/reporting owners engaged from Phase 0 so rollout evidence is ready by Phase 5.

## Risks and Controls

- Risk: stronger theory but short-term metric drops.
  - Control: gate on a metric bundle, not a single KPI.
- Risk: migration complexity for existing models.
  - Control: semantic versioning and dual-run migration.
- Risk: overfitting in dependence-aware extension.
  - Control: start with simple block/shrinkage baseline and strict holdout validation.