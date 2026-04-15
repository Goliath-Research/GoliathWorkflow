# MethylAlignmentQC Usage

## CLI Entry Points

The package exposes:

- `methyl-alignment-qc`
- `methyl-qc`

## Typical Inputs

Typical runs require:

- one or more sample directories or a metrics root,
- Picard- or Parabricks-style duplication/alignment metrics files,
- optional WGBS Parabricks metrics JSON for initial guardrail screening via `methyl_alignment_qc/core/wgbs_parabricks_qc.py`,
- an output directory for normalized JSON summaries.

## Typical Outputs

The package writes one structured JSON summary per sample and can optionally validate those files against the package schema.
When a sample directory contains the canonical Parabricks metrics JSON file `{sample_name}.json`, `methyl-qc` enriches that same output file with a top-level `guardrails` block in the same pass.

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

Export the strict, versionable JSON Schema generated from the Pydantic export model:

- `methyl-qc-export-schema`

This writes:

- `packages/methylalignmentqc/schemas/exported_sample_qc.schema.json`
