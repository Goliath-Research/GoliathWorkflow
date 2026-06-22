from __future__ import annotations

from pathlib import Path

from methyl_gene_select.utils.project_config import build_gene_select_config


def test_build_gene_select_config_merges_gene_selection_and_validation(tmp_path: Path):
    project = tmp_path / "project.json"
    project.write_text(
        """
        {
          "project_name": "t",
          "output_base": "/tmp/out",
          "controls": {"label": "healthy", "groups": [{"label": "all", "sample_paths": ["/a.csv"]}]},
          "diseases": {"label": "cancer", "groups": [{"label": "PCa", "sample_paths": ["/b.csv"]}]},
          "comparisons": "control_vs_each_disease",
          "chromosomes": ["1"],
          "contexts": ["CG"],
          "step_config": {
            "gene_selection": {
              "target_balanced_accuracy": 0.95,
              "min_selected_genes": 200,
              "biomarker_filter_enabled": true,
              "biomarker_mode": "ppi_only"
            },
            "validation": {
              "stability_gene_featurecuts_max_genes": 500,
              "stability_gene_region_hits": ["promoter"]
            }
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    cfg = build_gene_select_config(project)
    assert cfg.stability_target_balanced_accuracy == 0.95
    assert cfg.stability_min_selected_genes == 200
    assert cfg.stability_gene_biomarker_filter_enabled is True
    assert cfg.stability_gene_biomarker_mode == "ppi_only"
    assert cfg.stability_gene_featurecuts_max_genes == 500
    assert cfg.stability_gene_region_hits == ["promoter"]
