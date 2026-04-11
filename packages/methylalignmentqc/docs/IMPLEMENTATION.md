# MethylAlignmentQC Implementation Notes

## Canonical Theory

For scope and caveats, see [`docs/theory/chapters/09-methylalignmentqc.qmd`](../../../docs/theory/chapters/09-methylalignmentqc.qmd).

## Main Code Paths

- `methyl_alignment_qc/core/parser.py`: initial metrics-file discovery and extraction/parsing.
- `methyl_alignment_qc/core/writer.py`: JSON serialization.
- `methyl_alignment_qc/utils/schema_validator.py`: optional schema checks.
- `methyl_alignment_qc/utils/monitor.py`: subprocess monitoring and progress parsing.
- `methyl_alignment_qc/core/wgbs_parabricks_qc.py`: standalone WGBS Parabricks guardrail checker for pre-extraction QC screening.

## Implementation Notes

- The package does not estimate new methylation-specific statistical models.
- Output semantics depend on the upstream Picard or Parabricks metrics formats being parsed correctly.
