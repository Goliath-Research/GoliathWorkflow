"""
MethylModeler - A genomics sample classification tool using divergences.

This package provides tools for classifying two groups of genomics samples
using divergences calculated against a common reference sample (centroid).
"""

# Check for MethylUtils dependency (hard requirement)
try:
    import methyl_utils
    _METHYL_UTILS_AVAILABLE = True
except ImportError:
    _METHYL_UTILS_AVAILABLE = False
    import warnings
    warnings.warn(
        "MethylUtils not found. MethylUtils is a hard requirement for MethylModeler. "
        "Please ensure MethylUtils is installed and available in PYTHONPATH. "
        "You can set the METHYL_UTILS_PATH environment variable or use the run_in_container.sh script.",
        ImportWarning,
        stacklevel=2
    )

from .core.methylmodeler import MethylModeler
from .models.config import MethylModelerConfig
from .models.results import MethylModelerResult

# Import MethylCentroidPair from MethylUtils
from methyl_utils import MethylCentroidPair

__version__ = "0.2.0"
__all__ = [
    "MethylModeler",
    "MethylModelerConfig",
    "MethylModelerResult",
    "MethylCentroidPair"
] 