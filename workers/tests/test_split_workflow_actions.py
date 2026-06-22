"""Action catalog includes split detector workflow actions."""

from methyl_worker.action_catalog import ACTION_CATALOG, PROJECT_STEP_CONFIG_KEYS


def test_split_workflow_actions_registered():
    names = {e.action_name for e in ACTION_CATALOG}
    assert "pipeline.dmp_select" in names
    assert "pipeline.gene_select" in names
    assert "validation.biomarker_filter" in names


def test_step_config_keys_include_split_sections():
    assert "dmp_selection" in PROJECT_STEP_CONFIG_KEYS
    assert "gene_selection" in PROJECT_STEP_CONFIG_KEYS
