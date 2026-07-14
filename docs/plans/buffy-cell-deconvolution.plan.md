---
name: Buffy Cell Deconvolution
overview: "Simple path—pipeline.cell_deconvolution (FlowSorted.Blood.EPIC + Houseman QP) writes six leukocyte proportions per sample; always use all six as tabular model features with clinical covariates (sex/age/BMI). No control-centroid null, no Jaccard, no proportion FeatureCuts, no DMP/centroid MC."
azure_devops:
  type: Feature
  title: "Buffy-coat cell deconvolution (Houseman / FlowSorted)"
  work_item_id: null
  epic_id: 413
todos:
  - id: pkg-qp-core
    content: packages/methyldeconv — IDOL H5 extract batched for large N, Houseman QP via methyl_utils GPU stack (use_gpu + CPU fallback), cell_fractions.csv, methyl-cell-deconv CLI
    status: completed
  - id: flowsorted-basis-asset
    content: Derive WGBS/hg38 asset from FlowSorted.Blood.EPIC + IDOLOptimizedCpGs; seed_basis_path via site/profile
    status: completed
  - id: action-wiring
    content: Register pipeline.cell_deconvolution (catalog, task models, handler, schema export, seed)
    status: completed
  - id: program-profile
    content: Slim DomainProgram — cell_deconvolution; tabular profile covariates_path for Ω + clinical. Lifecycle nodes added.
    status: completed
  - id: tests
    content: QP recovery, H5 marker extract, tabular Ω+clinical join; CPU required, GPU/CuPy parity smoke via methyl_utils detection
    status: completed
  - id: docs-plan-promote
    content: Update BuffyCoat research doc for simple Ω→tabular path; promote plan under docs/plans/ + AB#413 README
    status: completed
---

# Buffy-coat cell deconvolution (simple Ω → tabular)

> **Status: IMPLEMENTED.** Packaged methyldeconv + FlowSorted IDOL asset + action/program/profile wiring.

## Design

```mermaid
flowchart LR
  H5["sample chr-ctx.h5"] --> HD["pipeline.cell_deconvolution"]
  FS["FlowSorted.Blood.EPIC + IDOL M"] --> HD
  HD --> CSV["cell_fractions.csv\n6 Omega columns"]
  Clin["clinical CSV\nsex age BMI"] --> Model["validation.model_mc\ntabular_sklearn"]
  CSV --> Model
```

| Piece | Role |
|-------|------|
| FlowSorted.Blood.EPIC + IDOL (~450 CpGs) | Published \(M\) for Houseman QP |
| Six Ω per sample (CD8T, CD4T, NK, Bcell, Mono, Neu) | Always-on features (no selection) |
| Sex, age, BMI | Covariates via existing `covariates_path` |
| Control centroid / ΔΩ / Jaccard | Not used |

Deconvolution is deterministic given sample H5 and fixed \(M\). No MC feature-panel stability loop: the feature set is fixed.

## Scale now vs later

| Concern | v1 (now) | Later (not in this plan’s delivery) |
|---------|----------|-------------------------------------|
| Cohort size | Implement deconvolution to **batch thousands of samples** efficiently (I/O + optional GPU via MethylUtils; write one `cell_fractions.csv`) | Same action; no API change expected |
| Labels / model | Wire tabular path for the **current study design** (existing binary or whatever classes the project already defines) | **Multi-class model evaluation** (OvR / multi-way metrics sweeps) — deferred; do not build a special multi-class Ω evaluator now |
| GPU | Worth wiring because N can be large even if QP is small per sample | Same |

So: **scale the deconvolution path for large N now**; **do not** expand model_mc for multi-class Ω experiments in this feature.

## Fit into current stack

| Reuse | Skip |
|-------|------|
| `covariate_preprocessor` + `tabular_sklearn` / `validation.model_mc` | `pipeline.centroid`, `pipeline.detector`, mapper, gene_select |
| Action/catalog/schema patterns from `derived_measures` | `validation.stability` Jaccard / DMP–gene frequency panels |
| **MethylUtils NVIDIA/CuPy GPU framework** (same as centroid/metrics) | Extending `samd_research` dual_fc topology |
| New slim DomainProgram (cell_deconv → model_mc) | |

Existing DMP/gene SaMD MC remains a separate track for methylation signatures.

## GPU (MethylUtils)

Do **not** invent a separate CUDA path. Follow the existing MethylUtils pattern used by centroid and metrics:

- [`methyl_utils/gpu_detection.py`](packages/methylutils/methyl_utils/gpu_detection.py) — `is_gpu_available()`, `get_cupy()`, cleanup / optional NVML
- [`methyl_utils/gpu_utils.py`](packages/methylutils/methyl_utils/gpu_utils.py) — backend array prep
- Config: `use_gpu: Optional[bool] = Field(default=None, …)` on `CellDeconvStepConfig` (operator-set; same style as centroid `use_gpu`), honor `METHYL_DISABLE_GPU` via detection helpers
- Runtime: prefer batched per-sample (or mini-batch) QP over the cohort so **thousands of samples** stay practical; CuPy when `use_gpu` for shared matrix ops / batching; else NumPy/SciPy. Per-sample QP is ~450×6 — cost is dominated by H5 marker extract × N, not the QP.

## Implementation

1. **`packages/methyldeconv/`** — IDOL extract → Houseman QP (MethylUtils GPU/CPU backend) → `cell_fractions.csv` + manifest
2. **FlowSorted asset** — offline export of IDOL probes + cell-type mean β → hg38 JSON/HDF5; `actionConfig.cell_deconvolution.seed_basis_path`
3. **`pipeline.cell_deconvolution`** — catalog, Pydantic I/O (incl. `use_gpu`), worker handler, config schema
4. **Program + profile** — slim program: deconvolution once per cohort, then `validation.model_mc` with tabular enabled, Ω as features, clinical sidecar as covariates; ECDF off
5. **Tests + docs** — CPU path required; GPU path when CuPy present (parity smoke); promote to `docs/plans/buffy-cell-deconvolution.plan.md`

## Non-goals

- Control-centroid biological null
- Jaccard / early-stop on proportion panels
- Selecting a subset of the six proportions
- Detector residualization or DMP→gene as part of this path
- R/minfi at worker runtime
- **Multi-class model evaluation** specialized for Ω (deferred; not now)
