"""
Write per-sample QC JSON files for database storage.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from . import parser as core_parser


def write_sample_qc_json(metrics: Dict[str, Any], output_path: Path) -> None:
    """
    Write one sample's metrics dict to a JSON file.
    Optionally include summary_stats if present in metrics.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(metrics, f, indent=2)


def process_samples_to_qc_jsons(
    sample_paths: List[str],
    output_dir: str,
    validate_schema: bool = True,
) -> None:
    """
    Parse each sample directory and write one JSON per sample to output_dir.
    Output files: {output_dir}/{sample_basename}.json.

    Args:
        sample_paths: List of sample directory paths
        output_dir: Output directory for JSON files
        validate_schema: If True, validate each sample's JSON structure (via utils.schema_validator)
    """
    from pathlib import Path

    from ..utils.schema_validator import validate_sample_qc_metrics

    paths = [Path(p) for p in sample_paths]
    parsed = core_parser.parse_metrics_from_sample_paths(paths)
    if not parsed:
        return

    summary = core_parser.calculate_summary_stats(parsed)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for sample_name, metrics in parsed.items():
        payload: Dict[str, Any] = dict(metrics)
        if sample_name in summary:
            payload["summary_stats"] = summary[sample_name]
        if validate_schema:
            errs = validate_sample_qc_metrics(payload)
            if errs:
                raise RuntimeError(f"Validation failed for {sample_name}: " + "; ".join(errs))
        write_sample_qc_json(payload, out / f"{sample_name}.json")
