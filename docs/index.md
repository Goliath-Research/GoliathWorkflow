# MethylPipeline Documentation

This `docs/` tree is intentionally thin. The canonical mathematical and statistical reference now lives in the Quarto book under [`docs/theory/`](theory/README.md), while package-local documentation remains the operational entry point for CLI usage and implementation notes.

## Documentation Layers

- [`theory/README.md`](theory/README.md): build instructions and authoring guide for the Quarto theory book.
- [`theory/index.qmd`](theory/index.qmd): code-backed overview of the statistical pipeline, notation, and traceability rules.
- [`DEPLOYMENT.md`](DEPLOYMENT.md): environment setup for the monorepo and command-line tools.
- `packages/*/docs/`: package-local summaries, usage notes, and implementation details.

## Source Of Truth

For theory, the source of truth is the code. The Quarto book documents the mathematics and statistics that are actually implemented, and it labels each method as one of:

- principled,
- approximate,
- heuristic, or
- external-service-backed.

That distinction matters for this repository. The centroid, detector, and classifier path is largely ECDF-centered, but downstream packages also include beta-based clustering, p-value aggregation, graph heuristics, and external biological knowledge services.

## Recommended Reading Order

1. Start with the [theory book](theory/README.md) for the mathematical model.
2. Use the package `README.md` files for high-level package placement.
3. Use package `USAGE.md` and `IMPLEMENTATION.md` files when you need operational or code-level detail.
