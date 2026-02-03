"""
JSON Schema validation for MethylAlignmentQC columnar output format.

This module provides JSON schema validation for the columnar JSON output
format used by MethylAlignmentQC.
"""

import json
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path


# JSON Schema for columnar QC metrics format
COLUMNAR_QC_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "MethylAlignmentQC Columnar Format",
    "description": "Schema for MethylAlignmentQC columnar JSON output",
    "type": "object",
    "required": ["format", "version", "description", "samples", "columns", "data"],
    "properties": {
        "format": {
            "type": "string",
            "const": "columnar_json"
        },
        "version": {
            "type": "string",
            "pattern": "^\\d+\\.\\d+$"
        },
        "description": {
            "type": "string"
        },
        "samples": {
            "type": "array",
            "items": {
                "type": "string"
            },
            "minItems": 0
        },
        "columns": {
            "type": "object",
            "required": ["names", "count"],
            "properties": {
                "names": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    }
                },
                "count": {
                    "type": "integer",
                    "minimum": 0
                }
            },
            "additionalProperties": False
        },
        "data": {
            "type": "object",
            "patternProperties": {
                ".*": {
                    "type": "array",
                    "items": {
                        "oneOf": [
                            {"type": "number"},
                            {"type": "string"},
                            {"type": "boolean"},
                            {"type": "null"}
                        ]
                    }
                }
            },
            "additionalProperties": False
        }
    },
    "additionalProperties": False
}


def validate_columnar_qc_data(data: Dict[str, Any]) -> List[str]:
    """
    Validate columnar QC data against the JSON schema.

    Args:
        data: Columnar QC data to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    # Check required fields
    required_fields = ["format", "version", "description", "samples", "columns", "data"]
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    if errors:
        return errors

    # Validate format
    if data["format"] != "columnar_json":
        errors.append(f"Invalid format: expected 'columnar_json', got '{data['format']}'")

    # Validate version format
    import re
    if not re.match(r"^\d+\.\d+$", str(data["version"])):
        errors.append(f"Invalid version format: {data['version']}")

    # Validate samples
    if not isinstance(data["samples"], list):
        errors.append("Field 'samples' must be an array")
    else:
        sample_count = len(data["samples"])
        for i, sample in enumerate(data["samples"]):
            if not isinstance(sample, str):
                errors.append(f"Sample at index {i} must be a string, got {type(sample)}")

    # Validate columns structure
    columns = data["columns"]
    if not isinstance(columns, dict):
        errors.append("Field 'columns' must be an object")
    else:
        if "names" not in columns:
            errors.append("Missing 'names' in columns")
        elif not isinstance(columns["names"], list):
            errors.append("Field 'columns.names' must be an array")
        else:
            column_names = columns["names"]
            for i, col_name in enumerate(column_names):
                if not isinstance(col_name, str):
                    errors.append(f"Column name at index {i} must be a string")

        if "count" not in columns:
            errors.append("Missing 'count' in columns")
        elif not isinstance(columns["count"], int) or columns["count"] < 0:
            errors.append("Field 'columns.count' must be a non-negative integer")
        elif "names" in columns and len(columns["names"]) != columns["count"]:
            errors.append(f"Column count mismatch: {columns['count']} expected, {len(columns['names'])} found")

    # Validate data structure
    data_section = data["data"]
    if not isinstance(data_section, dict):
        errors.append("Field 'data' must be an object")
    else:
        expected_sample_count = len(data.get("samples", []))
        expected_columns = data.get("columns", {}).get("names", [])

        for col_name in expected_columns:
            if col_name not in data_section:
                errors.append(f"Missing data array for column: {col_name}")
            elif not isinstance(data_section[col_name], list):
                errors.append(f"Data for column '{col_name}' must be an array")
            elif len(data_section[col_name]) != expected_sample_count:
                errors.append(f"Data array length mismatch for column '{col_name}': "
                             f"expected {expected_sample_count}, got {len(data_section[col_name])}")

        # Check for extra columns in data
        for col_name in data_section:
            if col_name not in expected_columns:
                errors.append(f"Unexpected data array for column: {col_name}")

    return errors


def validate_qc_metrics_structure(data: Dict[str, Any]) -> List[str]:
    """
    Validate the structure and content of QC metrics data.

    Args:
        data: QC metrics data to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    # Check that data is a dictionary
    if not isinstance(data, dict):
        return ["QC metrics data must be a dictionary"]

    # Check for expected sample structure
    for sample_name, sample_data in data.items():
        if not isinstance(sample_data, dict):
            errors.append(f"Sample '{sample_name}' data must be a dictionary")
            continue

        # Check for expected metric sections
        expected_sections = ["duplication_metrics", "duplication_histogram"]
        for section in expected_sections:
            if section in sample_data:
                section_data = sample_data[section]
                if not isinstance(section_data, list):
                    errors.append(f"Sample '{sample_name}' section '{section}' must be a list")
                elif not section_data:
                    errors.append(f"Sample '{sample_name}' section '{section}' is empty")
                else:
                    # Check first item structure
                    first_item = section_data[0]
                    if not isinstance(first_item, dict):
                        errors.append(f"Sample '{sample_name}' section '{section}' items must be dictionaries")
                    elif not first_item:
                        errors.append(f"Sample '{sample_name}' section '{section}' first item is empty")

    return errors


def validate_file_against_schema(file_path: Path) -> Tuple[bool, List[str]]:
    """
    Validate a JSON file against the columnar QC schema.

    Args:
        file_path: Path to JSON file to validate

    Returns:
        Tuple of (is_valid, error_messages)
    """
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON: {e}"]
    except FileNotFoundError:
        return False, [f"File not found: {file_path}"]
    except Exception as e:
        return False, [f"Error reading file: {e}"]

    errors = validate_columnar_qc_data(data)
    return len(errors) == 0, errors


def create_schema_file(output_path: Path) -> None:
    """
    Create a JSON schema file for the columnar QC format.

    Args:
        output_path: Path to save the schema file
    """
    with open(output_path, 'w') as f:
        json.dump(COLUMNAR_QC_SCHEMA, f, indent=2)


def get_schema() -> Dict[str, Any]:
    """
    Get the JSON schema for columnar QC format.

    Returns:
        JSON schema dictionary
    """
    return COLUMNAR_QC_SCHEMA.copy()


def validate_and_report(data: Dict[str, Any], verbose: bool = True) -> bool:
    """
    Validate data and report results.

    Args:
        data: Data to validate
        verbose: Whether to print detailed error messages

    Returns:
        True if valid, False otherwise
    """
    errors = validate_columnar_qc_data(data)

    if errors:
        if verbose:
            print("Validation failed with the following errors:")
            for error in errors:
                print(f"  - {error}")
        return False
    else:
        if verbose:
            print("Validation successful!")
        return True