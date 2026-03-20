# MethylAlignmentQC Implementation Notes

## Canonical Theory

For scope and caveats, see [`docs/theory/chapters/09-methylalignmentqc.qmd`](../../../docs/theory/chapters/09-methylalignmentqc.qmd).

## Main Code Paths

- `methyl_alignment_qc/core/parser.py`: metrics-file discovery and parsing.
- `methyl_alignment_qc/core/writer.py`: JSON serialization.
- `methyl_alignment_qc/utils/schema_validator.py`: optional schema checks.
- `methyl_alignment_qc/utils/monitor.py`: subprocess monitoring and progress parsing.

## Implementation Notes

- The package does not estimate new methylation-specific statistical models.
- Output semantics depend on the upstream Picard or Parabricks metrics formats being parsed correctly.
