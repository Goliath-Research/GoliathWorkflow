"""Unit tests for PostgreSQL --dsn catalog seed SQL generation."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

_SEED_PATH = (
    Path(__file__).resolve().parents[1] / "sql_mssql" / "seed_action_catalog.py"
)
_SPEC = importlib.util.spec_from_file_location("seed_action_catalog", _SEED_PATH)
assert _SPEC is not None and _SPEC.loader is not None
seed_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(seed_mod)


def test_upsert_action_psql_emits_twelve_arg_call() -> None:
    captured: list[str] = []

    def fake_exec(dsn: str, sql: str) -> None:
        captured.append(sql)

    with patch.object(seed_mod, "_exec_psql", side_effect=fake_exec):
        seed_mod._upsert_action_psql(
            "postgresql://localhost/test",
            "pipeline.centroid",
            "methyl-centroid",
            "pipeline.centroid",
            execution_mode="cli",
            cli_tool="methyl-centroid",
            in_process_handler=None,
            argv_map={"project": "--project", "outputDir": "--output-dir"},
            max_per_worker=None,
            exclusive_worker=False,
        )

    assert len(captured) == 1
    sql = captured[0]
    assert sql.startswith("CALL wf.wf_repo_upsert_workflow_action(")
    assert "'pipeline.centroid'" in sql
    assert "'methyl-centroid'" in sql
    assert "'cli'" in sql
    assert "NULL" in sql  # in_process_handler / max_per_worker / affinity_key_field
    assert "::jsonb" in sql
    # trailing: exclusive, affinity_key_field, prefer_previous, prefer_continue
    assert sql.rstrip().endswith("NULL, false, false);")
    assert sql.count(",") >= 11


def test_upsert_action_psql_exclusive_dispatch() -> None:
    captured: list[str] = []

    with patch.object(seed_mod, "_exec_psql", side_effect=lambda dsn, sql: captured.append(sql)):
        seed_mod._upsert_action_psql(
            "postgresql://localhost/test",
            "sample.methylgrapher_wgbs_align",
            "methylgrapher.wgbs_align",
            "sample.methylgrapher_wgbs_align",
            execution_mode="in_process",
            cli_tool=None,
            in_process_handler="_handle_methylgrapher_wgbs_align",
            argv_map=None,
            max_per_worker=1,
            exclusive_worker=True,
            affinity_key_field="sampleId",
            prefer_previous_worker=True,
            prefer_continue_group=True,
        )

    sql = captured[0]
    assert "'_handle_methylgrapher_wgbs_align'" in sql
    assert ", 1, true, 'sampleId', true, true);" in sql


def test_upsert_action_psql_null_dispatch_fields() -> None:
    captured: list[str] = []

    with patch.object(seed_mod, "_exec_psql", side_effect=lambda dsn, sql: captured.append(sql)):
        seed_mod._upsert_action_psql(
            "postgresql://localhost/test",
            "validation.biomarker_filter",
            "validation.biomarker-filter",
            "validation.biomarker_filter",
            execution_mode="in_process",
            cli_tool=None,
            in_process_handler="_handle_validation_biomarker_filter",
            argv_map=None,
        )

    sql = captured[0]
    assert "'_handle_validation_biomarker_filter'" in sql
    assert "'in_process'" in sql
    assert sql.rstrip().endswith("NULL, false, false);")
