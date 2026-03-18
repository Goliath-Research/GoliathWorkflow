# MethylPipeline Comprehensive Documentation

This file is now a documentation hub rather than a duplicate long-form narrative.

The repository has one supported project-driven workflow, and the detailed theory and implementation live in the package-specific docs.

## Primary References

- [README](../README.md)
- [OPERATIONS_MANUAL.md](OPERATIONS_MANUAL.md)
- [UNIFIED_PROJECT_CONFIG_GUIDE.md](UNIFIED_PROJECT_CONFIG_GUIDE.md)
- [THEORY_AND_PACKAGES.md](THEORY_AND_PACKAGES.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)

## Package Theory And Implementation

- `packages/methylutils/docs/MethylUtils_Theoretical_Foundation.md`
- `packages/methylutils/docs/METHYLUTILS_IMPLEMENTATION.md`
- `packages/methylcentroid/docs/MethylCentroid_Theoretical_Foundation.md`
- `packages/methylcentroid/docs/METHYLCENTROID_IMPLEMENTATION.md`
- `packages/methyldetector/docs/MethylDetector_Theoretical_Foundation.md`
- `packages/methyldetector/docs/METHYLDETECTOR_IMPLEMENTATION.md`
- `packages/methylclassifier/docs/MethylClassifier_Theoretical_Foundation.md`
- `packages/methylclassifier/docs/METHYLCLASSIFIER_IMPLEMENTATION.md`
- `packages/methylpredictor/docs/MethylPredictor_Theoretical_Foundation.md`
- `packages/methylpredictor/docs/METHYLPREDICTOR_IMPLEMENTATION.md`
- `packages/methylvalidation/docs/MethylValidation_Theoretical_Foundation.md`
- `packages/methylvalidation/docs/METHYLVALIDATION_IMPLEMENTATION.md`

## Canonical Run Order

```bash
methyl-centroid --project project.json --group all
methyl-detector --project project.json
methyl-mapper --project project.json
methyl-enricher --project project.json
methyl-classifier --project project.json
methyl-predictor --project project.json
```

Validation:

```bash
methyl-validation --config monte_carlo.json
```
