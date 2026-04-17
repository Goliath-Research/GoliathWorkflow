---
name: stability-aware dual cutoff
overview: Add a post-Monte-Carlo dual-cutoff strategy in methylvalidation stability outputs, ranking DMPs by combined stability-aware score and deriving strict/relaxed cutoffs via log-scale elbow detection.
todos:
  - id: inspect-stability-io
    content: Map current stability.py output/write path and identify exact insertion points for dual-cutoff scoring and exports.
    status: pending
  - id: add-score-and-elbow-helpers
    content: Implement combined score computation and log-scale elbow detection helpers with edge-case guards.
    status: pending
  - id: wire-dual-output-selection
    content: Integrate strict/relaxed selection into stable panel write flow while preserving backward compatibility.
    status: pending
  - id: add-tests
    content: Add focused unit tests for scoring, elbow behavior, and strict subset relaxed invariant.
    status: pending
  - id: docs-and-verify
    content: Document new outputs/config knobs and run targeted validation on one real stability result set.
    status: pending
isProject: false
---

# Stability-Aware Dual Cutoff In Stability Outputs

## Goal
Implement strict vs relaxed DMP selection in the Monte Carlo stability stage (not detector runtime), using:

- `combined_score = effect_size * sqrt(frequency)`
- elbow detection on `log(combined_score)`

This keeps modeling panels compact/high-confidence while preserving broader biology for mapping/enrichment.

## Scope
- Primary file: [`/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py)
- Optional docs update: [`/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/USAGE.md`](/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/USAGE.md)

## Planned Changes
- Add a reusable scoring helper in `stability.py`:
  - compute `combined_score`
  - validate finite/non-negative values
  - stable sort descending by score
- Add elbow helper on log-scale scores:
  - input: sorted `combined_score`
  - operate on `log(score + eps)` to avoid long-tail bias
  - return cutoff index and threshold
- Extend stable panel selection flow (currently frequency-based in `_select_stable_dmps_df` / `write_stable_panel`) to produce two outputs:
  - **strict panel** (modeling): cutoff at main elbow (higher precision)
  - **relaxed panel** (mapping/enrichment): cutoff at later elbow/relaxed multiplier of strict threshold
- Keep existing `min_frequency` filter as precondition, then apply score-elbow logic.
- Export additional artifacts from `run_stability_analysis()`:
  - `stable_dmps_strict.csv`
  - `stable_dmps_relaxed.csv`
  - score diagnostics CSV/JSON (cutoff index, threshold, retained counts)
- Ensure backward compatibility:
  - preserve existing `stable_dmps_production.csv` behavior (either alias to strict or controlled by config flag)

## Config Additions (in stability config surface)
- `dual_cutoff_enabled: bool` (default `False` for compatibility)
- `strict_cutoff_mode: "elbow_log_score"`
- `relaxed_cutoff_mode: "elbow_log_score" | "strict_multiplier"`
- `relaxed_multiplier: float` (only if multiplier mode is selected)
- `score_eps: float` (small epsilon for log safety)

## Validation Strategy
- Unit tests in methylvalidation test suite for:
  - score computation correctness
  - elbow detection robustness on heavy-tail synthetic vectors
  - strict set is subset of relaxed set
  - deterministic output with ties and edge cases (all equal scores, few rows)
- Integration check on one existing MC stability output directory:
  - confirm artifact creation
  - compare counts and score distributions

## Data Flow
```mermaid
flowchart TD
  stabilityRuns[MC discovery runs] --> freqTable[dmp_frequency.csv]
  freqTable --> minFreqFilter[min_frequency filter]
  minFreqFilter --> scoreBuild[combined_score=effect_size*sqrt(frequency)]
  scoreBuild --> strictElbow[log-score elbow strict cutoff]
  scoreBuild --> relaxedRule[log-score relaxed cutoff]
  strictElbow --> strictPanel[stable_dmps_strict.csv]
  relaxedRule --> relaxedPanel[stable_dmps_relaxed.csv]
```

## Notes
- This plan intentionally avoids detector-time joins and keeps frequency-aware logic where frequency is truly defined (post-MC).
- If accepted and validated, a second phase can propagate these strict/relaxed outputs into downstream classifier/mapper defaults.