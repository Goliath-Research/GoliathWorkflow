# methylutils

This package is a core component of the MethylPipeline monorepo, sharing the `MethylUtils` foundation.

## High-Level Functionality
Please refer to the root [README.md](../../README.md) for the functional placement of this package in the canonical ECDF-based pipeline.

## Documentation

To ensure consistency across the MethylPipeline ecosystem, this package follows a strict documentation contract:

- 📖 **[THEORY.md](docs/THEORY.md)**: Theoretical foundation, including high-quality formulas, statistical models, and references.
- ⚙️ **[IMPLEMENTATION.md](docs/IMPLEMENTATION.md)**: Implementation details, code design, architecture, and memory organization.
- 🚀 **[USAGE.md](docs/USAGE.md)**: Practical usage, CLI commands, Python API snippets, and configuration parameters.
- 🌲 **[COHORT_TREE.md](docs/COHORT_TREE.md)**: Control/disease project JSON—`stages` semantics (generic child strata), resolved leaves, `cohort_hierarchy`, and a v2 recursive-tree design appendix.

For deployment instructions on supported platforms (Linux/macOS) via virtual environments or Docker, please consult the global [DEPLOYMENT.md](../../docs/DEPLOYMENT.md).
