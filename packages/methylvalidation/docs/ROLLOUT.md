# Probabilistic V2 Rollout Playbook

## Purpose

Provide a dual-run migration protocol from legacy inference outputs to probabilistic-v2
outputs with explicit promotion and rollback criteria.

## Dual-Run Protocol

1. Train/freeze legacy and v2 candidates from the same source cohorts.
2. Run `--post-model-validation` (or `--model-mc`) for both artifacts on identical split
   settings (`train_fraction`, `n_iterations`, `seed` base).
3. Compare aggregate metrics from each root:
   - discrimination: `balanced_accuracy`, `macro_f1`
   - reliability: `nll`, `brier_score`, `ece`
   - stability: run-to-run variance (std from `metrics_summary.json`)
4. Keep both artifacts deployable during probation (read-only legacy fallback).

## Promotion Criteria (Recommended Defaults)

- `balanced_accuracy` median (p50): candidate >= legacy - 0.005
- `macro_f1` median (p50): candidate >= legacy - 0.005
- `nll` mean: candidate <= legacy * 0.98
- `brier_score` mean: candidate <= legacy * 0.98
- `ece` mean: candidate <= legacy * 0.95
- No increase in hard-failure rates (missing outputs, invalid probability rows).

If reliability improves materially while discrimination is flat/slightly better, promote.

## Rollback Criteria

Rollback to legacy if any condition holds in production monitoring window:

- reliability regression beyond thresholds for two consecutive evaluation windows,
- severe class-collapse/degenerate prediction warning spike,
- unexplained increase in prediction failure rate.

## Artifact Requirements

- Keep both model artifacts with explicit metadata:
  - `ovr_inference_version`
  - `ovr_fuse_mode`
  - calibration flags and training split semantics
- Keep each run root's `baseline_manifest.json` for auditability.

## Decision Report Template

- Scope (cohorts, timeframe, backend)
- Baseline vs candidate metric table
- Pass/fail against promotion thresholds
- Recommendation: promote / hold / rollback
- Notes on operational incidents and mitigation steps
