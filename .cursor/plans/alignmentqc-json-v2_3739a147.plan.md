---
name: alignmentqc-json-v2
overview: Define a versioned, row-oriented MethylAlignmentQC JSON schema optimized for downstream tools and Azure SQL JSON querying, and add a converter CLI to migrate existing V1 outputs to V2.
todos:
  - id: define-v2-model-schema
    content: Design and add row-oriented V2 Pydantic models plus generated JSON schema artifact.
    status: pending
  - id: implement-v1-to-v2-converter
    content: Implement deterministic V1->V2 converter utility with dry-run/apply/backup semantics.
    status: pending
  - id: add-converter-cli
    content: Expose converter through a dedicated CLI entrypoint in pyproject.
    status: pending
  - id: add-v2-validation-tests
    content: Add unit tests for transposition correctness, idempotency, and schema validation.
    status: pending
  - id: update-docs-azure-sql-guidance
    content: Document V2 format and Azure SQL OPENJSON usage examples in package docs.
    status: pending
isProject: false
---

# MethylAlignmentQC JSON V2 Plan

## Scope
Deliver a canonical `row-oriented` V2 export format for `methylalignmentqc`, keep V1 readable, and provide a deterministic `v1 -> v2` conversion CLI for historical files.

## Current Baseline (to preserve compatibility)
- Canonical V1 model/schema source:
  - [`/home/ubuntu/MethylPipeline/packages/methylalignmentqc/methyl_alignment_qc/models/sample_qc.py`](/home/ubuntu/MethylPipeline/packages/methylalignmentqc/methyl_alignment_qc/models/sample_qc.py)
  - [`/home/ubuntu/MethylPipeline/packages/methylalignmentqc/schemas/exported_sample_qc.schema.json`](/home/ubuntu/MethylPipeline/packages/methylalignmentqc/schemas/exported_sample_qc.schema.json)
- V1 payload currently uses many columnar sections (`field -> array`), which are valid but awkward for SQL `OPENJSON` table shredding.
- Existing migration pattern is already present for guardrails:
  - [`/home/ubuntu/MethylPipeline/packages/methylalignmentqc/methyl_alignment_qc/utils/guardrail_migration.py`](/home/ubuntu/MethylPipeline/packages/methylalignmentqc/methyl_alignment_qc/utils/guardrail_migration.py)

## Target V2 Schema Design
- Introduce top-level metadata:
  - `schema_name` (e.g., `methylalignmentqc.sample_qc`)
  - `schema_version` (e.g., `2.0.0`)
  - `exported_at_utc`
  - `producer` `{package, version}`
- Keep scalar metric blocks as objects where already natural (`quality_yield`, `gc_bias_summary`, `summary_stats`, `conversion_log`, `guardrails`).
- Convert chart/table-oriented blocks from columnar arrays into arrays of row objects:
  - `mean_quality_by_cycle.rows: [{cycle, mean_quality}]`
  - `quality_score_distribution.rows: [{q, count_of_q}]`
  - `base_distribution_by_cycle.rows: [{cycle, pct_a, pct_c, pct_g, pct_t, pct_n}]`
  - `gc_bias_details.rows: [{gc, windows, read_starts, mean_base_quality, normalized_coverage, error_bar}]`
  - `insert_size_histogram.rows: [{insert_size, pair_orientation, all_reads_fr_count, value?, all_sets?, optical_sets?, non_optical_sets?}]`
  - `error_summaries.rows: [{ref, alt, count, rate, qscore}]`
  - `pre_adapter_summaries.rows` and `bait_bias_summaries.rows`
  - `duplication_histogram.rows: [{bin, value, all_sets?, optical_sets?, non_optical_sets?}]`
- Normalize key casing for V2 (snake_case for new row fields) while preserving semantic meaning.

## Implementation Workstreams
1. **Add V2 models and schema export**
   - Add `sample_qc_v2.py` model definitions and a generated schema artifact `exported_sample_qc_v2.schema.json`.
   - Extend schema export utility so V1 and V2 artifacts can be generated predictably.

2. **Build conversion engine (`v1 -> v2`)**
   - Create a new utility module (parallel to guardrail migration utility) that:
     - detects V1 payloads,
     - transposes columnar arrays to row arrays,
     - preserves required scalar blocks,
     - writes `schema_version=2.0.0` metadata.
   - Add dry-run/apply/backup behavior matching current migration utility ergonomics.

3. **Add CLI entrypoint for conversion**
   - Add a dedicated command (e.g., `methyl-qc-convert-v1-to-v2`) in [`/home/ubuntu/MethylPipeline/packages/methylalignmentqc/pyproject.toml`](/home/ubuntu/MethylPipeline/packages/methylalignmentqc/pyproject.toml).
   - Support file or directory targets, recursive scanning, clear status reporting.

4. **Wire optional V2 validation path**
   - Reuse schema validation plumbing to validate converted outputs against V2 model/schema.
   - Keep existing `methyl-qc` writer behavior unchanged unless explicitly asked later.

5. **Docs and migration guidance**
   - Update:
     - [`/home/ubuntu/MethylPipeline/packages/methylalignmentqc/docs/USAGE.md`](/home/ubuntu/MethylPipeline/packages/methylalignmentqc/docs/USAGE.md)
     - [`/home/ubuntu/MethylPipeline/packages/methylalignmentqc/docs/IMPLEMENTATION.md`](/home/ubuntu/MethylPipeline/packages/methylalignmentqc/docs/IMPLEMENTATION.md)
   - Document Azure SQL query examples with `OPENJSON` against row arrays.

6. **Test coverage**
   - Add unit tests for:
     - per-section transposition correctness,
     - round-trip invariants for key metrics,
     - CLI dry-run/apply/backup behavior,
     - schema validation success/failure for V2.

## Azure SQL-Oriented Acceptance Criteria
- Converted V2 payload supports direct shredding with one `OPENJSON` per row-array section (no zip-by-index reconstruction).
- Representative queries for charts/tables use stable JSON paths and typed projections.
- Converter is idempotent for already-V2 files and fails clearly on malformed inputs.

## Planned File Touches
- Existing:
  - [`/home/ubuntu/MethylPipeline/packages/methylalignmentqc/methyl_alignment_qc/models/sample_qc.py`](/home/ubuntu/MethylPipeline/packages/methylalignmentqc/methyl_alignment_qc/models/sample_qc.py) (shared type reuse only if needed)
  - [`/home/ubuntu/MethylPipeline/packages/methylalignmentqc/methyl_alignment_qc/utils/schema_export.py`](/home/ubuntu/MethylPipeline/packages/methylalignmentqc/methyl_alignment_qc/utils/schema_export.py)
  - [`/home/ubuntu/MethylPipeline/packages/methylalignmentqc/pyproject.toml`](/home/ubuntu/MethylPipeline/packages/methylalignmentqc/pyproject.toml)
  - [`/home/ubuntu/MethylPipeline/packages/methylalignmentqc/docs/USAGE.md`](/home/ubuntu/MethylPipeline/packages/methylalignmentqc/docs/USAGE.md)
  - [`/home/ubuntu/MethylPipeline/packages/methylalignmentqc/docs/IMPLEMENTATION.md`](/home/ubuntu/MethylPipeline/packages/methylalignmentqc/docs/IMPLEMENTATION.md)
- New:
  - `.../models/sample_qc_v2.py`
  - `.../schemas/exported_sample_qc_v2.schema.json`
  - `.../utils/v1_to_v2_migration.py`
  - `.../tests/test_v1_to_v2_migration.py`
