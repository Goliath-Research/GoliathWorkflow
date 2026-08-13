---
name: Model-MC centroid reuse
overview: Stop rebuilding centroids in model-MC shared when stability splits (and centroids) are reusable but detections must be rebuilt under a frozen panel; stop writing legacy val_* holdout CSV aliases and use test_* as the sole on-disk canonical names.

> **Status: IMPLEMENTED.** Selective centroid reuse lives in `_build_model_mc_shared_runs`; new runs write only `test_*` holdout files.

azure_devops:
  type: Feature
  title: "Model-MC centroid reuse + drop val_* aliases"
  work_item_id: null
  epic_id: 413
todos:
  - id: selective-reuse
    content: Split centroid vs detection reuse in _build_model_mc_shared_runs; symlink centroids + skip_centroid=True when detections need rebuild
    status: completed
    work_item_id: null
  - id: link-helper
    content: Allow link_run_artifacts_from_source to link centroids-only; update _shared_run_ready for selective resume
    status: completed
    work_item_id: null
  - id: reuse-tests
    content: Add/update model-MC shared tests for selective reuse, full reuse, and strict fail
    status: completed
    work_item_id: null
  - id: stop-val-write
    content: Stop writing val_*/testing_* copies in project_gen and holdout_eval; return/copy test_* only
    status: completed
    work_item_id: null
  - id: retarget-readers
    content: Prefer test_* in gene_featurecuts, executor counters, worker multiclass, CLI skip-centroid; keep reuse_splits fallback
    status: completed
    work_item_id: null
  - id: docs-tests-val
    content: Update tests/docs that assert or describe val_* aliases; promote plan under docs/plans + README
    status: completed
    work_item_id: null
---

# Model-MC centroid reuse + drop val_* aliases

> **Status: IMPLEMENTED.**

## Problem

1. **Centroids:** After discovery-only stability + freeze, model-MC shared reuses train/test **splits** but rebuilt **both** centroids and detections because detection contract differs (`discovery_only` vs `fixed_dmp_panel`). Same train membership ⇒ same centroids; frozen-panel detector only **reads** centroids to intersect the panel.

2. **`val_*`:** `generate_run_project` already wrote `test_*`, then byte-copied `val_*`.

## Locked decisions

- **Automatic** selective reuse when: split source is `reused`, primary `centroids/` exists, detections are **not** reusable. No new operator flag.
- **Symlink** primary centroids into `model_mc/shared/run_XXXX/centroids`.
- **`requireArtifactReuse: true`** stays strict.
- **Stop writing** `val_*` / `testing_*` copies. Keep **read** fallbacks in split-reuse loaders.

## Implementation

- [`packages/methylvalidation/methyl_validation/cli.py`](../../packages/methylvalidation/methyl_validation/cli.py) — `_can_reuse_centroids` / `_can_reuse_detections`; selective `skip_centroid=True`
- [`packages/methylvalidation/methyl_validation/project_gen.py`](../../packages/methylvalidation/methyl_validation/project_gen.py) — `link_run_artifacts_from_source(..., artifacts=...)`; no `val_*` writers
- Tests in [`packages/methylvalidation/tests/test_cli_resume.py`](../../packages/methylvalidation/tests/test_cli_resume.py)
