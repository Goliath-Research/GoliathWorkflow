---
name: Complete ECDF Migration
overview: Complete the migration from Beta/Beta-Binomial/BetaMixtureModel to ECDF-only architecture across all MethylPipeline components, completely removing all legacy code with no backward compatibility.
todos:
  - id: remove-beta-classes
    content: Completely remove core Beta model classes (BetaClassifier, BetaBinomialClassifier, MultiClassBetaMixtureClassifier) and their files
    status: pending
  - id: clean-mixture-models
    content: Remove Beta mixture model components (MethylBetaMixtureCentroid, fit_beta_mixture) and delete entire files
    status: pending
  - id: update-distribution-views
    content: Remove BetaView and BetaBinomialView from distribution_views.py, update get_distribution_view() to ECDF-only
    status: pending
  - id: clean-constants
    content: Remove unused distribution constants (DIST_BETA, DIST_NORMAL, DIST_BETA_BINOM, DIST_BETA_MIXTURE) throughout codebase
    status: pending
  - id: update-package-exports
    content: Remove all Beta* class exports from __init__.py files with no compatibility warnings
    status: pending
  - id: clean-config-enums
    content: Remove ClassifierType.BETA enum and clean up configuration to be ECDF-only
    status: pending
isProject: false
---

# Complete ECDF Migration Plan

## Current Migration Status

The core runtime is **~70% migrated** to ECDF-only:
✅ **Configuration layer** actively rejects Beta parameters  
✅ **ECDFClassifier** implemented as drop-in BetaClassifier replacement  
✅ **MethylCentroidPair** hardcoded to ECDF-only operation  
✅ **MethylDetector** uses ECDFClassifier exclusively  

**Remaining work** is aggressive cleanup and complete removal of Beta model files and references.

## Files to be Completely Deleted

The following files will be deleted entirely as they contain only Beta/Beta-Binomial functionality:

1. `packages/methylutils/methyl_utils/beta_classifier.py` (883 lines)
2. `packages/methylutils/methyl_utils/beta_binomial_classifier.py` 
3. `packages/methylutils/methyl_utils/multi_class_beta_classifier.py`
4. `packages/methylutils/methyl_utils/core/methyl_mixture_centroid.py` (168 lines)
5. `packages/methylutils/methyl_utils/beta_mixture.py`
6. `packages/methylutils/methyl_utils/beta_analytics.py`

**Total deletion:** ~1500+ lines of Beta-specific code across 6+ files.

## Phase 1: Remove Legacy Model Classes

### 1.1 Remove Core Beta Model Files

**Files to completely delete:**

- `[packages/methylutils/methyl_utils/beta_classifier.py](packages/methylutils/methyl_utils/beta_classifier.py)` - Delete entire file (BetaClassifier class)
- `[packages/methylutils/methyl_utils/beta_binomial_classifier.py](packages/methylutils/methyl_utils/beta_binomial_classifier.py)` - Delete entire file (BetaBinomialClassifier class)  
- `[packages/methylutils/methyl_utils/multi_class_beta_classifier.py](packages/methylutils/methyl_utils/multi_class_beta_classifier.py)` - Delete entire file (MultiClassBetaMixtureClassifier)

### 1.2 Remove Beta Mixture Model Files

**Files to completely delete:**

- `[packages/methylutils/methyl_utils/core/methyl_mixture_centroid.py](packages/methylutils/methyl_utils/core/methyl_mixture_centroid.py)` - Delete entire file (MethylBetaMixtureCentroid class)
- `[packages/methylutils/methyl_utils/beta_mixture.py](packages/methylutils/methyl_utils/beta_mixture.py)` - Delete entire file (fit_beta_mixture functions)

### 1.3 Remove Beta Analytics

**Files to completely delete:**

- `[packages/methylutils/methyl_utils/beta_analytics.py](packages/methylutils/methyl_utils/beta_analytics.py)` - Delete entire file (GPU-aware Beta-Binomial PMF functions)

**Clean specific functions:**

- `[packages/methylutils/methyl_utils/statistical_tests.py](packages/methylutils/methyl_utils/statistical_tests.py)` - Remove `beta_binomial_mom_estimation` function and related Beta utilities

## Phase 2: Update Distribution System

### 2.1 Remove Legacy Distribution Views

In `[packages/methylutils/methyl_utils/core/distribution_views.py](packages/methylutils/methyl_utils/core/distribution_views.py)`:

- Remove `BetaView` class
- Remove `BetaBinomialView` class  
- Update `get_distribution_view()` to only support `"ecdf"` mode
- Remove mode parameters: `"beta"`, `"beta_binomial"`, `"beta_mixture"`

### 2.2 Clean Distribution Constants

Remove unused distribution constants throughout codebase:

- `DIST_BETA = 2`
- `DIST_NORMAL = 3` 
- `DIST_BETA_BINOM = 4`
- `DIST_BETA_MIXTURE = 6`
- Keep only `DIST_ECDF = 5`

### 2.3 Remove Method Parameters

Clean method signatures removing Beta-specific parameters:

- Distribution mode parameters (`distribution`, `delta_mean_mode`, `overlap_mode`) 
- Beta-specific thresholds (`max_N_for_ecdf`, `MIN_BETA_PARAM`)
- Statistical test options (already handled in config)

## Phase 3: Configuration and Export Cleanup

### 3.1 Clean Configuration Enums

In `[packages/methyldetector/methyl_detector/models/config.py](packages/methyldetector/methyl_detector/models/config.py)`:

- Remove `ClassifierType.BETA = "beta"` enum value
- Keep validation that rejects legacy parameters
- Update docstrings to reflect ECDF-only support

### 3.2 Update Package Imports/Exports

**Files to modify:**

- `[packages/methylutils/methyl_utils/__init__.py](packages/methylutils/methyl_utils/__init__.py)` - Remove all Beta* exports completely
- `[packages/methylutils/__init__.py](packages/methylutils/__init__.py)` - Remove all Beta* exports completely
- `[packages/methylclassifier/methyl_classifier/__init__.py](packages/methylclassifier/methyl_classifier/__init__.py)` - Remove Beta-related imports

**Strategy:** Clean removal with no compatibility warnings or fallbacks.

## Phase 4: Update Dependent Components

### 4.1 MethylClassifier Updates

- `[packages/methylclassifier/methyl_classifier/core/classifier.py](packages/methylclassifier/methyl_classifier/core/classifier.py)` - Remove all Beta classifier creation and loading paths
- `[packages/methylclassifier/methyl_classifier/utils/multiclass_builder.py](packages/methylclassifier/methyl_classifier/utils/multiclass_builder.py)` - Replace with ECDF-based building only
- Remove any references to Beta model types or loading

### 4.2 MethylCentroid Explorer

- `[packages/methylcentroid/explorer.py](packages/methylcentroid/explorer.py)` - Remove Beta-Binomial diagnostics completely
- Update analysis functions to use ECDF-only comparisons
- Remove any Beta-specific analysis or visualization code

### 4.3 CLI and Documentation

- Update CLI help text and examples to remove Beta references
- Remove all references to Beta modes in documentation  
- Update theoretical foundation docs (already in progress per git history)
- Clean up any remaining Beta-specific configuration examples

## Phase 5: Testing and Validation

### 5.1 Update Test Suite

- Remove all tests for deprecated Beta functionality
- Add comprehensive ECDF-only integration tests
- Verify that Beta model references are completely removed

### 5.2 Performance Validation

- Validate statistical consistency in ECDF-only centroid comparisons
- Test memory usage with large datasets
- Ensure no performance regressions from cleanup

## Implementation Priority

**High Priority** (Core functionality):

- Phase 1: Remove model classes
- Phase 2.1: Update distribution views  
- Phase 3.1: Configuration cleanup

**Medium Priority** (Code organization):

- Phase 2.2-2.3: Constants and parameters
- Phase 3.2: Import/export cleanup

**Low Priority** (Polish):

- Phase 4: Dependent component updates
- Phase 5: Testing and validation

This plan completes the ECDF migration with a clean break from Beta models, removing ~2000+ lines of legacy code and deleting 6+ entire files. The result will be a streamlined, ECDF-only codebase with no backward compatibility burden.