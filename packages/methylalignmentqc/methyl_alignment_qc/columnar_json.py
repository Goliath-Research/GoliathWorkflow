"""
Columnar JSON (Structure of Arrays) implementation for QC metrics.

This module provides functionality to convert parsed QC metrics into
columnar JSON format for efficient storage and analysis. Columnar format
stores data as arrays of values for each column rather than arrays of objects.
"""

import json
from typing import Dict, List, Any, Union
from pathlib import Path


def convert_to_columnar_format(metrics_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert parsed metrics data to columnar JSON format.

    Args:
        metrics_data: Dictionary with parsed metrics organized by sample

    Returns:
        Columnar JSON structure
    """
    columnar_data = {
        "format": "columnar_json",
        "version": "1.0",
        "description": "Methylation alignment QC metrics in columnar format",
        "samples": [],
        "columns": {},
        "data": {}
    }

    # Collect all unique column names across all samples
    all_columns = set()

    # First pass: collect all column names
    for sample_name, sample_data in metrics_data.items():
        columnar_data["samples"].append(sample_name)

        # Process duplication metrics
        if "duplication_metrics" in sample_data:
            for metric_row in sample_data["duplication_metrics"]:
                all_columns.update(metric_row.keys())

        # Process histogram data
        if "duplication_histogram" in sample_data:
            for hist_row in sample_data["duplication_histogram"]:
                # Add histogram-specific columns with prefixes
                prefixed_cols = {f"hist_{k}": v for k, v in hist_row.items()}
                all_columns.update(prefixed_cols.keys())

    # Sort columns for consistent ordering
    columnar_data["columns"] = {
        "names": sorted(list(all_columns)),
        "count": len(all_columns)
    }

    # Second pass: populate columnar data
    for col_name in columnar_data["columns"]["names"]:
        columnar_data["data"][col_name] = []

    # Fill data arrays
    for sample_name in columnar_data["samples"]:
        sample_data = metrics_data[sample_name]

        # Initialize all columns with None for this sample
        sample_values = {col: None for col in columnar_data["columns"]["names"]}

        # Fill duplication metrics (use first row if multiple)
        if "duplication_metrics" in sample_data and sample_data["duplication_metrics"]:
            metric_row = sample_data["duplication_metrics"][0]
            for key, value in metric_row.items():
                if key in sample_values:
                    sample_values[key] = value

        # Fill histogram data (flatten all histogram rows)
        if "duplication_histogram" in sample_data:
            for i, hist_row in enumerate(sample_data["duplication_histogram"]):
                for key, value in hist_row.items():
                    hist_key = f"hist_{key}"
                    if hist_key in sample_values:
                        # For multiple histogram rows, create indexed columns
                        if i == 0:
                            sample_values[hist_key] = value
                        else:
                            indexed_key = f"{hist_key}_{i}"
                            if indexed_key in columnar_data["columns"]["names"]:
                                sample_values[indexed_key] = value

        # Add values to columnar arrays
        for col_name in columnar_data["columns"]["names"]:
            columnar_data["data"][col_name].append(sample_values[col_name])

    return columnar_data


def convert_from_columnar_format(columnar_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert columnar JSON back to row-based format.

    Args:
        columnar_data: Columnar JSON data

    Returns:
        Row-based dictionary format
    """
    if columnar_data.get("format") != "columnar_json":
        raise ValueError("Invalid columnar JSON format")

    samples = columnar_data["samples"]
    columns = columnar_data["columns"]["names"]
    data = columnar_data["data"]

    row_data = {}

    for i, sample_name in enumerate(samples):
        sample_data = {}

        # Extract duplication metrics
        dup_metrics = {}
        hist_data = []

        for col_name in columns:
            value = data[col_name][i]
            if value is not None:
                if col_name.startswith("hist_"):
                    # Histogram data
                    clean_key = col_name[5:]  # Remove "hist_" prefix
                    # Check if this is an indexed histogram column
                    if "_" in clean_key and clean_key.split("_")[-1].isdigit():
                        base_key, idx = clean_key.rsplit("_", 1)
                        idx = int(idx)
                        # Extend hist_data list if needed
                        while len(hist_data) <= idx:
                            hist_data.append({})
                        hist_data[idx][base_key] = value
                    else:
                        # Single histogram row
                        if not hist_data:
                            hist_data.append({})
                        hist_data[0][clean_key] = value
                else:
                    # Regular duplication metric
                    dup_metrics[col_name] = value

        if dup_metrics:
            sample_data["duplication_metrics"] = [dup_metrics]
        if hist_data:
            sample_data["duplication_histogram"] = [row for row in hist_data if row]

        row_data[sample_name] = sample_data

    return row_data


def save_columnar_json(columnar_data: Dict[str, Any], output_path: Path) -> None:
    """
    Save columnar data to JSON file with compression-friendly formatting.

    Args:
        columnar_data: Columnar JSON data
        output_path: Output file path
    """
    # Use compact JSON formatting for better compression
    with open(output_path, 'w') as f:
        json.dump(columnar_data, f, separators=(',', ':'), indent=None)


def load_columnar_json(input_path: Path) -> Dict[str, Any]:
    """
    Load columnar JSON data from file.

    Args:
        input_path: Input file path

    Returns:
        Columnar JSON data
    """
    with open(input_path, 'r') as f:
        return json.load(f)


def calculate_compression_ratio(original_data: Dict[str, Any], columnar_data: Dict[str, Any]) -> float:
    """
    Calculate the compression ratio achieved by columnar format.

    Args:
        original_data: Original row-based data
        columnar_data: Columnar format data

    Returns:
        Compression ratio (original_size / columnar_size)
    """
    # Estimate sizes (rough approximation)
    original_json = json.dumps(original_data, separators=(',', ':'))
    columnar_json = json.dumps(columnar_data, separators=(',', ':'))

    original_size = len(original_json)
    columnar_size = len(columnar_json)

    return original_size / columnar_size if columnar_size > 0 else 1.0


def validate_columnar_structure(columnar_data: Dict[str, Any]) -> bool:
    """
    Validate that columnar data has the correct structure.

    Args:
        columnar_data: Columnar JSON data to validate

    Returns:
        True if valid, False otherwise
    """
    required_keys = ["format", "version", "samples", "columns", "data"]

    # Check required top-level keys
    for key in required_keys:
        if key not in columnar_data:
            return False

    # Check format
    if columnar_data["format"] != "columnar_json":
        return False

    # Check samples is a list
    if not isinstance(columnar_data["samples"], list):
        return False

    # Check columns structure
    columns = columnar_data["columns"]
    if not isinstance(columns, dict) or "names" not in columns or "count" not in columns:
        return False

    if not isinstance(columns["names"], list):
        return False

    if len(columns["names"]) != columns["count"]:
        return False

    # Check data structure
    data = columnar_data["data"]
    if not isinstance(data, dict):
        return False

    # Check that all columns have data arrays
    sample_count = len(columnar_data["samples"])
    for col_name in columns["names"]:
        if col_name not in data:
            return False
        if not isinstance(data[col_name], list):
            return False
        if len(data[col_name]) != sample_count:
            return False

    return True


def optimize_columnar_data(columnar_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Optimize columnar data for storage and processing.

    Args:
        columnar_data: Columnar JSON data

    Returns:
        Optimized columnar data
    """
    optimized = columnar_data.copy()

    # Convert numeric arrays where possible
    for col_name, values in optimized["data"].items():
        # Try to convert to more efficient numeric types
        try:
            # Check if all values are numeric
            numeric_values = []
            for val in values:
                if val is None or val == "":
                    numeric_values.append(None)
                else:
                    try:
                        num_val = float(val) if '.' in str(val) else int(val)
                        numeric_values.append(num_val)
                    except (ValueError, TypeError):
                        numeric_values.append(val)
                        break
            else:
                # All values were successfully converted
                optimized["data"][col_name] = numeric_values
        except:
            pass  # Keep original values if conversion fails

    return optimized