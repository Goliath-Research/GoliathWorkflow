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

For initial metrics extraction workflows, use the package CLI for normalized per-sample QC JSON outputs; the standalone `wgbs_parabricks_qc.py` utility can be used as an additional pre-extraction guardrail check for WGBS Parabricks JSON metrics.

## Related Documentation

- Theory: [`THEORY.md`](THEORY.md)
- Implementation: [`IMPLEMENTATION.md`](IMPLEMENTATION.md)
