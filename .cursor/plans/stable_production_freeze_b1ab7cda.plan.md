---
name: stable production freeze
overview: Implement a final full-data retrain using stable DMPs from MC stability analysis, respecting train_fraction (including 1.0) and merging per-chromosome stable panels.
todos:
  - id: extend-config
    content: Add freeze_stable_dmp_csv and production_output_dir to MonteCarloConfig
    status: pending
  - id: add-freeze-cli
    content: Add --freeze flag to cli.py that sets production mode
    status: pending
  - id: stability-freeze-function
    content: Implement freeze_production_model in stability.py that merges per-chromosome stable DMPs
    status: pending
  - id: detector-fixed-panel
    content: Add fixed_dmp_panel support in MethylDetector to bypass discovery
    status: pending
  - id: update-runner
    content: Update pipeline_runner.py to support final production run
    status: pending
  - id: update-docs
    content: Update IMPLEMENTATION.md and USAGE.md with the new workflow
    status: pending
isProject: false
---

**Overview**

Add a production-freeze capability that takes the stable DMP list produced by `--stability` (or `run_stability`) and runs one final pipeline on the full dataset (or a final train set according to `train_fraction`).

**Implementation tasks**

- Extend `MonteCarloConfig` with `freeze_stable_dmp_csv` and `production_output_dir` fields.
- Add `--freeze` CLI flag in `cli.py` that triggers a final run using the latest stable DMP CSV.
- Create `freeze_production_model` in `stability.py` that:
  - Merges per-chromosome stable DMPs into one genome-wide panel.
  - Generates a production project JSON with `fixed_dmp_panel` pointing at the merged CSV.
- Extend `MethylDetector` (`methyldetector/core/methyldetector.py`) to support a `fixed_dmp_panel` config option (bypass discovery, use only listed positions).
- Update `pipeline_runner.py` to support a final production run mode.
- Update documentation in `IMPLEMENTATION.md` and `USAGE.md`.

**Key files**

- `packages/methylvalidation/methyl_validation/config.py`
- `packages/methylvalidation/methyl_validation/cli.py`
- `packages/methylvalidation/methyl_validation/stability.py`
- `packages/methyldetector/methyl_detector/core/methyldetector.py`
- `packages/methylvalidation/docs/IMPLEMENTATION.md`

**Mermaid flow**

```mermaid
flowchart LR
  MC[MC with --stability] --> Stable[stable_dmps_production.csv per chromosome]
  Stable --> Merge[Merge per-chromosome panels]
  Merge --> Freeze[freeze_production_model]
  Freeze --> FullRun[Centroid(full data) → Detector(fixed panel) → Classifier → Mapper+Enricher]
  FullRun --> Production[production classifier + full gene report]
```



**Next step**

Confirm this plan or provide modifications. Once confirmed, I will implement it step by step.