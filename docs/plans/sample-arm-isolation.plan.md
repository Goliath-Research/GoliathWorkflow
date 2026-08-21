---
name: Sample Arm Isolation
overview: "Make production SamplePrep bind each alignment method to its documented arm leaf (`align.linear.parabricks/`, etc.) so switching engines cannot clobber another method’s BAM/QC/H5. Do not change live instance 67; relocate that run’s root Clara products into `align.linear.parabricks/` after it finishes."

> **Status: Implemented** — production bind via `methyl_utils.sample_arm_layout` + `finalize_instance_context` / `sample_lifecycle`. Relocate script is ops-only and must not be run against live instance 67.

azure_devops:
  type: Feature
  title: "Production alignment-arm isolation"
  work_item_id:
  epic_id: 413
todos:
  - id: promote-arm-helper
    content: Promote align-arm maps from testing into methyl_utils.sample_arm_layout; compare helpers wrap it
    status: completed
  - id: planner-bind-arm
    content: Planner + sample_lifecycle emit sampleRoot + sampleDir={root}/{arm} after finalize_instance_context; explicit sampleDir still wins
    status: completed
  - id: fastq-caas-split
    content: download_fastq to sampleRoot then link into arm; CAAS store at sampleRoot; output_dir/products at arm; delete_fastqs vs delete_bam split
    status: completed
  - id: caas-product-symlinks
    content: Always restore {id}.bam / qc-metrics.tar / json as product symlinks after CAAS harvest/skip
    status: completed
  - id: qc-parser-arm-dirs
    content: methyl_qc parser treats align.* as mode leaves so sampleId is not the arm folder name
    status: completed
  - id: contracts-docs-tests
    content: Update SamplePrep contracts/docs from flat root to arm layout; planner/CAAS/QC tests; promote plan under AB#413
    status: completed
  - id: post-67-relocate
    content: "After instance 67 finishes: relocate root Clara products into align.linear.parabricks without deleting historical align.* trees"
    status: completed
---

# Production alignment-arm isolation

See Cursor plan `sample_arm_isolation_a5a3079e` for the original write-up. Implementation notes:

- Production helper: [`packages/methylutils/methyl_utils/sample_arm_layout.py`](../../packages/methylutils/methyl_utils/sample_arm_layout.py)
- Bind after finalize: [`workflow_engine/ops/sample_lifecycle.py`](../../workflow_engine/ops/sample_lifecycle.py) and [`workflow_engine/domain/workflow_context.py`](../../workflow_engine/domain/workflow_context.py)
- Layout contract: [`docs/architecture/sample-prep-tooling.md`](../architecture/sample-prep-tooling.md)
- Post-67 relocate (do not run while instance 67 is live): [`scripts/relocate_root_clara_products.py`](../../scripts/relocate_root_clara_products.py)

Hard rules: do not reopen instance 59; do not rewrite baked instance 67 tasks; do not flip production site defaults.
