"""
Write per-sample QC JSON files for database storage.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import parser as core_parser
from .wgbs_parabricks_qc import check_wgbs_guardrails


def write_sample_qc_json(metrics: Dict[str, Any], output_path: Path) -> None:
    """
    Write one sample's metrics dict to a JSON file.
    Optionally include summary_stats if present in metrics.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(metrics, f, indent=2)


def _looks_like_parabricks_metrics_json(data: Dict[str, Any]) -> bool:
    """Heuristic check for Parabricks metrics JSON required for guardrails."""
    if not isinstance(data, dict):
        return False
    required_keys = (
        "quality_yield",
        "mean_quality_by_cycle",
        "gc_bias_summary",
        "insert_size_metrics",
    )
    return all(key in data for key in required_keys)


def _find_parabricks_metrics_json(sample_dir: Path, sample_name: str) -> Optional[Path]:
    """
    Discover per-sample Parabricks JSON used for guardrails.

    Preference order:
    1) {sample_dir}/{sample_name}.json
    2) first *.json in sample_dir that matches required Parabricks keys
    """
    direct_candidate = sample_dir / f"{sample_name}.json"
    candidates: List[Path] = []
    if direct_candidate.exists():
        candidates.append(direct_candidate)
    for candidate in sorted(sample_dir.glob("*.json")):
        if candidate not in candidates:
            candidates.append(candidate)

    for candidate in candidates:
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                data = json.load(f)
            if _looks_like_parabricks_metrics_json(data):
                return candidate
        except Exception:
            continue
    return None


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
    sample_paths_by_name = {Path(p).name: Path(p) for p in paths}
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for sample_name, metrics in parsed.items():
        payload: Dict[str, Any] = dict(metrics)
        if sample_name in summary:
            payload["summary_stats"] = summary[sample_name]

        sample_dir = sample_paths_by_name.get(sample_name)
        if sample_dir is not None:
            parabricks_json = _find_parabricks_metrics_json(sample_dir, sample_name)
            if parabricks_json is not None:
                try:
                    payload["guardrails"] = check_wgbs_guardrails(str(parabricks_json), print_report=False)
                except Exception as e:
                    print(f"Warning: Failed to compute guardrails for {sample_name} from {parabricks_json}: {e}")

        if validate_schema:
            errs = validate_sample_qc_metrics(payload)
            if errs:
                raise RuntimeError(f"Validation failed for {sample_name}: " + "; ".join(errs))
        write_sample_qc_json(payload, out / f"{sample_name}.json")
