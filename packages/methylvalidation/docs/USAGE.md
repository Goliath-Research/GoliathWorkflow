# MethylValidation Usage Guide

## Overview

MethylValidation supports **two distinct workflows**:

1. **Model Creation** — Build a stable, production-ready model using Monte Carlo validation, stability analysis, and a final production freeze.
2. **Model Use for Prediction** — Evaluate or deploy the frozen production model on new data using predictor-only mode.

---

## Workflow 1: Model Creation

**Purpose**: Create a robust production model by identifying stable DMPs across many random splits and building a final model on the full dataset.

### Correct Usage: Separate MC Config (Recommended)

Use a **minimal MC config** that references your main project:

**Command:**
```bash
# Use the test MC config that references the project
methyl-validation --config configs/test_mc_config.json --stability
```

**The MC config (`test_mc_config.json`) contains:**
- Monte Carlo specific settings (`train_fraction`, `n_iterations`, etc.)
- Reference to your main project (`base_project`)

**The Project config (`project_Healthy_vs_PCa1-4_CG.json`) contains:**
- Pipeline settings (`step_config.centroid`, `step_config.detection`, etc.)
- The `step_config.validation` section (for documentation/reference)

This separation keeps concerns distinct while maintaining a clean structure.

### Alternative: Separate MC Config

You can also use a separate Monte Carlo config that references the project (as shown in the original examples).

**Example `step_config.validation` in project config:**

```json
"step_config": {
  "validation": {
    "train_fraction": 0.8,
    "n_iterations": 5,
    "seed": 42,
    "run_stability": true,
    "stability_dmp_freq": 0.6
  }
}
```

### Why this workflow?

- Monte Carlo + stability identifies **consistently recurring DMPs** across random data splits (robustness).
- The `--freeze` step builds a **single high-quality production model** on the full dataset using the stable DMP panel.
- The `fixed_dmp_panel` option in MethylDetector bypasses statistical/biological discovery and uses only the stable positions.
- Output: production classifier, mapper, and enricher results in `monte_carlo_runs/production/`.

```mermaid
flowchart TD
    Config[monte_carlo_config.json] --> MC[Monte Carlo + --stability]
    MC --> Stability[stable_dmps_production.csv]
    Stability --> Freeze[--freeze]
    Freeze --> Merge[Merge stable DMPs]
    Merge --> ProdProject[production/project.json with fixed_dmp_panel]
    ProdProject --> Pipeline[centroid → detector(fixed panel) → classifier → mapper → enricher]
    Pipeline --> Output[production/ directory with final model]
```

---

## Workflow 2: Model Use for Prediction

**Purpose**: Evaluate the performance of the frozen production model on multiple random holdouts without retraining.

### Steps

1. Complete **Workflow 1** first (to create the frozen model).
2. Use the same (or similar) config file with `predictor_only: true` (or use `--predictor-only` flag).
3. Run predictor-only evaluation:
   ```bash
   methyl-validation --config monte_carlo_config.json --predictor-only
   ```

### Why this workflow?

- Much faster than full MC (only runs `methyl-predictor`).
- Provides the **empirical performance distribution** of the *final production model*.
- Uses the same stratified splitting logic as Model Creation for fair comparison.

```mermaid
flowchart TD
    Frozen[Frozen production/project.json] --> PO[--predictor-only]
    PO --> Splits[Stratified train/val splits]
    Splits --> Predictor[methyl-predictor only]
    Predictor --> Metrics[validation_metrics.json per iteration]
    Metrics --> Aggregate[all_metrics.csv + metrics_summary.json]
```

---

## Flags

- `--stability` — run stability analysis after MC (part of Model Creation)
- `--freeze` — run production freeze (final step of Model Creation)
- `--predictor-only` — run only predictor against frozen model (Model Use for Prediction)
- `--skip-enricher` — skip enricher during MC iterations

---

## Setup

*(The rest of the original documentation continues below...)*

There are **two ways** to run MethylValidation:

1. **Docker container** — Run inside the MethylPipeline image.
2. **Local host with virtual environment** — Create and activate a venv.

*(Original setup, config, outputs, and troubleshooting sections follow...)*
