# MethylAlignmentQC Implementation Notes

## Canonical Theory

For scope and caveats, see [`docs/theory/chapters/09-methylalignmentqc.md`](../../../docs/theory/chapters/09-methylalignmentqc.md).

## Main Code Paths

- `methyl_alignment_qc/cli/main.py`: mode dispatch for `--project`, `--samples`, and `--metrics-root`.
- `methyl_alignment_qc/core/parser.py`: initial metrics-file discovery and extraction/parsing.
- `methyl_alignment_qc/core/writer.py`: JSON serialization (validates V1-shaped assembly, converts to **V2** for disk).
- `methyl_alignment_qc/utils/schema_validator.py`: optional schema checks.
- `methyl_alignment_qc/utils/monitor.py`: subprocess monitoring and progress parsing.
- `methyl_alignment_qc/core/wgbs_parabricks_qc.py`: standalone WGBS Parabricks guardrail checker for pre-extraction QC screening.
- `methyl_alignment_qc/utils/guardrail_migration.py`: migration utility for legacy guardrail schema keys.
- `methyl_alignment_qc/utils/schema_export.py`: exporter for versioned JSON schema artifacts (V1 and V2).
- `methyl_alignment_qc/models/sample_qc_v2.py`: Pydantic model for **V2** row-oriented export (`ExportedSampleQCV2Payload`).
- `methyl_alignment_qc/utils/v1_to_v2_migration.py`: deterministic **V1 → V2** conversion and `methyl-qc-convert-v1-to-v2` CLI entrypoint.

## Implementation Notes

- The package does not estimate new methylation-specific statistical models.
- Output semantics depend on the upstream Picard or Parabricks metrics formats being parsed correctly.
- `--samples` supports both direct paths and list files (`.txt` lines or JSON arrays), which simplifies batch operation in external orchestrators.
- `--metrics-root` discovers candidate samples via recursive metrics-file search and then deduplicates by parent path before processing.
- Project mode uses `resolve_alignment_qc_config()` so step overrides and project defaults are consistently applied across CLI and pipeline execution.
