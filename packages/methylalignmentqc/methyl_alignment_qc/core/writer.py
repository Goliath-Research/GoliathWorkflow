"""
Write per-sample QC JSON files for database storage.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models.sample_qc import ExportedSampleQCPayload, ParabricksMetricsPayload
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


def _find_parabricks_metrics_json(sample_dir: Path, sample_name: str) -> Optional[Path]:
    """
    Resolve canonical per-sample Parabricks JSON used for export and guardrails.

    We use the known file contract: {sample_dir}/{sample_name}.json.
    """
    direct_candidate = sample_dir / f"{sample_name}.json"
    return direct_candidate if direct_candidate.exists() else None


def _normalize_duplication_histogram(histogram: Any) -> Dict[str, Any]:
    """Normalize histogram to columnar schema expected by exported model."""
    if isinstance(histogram, dict):
        return histogram
    if isinstance(histogram, list):
        bins: List[float] = []
        values: List[float] = []
        for row in histogram:
            if not isinstance(row, dict):
                continue
            bins.append(float(row.get("BIN")))
            values.append(float(row.get("VALUE")))
        return {
            "BIN": bins,
            "VALUE": values,
            "all_sets": [],
            "optical_sets": [],
            "non_optical_sets": [],
        }
    return {
        "BIN": [],
        "VALUE": [],
        "all_sets": [],
        "optical_sets": [],
        "non_optical_sets": [],
    }


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
        payload: Dict[str, Any] = {}
        sample_dir = sample_paths_by_name.get(sample_name)
        if sample_dir is None:
            raise RuntimeError(f"Sample directory not found for parsed sample: {sample_name}")

        parabricks_json = _find_parabricks_metrics_json(sample_dir, sample_name)
        if parabricks_json is None:
            raise RuntimeError(
                f"Missing required Parabricks JSON for {sample_name}: expected {sample_dir / f'{sample_name}.json'}"
            )

        try:
            # Keep all original Parabricks metrics as the base payload.
            with open(parabricks_json, "r", encoding="utf-8") as f:
                raw_payload = json.load(f)
            payload = ParabricksMetricsPayload.model_validate(raw_payload).model_dump(
                mode="python",
                by_alias=True,
                exclude_none=True,
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to load/validate required Parabricks JSON for {sample_name} from {parabricks_json}: {e}"
            ) from e

        # Ensure deduplication-derived fields are present.
        for key, value in metrics.items():
            if key not in payload:
                payload[key] = value

        if "duplication_histogram" in payload:
            payload["duplication_histogram"] = _normalize_duplication_histogram(payload["duplication_histogram"])

        if sample_name in summary:
            payload["summary_stats"] = summary[sample_name]

        try:
            payload["guardrails"] = check_wgbs_guardrails(str(parabricks_json), print_report=False)
        except Exception as e:
            raise RuntimeError(f"Failed to compute guardrails for {sample_name} from {parabricks_json}: {e}") from e

        if validate_schema:
            errs = validate_sample_qc_metrics(payload)
            if errs:
                raise RuntimeError(f"Validation failed for {sample_name}: " + "; ".join(errs))
        # Validate against the canonical exported payload model before writing.
        payload = ExportedSampleQCPayload.model_validate(payload).model_dump(
            mode="python",
            by_alias=True,
            exclude_none=True,
        )
        write_sample_qc_json(payload, out / f"{sample_name}.json")
