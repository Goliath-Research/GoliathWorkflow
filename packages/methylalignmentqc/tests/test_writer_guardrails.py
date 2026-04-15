import json
from pathlib import Path

import pytest


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _dedup_metrics_fixture() -> str:
    return """## METRICS CLASS\tpicard.sam.markduplicates.MarkDuplicatesMetrics
LIBRARY\tUNPAIRED_READS_EXAMINED\tREAD_PAIRS_EXAMINED\tSECONDARY_OR_SUPPLEMENTARY_RDS\tUNMAPPED_READS\tUNPAIRED_READ_DUPLICATES\tREAD_PAIR_DUPLICATES\tREAD_PAIR_OPTICAL_DUPLICATES\tPERCENT_DUPLICATION\tESTIMATED_LIBRARY_SIZE
lib1\t0\t100\t0\t0\t0\t8\t1\t0.08\t1000
## HISTOGRAM\tjava.lang.Double
BIN\tVALUE
1\t100
2\t20
""".replace("\\t", "\t")


def _parabricks_json_fixture(sample_name: str) -> dict:
    return {
        "sample_id": sample_name,
        "quality_yield": {
            "total_reads": 1000,
            "pf_reads": 950,
            "total_bases": 120000,
            "pf_bases": 100000,
            "q20_bases": 110000,
            "pf_q20_bases": 98000,
            "q30_bases": 95000,
            "pf_q30_bases": 90000,
            "q20_equivalent_yield": 200000,
            "pf_q20_equivalent_yield": 190000,
        },
        "mean_quality_by_cycle": {"cycle": [1, 2, 3, 4, 5], "mean_quality": [38.0, 37.5, 36.2, 35.5, 35.0]},
        "quality_score_distribution": {"Q": [20, 30], "COUNT_OF_Q": [100, 90]},
        "base_distribution_by_cycle": {
            "cycle": [1, 2, 3, 4, 5],
            "PCT_A": [25.0, 25.0, 25.0, 25.0, 25.0],
            "PCT_C": [25.0, 25.0, 25.0, 25.0, 25.0],
            "PCT_G": [25.0, 25.0, 25.0, 25.0, 25.0],
            "PCT_T": [24.9, 24.9, 24.9, 24.9, 24.9],
            "PCT_N": [0.1, 0.1, 0.1, 0.1, 0.1],
        },
        "gc_bias_summary": {"at_dropout": 1.2, "gc_dropout": 2.3},
        "gc_bias_details": {
            "GC": [0, 1],
            "WINDOWS": [10, 10],
            "READ_STARTS": [5, 5],
            "MEAN_BASE_QUALITY": [30.0, 30.0],
            "NORMALIZED_COVERAGE": [1.0, 1.0],
            "ERROR_BAR": [0.1, 0.1],
        },
        "insert_size_metrics": {
            "median_insert_size": 210,
            "mode_insert_size": 200,
            "mean_insert_size": 220.0,
            "standard_deviation": 10.0,
            "read_pairs": 100,
            "width_of_10_percent": 10,
            "width_of_20_percent": 20,
            "width_of_30_percent": 30,
            "width_of_40_percent": 40,
            "width_of_50_percent": 50,
            "width_of_60_percent": 60,
            "width_of_70_percent": 70,
            "width_of_80_percent": 80,
            "width_of_90_percent": 90,
            "width_of_95_percent": 95,
            "width_of_99_percent": 99,
        },
        "insert_size_histogram": {
            "insert_size": [100, 101],
            "pair_orientation": ["FR", "FR"],
            "All_Reads.fr_count": [10, 20],
            "VALUE": [1.0, 2.0],
            "all_sets": [1, 1],
            "optical_sets": [0, 0],
            "non_optical_sets": [1, 1],
        },
        "error_summaries": {
            "REF": ["A", "C"],
            "ALT": ["T", "G"],
            "COUNT": [10, 20],
            "RATE": [0.1, 0.2],
            "QSCORE": [20, 30],
        },
        "pre_adapter_summaries": {
            "ARTIFACT_NAME": ["Deamination", "OxoG"],
            "TOTAL_QSCORE": [5, 25],
            "WORST_CXT": ["ACA", "TGC"],
            "WORST_CXT_QSCORE": [5, 25],
        },
        "bait_bias_summaries": {
            "ARTIFACT_NAME": ["Cref", "Gref"],
            "TOTAL_QSCORE": [40, 40],
            "WORST_CXT": ["CCA", "GGC"],
            "WORST_CXT_QSCORE": [35, 35],
        },
        "conversion_log": {
            "program": "Parabricks",
            "version": "4.6.0-1",
            "start_time": "now",
            "end_time": "later",
            "total_time": "1 minute",
        },
    }


def test_process_samples_to_qc_jsons_includes_guardrails_when_parabricks_json_present(tmp_path: Path):
    from methyl_alignment_qc.core.writer import process_samples_to_qc_jsons

    sample_dir = tmp_path / "sampleA"
    sample_dir.mkdir(parents=True, exist_ok=True)

    _write_text(sample_dir / "sampleA.deduplicate_metrics.txt", _dedup_metrics_fixture())
    (sample_dir / "sampleA.json").write_text(json.dumps(_parabricks_json_fixture("sampleA")), encoding="utf-8")

    output_dir = tmp_path / "out"
    process_samples_to_qc_jsons([str(sample_dir)], str(output_dir), validate_schema=True)

    output_file = output_dir / "sampleA.json"
    assert output_file.exists()

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert "quality_yield" in payload
    assert payload["sample_id"] == "sampleA"
    assert "duplication_histogram" in payload
    assert "guardrails" in payload
    assert payload["guardrails"]["sample_id"] == "sampleA"
    assert "details" in payload["guardrails"]
    assert "pf_percent" in payload["guardrails"]["details"]
    assert "message" in payload["guardrails"]["details"]["pf_percent"]


def test_process_samples_to_qc_jsons_fails_when_parabricks_json_missing(tmp_path: Path):
    from methyl_alignment_qc.core.writer import process_samples_to_qc_jsons

    sample_dir = tmp_path / "sampleB"
    sample_dir.mkdir(parents=True, exist_ok=True)
    _write_text(sample_dir / "sampleB.deduplicate_metrics.txt", _dedup_metrics_fixture())

    output_dir = tmp_path / "out"
    with pytest.raises(RuntimeError, match="Missing required Parabricks JSON"):
        process_samples_to_qc_jsons([str(sample_dir)], str(output_dir), validate_schema=True)


def test_process_samples_to_qc_jsons_uses_canonical_sample_json_name_only(tmp_path: Path):
    from methyl_alignment_qc.core.writer import process_samples_to_qc_jsons

    sample_dir = tmp_path / "sampleC"
    sample_dir.mkdir(parents=True, exist_ok=True)
    _write_text(sample_dir / "sampleC.deduplicate_metrics.txt", _dedup_metrics_fixture())
    # Present but non-canonical JSON name; should not be auto-used.
    (sample_dir / "other_metrics.json").write_text(
        json.dumps(_parabricks_json_fixture("sampleC")),
        encoding="utf-8",
    )

    output_dir = tmp_path / "out"
    with pytest.raises(RuntimeError, match="Missing required Parabricks JSON"):
        process_samples_to_qc_jsons([str(sample_dir)], str(output_dir), validate_schema=True)
