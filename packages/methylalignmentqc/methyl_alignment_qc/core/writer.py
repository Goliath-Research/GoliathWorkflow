"""
Write per-sample QC JSON files for database storage.
"""

import json
import math
import tarfile
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


def _find_qc_metrics_tar(sample_dir: Path, sample_name: str) -> Optional[Path]:
    """Resolve canonical qc-metrics tar path for sample."""
    candidate = sample_dir / f"{sample_name}.qc-metrics.tar"
    return candidate if candidate.exists() else None


def _extract_table_rows_from_tar(tar: tarfile.TarFile, suffix: str) -> List[Dict[str, str]]:
    """Extract tabular rows from one text file inside qc-metrics tar by suffix."""
    member = next((m for m in tar.getnames() if m.endswith(suffix)), None)
    if member is None:
        return []
    raw = tar.extractfile(member)
    if raw is None:
        return []
    lines = raw.read().decode("utf-8", errors="ignore").splitlines()
    header: Optional[List[str]] = None
    rows: List[Dict[str, str]] = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("##") or line.startswith("#"):
            continue
        if "\t" not in line:
            continue
        parts = line.split("\t")
        if header is None:
            header = parts
            continue
        if len(parts) < len(header):
            continue
        rows.append({header[i]: parts[i] for i in range(len(header))})
    return rows


def _to_int(value: str) -> int:
    return int(float(value))


def _to_float(value: str) -> float:
    return float(value)


def _build_parabricks_payload_from_qc_tar(sample_dir: Path, sample_name: str) -> Optional[Dict[str, Any]]:
    """Build full Parabricks-like payload from qc-metrics tar text files."""
    tar_path = _find_qc_metrics_tar(sample_dir, sample_name)
    if tar_path is None:
        return None

    with tarfile.open(tar_path, "r") as tar:
        quality_yield_rows = _extract_table_rows_from_tar(tar, "quality_yield.txt")
        mean_quality_rows = _extract_table_rows_from_tar(tar, "mean_quality_by_cycle.txt")
        quality_score_rows = _extract_table_rows_from_tar(tar, "qualityscore.txt")
        base_dist_rows = _extract_table_rows_from_tar(tar, "base_distribution_by_cycle.txt")
        gc_summary_rows = _extract_table_rows_from_tar(tar, "gcbias_summary.txt")
        gc_detail_rows = _extract_table_rows_from_tar(tar, "gcbias_detail.txt")
        insert_rows = _extract_table_rows_from_tar(tar, "insert_size.txt")
        error_rows = _extract_table_rows_from_tar(tar, "sequencingArtifact.error_summary_metrics.txt")
        pre_adapter_rows = _extract_table_rows_from_tar(tar, "sequencingArtifact.pre_adapter_summary_metrics.txt")
        bait_bias_rows = _extract_table_rows_from_tar(tar, "sequencingArtifact.bait_bias_summary_metrics.txt")

    if not quality_yield_rows:
        return None

    qy = quality_yield_rows[0]

    # Insert-size histogram is in the same file but in a separate section; parse manually.
    insert_hist_insert_size: List[int] = []
    insert_hist_counts: List[int] = []
    with tarfile.open(tar_path, "r") as tar:
        member = next((m for m in tar.getnames() if m.endswith("insert_size.txt")), None)
        if member is not None:
            raw = tar.extractfile(member)
            if raw is not None:
                lines = raw.read().decode("utf-8", errors="ignore").splitlines()
                in_hist = False
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("## HISTOGRAM"):
                        in_hist = True
                        continue
                    if not in_hist or line.startswith("#") or line.startswith("##"):
                        continue
                    if line.startswith("insert_size\tAll_Reads.fr_count"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        insert_hist_insert_size.append(_to_int(parts[0]))
                        insert_hist_counts.append(_to_int(parts[1]))

    payload: Dict[str, Any] = {
        "sample_id": sample_name,
        "quality_yield": {
            "total_reads": _to_int(qy["TOTAL_READS"]),
            "pf_reads": _to_int(qy["PF_READS"]),
            "total_bases": _to_int(qy["TOTAL_BASES"]),
            "pf_bases": _to_int(qy["PF_BASES"]),
            "q20_bases": _to_int(qy["Q20_BASES"]),
            "pf_q20_bases": _to_int(qy["PF_Q20_BASES"]),
            "q30_bases": _to_int(qy["Q30_BASES"]),
            "pf_q30_bases": _to_int(qy["PF_Q30_BASES"]),
            "q20_equivalent_yield": _to_int(qy["Q20_EQUIVALENT_YIELD"]),
            "pf_q20_equivalent_yield": _to_int(qy["PF_Q20_EQUIVALENT_YIELD"]),
        },
        "mean_quality_by_cycle": {
            "cycle": [_to_int(r["CYCLE"]) for r in mean_quality_rows],
            "mean_quality": [_to_float(r["MEAN_QUALITY"]) for r in mean_quality_rows],
        },
        "quality_score_distribution": {
            "Q": [_to_int(r.get("QUALITY", r.get("Q", "0"))) for r in quality_score_rows],
            "COUNT_OF_Q": [_to_int(r["COUNT_OF_Q"]) for r in quality_score_rows],
        },
        "base_distribution_by_cycle": {
            "cycle": [_to_int(r["CYCLE"]) for r in base_dist_rows],
            "PCT_A": [_to_float(r["PCT_A"]) for r in base_dist_rows],
            "PCT_C": [_to_float(r["PCT_C"]) for r in base_dist_rows],
            "PCT_G": [_to_float(r["PCT_G"]) for r in base_dist_rows],
            "PCT_T": [_to_float(r["PCT_T"]) for r in base_dist_rows],
            "PCT_N": [_to_float(r["PCT_N"]) for r in base_dist_rows],
        },
        "gc_bias_summary": {
            "at_dropout": _to_float(gc_summary_rows[0]["AT_DROPOUT"]) if gc_summary_rows else 0.0,
            "gc_dropout": _to_float(gc_summary_rows[0]["GC_DROPOUT"]) if gc_summary_rows else 0.0,
        },
        "gc_bias_details": {
            "GC": [_to_int(r["GC"]) for r in gc_detail_rows],
            "WINDOWS": [_to_int(r["WINDOWS"]) for r in gc_detail_rows],
            "READ_STARTS": [_to_int(r["READ_STARTS"]) for r in gc_detail_rows],
            "MEAN_BASE_QUALITY": [_to_float(r["MEAN_BASE_QUALITY"]) for r in gc_detail_rows],
            "NORMALIZED_COVERAGE": [_to_float(r["NORMALIZED_COVERAGE"]) for r in gc_detail_rows],
            "ERROR_BAR": [_to_float(r["ERROR_BAR_WIDTH"]) for r in gc_detail_rows],
        },
        "insert_size_metrics": {
            "median_insert_size": _to_int(insert_rows[0]["MEDIAN_INSERT_SIZE"]) if insert_rows else 0,
            "mode_insert_size": _to_int(insert_rows[0]["MODE_INSERT_SIZE"]) if insert_rows else 0,
            "mean_insert_size": _to_float(insert_rows[0]["MEAN_INSERT_SIZE"]) if insert_rows else 0.0,
            "standard_deviation": _to_float(insert_rows[0]["STANDARD_DEVIATION"]) if insert_rows else 0.0,
            "read_pairs": _to_int(insert_rows[0]["READ_PAIRS"]) if insert_rows else 0,
            "width_of_10_percent": _to_int(insert_rows[0]["WIDTH_OF_10_PERCENT"]) if insert_rows else 0,
            "width_of_20_percent": _to_int(insert_rows[0]["WIDTH_OF_20_PERCENT"]) if insert_rows else 0,
            "width_of_30_percent": _to_int(insert_rows[0]["WIDTH_OF_30_PERCENT"]) if insert_rows else 0,
            "width_of_40_percent": _to_int(insert_rows[0]["WIDTH_OF_40_PERCENT"]) if insert_rows else 0,
            "width_of_50_percent": _to_int(insert_rows[0]["WIDTH_OF_50_PERCENT"]) if insert_rows else 0,
            "width_of_60_percent": _to_int(insert_rows[0]["WIDTH_OF_60_PERCENT"]) if insert_rows else 0,
            "width_of_70_percent": _to_int(insert_rows[0]["WIDTH_OF_70_PERCENT"]) if insert_rows else 0,
            "width_of_80_percent": _to_int(insert_rows[0]["WIDTH_OF_80_PERCENT"]) if insert_rows else 0,
            "width_of_90_percent": _to_int(insert_rows[0]["WIDTH_OF_90_PERCENT"]) if insert_rows else 0,
            "width_of_95_percent": _to_int(insert_rows[0]["WIDTH_OF_95_PERCENT"]) if insert_rows else 0,
            "width_of_99_percent": _to_int(insert_rows[0]["WIDTH_OF_99_PERCENT"]) if insert_rows else 0,
        },
        "insert_size_histogram": {
            "insert_size": insert_hist_insert_size,
            "pair_orientation": ["FR"] * len(insert_hist_insert_size),
            "All_Reads.fr_count": insert_hist_counts,
            "VALUE": [],
            "all_sets": [],
            "optical_sets": [],
            "non_optical_sets": [],
        },
        "error_summaries": {
            "REF": [r["REF_BASE"] for r in error_rows],
            "ALT": [r["ALT_BASE"] for r in error_rows],
            "COUNT": [_to_int(r["ALT_COUNT"]) for r in error_rows],
            "RATE": [_to_float(r["SUBSTITUTION_RATE"]) for r in error_rows],
            "QSCORE": [
                int(round(-10.0 * math.log10(max(_to_float(r["SUBSTITUTION_RATE"]), 1e-12)))) for r in error_rows
            ],
        },
        "pre_adapter_summaries": {
            "ARTIFACT_NAME": [r["ARTIFACT_NAME"] for r in pre_adapter_rows],
            "TOTAL_QSCORE": [_to_int(r["TOTAL_QSCORE"]) for r in pre_adapter_rows],
            "WORST_CXT": [r["WORST_CXT"] for r in pre_adapter_rows],
            "WORST_CXT_QSCORE": [_to_int(r["WORST_CXT_QSCORE"]) for r in pre_adapter_rows],
        },
        "bait_bias_summaries": {
            "ARTIFACT_NAME": [r["ARTIFACT_NAME"] for r in bait_bias_rows],
            "TOTAL_QSCORE": [_to_int(r["TOTAL_QSCORE"]) for r in bait_bias_rows],
            "WORST_CXT": [r["WORST_CXT"] for r in bait_bias_rows],
            "WORST_CXT_QSCORE": [_to_int(r["WORST_CXT_QSCORE"]) for r in bait_bias_rows],
        },
        "conversion_log": {
            "program": "Parabricks",
            "version": "unknown",
            "start_time": "unknown",
            "end_time": "unknown",
            "total_time": "unknown",
        },
    }
    return payload


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
        if parabricks_json is not None:
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
                    f"Failed to load/validate Parabricks JSON for {sample_name} from {parabricks_json}: {e}"
                ) from e
        else:
            parsed_from_tar = _build_parabricks_payload_from_qc_tar(sample_dir, sample_name)
            if parsed_from_tar is None:
                raise RuntimeError(
                    f"Missing Parabricks metrics for {sample_name}: expected either "
                    f"{sample_dir / f'{sample_name}.json'} or {sample_dir / f'{sample_name}.qc-metrics.tar'}"
                )
            payload = ParabricksMetricsPayload.model_validate(parsed_from_tar).model_dump(
                mode="python",
                by_alias=True,
                exclude_none=True,
            )
            parabricks_json = _find_qc_metrics_tar(sample_dir, sample_name)

        # Ensure deduplication-derived fields are present.
        for key, value in metrics.items():
            if key not in payload:
                payload[key] = value

        if "duplication_histogram" in payload:
            payload["duplication_histogram"] = _normalize_duplication_histogram(payload["duplication_histogram"])

        if sample_name in summary:
            payload["summary_stats"] = summary[sample_name]

        try:
            if str(parabricks_json).endswith(".json"):
                payload["guardrails"] = check_wgbs_guardrails(str(parabricks_json), print_report=False)
            else:
                # Guardrails can be computed from reconstructed payload.
                from .wgbs_parabricks_qc import _build_wgbs_guardrail_report

                payload["guardrails"] = _build_wgbs_guardrail_report(payload)
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
