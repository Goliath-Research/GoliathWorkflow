---
name: Speed Up Hybrid Build
overview: Keep the full observed-only scope (tabular + generative + ECDF second-stage + full benchmark) but restructure execution around a strict feature-contract freeze and milestone gates to cut rework time.
todos:
  - id: freeze-contract
    content: Lock observed_feature_builder feature schema/order and add parity checks before downstream changes.
    status: completed
  - id: wire-backends
    content: Complete tabular and generative wiring using the frozen observed-hybrid contract and config routing.
    status: completed
  - id: integrate-ecdf-second-stage
    content: Integrate optional ECDF second-stage scorer while preserving base ECDF output compatibility.
    status: completed
  - id: run-full-benchmark
    content: Execute one full baseline-vs-hybrid benchmark pass and capture promotion metrics/report.
    status: in_progress
isProject: false
---

# Accelerated Observed-Hybrid Delivery Plan

## Why current build feels slow
- The current workflow couples feature engineering, backend wiring, and benchmarking in one loop, so schema changes force expensive reruns.
- Both model backends depend on the same observed feature contract, but integration/validation is not explicitly gated around that shared contract.
- Full-benchmark checks are being treated as development feedback, which makes iteration latency high.

## Critical-path strategy
- **Freeze one feature contract first** in [packages/methylvalidation/methyl_validation/observed_feature_builder.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/observed_feature_builder.py), then block downstream edits that would change feature order/meaning.
- **Complete backend wiring against frozen contract** in [packages/methylvalidation/methyl_validation/tabular_backend.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/tabular_backend.py) and [packages/methylvalidation/methyl_validation/generative_backend.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/generative_backend.py).
- **Attach ECDF second-stage only after base ECDF outputs are stable** via [packages/methylvalidation/methyl_validation/ecdf_second_stage.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/ecdf_second_stage.py).
- **Run full benchmark once per milestone candidate**, not during core wiring loops.

## Milestones and gates
1. **M1: Feature contract freeze**
   - Finalize observed feature set, ordering, reliability fields, and fill-value policy.
   - Persist/verify schema metadata shape used by training and prediction.
   - Gate: deterministic schema + train/infer parity tests pass.
2. **M2: Tabular + generative parity on frozen schema**
   - Wire both backends to consume the same observed-hybrid builder and metadata contract.
   - Ensure routing/config pass-through in [packages/methylvalidation/methyl_validation/config.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/config.py) and [packages/methylvalidation/methyl_validation/trainer_api.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/trainer_api.py).
   - Gate: both backends complete train+predict without shape mismatch.
3. **M3: ECDF second-stage integration**
   - Train/apply optional second-stage refiner from `predictions.csv` + observed features.
   - Preserve base ECDF outputs and add refined columns only.
   - Gate: second-stage artifact + metadata emitted, and output compatibility confirmed.
4. **M4: Full benchmark and promotion decision**
   - Run full baseline comparison once with fixed config and dataset split.
   - Record BA/F1/calibration deltas and feature reliability behavior.
   - Gate: promotion criteria met or rollback flags documented.

## Execution flow
```mermaid
flowchart LR
featureFreeze[FeatureContractFreeze] --> backendWire[TabularAndGenerativeWireup]
backendWire --> ecdfStage[ECDFSecondStageHook]
ecdfStage --> fullBenchmark[FullBenchmarkRun]
fullBenchmark --> promoteDecision[PromoteOrIterate]
```

## Fast-loop rules (to reduce wall time)
- Do not modify feature definitions after M1 unless a blocker is confirmed; otherwise only fix wiring/metadata bugs.
- Use smoke/integration checks during M1-M3; reserve full benchmark runs for M4 candidate builds.
- Keep one canonical benchmark config snapshot (same cohort split and thresholds) to avoid noisy reruns.

## Key files in this plan
- [packages/methylvalidation/methyl_validation/observed_feature_builder.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/observed_feature_builder.py)
- [packages/methylvalidation/methyl_validation/tabular_backend.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/tabular_backend.py)
- [packages/methylvalidation/methyl_validation/generative_backend.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/generative_backend.py)
- [packages/methylvalidation/methyl_validation/ecdf_second_stage.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/ecdf_second_stage.py)
- [packages/methylvalidation/methyl_validation/config.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/config.py)
- [packages/methylvalidation/methyl_validation/trainer_api.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/trainer_api.py)