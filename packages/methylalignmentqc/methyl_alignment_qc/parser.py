"""
Main parser module for MethylAlignmentQC.

This module provides the main functionality for parsing Parabricks alignment
QC metrics and converting them to columnar JSON format. It serves as both
the CLI entry point and the main API interface.
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, Any, Optional

from .qc_parser import parse_all_metrics, calculate_summary_stats
from .columnar_json import (
    convert_to_columnar_format,
    save_columnar_json,
    validate_columnar_structure,
    calculate_compression_ratio
)
from .schema_validator import validate_columnar_qc_data, validate_and_report


def build_alignment_qc_json(
    metrics_root: str,
    output_path: Optional[str] = None,
    validate_schema: bool = True,
    calculate_stats: bool = True
) -> Dict[str, Any]:
    """
    Build columnar JSON from alignment QC metrics.

    Args:
        metrics_root: Root directory containing QC metrics files
        output_path: Optional path to save JSON output
        validate_schema: Whether to validate output against schema
        calculate_stats: Whether to include summary statistics

    Returns:
        Dictionary containing columnar JSON data

    Raises:
        ValueError: If metrics_root is invalid or no metrics files found
        RuntimeError: If parsing or validation fails
    """
    metrics_root_path = Path(metrics_root)

    if not metrics_root_path.exists():
        raise ValueError(f"Metrics root directory does not exist: {metrics_root}")

    if not metrics_root_path.is_dir():
        raise ValueError(f"Metrics root must be a directory: {metrics_root}")

    # Parse all metrics files
    print(f"Scanning for metrics files in: {metrics_root}")
    raw_metrics = parse_all_metrics(metrics_root_path)

    if not raw_metrics:
        raise ValueError(f"No metrics files found in: {metrics_root}")

    print(f"Found metrics for {len(raw_metrics)} samples")

    # Convert to columnar format
    print("Converting to columnar JSON format...")
    columnar_data = convert_to_columnar_format(raw_metrics)

    # Validate columnar structure
    if not validate_columnar_structure(columnar_data):
        raise RuntimeError("Generated columnar data has invalid structure")

    # Validate against schema
    if validate_schema:
        print("Validating against JSON schema...")
        validation_errors = validate_columnar_qc_data(columnar_data)
        if validation_errors:
            error_msg = "Schema validation failed:\n" + "\n".join(f"  - {err}" for err in validation_errors)
            raise RuntimeError(error_msg)

    # Calculate compression ratio
    compression_ratio = calculate_compression_ratio(raw_metrics, columnar_data)
    columnar_data["metadata"] = {
        "compression_ratio": round(compression_ratio, 2),
        "original_samples": len(raw_metrics),
        "column_count": len(columnar_data["columns"]["names"])
    }

    # Add summary statistics if requested
    if calculate_stats:
        print("Calculating summary statistics...")
        summary_stats = calculate_summary_stats(raw_metrics)
        columnar_data["summary_stats"] = summary_stats

    # Save to file if requested
    if output_path:
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        print(f"Saving columnar JSON to: {output_path}")
        save_columnar_json(columnar_data, output_path_obj)

        # Report compression achieved
        print(".2f")

    return columnar_data


def main():
    """
    Main CLI entry point for methyl-qc command.
    """
    parser = argparse.ArgumentParser(
        description="Parse NVIDIA Clara Parabricks alignment QC metrics into columnar JSON format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  methyl-qc --metrics_root /path/to/metrics
  methyl-qc --metrics_root /data --output results.json --no-validation
  methyl-qc --metrics_root /metrics --output qc_data.json --stats-only
        """
    )

    parser.add_argument(
        "--metrics_root",
        required=True,
        help="Root directory containing QC metrics files"
    )

    parser.add_argument(
        "--output", "-o",
        help="Output path for columnar JSON file (default: auto-generated)"
    )

    parser.add_argument(
        "--no-validation",
        action="store_true",
        help="Skip JSON schema validation"
    )

    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Only calculate and display summary statistics"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )

    args = parser.parse_args()

    try:
        # Determine output path
        output_path = args.output
        if not output_path and not args.stats_only:
            # Auto-generate output path based on metrics root
            metrics_name = Path(args.metrics_root).name
            output_path = f"{metrics_name}_qc_metrics.json"

        if args.verbose:
            print("MethylAlignmentQC Parser")
            print("=" * 40)
            print(f"Metrics root: {args.metrics_root}")
            print(f"Output path: {output_path}")
            print(f"Validation: {'disabled' if args.no_validation else 'enabled'}")
            print()

        # Build columnar JSON
        result = build_alignment_qc_json(
            metrics_root=args.metrics_root,
            output_path=output_path if not args.stats_only else None,
            validate_schema=not args.no_validation,
            calculate_stats=True
        )

        # Display results
        if args.stats_only or args.verbose:
            print("\nResults Summary:")
            print("-" * 20)
            print(f"Samples processed: {result['metadata']['original_samples']}")
            print(f"Columns created: {result['metadata']['column_count']}")
            print(".2f")

            if "summary_stats" in result:
                print(f"\nSample Statistics:")
                for sample_name, stats in result["summary_stats"].items():
                    print(f"  {sample_name}:")
                    print(f"    Total reads: {stats.get('total_reads', 'N/A'):,}")
                    print(".3f")
                    print(f"    Estimated library size: {stats.get('estimated_library_size', 'N/A'):,}")

        if not args.stats_only:
            print(f"\nColumnar JSON saved to: {output_path}")

        print("\nProcessing completed successfully!")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()