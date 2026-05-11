# MethylAlignmentQC Usage

## CLI Entry Points

The package exposes:

- `methyl-alignment-qc`
- `methyl-qc`
- `methyl-qc-migrate-guardrails`
- `methyl-qc-export-schema`
- `methyl-qc-convert-v1-to-v2`

## Main execution modes

`methyl-qc` requires exactly one input mode:

- `--project` (optionally `--step-override`) to resolve samples/output from project config,
- `--samples` (repeatable; can be a sample dir, newline list file, or JSON array file),
- `--metrics-root` (auto-discovers `*deduplicate_metrics.txt` and derives sample dirs).

For `--samples` and `--metrics-root`, `--output-dir` is required.

Useful flags:

- `--no-validation`: skip schema validation,
- `--verbose`: print sample counts and output path.

## Typical Inputs

Typical runs require:

- one or more sample directories or a metrics root,
- Picard- or Parabricks-style duplication/alignment metrics files,
- optional WGBS Parabricks metrics JSON for initial guardrail screening via `methyl_alignment_qc/core/wgbs_parabricks_qc.py`,
- an output directory for normalized JSON summaries.

## Typical Outputs

The package writes one structured **V2** (row-oriented) JSON summary per sample and can optionally validate those files against the package schema (V1-shaped assembly is validated internally, then converted to V2 for export).
When a sample directory contains the canonical Parabricks metrics JSON file `{sample_name}.json`, `methyl-qc` uses it for metrics and guardrails; the written output in `--output-dir` is always the V2 export shape.

For initial metrics extraction workflows, use the package CLI for normalized per-sample QC JSON outputs; the standalone `wgbs_parabricks_qc.py` utility can be used as an additional pre-extraction guardrail check for WGBS Parabricks JSON metrics.

When `wgbs_parabricks_qc.py` runs directly, it writes a `guardrails` block into the input JSON (or into `--output` if specified). This block includes each metric's `value`, `normal_range`, pass/fail state, and a user-facing `message` that explains why the guardrail matters.

## Related Documentation

- Theory: [`THEORY.md`](THEORY.md)
- Implementation: [`IMPLEMENTATION.md`](IMPLEMENTATION.md)

## Guardrail Schema Migration

If you already have historical JSON outputs with older guardrail fields (`threshold`, `note`, `diagnose`, `description`, `meaning`, `reason`), migrate them in bulk to the current message-based schema:

- Dry-run (no file writes):
  - `methyl-qc-migrate-guardrails /path/to/alignment_qc_jsons`
- Apply in place:
  - `methyl-qc-migrate-guardrails /path/to/alignment_qc_jsons --apply`
- Apply with per-file backups:
  - `methyl-qc-migrate-guardrails /path/to/alignment_qc_jsons --apply --backup`

## Export JSON Schema

Export the strict, versionable JSON Schema generated from the Pydantic export models:

- `methyl-qc-export-schema` (default: **V1** columnar payload)
- `methyl-qc-export-schema --variant v2` (**V2** row-oriented payload)

Default output paths:

- V1: `packages/methylalignmentqc/schemas/exported_sample_qc.schema.json`
- V2: `packages/methylalignmentqc/schemas/exported_sample_qc_v2.schema.json`

Use `--output` to write elsewhere. Regenerate whenever the corresponding Pydantic models change.

## V2 row-oriented JSON (tools / Azure SQL)

`methyl-qc` writes **V2** JSON (`ExportedSampleQCV2Payload`; see `exported_sample_qc_v2.schema.json`). For **legacy V1** files already on disk (columnar arrays), convert in place or to a new tree with:

- Dry-run (no writes):
  - `methyl-qc-convert-v1-to-v2 /path/to/sample.json`
  - `methyl-qc-convert-v1-to-v2 /path/to/json_dir`
- Write V2 next to a single file (default name `<stem>.v2.json`):
  - `methyl-qc-convert-v1-to-v2 /path/to/sample.json --apply`
- Write a directory of V1 files into a target folder (each output basename `<stem>.v2.json`):
  - `methyl-qc-convert-v1-to-v2 /path/to/json_dir --apply --output-dir /path/to/v2_out`
- Custom output path (single file):
  - `methyl-qc-convert-v1-to-v2 /path/to/sample.json --apply --output /path/to/out.json`
- If `--output` already exists and you want a backup before overwrite:
  - `... --apply --output /path/to/out.json --backup`
- Skip post-conversion Pydantic validation (not recommended):
  - `... --no-validate-v2`

V2 files include top-level `metadata` (`schema_name`, `schema_version`, `exported_at_utc`, `producer`) and row arrays under keys such as `mean_quality_by_cycle.rows`, `insert_size_histogram.rows`, etc. Files that already look like V2 are skipped.

### Azure SQL Database (`json` column + `OPENJSON`)

Assume a table `dbo.sample_qc (sample_id nvarchar(256) NOT NULL, qc_json json NOT NULL)` and V2 payload in `qc_json`.

**Mean quality by cycle (typed rows):**

```sql
SELECT s.sample_id, j.cycle, j.mean_quality
FROM dbo.sample_qc AS s
CROSS APPLY OPENJSON(s.qc_json, '$.mean_quality_by_cycle.rows')
  WITH (
    cycle           int             '$.cycle',
    mean_quality    float           '$.mean_quality'
  ) AS j;
```

**Insert-size histogram:**

```sql
SELECT s.sample_id, j.insert_size, j.pair_orientation, j.all_reads_fr_count
FROM dbo.sample_qc AS s
CROSS APPLY OPENJSON(s.qc_json, '$.insert_size_histogram.rows')
  WITH (
    insert_size           int     '$.insert_size',
    pair_orientation      nvarchar(8) '$.pair_orientation',
    all_reads_fr_count    int     '$.all_reads_fr_count'
  ) AS j;
```

**Scalar summary + guardrails (no `OPENJSON` on arrays):**

```sql
SELECT
  JSON_VALUE(s.qc_json, '$.sample_id') AS sample_id,
  CAST(JSON_VALUE(s.qc_json, '$.summary_stats.duplication_rate') AS float) AS duplication_rate,
  CAST(JSON_VALUE(s.qc_json, '$.guardrails.overall_pass') AS bit) AS overall_pass,
  JSON_VALUE(s.qc_json, '$.guardrails.details.q30_percent.value') AS q30_value,
  JSON_VALUE(s.qc_json, '$.guardrails.details.q30_percent.pass') AS q30_pass
FROM dbo.sample_qc AS s;
```

For filtered indexes on extracted scalars, use persisted computed columns that wrap `JSON_VALUE` / `OPENJSON` projections (Azure SQL supports indexed computed columns when deterministic).
