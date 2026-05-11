# Stability and freeze readiness (pre-model)

After Monte Carlo **stability** and production **freeze**, review artifacts before **`--model`** so the frozen DMP panel and progression summaries support the intended disease narrative.

## What this checks

| Area | Inputs | Notes |
|------|--------|--------|
| **Stability** | `monte_carlo_runs/stability/stability_summary.json`, `stable_dmps_production.csv`, `dmp_frequency.csv` | Run counts, recurrence threshold, panel non-empty |
| **Freeze** | `monte_carlo_runs/production/production_summary.json`, `project.json`, `stable_dmps_genomewide.csv` | Step RCs, `fixed_dmp_panel`, legacy detector keys |
| **Progression** | `monte_carlo_runs/production/progression/summary.json`, `modules_long.csv`, `entities_progression_labels.csv` | Stage order, missing inputs, module score vs stage trend |
| **Balance** | Stable panel or frequency CSV | Chromosome concentration warnings |

**Important:** MC **stability** does not run disease progression; progression is produced during **freeze** (and downstream mapper/enricher) when `step_config.progression.enabled` is true. See [`USAGE.md`](USAGE.md).

## CLI

From the repo root (venv active):

```bash
methyl-stability-freeze-readiness /path/to/<project_name> [--json-out report.json] [--markdown-out report.md]
```

`<project_name>` is the directory that **contains** `monte_carlo_runs/` (e.g. `/work/prostate-cancer/Healthy_vs_PCa1-4-CG`).

Exit codes:

- `0` — overall verdict is `go` or `go_with_risks`
- `2` — overall verdict is `no_go`

## Verdicts

- **`go`** — stability and freeze checks passed; progression present and parsable without blocking gaps (warnings may still apply).
- **`go_with_risks`** — non-blocking warnings (e.g. weak module trajectory, chromosome imbalance, missing progression).
- **`no_go`** — missing stability/freeze artifacts, empty stable panel, failed freeze steps, or forbidden legacy detector keys in `production/project.json`.

Human biological review remains required before treating outputs as validated hypotheses.

## JSON output (module trajectory)

Field `progression.module_trajectory.median_abs_pearson_stage_vs_score` is the median of **absolute Pearson** correlations between stage order (comparison labels mapped to `0..K-1`) and per-module scores from `modules_long.csv`. It does **not** use Spearman rank correlation; use scipy/R separately if you need rank-based association.

## Example output

A report generated for `Healthy_vs_PCa1-4-CG` (when that tree exists on your machine) is checked in as:

- [`examples/stability_freeze_readiness_Healthy_vs_PCa1-4-CG.md`](examples/stability_freeze_readiness_Healthy_vs_PCa1-4-CG.md)

## Implementation

[`methyl_validation/stability_freeze_readiness.py`](../methyl_validation/stability_freeze_readiness.py)
