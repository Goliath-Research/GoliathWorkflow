---
name: Typed composition ALR
overview: Introduce first-class composition (simplex) groups transformed by ALR for every K>=2 set—including binary/multiclass ECDF class probabilities and deconvolution fractions—so redundant sum-to-1 features never enter the second-stage model as raw numerics, while ordinary categorical/ordinal/numeric covariates stay unchanged.

> **Status: IMPLEMENTED.** `CompositionGroup` model + `covariate_composition_groups` on the validation backend params; the covariate preprocessor runs ALR per group (raw proportions never enter X, per-group standardize control); the ECDF second stage encodes `prob_class*` as a built-in composition group (binary == clipped class-1 logit). Legacy `covariate_composition_*` and `ecdf_second_stage_probability_transform: logit_class1` resolve to the new path. Profiles `cell_deconv`, `cell_deconv_hitimed`, and `samd_research` migrated; schemas regenerated; regression tests in `packages/methylvalidation/tests/test_composition_groups.py` and updated `test_ecdf_second_stage_covariates.py`.

azure_devops:
  type: Feature
  title: "Typed composition (simplex) ALR covariates"
  work_item_id: null
  epic_id: 413
todos:
  - id: composition-group-model
    content: Add CompositionGroup Pydantic model + covariate_composition_groups; legacy single-group + logit_class1 migration; schema export
    status: completed
    work_item_id: null
  - id: preprocessor-multi-alr
    content: Run ALR per composition group; never feed raw proportions; per-group standardize for ALR coords
    status: completed
    work_item_id: null
  - id: ecdf-prob-alr-default
    content: "Second-stage: treat prob_class* as built-in composition group with default ALR (binary == logit)"
    status: completed
    work_item_id: null
  - id: profile-migrate
    content: "Migrate cell_deconv / hitimed / SaMD-Buffy ECDF profiles: Omega in composition groups, not numeric"
    status: completed
    work_item_id: null
  - id: tests-docs-promote
    content: Regression tests, usage/theory docs, promote docs/plans/typed-composition-alr.plan.md
    status: completed
    work_item_id: null
---

# Typed composition groups with universal ALR

## Decision (locked)

Treat every sum-to-1 feature set of size $K \ge 2$ as a **composition group** and encode it with **ALR** (drop the reference part via log-ratios). Applied uniformly to:

- ECDF second-stage class probabilities (`prob_class*`)
- Houseman / HiTIMED cell fractions (and future composition sidecars)

For binary ECDF, ALR of `prob_class1` vs reference `prob_class0` is the clipped class-1 logit within epsilon; the pipeline unifies under ALR instead of a separate `logit_class1` code path.

Raw proportions never enter `X`. ALR coordinates live on $\mathbb{R}$ and may be z-scored (default on). Ordinary `numeric` / `ordinal` / `categorical` roles are unchanged.

## What shipped

| Piece | Location |
|-------|----------|
| Config model + field | [`config.py`](../../packages/methylvalidation/methyl_validation/config.py) — `CompositionGroup`, `BackendSharedParams.covariate_composition_groups`, disjointness validators |
| Multi-group ALR preprocessor | [`covariate_preprocessor.py`](../../packages/methylvalidation/methyl_validation/covariate_preprocessor.py) — `CompositionGroupSpec`, `normalize_composition_groups`, per-group ALR + per-group standardize control, frozen train/apply |
| ECDF probability ALR | [`ecdf_second_stage.py`](../../packages/methylvalidation/methyl_validation/ecdf_second_stage.py) — `_probability_design` ALR default, `resolved_composition_groups()` |
| Schemas | `schemas/config/validation*.schema.json` (regenerated) |
| Profiles | `cell_deconv.profile.json`, `cell_deconv_hitimed.profile.json`, `samd_research.profile.json` |
| Tests | `tests/test_composition_groups.py`, updated `tests/test_ecdf_second_stage_covariates.py` |
| Docs | usage ch.07, theory ch.15 (@sec-model-creation-validation), MethylValidation `USAGE.md` |

## Config contract

`covariate_composition_groups: CompositionGroup[]`, each `{name, columns (K>=2), reference?=last, pseudocount?, standardize?=true}`. Parts must be disjoint across groups and from numeric/ordinal/categorical roles.

The ECDF `prob_class*` columns are an implicit composition group (reference `prob_class0`, ALR default). Legacy `covariate_composition_*` keys map to one group named `default`; `ecdf_second_stage_probability_transform: "logit_class1"` is accepted as an alias.

## Out of scope

- Changing first-stage ECDF classification itself
- CLR / ILR alternatives
- Making the second-stage LR multiclass (still binary labels)
- Auto-inferring composition groups from column names (groups stay operator-declared, except the built-in ECDF prob group)

## Follow-on (implemented)

Composition ALR is also wired into `tabular_sklearn` and `generative_hybrid` via the same `fit_covariates(..., composition_groups=...)` path. Categorical one-hot now drops one reference level ($L \to L-1$); ordinal remains a single numeric code per column.
