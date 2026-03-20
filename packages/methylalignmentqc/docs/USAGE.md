# MethylAlignmentQC Usage

## CLI Entry Points

The package exposes:

- `methyl-alignment-qc`
- `methyl-qc`

## Typical Inputs

Typical runs require:

- one or more sample directories or a metrics root,
- Picard- or Parabricks-style duplication/alignment metrics files,
- an output directory for normalized JSON summaries.

## Typical Outputs

The package writes one structured JSON summary per sample and can optionally validate those files against the package schema.

## Related Documentation

- Theory: [`THEORY.md`](THEORY.md)
- Implementation: [`IMPLEMENTATION.md`](IMPLEMENTATION.md)
