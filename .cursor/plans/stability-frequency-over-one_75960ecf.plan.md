---
name: stability-frequency-over-one
overview: Identify and prevent `frequency > 1.0` in stability DMP exports by enforcing invariants where panels are merged/consumed, not in the core recurrence formula.
todos:
  - id: trace-invariant-gap
    content: Pinpoint where invalid recurrence metadata enters merged/fixed panels and document invariants
    status: pending
  - id: add-stability-validation
    content: Implement recurrence metadata validation in stability merge path before writing merged panel
    status: pending
  - id: add-fixed-panel-guard
    content: Validate recurrence metadata when loading fixed_dmp_panel in methyldetector
    status: pending
  - id: test-invalid-frequency-paths
    content: Add tests for frequency/count/n_runs inconsistency and out-of-range rejection
    status: pending
isProject: false
---

# Fix Stability Frequency Overflow

## What I found
- Core DMP stability math is bounded in [`/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py): `frequency = count / run_count`, with per-run deduplication, so this path should not generate values > 1.0.
- Overflow can leak in downstream when precomputed panel metadata is reused without revalidation/recompute:
  - Merge/passthrough in [`/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py) (`_merge_stable_dmp_panels`)
  - Fixed panel ingestion/export in [`/home/ubuntu/MethylPipeline/packages/methyldetector/methyl_detector/core/methyldetector.py`](/home/ubuntu/MethylPipeline/packages/methyldetector/methyl_detector/core/methyldetector.py)
- Existing mapper guard already treats this as invalid stability metadata in [`/home/ubuntu/MethylPipeline/packages/methylmapper/methyl_mapper/bedtools_mapper.py`](/home/ubuntu/MethylPipeline/packages/methylmapper/methyl_mapper/bedtools_mapper.py).

## Implementation plan
- Add a shared validation/sanitization helper for stability recurrence columns (`frequency`, `count`, `n_runs`) in `stability.py`:
  - enforce finite numeric values
  - enforce `0 <= frequency <= 1`
  - enforce `0 <= count <= n_runs` when both are present
  - enforce consistency (`abs(frequency - count/n_runs) <= eps`) where possible
- Apply the helper in `_merge_stable_dmp_panels` before writing `stable_dmps_genomewide.csv`.
- Add fixed-panel input validation in `methyldetector.py` when `fixed_dmp_panel` is loaded; fail fast with clear error if recurrence metadata is invalid.
- Add/extend tests in methylvalidation + methyldetector to cover:
  - inconsistent row (`count > n_runs`)
  - mismatched ratio (`frequency != count/n_runs`)
  - out-of-range frequency (`>1.0`)
  - valid row pass-through.

## Verification
- Run targeted test files in `.venv` for stability/merge and fixed-panel loading paths.
- Confirm resulting `dmp_frequency.csv` and merged production panel have no row with `frequency > 1.0` and no `count > n_runs`.