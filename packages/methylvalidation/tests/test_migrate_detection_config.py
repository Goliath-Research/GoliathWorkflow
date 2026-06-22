"""Tests for detection config migration."""

from methyl_validation.utils.migrate_detection_config import migrate_step_config


def test_migrate_moves_dmp_selection_keys():
    step_config = {
        "detection": {
            "alpha": 0.05,
            "classifier_dmp_selection": "featurecuts_validation",
            "target_balanced_accuracy": 0.85,
            "classifier_export_margin_pct": 0.1,
        }
    }
    migrated, warnings = migrate_step_config(step_config)
    assert migrated["detection"]["alpha"] == 0.05
    assert "classifier_dmp_selection" not in migrated["detection"]
    assert migrated["dmp_selection"]["classifier_dmp_selection"] == "featurecuts_validation"
    assert migrated["dmp_selection"]["target_balanced_accuracy"] == 0.85
    assert warnings
