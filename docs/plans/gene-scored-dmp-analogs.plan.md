---
name: Gene scored dmp analogs
overview: Extend gene_scored with gene-level analogs of the dmp_scored centroid/directional aggregates (cosine distance/similarity, contrast, max directional, agreement), keeping existing gene_scored summaries and deferring histogram-based healthy_tail_evidence.

> **Status: IMPLEMENTED.** `gene_scored` emits `gene_max_weighted_directional_score`, `gene_weighted_centroid_contrast_score`, per-cancer agreement/cosine-similarity, and per-class cosine-distance columns (schema `gene_scored_v6_centroid_analogs`). No study contexts changed to `dmp_scored+gene_scored`.

azure_devops:
  type: Feature
  title: "Gene-level analogs of dmp_scored features"
  work_item_id: null
  epic_id: 413
todos:
  - id: gene-centroid-compute
    content: Implement gene-level centroid/directional feature compute + names in gene_scored_features.py
    status: completed
    work_item_id: null
  - id: wire-observed-hybrid
    content: Wire names + fill into observed_feature_builder gene_scored path; bump schema version
    status: completed
    work_item_id: null
  - id: tests
    content: Unit + hybrid/tabular tests for new gene_ features and no collision with dmp_scored
    status: completed
    work_item_id: null
  - id: docs-promo
    content: Document gene_scored additions; promote plan to docs/plans/
    status: completed
    work_item_id: null
---

# Gene-level analogs of dmp_scored features

## Delivered

- [`gene_scored_features.py`](../../packages/methylvalidation/methyl_validation/gene_scored_features.py): `compute_gene_scored_centroid_features`, name helpers, schema `gene_scored_v6_centroid_analogs`.
- [`observed_feature_builder.py`](../../packages/methylvalidation/methyl_validation/observed_feature_builder.py): wire into `gene_scored` path; extract class centroids whenever gene_scored is on; bump `observed_hybrid_v30_gene_scored_centroid_analogs`.
- Tests in `test_observed_feature_builder.py`; docs in USAGE / IMPLEMENTATION.

## Out of scope (unchanged)

- Gene-level `weighted_healthy_tail_evidence`.
- Any prostate (or other) context flip to `dmp_scored+gene_scored`.
