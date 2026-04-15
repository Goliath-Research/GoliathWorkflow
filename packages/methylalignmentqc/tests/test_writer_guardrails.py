import json
from pathlib import Path


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
            "pf_bases": 100000,
            "pf_q30_bases": 90000,
        },
        "mean_quality_by_cycle": {"mean_quality": [38.0, 37.5, 36.2, 35.5, 35.0]},
        "gc_bias_summary": {"at_dropout": 1.2, "gc_dropout": 2.3},
        "insert_size_metrics": {"median_insert_size": 210},
        "pre_adapter_summaries": {
            "ARTIFACT_NAME": ["Deamination", "OxoG"],
            "TOTAL_QSCORE": [5, 25],
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
    assert "duplication_histogram" in payload
    assert "guardrails" in payload
    assert payload["guardrails"]["sample_id"] == "sampleA"
    assert "details" in payload["guardrails"]
    assert "pf_percent" in payload["guardrails"]["details"]
    assert "message" in payload["guardrails"]["details"]["pf_percent"]


def test_process_samples_to_qc_jsons_skips_guardrails_when_parabricks_json_missing(tmp_path: Path):
    from methyl_alignment_qc.core.writer import process_samples_to_qc_jsons

    sample_dir = tmp_path / "sampleB"
    sample_dir.mkdir(parents=True, exist_ok=True)
    _write_text(sample_dir / "sampleB.deduplicate_metrics.txt", _dedup_metrics_fixture())

    output_dir = tmp_path / "out"
    process_samples_to_qc_jsons([str(sample_dir)], str(output_dir), validate_schema=True)

    output_file = output_dir / "sampleB.json"
    assert output_file.exists()
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert "guardrails" not in payload
