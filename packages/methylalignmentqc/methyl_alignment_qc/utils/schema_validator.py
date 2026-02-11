"""
Validation for MethylAlignmentQC per-sample QC JSON.

Validates a single sample's metrics dict (duplication_metrics, duplication_histogram)
written as {output_dir}/{sample_basename}.json.
"""

from typing import Dict, Any, List


def validate_sample_qc_metrics(data: Dict[str, Any]) -> List[str]:
    """
    Validate one sample's QC metrics dict (per-sample JSON).

    Args:
        data: Parsed metrics for one sample (duplication_metrics, duplication_histogram, etc.)

    Returns:
        List of validation error messages (empty if valid)
    """
    errors: List[str] = []

    if not isinstance(data, dict):
        return ["Sample QC data must be a dictionary"]

    # At least one of these should be present
    if "duplication_metrics" in data:
        dm = data["duplication_metrics"]
        if not isinstance(dm, list):
            errors.append("duplication_metrics must be a list")
        elif dm and not isinstance(dm[0], dict):
            errors.append("duplication_metrics items must be dictionaries")

    if "duplication_histogram" in data:
        dh = data["duplication_histogram"]
        if not isinstance(dh, list):
            errors.append("duplication_histogram must be a list")
        elif dh and not isinstance(dh[0], dict):
            errors.append("duplication_histogram items must be dictionaries")

    if not data:
        errors.append("Sample QC data is empty")

    return errors
