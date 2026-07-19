---
name: Release-stable Tier-A ops
overview: Confirm Buffy Tier-A work does not touch wf/cfg schemas; treat the two package edits as worker-side platform capability, and keep all Buffy experimentation as JSON/CLIs on /work against a promoted release—not study-specific source forks.

> **Status: IMPLEMENTED.** Runbook and hyperparam docs document the release-stable boundary; `run_slice1_search.sh` prefers the release venv when gene-FC BA scoring is present and falls back to repo `.venv` until the next promote.

azure_devops:
  type: Feature
  title: "Release-stable Tier-A experimentation"
  epic_id: 413
todos:
  - id: docs-release-boundary
    content: "Document in Buffy runbook: no DB schema impact; experiment=/work JSON; package fixes are release-bound platform capability"
    status: completed
  - id: docs-hyperparam-gene-fc
    content: Update hyperparam search usage docs for gene_featurecuts_metrics objective fallback
    status: completed
  - id: ops-release-pin
    content: "After next promote: pin run_slice1_search.sh / runbook to release venv + runtime-bundle (not repo .venv)"
    status: completed
---

# Release-stable Tier-A experimentation (no DB / no study forks)

## Your mental model is correct

| Layer | Touched by Buffy Tier-A? |
|-------|--------------------------|
| `wf` / `cfg` schemas, gateway, action catalog, worker task models | **No** |
| Study / experiment JSON under `/work/projects/prostate-cancer/` | **Yes** (intended) |
| Worker packages (`methylvalidation`, `methylgeneselect`) | **Two small platform fixes** — not disease-specific logic |

Experimentation is supposed to be: **promoted release venv + runtime-bundle + `/work` JSON + CLIs**. Operators should not patch Python per study.

## What actually required package changes

1. **Null cap precedence** (`packages/methylgeneselect/methyl_gene_select/utils/project_config.py`) — platform bug: study/MC `"max_dmps": null` could not clear site `gene_selection.max_dmps=1000`. Belongs in the next worker release. Slice-1 itself already raises caps with **explicit ints** (`20000`/`100000`), which works even on an older release via `--max-dmps`.
2. **Gene-FC BA objective fallback** (`packages/methylvalidation/methyl_validation/optimization.py`) — product gap for stability-only Tier-A: without it, every trial is `missing_metrics_summary` / infeasible. Also belongs in the worker package (generic aggregator), not a Buffy-only script.

Neither change encodes prostate/Buffy disease logic. Neither changes DB contracts.

## Intended ops model

- **Promote** the two package capabilities with the next MethylPipeline release (runtime-bundle + release venv under `/work/epimethyl/current`).
- **Run experiments only via** `/work` JSON + release `methyl-hyperparam-search` / `methyl-validation`, with DomainPrograms from `/work/epimethyl/current/runtime-bundle/`.
- **Do not** add study-specific Python, profile names, or schema migrations for Tier-A grids.

## Delivered follow-ups

1. [`docs/deployment/buffy_gene_tier_a_cross_vm.md`](../deployment/buffy_gene_tier_a_cross_vm.md) — architecture boundary; runtime-bundle paths; release venv preferred.
2. [`docs/usage/15-optional-hyperparameter-search.qmd`](../usage/15-optional-hyperparameter-search.qmd) and [`packages/methylvalidation/docs/HYPERPARAMETER_SEARCH.md`](../../packages/methylvalidation/docs/HYPERPARAMETER_SEARCH.md) — gene FeatureCuts metrics as first-class objective source.
3. `/work/projects/prostate-cancer/experiments/Buffy_ecdf_gene_covariates_tier_a/run_slice1_search.sh` — release-first with capability probe; repo `.venv` fallback until promote includes gene-FC BA scoring.
