# MethylPipeline Documentation

This directory contains comprehensive documentation for the MethylPipeline system.

## Documentation Files

### [THEORY_AND_PACKAGES.md](THEORY_AND_PACKAGES.md)
Project and all 10 packages with theoretical foundations (LaTeX formulas): MethylUtils, MethylCentroid, MethylCluster, MethylDetector, MethylClassifier, MethylMapper, MethylEnricher, MethylAlignmentQC, MethylPredictor, MethylValidation.

### [OPERATIONS_MANUAL.md](OPERATIONS_MANUAL.md)
Operations manual for users and developers: installation, project config, workflow order, CLI reference, config fields, inputs/outputs, troubleshooting, rendering/printing docs; plus developer guide (repo layout, adding steps, config schema, testing, logging, doc conventions).

### [UNIFIED_PROJECT_CONFIG.md](UNIFIED_PROJECT_CONFIG.md)
Unified project config for **one healthy group + several disease groups**: project JSON layout, **hierarchical result structure** (centroids, detection, mapper, enricher, classifier under `cancer/{label}`), workflow order, and CLI commands per step.

### [DEVELOPMENT.md](DEVELOPMENT.md)
Complete guide for developers working on the MethylPipeline codebase:
- Setting up development environment
- Development workflow and best practices
- Testing and debugging
- Code quality tools
- Common development tasks
- GPU development guidelines
- Troubleshooting

### [PRODUCTION.md](PRODUCTION.md)
Guide for deploying and operating MethylPipeline in production:
- Production setup and deployment
- Container management
- Version management and release tagging
- Health monitoring and performance optimization
- Backup and recovery procedures
- Security considerations
- Scaling strategies
- CI/CD integration

### [ARCHITECTURE.md](ARCHITECTURE.md)
System architecture and design documentation:
- Component architecture and dependencies
- Package hierarchy and relationships
- Data flow and formats
- GPU architecture and optimization patterns
- Container architecture
- Performance considerations
- Scalability approaches
- Security model
- External dependencies

## Quick Links

### For Everyone
- [Theory and packages](THEORY_AND_PACKAGES.md) – Project and package theory (math)
- [Operations manual](OPERATIONS_MANUAL.md) – How to run and extend the pipeline
- [Unified project config](UNIFIED_PROJECT_CONFIG.md) – One healthy + N disease groups: directory tree and CLI

### For Developers
- [Getting Started](DEVELOPMENT.md#setting-up-development-environment)
- [Development Workflow](DEVELOPMENT.md#development-workflow)
- [Testing Guide](DEVELOPMENT.md#testing)
- [GPU Development](DEVELOPMENT.md#gpu-development)

### For Operations
- [Production Setup](PRODUCTION.md#production-setup)
- [Container Management](PRODUCTION.md#container-management)
- [Monitoring](PRODUCTION.md#health-monitoring)
- [Troubleshooting](PRODUCTION.md#troubleshooting)

### For Architects
- [System Overview](ARCHITECTURE.md#system-overview)
- [Component Architecture](ARCHITECTURE.md#component-architecture)
- [Data Flow](ARCHITECTURE.md#data-flow)
- [GPU Architecture](ARCHITECTURE.md#gpu-architecture)

## Additional Resources

- [Main README](../README.md) - Project overview and quick start
- Package-specific documentation in `packages/*/docs/`
- API documentation (generate with Sphinx)

## Contributing to Documentation

When updating documentation:
1. Keep it concise and actionable
2. Include code examples where relevant
3. Update all related documents
4. Test all commands and code snippets
5. Use clear section headings

## Building API Documentation

Generate API documentation using Sphinx:

```bash
# Inside container
cd /workspace/packages/methylutils
sphinx-build -b html docs docs/_build
```

## Documentation Standards

- Use Markdown format
- Include code blocks with language tags
- Add inline comments for complex commands
- Link to related documentation
- Keep examples up-to-date
- Include troubleshooting sections

