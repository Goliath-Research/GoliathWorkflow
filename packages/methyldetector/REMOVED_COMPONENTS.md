# Removed Components - MethylDetector Refactor

This document tracks components removed from MethylDetector as part of the multi-project architecture refactor.

## Removed Files

### 1. Local Classifier Implementation
**Removed:** `/methyl_detector/classifiers/` directory
- `__init__.py` - Module exports
- `classifier.py` - ProbabilisticBetaClassifier implementation

**Reason:** Classifier now lives in MethylUtils and is used by MethylClassifier CLI tool.

**Migration Path:**
```python
# Old (removed):
from methyl_detector.classifiers import ProbabilisticBetaClassifier

# New:
from methyl_utils import ProbabilisticBetaClassifier
```

### 2. Standalone Classifier File
**Removed:** `/probabilistic_beta_classifier.py`

**Reason:** Duplicate implementation. Classifier is now in MethylUtils.

## Removed Functionality

### 1. Classifier Training
**Removed from:** `methyl_detector/core/methyldetector.py`
- `_create_probabilistic_classifier()` method
- Training logic in `run()` method
- Training logic in `_filter_and_select_dmps()` method
- Model saving in `_save_results()` method

**Now handled by:** MethylTrainer CLI tool

### 2. Training Configuration
**Removed from:** `methyl_detector/models/config.py`
- `train_classifier_model: bool` field
- `model_output_path: Optional[Path]` field

**Now handled by:** MethylTrainer configuration

## What MethylDetector Now Does

MethylDetector is now **focused exclusively on DMP detection**:

✅ Load centroid pairs  
✅ Compare centroids using MethylCentroidPair  
✅ Apply statistical significance testing  
✅ Apply biological filtering  
✅ Export DMPs to CSV/JSON  

❌ ~~Train classifiers~~ → Use **MethylTrainer**  
❌ ~~Classify samples~~ → Use **MethylClassifier**  

## Migration Guide

### For Training Models

**Before:**
```bash
# MethylDetector did everything
methyldetector --centroid1 c1.h5 --centroid2 c2.h5 --output dmps/ \
               --train-classifier-model --model-output model.pkl
```

**After:**
```bash
# Step 1: Detect DMPs (MethylDetector)
methyldetector --centroid1 c1.h5 --centroid2 c2.h5 --output dmps/

# Step 2: Train model (MethylTrainer - NEW)
methyltrainer --centroid1 c1.h5 --centroid2 c2.h5 --output model.pkl
```

### For Classification

**Before:**
```python
# Load classifier from MethylDetector
from methyl_detector.classifiers import ProbabilisticBetaClassifier
classifier = ProbabilisticBetaClassifier(data)
```

**After:**
```bash
# Use MethylClassifier CLI
methylclassifier --model model.pkl --input samples/ --output results.csv
```

Or programmatically:
```python
# Import from MethylUtils
from methyl_utils import ProbabilisticBetaClassifier
classifier = ProbabilisticBetaClassifier(data)
```

## Architecture Changes

### Before Refactor
```
MethylDetector
├── DMP Detection
├── Classifier Training  ← REMOVED
└── Classification       ← REMOVED
```

### After Refactor
```
MethylUtils (shared library)
├── MethylCentroidPair (DMP detection)
├── ProbabilisticBetaClassifier (classification)
└── BayesianClassifierTrainer (training)

MethylDetector (CLI) → DMP Detection only
MethylTrainer (CLI)  → Model Training
MethylClassifier (CLI) → Sample Classification
```

## Benefits of Separation

1. **Single Responsibility**: Each tool does one thing well
2. **Modularity**: Use tools independently or together
3. **Maintainability**: Easier to update and test
4. **Code Reuse**: Shared logic in MethylUtils
5. **Flexibility**: Mix and match tools for different workflows

## Backward Compatibility

- ✅ Old DMP detection workflows still work
- ✅ MethylClassifier can load old model PKL files
- ❌ Training configuration options removed (use MethylTrainer instead)
- ❌ Local classifier imports removed (use MethylUtils instead)

## Summary

| Component | Status | New Location |
|-----------|--------|--------------|
| DMP Detection | ✅ Kept | MethylDetector |
| Classifier Training | ❌ Removed | MethylTrainer |
| ProbabilisticBetaClassifier | ❌ Removed | MethylUtils |
| Classification | ❌ Removed | MethylClassifier |

---

**Date:** October 9, 2025  
**Refactor:** Multi-Project Architecture  
**Status:** Complete ✅

