---
name: MethylValidation multiclass
overview: "Extend MethylValidation for K-class Monte Carlo validation (aligned with multiclass MethylPredictor: `--test-groups`, single `validation_metrics.json` under `predictors/`), keep binary mode as a compatibility path, run centroid with `--group all` when K&gt;2 (no group1/group2 delta overrides), and fail fast if the base project uses blind-only predictor."
todos:
  - id: mc-config-cohorts
    content: "Extend MonteCarloConfig: cohorts list + legacy healthy/disease synthesis; validate K>=2"
    status: pending
  - id: mc-split-k
    content: Add stratified_split_multiclass (per-cohort train/val); keep binary API
    status: pending
  - id: mc-project-gen-k
    content: "generate_run_project_multiclass: per-cohort train/val CSVs + flat groups project JSON from base template"
    status: pending
  - id: mc-pipeline-predictor
    content: "pipeline_runner: centroid all for K>2; run_predictor_multiclass with --test-groups JSON"
    status: pending
  - id: mc-cli-blind-guard
    content: "cli: branch K=2 vs K>2; reject base project blind predictor at startup"
    status: pending
  - id: mc-metrics-docs-tests
    content: Docs (multiclass-first, no blind MC); pytest for split + config + optional CLI argv
    status: pending
isProject: false
---

# MethylValidation: multiclass-first, no blind MC

## Goal

- **Primary:** Monte Carlo validation for **K-class** pipelines (one multiclass classifier, held-out samples per class), matching how `[methyl_predictor/cli.py](packages/methylpredictor/methyl_predictor/cli.py)` runs multiclass: `--project` + `**--test-groups`** JSON + optional `--output-dir` (and `resolve_predictor_config_per_comparison` returning `("multiclass", ...)` when `multiclass-classifier.pkl` exists — see `[project_resolver.py](packages/methylpredictor/methyl_predictor/project_resolver.py)` ~519–573).
- **Out of scope for MC:** `**predictor.blind` / blind-only** runs — document and **reject** at validation startup if `step_config.predictor` has active blind groups (same signal as `[_predictor_blind_has_groups](packages/methylpredictor/methyl_predictor/project_resolver.py)`); blind stays for other workflows only.
- **Secondary:** Preserve today’s **binary** path (`healthy_csv` + `disease_csv`) as legacy / special case of K=2.

## Design choices

1. **Config (`[config.py](packages/methylvalidation/methyl_validation/config.py)`)**
  - Add an ordered `**cohorts`** list: `[{ "label": str, "csv": str }, ...]` with `len >= 2` (K classes).  
  - **Backward compatibility:** if `cohorts` is absent, synthesize it from existing `healthy_csv` + `disease_csv` (labels e.g. `healthy` / `disease` or from optional fields).  
  - Optional: `cohort_labels` override if we need stable labels matching the base project’s `groups` / class names.
2. **Split (`[split.py](packages/methylvalidation/methyl_validation/split.py)`)**
  - Add `**stratified_split_multiclass`**: for each cohort list, apply the same rules as today (shuffle, `train_fraction`, ensure non-empty train/val per class when counts allow). Return `train_by_label`, `val_by_label` dicts.  
  - Keep `**stratified_split**` as a thin wrapper for K=2 or delegate to the multiclass helper.
3. **Run project generation (`[project_gen.py](packages/methylvalidation/methyl_validation/project_gen.py)`)**
  - New `**generate_run_project_multiclass`** (or generalized `generate_run_project`):  
    - Write `**train_<safe_label>.csv**` (sample names + `samples_base_path`) and `**val_<safe_label>.csv**` (absolute paths, same as current `write_val_csv`) **per cohort**.  
    - Load `**base_project`** JSON and override `**groups**` (flat multiclass template) **or** mirror the base project’s intended shape. **Pragmatic v1:** require base project to use **flat `groups`** (N groups) matching cohort labels/order, and set each group’s `sample_paths` to the corresponding **train** CSV only — this matches `[PipelineConfig` flat groups](packages/methylutils/methyl_utils/pipeline_config.py) and `methyl-centroid --group all`.  
    - If the team’s “main” template is instead control/disease + `multiclass-classifier.pkl` only (no flat `groups`), add a second template branch in the same module driven by a small `**monte_carlo_config.project_layout`** flag or auto-detect from base JSON (`groups` vs `control`/`disease` + presence of multiclass artifact path in docs). **Start with flat `groups` + multiclass classifier output layout** documented in USAGE; expand if configs like `[project_Healthy_vs_PCa1-4.json](configs/project_Healthy_vs_PCa1-4.json)` must be supported without flattening.
4. **Pipeline runner (`[pipeline_runner.py](packages/methylvalidation/methyl_validation/pipeline_runner.py)`)**
  - **Binary:** unchanged — `run_centroid` with `group1`/`group2` step overrides; `run_predictor(..., test_control_csv, test_disease_csv, output_dir)`.  
  - **Multiclass:** `run_centroid(project_json)` **without** centroid overrides → single `methyl-centroid --project ... --group all` (same as `[run_centroid` no-override branch](packages/methylvalidation/methyl_validation/pipeline_runner.py) ~50–52).  
  - `**run_predictor_multiclass`:** build a temporary **val-only JSON** `[{ "label": ..., "paths": [...] }, ...]` from resolved val paths; invoke `methyl-predictor --project ... --test-groups <json> --output-dir ...` (and `**--per-comparison`** remains implied when `load_project` sets `uses_control_disease` — current CLI already forces that; multiclass branch still runs one predictor config).  
  - `**predictor_output_dir`:** for multiclass, align with resolver default `**paths.validator_dir`** (project root + `/predictors`), i.e. `run_dir / "predictors"` when not using `predictors/<ctrl>/<dis>`. Match `[cli.py](packages/methylvalidation/methyl_validation/cli.py)` logic: if comparisons exist **and** predictor is binary per comparison, keep subdirs; if multiclass-only output, use flat `run_dir / "predictors"`.
5. **CLI orchestration (`[cli.py](packages/methylvalidation/methyl_validation/cli.py)`)**
  - After loading `MonteCarloConfig`, `**load_project(base_project)`** and **abort** if blind predictor is configured (reuse same structural check as predictor package: `blind` dict with non-empty `groups`, or non-empty `test_blind_paths` in step config if present).  
  - Branch on **K == 2** vs **K > 2** (or explicit `mode` field) for split → `generate_run_*` → `run_pipeline_for_iteration` variant.  
  - Progress task total stays **4 steps** per iteration.
6. **Metrics (`[validator_metrics.py](packages/methylvalidation/methyl_validation/validator_metrics.py)`)**
  - Existing `**SCALAR_KEYS`** already include macro/weighted F1; multiclass `validation_metrics.json` remains compatible. Optionally add `**n_classes**`-aware documentation; no schema break required.
7. **Documentation**
  - `[packages/methylvalidation/docs/THEORY.md](packages/methylvalidation/docs/THEORY.md)`, `[USAGE.md](packages/methylvalidation/docs/USAGE.md)`, `[IMPLEMENTATION.md](packages/methylvalidation/docs/IMPLEMENTATION.md)`: state **multiclass-first**, **binary legacy**, **blind not supported** for `methyl-validation`.
8. **Tests**
  - `stratified_split_multiclass` with K=3, edge cases (min samples).  
  - Config round-trip: legacy JSON vs `cohorts`.  
  - Optional: monkeypatch `run_cmd` to assert multiclass predictor command includes `--test-groups`.

## Risks / follow-ups

- **Base project shape:** If production projects are **only** control/disease + many comparisons (binary PKLs) and not multiclass PKL, MC validation is a different product (N predictor runs per iteration). This plan targets **one multiclass PKL** per run; call that out in docs and add a follow-up milestone if you need “MC over all comparisons.”  
- **Centroid deltas:** Multiclass v1 uses **full `--group all`** per iteration (simpler, correct); binary keeps **delta overrides**. K-group deltas can be a later optimization.

