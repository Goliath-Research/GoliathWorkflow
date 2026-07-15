---
name: Cell Fraction Group Column
overview: Add the resolved project subgroup label to every `cell_fractions.csv` row, producing `all` / `PCa` for the current project while preserving existing sample ordering and deduplication.
azure_devops:
  type: Feature
  title: "Cell fraction group column"
  work_item_id: null
  epic_id: 413
todos:
  - id: propagate-group-label
    content: Propagate resolved subgroup labels into the deconvolution sample contract and CSV output
    status: completed
    work_item_id: null
  - id: verify-group-column
    content: Add regression coverage, update usage documentation, and run deconvolution tests
    status: completed
    work_item_id: null
---

# Cell Fraction Group Column

> **Status: IMPLEMENTED.** Group propagation, CSV output, regression coverage, and usage documentation are complete.

## Implementation
- Update [`packages/methyldeconv/methyl_deconv/project_resolver.py`](../../packages/methyldeconv/methyl_deconv/project_resolver.py) so resolved samples carry `(sample_id, sample_dir, group_label)`, following the established pattern in `methylinfotheory`.
- Update [`packages/methyldeconv/methyl_deconv/core/runner.py`](../../packages/methyldeconv/methyl_deconv/core/runner.py) to write `group` immediately after `sample_id`; the remaining six fractions and diagnostics retain their current order. `n_columns` consequently becomes 11.
- Preserve current duplicate handling: if a sample appears in multiple resolved groups, the first resolved group wins.

## Verification and documentation
- Extend [`packages/methyldeconv/tests/test_runner_h5.py`](../../packages/methyldeconv/tests/test_runner_h5.py) to verify group propagation and stable CSV column order.
- Add resolver coverage for multiple groups and deduplication, then run the complete `packages/methyldeconv/tests` suite and lint checks.
- Update [`packages/methyldeconv/docs/USAGE.md`](../../packages/methyldeconv/docs/USAGE.md) to document the new column and note that existing CSVs require a rerun.
