"""
Monte Carlo binary run project.json must keep comparisons consistent with flattened cohort labels.
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from methyl_validation.project_gen import generate_run_project

pytest.importorskip("methyl_utils", reason="pipeline_config.load_project")


def test_generate_run_project_comparisons_match_resolved_groups_staged_template():
    """
    Template with control leaf 'all' and disease parent 'pca' + stage 'pca1' resolves to pca_pca1
    in the base file. MC flattens to one disease group labeled 'pca'; comparisons must use that label.
    """
    from methyl_utils import load_project

    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        ctrl_csv = root / "ctrl_list.csv"
        dis_csv = root / "dis_list.csv"
        ctrl_csv.write_text("sample\ns1\n", encoding="utf-8")
        dis_csv.write_text("sample\ns2\n", encoding="utf-8")
        base = root / "base.json"
        base.write_text(
            json.dumps(
                {
                    "project_name": "mc-base",
                    "output_base": str(root / "out"),
                    "samples_base_path": str(root / "samples"),
                    "controls": {
                        "label": "healthy",
                        "groups": [{"label": "all", "sample_paths": [str(ctrl_csv)]}],
                    },
                    "diseases": {
                        "label": "cancer",
                        "groups": [
                            {
                                "label": "pca",
                                "stages": [
                                    {"label": "pca1", "sample_paths": [str(dis_csv)]}
                                ],
                            }
                        ],
                    },
                    "comparisons": "control_vs_each_disease",
                    "step_config": {"predictor": {}},
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        samples_root = root / "samples"
        samples_root.mkdir()
        for name in ("s1", "s2", "a1", "b1", "vc", "vd"):
            (samples_root / name).mkdir()

        base_proj = load_project(base)
        base_resolved = [x[0] for x in base_proj.get_resolved_groups()]
        assert base_resolved == ["all", "pca_pca1"]

        run_dir = root / "run_0001"
        samples_base = str((root / "samples").resolve())
        (
            project_path,
            *_rest,
        ) = generate_run_project(
            base,
            run_dir,
            "run_0001",
            str(root / "runs"),
            [str(root / "samples" / "a1")],
            [str(root / "samples" / "b1")],
            [str(root / "samples" / "vc")],
            [str(root / "samples" / "vd")],
            samples_base,
        )

        run_proj = load_project(project_path)
        resolved = [x[0] for x in run_proj.get_resolved_groups()]
        assert resolved == ["all", "pca"]

        comps = run_proj.get_comparisons()
        assert len(comps) == 1
        assert comps[0].control_group == "all"
        assert comps[0].disease_group == "pca"

        det = run_proj.get_detection_output_dir("all", "pca")
        assert det.endswith("/detections/all/pca")
