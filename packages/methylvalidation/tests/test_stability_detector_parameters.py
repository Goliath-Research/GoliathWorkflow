import json
from pathlib import Path

from methyl_validation.stability import (
    extract_detector_parameters_for_run,
    run_stability_analysis,
)


def _write_results_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_discovery_csv(path: Path, rows: list[dict]) -> None:
    import pandas as pd

    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def test_extract_detector_parameters_for_run_summarizes_multichromosome_results(tmp_path):
    run_dir = tmp_path / "run_0001"
    base_cfg = {
        "effect_size_coverage": 0.95,
        "delta_mean_reduction": 0.15,
        "classifier_dmp_selection": "elbow",
        "dynamic_dmp_cutoff_enabled": True,
    }
    _write_results_json(
        run_dir / "detections" / "all" / "pca_pca1" / "results-1.json",
        {
            "n_dmps_exported": 1000,
            "total_statistical_dmps": 1500,
            "total_biological_dmps": 1200,
            "config": base_cfg,
        },
    )
    _write_results_json(
        run_dir / "detections" / "all" / "pca_pca1" / "results-2.json",
        {
            "n_dmps_exported": 1200,
            "total_statistical_dmps": 1800,
            "total_biological_dmps": 1400,
            "config": base_cfg,
        },
    )

    row = extract_detector_parameters_for_run(run_dir)
    assert row is not None
    assert row["run_id"] == "run_0001"
    assert row["n_result_files"] == 2
    assert row["n_dmps_exported"]["mean"] == 1100.0
    assert row["n_dmps_exported"]["min"] == 1000.0
    assert row["n_dmps_exported"]["max"] == 1200.0
    assert row["total_statistical_dmps"]["mean"] == 1650.0
    assert row["total_biological_dmps"]["mean"] == 1300.0
    assert row["effect_size_coverage"] == 0.95
    assert row["delta_mean_reduction"] == 0.15
    assert row["classifier_dmp_selection"] == "elbow"
    assert row["dynamic_dmp_cutoff_enabled"] is True
    assert row["inconsistent_fields"] == []


def test_extract_detector_parameters_marks_inconsistent_config_fields(tmp_path):
    run_dir = tmp_path / "run_0002"
    _write_results_json(
        run_dir / "detections" / "all" / "pca_pca1" / "results-1.json",
        {
            "n_dmps_exported": 1000,
            "total_statistical_dmps": 1500,
            "total_biological_dmps": 1200,
            "config": {
                "effect_size_coverage": 0.95,
                "delta_mean_reduction": 0.15,
                "classifier_dmp_selection": "elbow",
                "dynamic_dmp_cutoff_enabled": True,
            },
        },
    )
    _write_results_json(
        run_dir / "detections" / "all" / "pca_pca1" / "results-2.json",
        {
            "n_dmps_exported": 900,
            "total_statistical_dmps": 1400,
            "total_biological_dmps": 1100,
            "config": {
                "effect_size_coverage": 0.90,
                "delta_mean_reduction": 0.15,
                "classifier_dmp_selection": "featurecuts_validation",
                "dynamic_dmp_cutoff_enabled": False,
            },
        },
    )

    row = extract_detector_parameters_for_run(run_dir)
    assert row is not None
    assert row["effect_size_coverage"] is None
    assert row["classifier_dmp_selection"] is None
    assert row["dynamic_dmp_cutoff_enabled"] is None
    assert "effect_size_coverage" in row["inconsistent_fields"]
    assert "classifier_dmp_selection" in row["inconsistent_fields"]
    assert "dynamic_dmp_cutoff_enabled" in row["inconsistent_fields"]


def test_run_stability_analysis_includes_detector_parameters_and_missing_runs(tmp_path):
    monte_root = tmp_path / "monte_carlo_runs"
    run_with_results = monte_root / "run_0001"
    run_without_results = monte_root / "run_0002"
    run_without_results.mkdir(parents=True, exist_ok=True)

    _write_results_json(
        run_with_results / "detections" / "all" / "pca_pca1" / "results-1.json",
        {
            "n_dmps_exported": 1396,
            "total_statistical_dmps": 14957,
            "total_biological_dmps": 13015,
            "config": {
                "effect_size_coverage": 0.95,
                "delta_mean_reduction": 0.15,
                "classifier_dmp_selection": "elbow",
                "dynamic_dmp_cutoff_enabled": True,
            },
        },
    )

    summary = run_stability_analysis(
        monte_carlo_runs_root=monte_root,
        output_dir=monte_root / "stability",
    )
    detector = summary.get("detector_parameters")
    assert isinstance(detector, dict)
    assert len(detector.get("per_run", [])) == 1
    assert detector["aggregates"]["n_runs_with_results"] == 1
    assert detector["aggregates"]["n_runs_without_results"] == 1
    assert detector["aggregates"]["numeric"]["n_dmps_exported_mean"]["mean"] == 1396.0
    assert detector["aggregates"]["categorical"]["classifier_dmp_selection"]["elbow"] == 1

    summary_json = monte_root / "stability" / "stability_summary.json"
    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert "detector_parameters" in payload


def test_run_stability_analysis_writes_frequency_plot_html(tmp_path):
    monte_root = tmp_path / "monte_carlo_runs"
    # Create 4 runs with discovery DMPs so we get varied frequencies:
    # (1,100) in 4/4, (1,200) in 3/4, (1,300) in 2/4, (1,400) in 1/4
    run_rows = {
        "run_0001": [100, 200, 300, 400],
        "run_0002": [100, 200, 300],
        "run_0003": [100, 200],
        "run_0004": [100],
    }
    for run_id, positions in run_rows.items():
        _write_discovery_csv(
            monte_root / run_id / "detections" / "all" / "pca_pca1" / "dmps-1-discovery.csv",
            [{"chromosome": 1, "position": p} for p in positions],
        )

    summary = run_stability_analysis(
        monte_carlo_runs_root=monte_root,
        output_dir=monte_root / "stability",
    )
    assert "dmp_frequency_plot_html" in summary
    assert "dmp_frequency_elbow" in summary

    html_path = summary.get("dmp_frequency_plot_html")
    if html_path:
        plot_path = Path(html_path)
        assert plot_path.is_file()
        # With four unique frequency points, elbow detection should be present
        elbow = summary.get("dmp_frequency_elbow")
        assert isinstance(elbow, dict)
        assert "frequency_pct" in elbow
        assert "dmps_pct" in elbow
