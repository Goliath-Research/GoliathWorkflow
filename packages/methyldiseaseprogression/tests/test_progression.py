import csv
import json
from pathlib import Path

import pytest

from methyl_disease_progression.progression import run_progression_report

_LONG_GENE_COLS = ["stage_index", "comparison", "rank", "score", "gene"]
_LONG_PATHWAY_COLS = ["stage_index", "comparison", "rank", "score", "pathway"]
_LONG_MODULE_COLS = ["stage_index", "comparison", "rank", "score", "module"]
_LEGACY_LONG_COLS = {
    "entity_type",
    "entity_id",
    "entity_label",
    "comparison_label",
    "disease_group",
    "control_group",
    "q_value",
    "source_file",
}


def _write_project(tmp_path: Path) -> Path:
    list_dir = tmp_path / "lists"
    list_dir.mkdir(parents=True, exist_ok=True)
    for name in ("healthy.csv", "p1.csv", "p2.csv", "p3.csv"):
        (list_dir / name).write_text("sample\ns1\n", encoding="utf-8")

    project_path = tmp_path / "project.json"
    project_path.write_text(
        json.dumps(
            {
                "project_name": "prog",
                "output_base": str((tmp_path / "out").resolve()),
                "samples_base_path": str(tmp_path.resolve()),
                "controls": {
                    "label": "healthy",
                    "groups": [{"label": "all", "sample_paths": [str((list_dir / "healthy.csv").resolve())]}],
                },
                "diseases": {
                    "label": "cancer",
                    "groups": [
                        {
                            "label": "pca",
                            "stages": [
                                {"label": "pca1", "sample_paths": [str((list_dir / "p1.csv").resolve())]},
                                {"label": "pca2", "sample_paths": [str((list_dir / "p2.csv").resolve())]},
                                {"label": "pca3", "sample_paths": [str((list_dir / "p3.csv").resolve())]},
                            ],
                        }
                    ],
                },
                "comparisons": "control_vs_each_disease",
                "step_config": {"enricher": {"combined_csv_name": "all-gene_name-combined.csv"}},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return project_path


def _write_stage_outputs(tmp_path: Path) -> None:
    root = tmp_path / "out" / "prog"
    stages = ["pca_pca1", "pca_pca2", "pca_pca3"]
    stage_genes = {
        "pca_pca1": [("GENE_A", 0.9), ("GENE_B", 0.5)],
        "pca_pca2": [("GENE_A", 1.2), ("GENE_C", 0.8)],
        "pca_pca3": [("GENE_A", 2.0), ("GENE_D", 1.1)],
    }
    stage_paths = {
        "pca_pca1": [("Pathway One", 1e-3, 10.0)],
        "pca_pca2": [("Pathway One", 1e-4, 12.0), ("Pathway Two", 5e-3, 8.0)],
        "pca_pca3": [("Pathway One", 1e-5, 16.0)],
    }
    for stage in stages:
        mapper_dir = root / "mapper" / "all" / stage
        enricher_dir = root / "enricher" / "all" / stage
        mapper_dir.mkdir(parents=True, exist_ok=True)
        enricher_dir.mkdir(parents=True, exist_ok=True)
        gene_rows = ["gene_name,total_weight"] + [f"{g},{w}" for g, w in stage_genes[stage]]
        (mapper_dir / "all-gene_name-combined.csv").write_text("\n".join(gene_rows) + "\n", encoding="utf-8")
        p_rows = ["Term,Adjusted P-value,Combined Score"] + [f"{t},{q},{s}" for t, q, s in stage_paths[stage]]
        (enricher_dir / "enrichment_merged.csv").write_text("\n".join(p_rows) + "\n", encoding="utf-8")
        m_rows = ["Module,Score", f"Module_{stage},0.5"]
        (enricher_dir / "modules_ranked.csv").write_text("\n".join(m_rows) + "\n", encoding="utf-8")


def test_progression_report_writes_outputs(tmp_path: Path):
    project_path = _write_project(tmp_path)
    _write_stage_outputs(tmp_path)
    summary = run_progression_report(project_path=project_path, report_md=True)

    out_dir = Path(summary["output_dir"])
    assert (out_dir / "genes_long.csv").exists()
    assert (out_dir / "pathways_long.csv").exists()
    assert (out_dir / "modules_long.csv").exists()
    assert (out_dir / "modules_long_variant.csv").exists()
    assert (out_dir / "entities_progression_labels.csv").exists()
    assert (out_dir / "summary.json").exists()
    assert (out_dir / "report.md").exists()
    labels = (out_dir / "entities_progression_labels.csv").read_text(encoding="utf-8")
    assert "GENE_A" in labels
    assert "stable_across_stages" in labels

    def _header(path: Path) -> list[str]:
        with path.open(encoding="utf-8", newline="") as f:
            return next(csv.reader(f))

    assert _header(out_dir / "genes_long.csv") == _LONG_GENE_COLS
    assert _header(out_dir / "pathways_long.csv") == _LONG_PATHWAY_COLS
    assert _header(out_dir / "modules_long.csv") == _LONG_MODULE_COLS
    assert _header(out_dir / "modules_long_variant.csv") == _LONG_MODULE_COLS

    mod_text = (out_dir / "modules_long.csv").read_text(encoding="utf-8")
    for legacy in _LEGACY_LONG_COLS:
        assert legacy not in mod_text


def test_progression_report_respects_explicit_order(tmp_path: Path):
    project_path = _write_project(tmp_path)
    _write_stage_outputs(tmp_path)
    summary = run_progression_report(
        project_path=project_path,
        ordered_comparison_labels=["pca_pca3", "pca_pca1", "pca_pca2"],
    )
    assert summary["ordered_disease_groups"] == ["pca_pca3", "pca_pca1", "pca_pca2"]


def test_progression_report_strict_missing_fails(tmp_path: Path):
    project_path = _write_project(tmp_path)
    _write_stage_outputs(tmp_path)
    missing_file = tmp_path / "out" / "prog" / "enricher" / "all" / "pca_pca2" / "enrichment_merged.csv"
    missing_file.unlink()
    with pytest.raises(ValueError, match="Missing required progression inputs"):
        run_progression_report(project_path=project_path, strict_missing=True)


def test_progression_prefers_module_primary_for_long_table(tmp_path: Path):
    project_path = _write_project(tmp_path)
    _write_stage_outputs(tmp_path)
    root = tmp_path / "out" / "prog"
    stages = ["pca_pca1", "pca_pca2", "pca_pca3"]
    for stage in stages:
        enricher_dir = root / "enricher" / "all" / stage
        m_rows = [
            "Module_display,Module_primary,Module,Score",
            f"Display_{stage},Primary_{stage},Legacy_{stage},0.5",
        ]
        (enricher_dir / "modules_ranked.csv").write_text("\n".join(m_rows) + "\n", encoding="utf-8")

    summary = run_progression_report(project_path=project_path)
    out_dir = Path(summary["output_dir"])
    mod_text = (out_dir / "modules_long.csv").read_text(encoding="utf-8")
    assert "Primary_pca_pca1" in mod_text
    assert "Primary_pca_pca2" in mod_text
    assert "Primary_pca_pca3" in mod_text
    assert "Display_pca_pca1" not in mod_text


def test_progression_falls_back_to_module_display_when_primary_missing(tmp_path: Path):
    project_path = _write_project(tmp_path)
    _write_stage_outputs(tmp_path)
    root = tmp_path / "out" / "prog"
    stages = ["pca_pca1", "pca_pca2", "pca_pca3"]
    for stage in stages:
        enricher_dir = root / "enricher" / "all" / stage
        m_rows = [
            "Module_display,Module,Score",
            f"Display_{stage},Legacy_{stage},0.5",
        ]
        (enricher_dir / "modules_ranked.csv").write_text("\n".join(m_rows) + "\n", encoding="utf-8")

    summary = run_progression_report(project_path=project_path)
    out_dir = Path(summary["output_dir"])
    mod_text = (out_dir / "modules_long.csv").read_text(encoding="utf-8")
    assert "Display_pca_pca1" in mod_text

