"""Tests for GeneSelectCliAction argv defaults."""

from methyl_worker.actions.gene_select import GENE_SELECT_ARGV_MAP, GeneSelectCliAction


def test_gene_select_defaults_run_dir_to_project_parent():
    action = GeneSelectCliAction(cli_tool="methyl-gene-select", argv_map=GENE_SELECT_ARGV_MAP)
    cmd = action.build_argv(
        {
            "projectPath": "/work/prostate-cancer/configs/project_H_PCa.json",
        }
    )
    assert "--run-dir" in cmd
    run_dir_idx = cmd.index("--run-dir")
    assert cmd[run_dir_idx + 1] == "/work/prostate-cancer/configs"


def test_gene_select_keeps_explicit_run_dir():
    action = GeneSelectCliAction(cli_tool="methyl-gene-select", argv_map=GENE_SELECT_ARGV_MAP)
    cmd = action.build_argv(
        {
            "projectPath": "/work/prostate-cancer/configs/project_H_PCa.json",
            "runDir": "/work/prostate-cancer/monte_carlo_runs/run_0001",
        }
    )
    run_dir_idx = cmd.index("--run-dir")
    assert cmd[run_dir_idx + 1] == "/work/prostate-cancer/monte_carlo_runs/run_0001"
