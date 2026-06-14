"""Pipeline steps respect analyte profiles from primary_analyte."""

from pathlib import Path

from methyl_utils.pipeline_config import ProjectConfig


def test_cfdna_profile_enables_fragmentomics_step(tmp_path: Path):
    project_json = tmp_path / "project.json"
    project_json.write_text(
        """
        {
          "project_name": "cfdna_min",
          "output_base": "/out",
          "group1": {"label": "h", "sample_paths": ["/s/h"]},
          "group2": {"label": "t", "sample_paths": ["/s/t"]},
          "step_config": {
            "validation": {
              "regulatory": {"primary_analyte": "cfdna"}
            }
          }
        }
        """,
        encoding="utf-8",
    )

    project = ProjectConfig.model_validate(
        {
            "project_name": "cfdna_min",
            "output_base": "/out",
            "group1": {"label": "h", "sample_paths": ["/s/h"]},
            "group2": {"label": "t", "sample_paths": ["/s/t"]},
            "step_config": {
                "validation": {"regulatory": {"primary_analyte": "cfdna"}},
            },
        }
    )
    assert project.get_step_config("fragmentomics").get("enabled") is True
    assert project.get_step_config("validation").get("enforce_training_analyte_match") is True
