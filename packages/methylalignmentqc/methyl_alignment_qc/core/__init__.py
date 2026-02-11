"""Core parsing and writing for MethylAlignmentQC."""

from .parser import (
    parse_deduplication_metrics,
    parse_metrics_from_sample_paths,
    find_metrics_files,
    find_metrics_in_sample_dir,
    parse_all_metrics,
    calculate_summary_stats,
)
from .writer import write_sample_qc_json, process_samples_to_qc_jsons

__all__ = [
    "parse_deduplication_metrics",
    "parse_metrics_from_sample_paths",
    "find_metrics_files",
    "find_metrics_in_sample_dir",
    "parse_all_metrics",
    "calculate_summary_stats",
    "write_sample_qc_json",
    "process_samples_to_qc_jsons",
]
