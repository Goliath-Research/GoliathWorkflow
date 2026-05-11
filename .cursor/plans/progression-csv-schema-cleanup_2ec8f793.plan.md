---
name: progression-csv-schema-cleanup
overview: Simplify progression long-table CSV exports by removing redundant columns and normalizing stage/comparison identifiers, while updating label computation and docs/tests to match the new schema.
todos:
  - id: refactor-long-table-builders
    content: Refactor progression row builders to emit minimal per-file schemas and remove redundant columns.
    status: pending
  - id: update-label-aggregation
    content: Update compute_progression_labels to work with new long-table schemas.
    status: pending
  - id: docs-schema-update
    content: Update methyldiseaseprogression README to document new CSV columns.
    status: pending
  - id: tests-schema-assertions
    content: Add/adjust progression tests to assert cleaned CSV schema and behavior.
    status: pending
  - id: validate-progression-suite
    content: Run progression tests and verify generated CSV headers/summary integrity.
    status: pending
isProject: false
---

# Simplify Progression Long CSV Schema

## Goal
Clean `genes_long.csv`, `pathways_long.csv`, and `modules_long.csv` by removing redundant/empty columns and using canonical comparison identifiers so downstream validation tables are easier to consume.

## Current Findings
- All three row-builders in [`packages/methyldiseaseprogression/methyl_disease_progression/progression.py`](packages/methyldiseaseprogression/methyl_disease_progression/progression.py) emit a shared column set including redundant fields:
  - `entity_type` (constant per file)
  - `entity_id` == `entity_label` for module/pathway rows
  - `comparison_label` duplicates `disease_group` in typical configs
  - `control_group` often constant across rows
  - `q_value` is always empty for genes/modules
  - `source_file` is mostly provenance noise for this use case
- `compute_progression_labels()` currently expects `entity_type` and `entity_id`; this logic must be adjusted if those fields are removed from long tables.
- Tests currently verify file existence and progression ordering, but not strict long-table schemas; schema assertions should be added.

## Proposed Output Schema
For each long table (`genes_long`, `pathways_long`, `modules_long`), keep only analysis-relevant fields:
- `stage_index`
- `comparison` (canonical stage token)
- `rank`
- `score`
- entity name column (`gene`, `pathway`, `module`)

Drop:
- `entity_type`, `entity_id`, `entity_label`, `disease_group`, `control_group`, `q_value`, `source_file`, `comparison_label`.

Notes:
- `comparison` will be populated from `StageSpec.comparison_label` (already canonicalized in `resolve_stage_specs`).
- For pathways, keep `score` only (derived from q-value when available); do not export raw `q_value` column.

## Implementation Steps
1. **Refactor row builders in progression.py**
   - Update `_build_gene_rows`, `_build_pathway_rows`, `_build_module_rows` to emit only the new minimal columns and file-specific entity column names.
   - Ensure sorting/ranking behavior is preserved.

2. **Adapt progression label computation**
   - Update `compute_progression_labels()` to consume the new entity columns instead of generic `entity_type/entity_id/entity_label`.
   - Preserve output of `entities_progression_labels.csv` and monotonic/stability label logic.

3. **Keep summary/report compatibility**
   - Ensure `run_progression_report()` summary keys (`*_long_csv`, row counts) remain unchanged.
   - Confirm markdown report generation still works from `labels_df` and summary metadata.

4. **Update docs**
   - Update [`packages/methyldiseaseprogression/README.md`](packages/methyldiseaseprogression/README.md) to document the new long-table column layout and removed legacy fields.

5. **Add/adjust tests**
   - Extend [`packages/methyldiseaseprogression/tests/test_progression.py`](packages/methyldiseaseprogression/tests/test_progression.py) with assertions on long-table columns and semantic values.
   - Add one regression assertion that module rows no longer include redundant columns.

## Validation
- Run progression tests:
  - `packages/methyldiseaseprogression/tests/test_progression.py`
- Sanity-check generated CSV headers from a test run to confirm removed columns are absent and required columns are present.
- Confirm no breakage in progression summary JSON generation.

## Expected Outcome
- Long-table exports are compact and directly useful for stable DMP/gene/pathway/module validation.
- Redundant metadata columns are removed.
- Stage identifiers are unambiguous and consistent via canonical `comparison` values.