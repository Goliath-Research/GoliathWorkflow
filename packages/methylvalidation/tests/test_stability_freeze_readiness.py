"""Tests for stability_freeze_readiness analyzer."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from methyl_validation.grok_readiness import (
    build_sanitized_ai_payload,
    payload_contains_path_like_strings,
    redact_report_for_export,
    resolve_grok_api_key,
)
from methyl_validation.stability_freeze_readiness import (
    analyze_project_root,
    main,
    render_markdown,
)


def _write_minimal_project(tree: Path) -> None:
    mc = tree / "monte_carlo_runs"
    stab = mc / "stability"
    prod = mc / "production"
    prog = prod / "progression"
    stab.mkdir(parents=True)
    prod.mkdir(parents=True)
    prog.mkdir(parents=True)

    stability_summary = {
        "dmp_stability": {
            "n_runs_analyzed": 10,
            "skipped_no_discovery": 0,
            "skipped_low_balanced_accuracy": 0,
            "min_balanced_accuracy": None,
            "total_unique_dmps": 1000,
            "stable_dmps_at_threshold": 2,
            "min_frequency": 0.8,
            "stable_dmp_fraction": 0.002,
        }
    }
    (stab / "stability_summary.json").write_text(json.dumps(stability_summary), encoding="utf-8")
    pd.DataFrame(
        {
            "chromosome": ["1", "1"],
            "position": [100, 200],
            "frequency": [1.0, 1.0],
            "count": [10, 10],
            "n_runs": [10, 10],
            "effect_size": [0.5, 0.4],
            "p_value": [0.01, 0.02],
            "q_value": [0.05, 0.06],
        }
    ).to_csv(stab / "stable_dmps_production.csv", index=False)

    production_summary = {
        "success": True,
        "errors": [],
        "timings": [
            {"step_name": "methyl-detector", "duration_seconds": 1.0, "return_code": 0},
        ],
        "fixed_dmp_panel": str(prod / "stable_dmps_genomewide.csv"),
        "production_project": str(prod / "project.json"),
    }
    (prod / "production_summary.json").write_text(json.dumps(production_summary), encoding="utf-8")

    project = {
        "project_name": "production",
        "step_config": {
            "detection": {
                "fixed_dmp_panel": str(prod / "stable_dmps_genomewide.csv"),
                "alpha": 0.05,
            }
        },
    }
    (prod / "project.json").write_text(json.dumps(project), encoding="utf-8")
    pd.DataFrame({"chromosome": ["1", "1"], "position": [100, 200]}).to_csv(
        prod / "stable_dmps_genomewide.csv", index=False
    )

    progression_summary = {
        "ordered_comparison_labels": ["g1", "g2", "g3", "g4"],
        "missing_inputs": [],
        "genes_rows": 10,
        "pathways_rows": 20,
        "modules_rows": 8,
        "modules_long_csv": str(prog / "modules_long.csv"),
    }
    (prog / "summary.json").write_text(json.dumps(progression_summary), encoding="utf-8")

    # Slim progression schema (stage_index + comparison + module + score)
    rows = []
    for si, comp in enumerate(["g1", "g2", "g3", "g4"]):
        rows.append(
            {"stage_index": si, "comparison": comp, "rank": 1, "score": 0.1 * (si + 1), "module": "ModA"}
        )
        rows.append(
            {"stage_index": si, "comparison": comp, "rank": 2, "score": 0.5, "module": "ModB"}
        )
    pd.DataFrame(rows).to_csv(prog / "modules_long.csv", index=False)
    pd.DataFrame(
        {
            "entity_type": ["module"],
            "entity_id": ["ModA"],
            "entity_label": ["ModA"],
            "stages_present": ["0,1,2,3"],
            "n_stages_present": [4],
            "progression_labels": ["monotonic_up"],
        }
    ).to_csv(prog / "entities_progression_labels.csv", index=False)


def test_analyze_and_render_go(tmp_path: Path):
    root = tmp_path / "Proj"
    root.mkdir()
    _write_minimal_project(root)
    report = analyze_project_root(root)
    assert report["verdict"]["overall"] in ("go", "go_with_risks")
    assert report["verdict"]["stability"] == "pass"
    assert report["verdict"]["freeze"] == "pass"
    md = render_markdown(report)
    assert "Stability and freeze readiness report" in md
    assert "ModA" in md or "module" in md.lower()


def test_no_go_on_legacy_detector_keys(tmp_path: Path):
    root = tmp_path / "Proj"
    root.mkdir()
    _write_minimal_project(root)
    prod = root / "monte_carlo_runs" / "production"
    proj = json.loads((prod / "project.json").read_text(encoding="utf-8"))
    proj["step_config"]["detection"]["max_dmps_for_classifier"] = 10000
    (prod / "project.json").write_text(json.dumps(proj), encoding="utf-8")
    report = analyze_project_root(root)
    assert report["verdict"]["freeze"] == "fail"
    assert report["verdict"]["overall"] == "no_go"


def test_build_sanitized_ai_payload_no_path_like_strings(tmp_path: Path):
    root = tmp_path / "Proj"
    root.mkdir()
    _write_minimal_project(root)
    report = analyze_project_root(root)
    payload = build_sanitized_ai_payload(report, disease_context="Example disease", top_n=5)
    assert not payload_contains_path_like_strings(payload)


def test_build_sanitized_ai_payload_scrubs_paths_in_verdict_text(tmp_path: Path):
    root = tmp_path / "Proj"
    root.mkdir()
    _write_minimal_project(root)
    report = analyze_project_root(root)
    report.setdefault("verdict", {})
    report["verdict"]["warnings"] = list(report["verdict"].get("warnings") or []) + [
        "Missing file /home/someuser/secret/run/output.csv"
    ]
    payload = build_sanitized_ai_payload(report, disease_context=None, top_n=3)
    assert not payload_contains_path_like_strings(payload)
    dumped = json.dumps(payload)
    assert "[redacted]" in dumped
    assert "/home/someuser" not in dumped


def test_resolve_grok_api_key_explicit_overrides_env(monkeypatch):
    monkeypatch.setenv("GROK_API_KEY", "from-env")
    assert resolve_grok_api_key(explicit_key=" explicit ") == "explicit"


def test_render_markdown_ai_advisory_section(tmp_path: Path):
    root = tmp_path / "Proj"
    root.mkdir()
    _write_minimal_project(root)
    report = analyze_project_root(root)
    report["ai_review"] = {
        "status": "ok",
        "model_used": "grok-4.3",
        "advisory_only": True,
        "structured": {
            "consistency_assessment": "mixed",
            "summary_bullets": ["Signal A", "Signal B"],
            "caveats": ["Limited stages"],
            "suggested_human_checks": ["Review pathways"],
            "disease_progression_alignment": "Placeholder alignment text.",
        },
    }
    md = render_markdown(report)
    assert "AI readiness commentary (advisory)" in md
    assert "mixed" in md
    assert "Signal A" in md


def test_redact_report_for_export_strips_paths(tmp_path: Path):
    root = tmp_path / "Proj"
    root.mkdir()
    _write_minimal_project(root)
    report = analyze_project_root(root)
    redacted = redact_report_for_export(report)
    assert "project_root" not in redacted
    assert "paths" not in redacted
    mt = (redacted.get("progression") or {}).get("module_trajectory") or {}
    assert "modules_csv" not in mt


def test_main_no_grok_review_json(tmp_path: Path):
    root = tmp_path / "Proj"
    root.mkdir()
    _write_minimal_project(root)
    out = tmp_path / "report.json"
    prev = os.environ.get("GROK_API_KEY")
    try:
        if "GROK_API_KEY" in os.environ:
            del os.environ["GROK_API_KEY"]
        rc = main([str(root), "--no-grok-review", "--json-out", str(out)])
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["ai_review"]["status"] == "disabled"
        assert rc == 0
    finally:
        if prev is not None:
            os.environ["GROK_API_KEY"] = prev


def test_main_redact_paths_json(tmp_path: Path):
    root = tmp_path / "Proj"
    root.mkdir()
    _write_minimal_project(root)
    out = tmp_path / "redacted.json"
    prev = os.environ.get("GROK_API_KEY")
    try:
        if "GROK_API_KEY" in os.environ:
            del os.environ["GROK_API_KEY"]
        main([str(root), "--no-grok-review", "--json-out", str(out), "--redact-paths"])
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "project_root" not in data
    finally:
        if prev is not None:
            os.environ["GROK_API_KEY"] = prev


def test_main_mock_grok_does_not_change_verdict(tmp_path: Path):
    root = tmp_path / "Proj"
    root.mkdir()
    _write_minimal_project(root)
    expected = analyze_project_root(root)["verdict"]
    out = tmp_path / "with_ai.json"
    fake_review = {
        "provider": "xai",
        "status": "ok",
        "model_used": "grok-4.3",
        "advisory_only": True,
        "structured": {"consistency_assessment": "high", "summary_bullets": ["ok"]},
    }
    with patch("methyl_validation.grok_readiness.run_grok_readiness_review", return_value=fake_review):
        main([str(root), "--grok-api-key", "dummy", "--json-out", str(out)])
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["verdict"] == expected
    assert data["ai_review"]["status"] == "ok"


def test_main_skipped_no_key_non_blocking(tmp_path: Path):
    root = tmp_path / "Proj"
    root.mkdir()
    _write_minimal_project(root)
    out = tmp_path / "skipped.json"
    with patch("methyl_validation.grok_readiness.resolve_grok_api_key", return_value=None):
        rc = main([str(root), "--json-out", str(out)])
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["ai_review"]["status"] == "skipped_no_key"
    assert rc == 0
