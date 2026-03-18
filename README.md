# MethylPipeline

MethylPipeline is a comprehensive, monorepo-based suite for high-performance DNA methylation analysis. It utilizes an **ECDF-only pipeline** (Empirical Cumulative Distribution Functions) to avoid arbitrary parametric models (Beta/Normal), instead operating directly on raw bin count histograms with mathematically rigorous metrics.

## Functionality

The pipeline is split into focused, decoupled packages that operate strictly sequentially, sharing `MethylUtils` as their core dependency.

- **`methylutils`**: The mathematical core for memory management, sufficient statistics, ECDF processing, and PCHIP splines.
- **`methylcentroid`**: Generates class-level representations (Centroids) holding $N, S_x, S_{x^2}$ and `binned_stats`.
- **`methyldetector`**: Performs statistically rigorous testing (Kolmogorov-Smirnov) and canonical overlap to identify Differentially Methylated Positions (DMPs).
- **`methylclassifier`**: Leverages an `ECDFClassifier` (Naive Bayes + Temperature scaling) trained on the detector's funnel output to predict new samples.
- **`methylcluster`** / **`methylmapper`** / **`methylpredictor`** / **`methylvalidation`**: Downstream utilities for module clustering, gene mapping, and robust cross-validation.

## Documentation Structure

To ensure consistency and clarity, all packages in `MethylPipeline` share an identical documentation contract located in their respective `docs/` directories:
1. **`THEORY.md`**: Theoretical foundations, complete with mathematical formulas and rationale.
2. **`IMPLEMENTATION.md`**: Code design, architectural constraints, and organization.
3. **`USAGE.md`**: Practical instructions, inputs, and outputs.
4. **`README.md`**: High-level functionality and component overview.

## Deployment

For details on how to deploy this repository on supported platforms (Linux/macOS) via virtual environments (`.venv`) or Docker containers, please consult our dedicated guide:
- 📖 **[DEPLOYMENT.md](docs/DEPLOYMENT.md)**

---
*Powered by MethylPipeline.*
