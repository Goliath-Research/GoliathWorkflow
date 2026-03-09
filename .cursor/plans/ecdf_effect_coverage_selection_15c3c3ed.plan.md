---
name: ECDF effect coverage selection
overview: "Replace the four independent biological filter thresholds (min_delta_mean, max_overlap, min_effect_size, effect_size_quantile) with a single data-adaptive ECDF cumulative mass selection: given effect sizes sorted descending, keep the minimum set of positions whose effects sum to a target fraction of total effect mass, applied independently per context."
todos:
  - id: config-replace-bio-params
    content: "In config.py: remove min_delta_mean, max_overlap, min_effect_size, effect_size_quantile; add effect_size_coverage; simplify FilterFunnelExplore to one field"
    status: pending
  - id: detector-coverage-fn
    content: Replace _apply_biological_filters with _select_by_effect_coverage (per-context cumulative mass selection) in methyldetector.py
    status: pending
  - id: detector-filter-bio
    content: Replace _filter_biological_dmps body to use _select_by_effect_coverage with logging of per-context retention
    status: pending
  - id: detector-funnel-sweep
    content: Simplify _run_filter_funnel_sweep to sweep a single effect_size_coverage range, updating CSV columns accordingly
    status: pending
  - id: config-json-update
    content: Update configs/project_Healthy_vs_PCa1-4.json to replace old bio filter params with effect_size_coverage
    status: pending
isProject: false
---

# ECDF Effect-Coverage Biological Selection

## The Simplified 3-Stage Funnel

```
Stage 1  delta_mean_reduction gate   cheap coarse filter before statistical test
Stage 2  Mann-Whitney → FDR (q ≤ α)  statistical gate (from assumption-free plan)
Stage 3  ECDF coverage selection      data-adaptive biological selection  ← this plan
```

## Algorithm (Stage 3)

Applied **per context group** (CG, CHG, CHH separately) to prevent CG from dominating:

```python
def select_by_effect_coverage(effects, coverage_target):
    if len(effects) == 0 or effects.sum() == 0:
        return np.zeros(len(effects), dtype=bool)
    order = np.argsort(-effects)               # descending
    cumulative = np.cumsum(effects[order]) / effects.sum()
    K = np.searchsorted(cumulative, coverage_target) + 1
    keep = np.zeros(len(effects), dtype=bool)
    keep[order[:K]] = True
    return keep
```

Config parameter: `effect_size_coverage: float = 0.95`
Meaning: "select the minimum number of DMPs whose combined effect explains ≥95% of total biological effect mass within this context."

### Edge cases

- `S == 0` (all effect_sizes zero): return empty — no signal.
- `m == 1`: always kept — contributes 100%.
- Uniform effects (all equal): keeps `ceil(coverage × m)` positions — correct, since they're genuinely indistinguishable.
- `coverage_target == 1.0`: keeps all statistical DMPs — equivalent to no biological filter.

### Why per-context grouping is mandatory

`_filter_biological_dmps` receives the **combined multi-context DataFrame** (`pd.concat` of CG + CHG + CHH at line 206 of `methyldetector.py`). Effect sizes are not cross-context comparable — CG positions have systematically larger effects. Without per-context grouping, `coverage_target=0.95` would select only CG positions and zero CHG/CHH positions. The groupby over `dmps_df['context']` before selection fixes this.

---

## Changes Required

### 1. `[packages/methyldetector/methyl_detector/models/config.py](packages/methyldetector/methyl_detector/models/config.py)`

**Remove** (lines ~236–267):

```python
min_effect_size: Optional[float]
effect_size_quantile: Optional[float]
min_delta_mean: Optional[float]
max_overlap: Optional[float]
```

**Add**:

```python
effect_size_coverage: float = Field(
    default=0.95, ge=0.0, le=1.0,
    description=(
        "Biological filter: select the minimum set of statistical DMPs (per context) "
        "whose effect sizes sum to this fraction of total effect mass. "
        "1.0 = keep all statistical DMPs; 0.9 = keep the top-90%% mass. "
        "Applied per-context so CG/CHG/CHH are selected independently."
    )
)
```

**Simplify `FilterFunnelExplore`** (lines ~39–59): replace three `FilterFunnelRangeSpec` fields with one:

```python
class FilterFunnelExplore(BaseModel):
    mode: Literal["one_at_a_time", "full_grid"] = "one_at_a_time"
    effect_size_coverage: Optional[FilterFunnelRangeSpec] = Field(
        default=None,
        description="Range/step for effect_size_coverage (e.g. min=0.80, max=0.99, step=0.05)"
    )
```

`delta_mean_reduction` and `lambda_var` stay unchanged — they belong to a different stage.

### 2. `[packages/methyldetector/methyl_detector/core/methyldetector.py](packages/methyldetector/methyl_detector/core/methyldetector.py)`

**Replace `_apply_biological_filters` (lines 60–80)** with:

```python
def _select_by_effect_coverage(df: pd.DataFrame, coverage: float) -> pd.DataFrame:
    """Per-context ECDF cumulative mass selection on effect_size."""
    if len(df) == 0 or "effect_size" not in df.columns:
        return df
    keep_idx = []
    for ctx, grp in df.groupby("context", sort=False):
        effects = grp["effect_size"].astype(float).values
        S = effects.sum()
        if S == 0:
            continue
        order = np.argsort(-effects)
        cumulative = np.cumsum(effects[order]) / S
        K = int(np.searchsorted(cumulative, coverage)) + 1
        keep_idx.extend(grp.index[order[:K]].tolist())
    return df.loc[keep_idx].copy()
```

**Replace `_filter_biological_dmps` (lines 719–797)**: simplify body to call `_select_by_effect_coverage(dmps_df, self.config.effect_size_coverage)` and retain only the logging of per-context counts and value ranges.

**Replace `_run_filter_funnel_sweep` (lines 808–901)**: the sweep now iterates over a single range (`effect_size_coverage`), calling `_select_by_effect_coverage(dmps_df, v)` for each value `v`. The output CSV columns become: `n_statistical_dmps`, `effect_size_coverage`, `n_biological_dmps` (per context or total).

### 3. `[configs/project_Healthy_vs_PCa1-4.json](configs/project_Healthy_vs_PCa1-4.json)`

In the detection block, replace any `min_delta_mean`, `max_overlap`, `min_effect_size`, `effect_size_quantile` keys with `effect_size_coverage: 0.95` (or appropriate value determined by a funnel sweep).

---

## What is NOT changed

- `delta_mean_reduction` — coarse Stage-1 gate before the statistical test; different purpose.
- `alpha` — q-value threshold for Stage-2.
- `lambda_var` — controls the variance penalty inside `effect_size`; still needed.
- `effect_size_from_components` computation — unchanged.
- Continuous ECDF overlap integral (`ecdf_overlap_integral`) — unchanged; `overlap` stays as a column for interpretability but is no longer a filter gate.
- Per-chromosome output files and classifier training — unaffected.

---

## Interaction With the Assumption-Free Funnel Plan

That plan's biological-only rescue track proposed explicit thresholds (`biological_only_min_effect_size`, etc.) for positions failing the statistical gate. With this plan, those explicit thresholds are also replaced: the rescue track would call the same `_select_by_effect_coverage` on positions with `q_value > alpha`, with a stricter `coverage_target` (e.g., 0.80 instead of 0.95) to only admit very strong biological signals.