"""
MethylAlignmentQC - Parse NVIDIA Clara Parabricks Alignment QC Metrics

A Python package for parsing NVIDIA Clara Parabricks alignment quality control
metrics into optimized columnar JSON format for efficient storage and analysis.

Features:
- Parses Picard-style QC metrics from deduplication files
- Outputs columnar JSON (Structure of Arrays) for ~63% size reduction
- Validates output against internal JSON schema
- Command-line interface and Python API

Usage:
    # CLI
    methyl-qc --metrics_root /path/to/metrics

    # Python API
    from methyl_alignment_qc import build_alignment_qc_json
    result = build_alignment_qc_json(metrics_root="/path/to/metrics")
"""

from .parser import main, build_alignment_qc_json
from .monitor import run_with_logging

__version__ = "0.1.0"
__all__ = [
    "main",
    "build_alignment_qc_json",
    "run_with_logging"
]