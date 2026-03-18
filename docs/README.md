# MethylPipeline Documentation

This directory contains the repository-level docs for the supported MethylPipeline workflow.

## Start Here

- [README](../README.md): project overview, install entry points, and CLI list
- [OPERATIONS_MANUAL.md](OPERATIONS_MANUAL.md): supported operator workflow and developer contract
- [UNIFIED_PROJECT_CONFIG_GUIDE.md](UNIFIED_PROJECT_CONFIG_GUIDE.md): canonical `controls` / `diseases` / `comparisons` project schema
- [THEORY_AND_PACKAGES.md](THEORY_AND_PACKAGES.md): theory and package responsibilities

## Additional References

- [DEVELOPMENT.md](DEVELOPMENT.md): development environment and workflow
- [PRODUCTION.md](PRODUCTION.md): container and production guidance
- [ARCHITECTURE.md](ARCHITECTURE.md): repository architecture and dependencies

## Notes

- Package-specific behavior belongs in `packages/*/README.md` and `packages/*/docs/`.
- The code-level project schema is implemented in `packages/methylutils/methyl_utils/pipeline_config.py`.
- If a document still refers to older `group1` / `group2` or `detection/cancer/<group>` paths as the primary workflow, treat it as legacy context and prefer the docs listed above.

