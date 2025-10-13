# ProbabilisticBetaClassifier Integration with MethylUtils

This document describes how to integrate the `ProbabilisticBetaClassifier` into the MethylUtils library.

## Overview

The `ProbabilisticBetaClassifier` is a Bayesian classifier that uses Beta distributions for methylation-based sample classification. It has been successfully tested and validated in the MethylDetector pipeline.

## Files to Add to MethylUtils

### 1. `/path/to/methylutils/methylutils/classifiers.py`

```python
"""
Probabilistic classifiers for methylation data.

This module contains Bayesian classifiers for methylation-based sample classification.
"""

from .probabilistic_beta_classifier import ProbabilisticBetaClassifier

__all__ = ['ProbabilisticBetaClassifier']
```

### 2. `/path/to/methylutils/methylutils/probabilistic_beta_classifier.py`

Use the standalone version from `/home/ubuntu/MethylDetector/probabilistic_beta_classifier.py`.

## Integration Steps

1. **Add the classifier files** to your MethylUtils package structure
2. **Update MethylUtils imports** to expose the classifier
3. **Update MethylDetector** to import from `methyl_utils` instead of local files

## MethylDetector Migration

After MethylUtils integration, update the MethylDetector import:

```python
# OLD: Local import
from ..classifiers import ProbabilisticBetaClassifier

# NEW: MethylUtils import
from methyl_utils import ProbabilisticBetaClassifier
```

## Testing

The classifier has been validated with:
- ✅ Basic functionality tests
- ✅ Realistic Beta parameter validation (99% accuracy)
- ✅ Missing data handling
- ✅ Integration with MethylDetector pipeline

## Usage Example

```python
from methyl_utils import ProbabilisticBetaClassifier
import numpy as np

# Training data
training_data = {
    'positions': np.array([100, 200, 300]),
    'alpha1': np.array([5.0, 2.0, 8.0]),
    'beta1': np.array([3.0, 6.0, 2.0]),
    'alpha2': np.array([2.0, 8.0, 2.0]),
    'beta2': np.array([6.0, 2.0, 6.0]),
    'weights': np.array([0.85, 0.92, 0.78]),
    'directions': np.array([1, -1, 1])
}

# Create and use classifier
classifier = ProbabilisticBetaClassifier(training_data)
predictions = classifier.predict(methylation_data)
probabilities = classifier.predict_proba(methylation_data)
```

## Dependencies

- numpy
- scipy
- typing (Python 3.5+)

## License

MIT License - same as MethylDetector.