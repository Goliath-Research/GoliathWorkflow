---
name: HiTIMED hierarchical deconvolution
overview: "Add a HiTIMED-style hierarchical, tree-structured deconvolution as a selectable method inside the existing pipeline.cell_deconvolution action, reusing the Houseman constrained-projection core at each tree split. The tree is analyte-driven: buffy coat resolves to an immune/leukocyte subtree (no tumor); cfDNA resolves to a tumor-vs-non-tumor top split over that immune subtree using a dedicated plasma atlas; tissue/tumor analytes resolve to the full tumor/immune/stromal tree. Output stays the same cell_fractions.csv covariate contract."

> **Status: IMPLEMENTED.** `method: houseman | hitimed` switch on `pipeline.cell_deconvolution`; hierarchical solver reuses `houseman_qp` per node; buffy-coat immune subtree ships in the wheel (derived from the real IDOL basis); cfDNA/tissue trees are composed offline from operator-supplied tumor/plasma atlases.

azure_devops:
  type: Feature
  title: "HiTIMED hierarchical cell-type deconvolution"
  work_item_id: null
  epic_id: 413
todos:
  - id: hierarchy-core
    content: "core/hitimed.py: HierarchyBasis, load_hierarchy_basis, recursive hitimed_deconvolve reusing houseman_qp; single-pass marker extract"
    status: completed
  - id: config-method
    content: Extend CellDeconvStepConfig/RuntimeParams with method, hierarchy_basis_path, analyte (default via project primary_analyte)
    status: completed
  - id: runner-dispatch
    content: Dispatch houseman vs hitimed in runner.py; same CSV contract + manifest records method/analyte/tree
    status: completed
  - id: bases-build
    content: Wheel-packaged hitimed_blood_extended_v1.json + build_hitimed_basis.py / build_cfdna_atlas_basis.py; pyproject include
    status: completed
  - id: schema-export
    content: Regenerate schemas/config/cell_deconvolution.schema.json; catalog/task-model/collector unchanged
    status: completed
  - id: profile-covariates
    content: cell_deconv_hitimed profile with method=hitimed and ALR composition covariates; cfDNA adds tumor_fraction
    status: completed
  - id: tests
    content: "test_hitimed.py: tree recovery, analyte selection, low-tumor cfDNA, partial/insufficient, Houseman regression"
    status: completed
  - id: docs-promote
    content: Update BuffyCoat research doc for the method switch and analyte-driven tree; promote plan + README row
    status: completed
---

# Integrate HiTIMED hierarchical deconvolution alongside Houseman

## Why hierarchical, and what it produces

Flat Houseman does one constrained projection against the 6-cell IDOL basis (`CD8T, CD4T, NK, Bcell, Mono, Neu`) in [`houseman.py`](../../packages/methyldeconv/methyl_deconv/core/houseman.py). HiTIMED's idea is a **tree of small deconvolutions**: at each node split a parent compartment into its children with a node-specific marker basis, then multiply proportions down the path so leaves sum to 1. Each split is the same `houseman_qp` — no new math.

Analyte-driven tree (root chosen by `analyte_trees` in the basis JSON):

- **Buffy coat** (`primary_analyte = buffy_coat`): the **immune/leukocyte subtree** only. No tumor/stromal layer (blood has no tumor DNA).
- **cfDNA** (`primary_analyte = cfdna`): plasma is mostly hematopoietic background with a **low ctDNA fraction**. A two-compartment top split (`tumor_fraction` vs `immune`) from a dedicated plasma atlas descends into the shared immune subtree. Tumor is a single lumped leaf; leaves = `tumor_fraction` + immune leaves (renormalized to 1), exposing ctDNA burden as a covariate.
- **Tissue/tumor** (`primary_analyte = tissue`): the full tumor / immune / stromal tree over the immune subtree.

All three share the one immune subtree; only the top layer differs.

## What shipped

| Piece | Location |
|-------|----------|
| Hierarchical solver | [`packages/methyldeconv/methyl_deconv/core/hitimed.py`](../../packages/methyldeconv/methyl_deconv/core/hitimed.py) — `HierarchyBasis`, `load_hierarchy_basis`, `hitimed_deconvolve`, `deconvolve_sample_hierarchical` |
| Method switch | [`config.py`](../../packages/methyldeconv/methyl_deconv/config.py) — `method`, `hierarchy_basis_path`, `analyte` on `CellDeconvStepConfig`; carried on `CellDeconvRuntimeParams` |
| Dispatch | [`core/runner.py`](../../packages/methyldeconv/methyl_deconv/core/runner.py) — `_run_houseman` / `_run_hitimed`; same CSV + manifest with `method`/`analyte`/`tree_root` |
| Analyte default | [`project_resolver.py`](../../packages/methyldeconv/methyl_deconv/project_resolver.py) — fills `analyte` from `project.get_primary_analyte()` when hitimed and unset |
| Blood basis (shipped) | `packages/methyldeconv/methyl_deconv/data/hitimed_blood_extended_v1.json` (derived from the real IDOL basis) |
| Build scripts | [`build_hitimed_basis.py`](../../packages/methyldeconv/methyl_deconv/scripts/build_hitimed_basis.py) (blood, from IDOL) and [`build_cfdna_atlas_basis.py`](../../packages/methyldeconv/methyl_deconv/scripts/build_cfdna_atlas_basis.py) (cfDNA top split from an operator-supplied plasma atlas) |
| Schema | `schemas/config/cell_deconvolution.schema.json` (regenerated) |
| Profile | `workflow_engine/domain/profiles/cell_deconv_hitimed.profile.json` (`method=hitimed`, ALR composition covariates) |
| Tests | [`tests/test_hitimed.py`](../../packages/methyldeconv/tests/test_hitimed.py) — 8 tests; full package suite 22 passed |

## Design decisions (locked)

- Single action `pipeline.cell_deconvolution` with `method: houseman | hitimed` (default `houseman`), not a new action.
- Hierarchical bases are wheel-packaged JSON like the IDOL basis, with a `hierarchy_basis_path` override.
- Output stays `{output_base}/cell_fractions/cell_fractions.csv`; only the column set grows, so the ECDF/tabular `covariates_path` contract is unchanged.
- No fabricated tumor methylation: cfDNA/tissue tumor betas come from operator-supplied atlases composed offline; only the blood immune subtree (from measured IDOL data) ships in the wheel.

## Basis JSON (v2) contract

```json
{
  "schema_version": 2,
  "basis_kind": "hierarchy",
  "analyte_trees": {"buffy_coat": "immune", "cfdna": "plasma", "tissue": "tissue_root"},
  "nodes": {
    "<node>": {
      "children": ["childA", "childB"],
      "markers": [{"probe_id": "...", "chrom": "1", "pos": 123, "betas": {"childA": 0.9, "childB": 0.1}}]
    }
  }
}
```

A child id that is not itself a node is a terminal leaf (a `cell_fractions.csv` column). Leaf order is deterministic depth-first from the analyte root.

## Out of scope
- No R/`rpy2` at worker runtime; bases are built offline.
- No objective/stability changes; deconvolution stays deterministic and MC-free.
- No `wf`/`cfg` schema changes beyond regenerating the committed config JSON schema.
- The full tissue (`hitimed_full_v1.json`) and cfDNA (`cfdna_plasma_atlas_v1.json`) bases are composed by the build scripts from external atlases and are not committed until those atlases are provisioned.
