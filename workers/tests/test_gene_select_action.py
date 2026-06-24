"""Tests for GeneSelectCliAction argv defaults."""

from methyl_worker.action_catalog import find_catalog_entry
from methyl_worker.actions.gene_select import (
    GENE_SELECT_ARGV_MAP,
    GeneSelectCliAction,
    default_run_dir_for_project,
)


def _gene_select_action() -> GeneSelectCliAction:
    entry = find_catalog_entry("pipeline.gene_select")
    assert entry is not None
    return GeneSelectCliAction(entry=entry, cli_tool="methyl-gene-select", argv_map=GENE_SELECT_ARGV_MAP)


def test_default_run_dir_uses_parent_for_json_without_filesystem():
    # Path must not exist on disk; suffix alone drives the decision.
    assert default_run_dir_for_project("/nonexistent/ci/configs/project.json") == "/nonexistent/ci/configs"
    assert default_run_dir_for_project("/nonexistent/ci/monte_carlo_runs/run_0001") == (
        "/nonexistent/ci/monte_carlo_runs/run_0001"
    )


def test_gene_select_defaults_run_dir_to_project_parent():
    action = _gene_select_action()
    cmd = action.build_argv(
        {
            "projectPath": "/nonexistent/ci/configs/project_H_PCa.json",
        }
    )
    assert "--run-dir" in cmd
    run_dir_idx = cmd.index("--run-dir")
    assert cmd[run_dir_idx + 1] == "/nonexistent/ci/configs"


def test_gene_select_keeps_explicit_run_dir():
    action = _gene_select_action()
    cmd = action.build_argv(
        {
            "projectPath": "/work/prostate-cancer/configs/project_H_PCa.json",
            "runDir": "/work/prostate-cancer/monte_carlo_runs/run_0001",
        }
    )
    run_dir_idx = cmd.index("--run-dir")
    assert cmd[run_dir_idx + 1] == "/work/prostate-cancer/monte_carlo_runs/run_0001"
