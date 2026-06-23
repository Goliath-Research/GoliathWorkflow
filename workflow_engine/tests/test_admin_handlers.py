"""Tests for admin gateway handlers."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import json
import pytest

WF_ENGINE = Path(__file__).resolve().parents[1]
REST = WF_ENGINE / "rest"
DOMAIN = WF_ENGINE / "domain"
CONTRACT = WF_ENGINE / "contract"
for _p in (REST, DOMAIN, CONTRACT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from rest.admin_handlers import (  # noqa: E402
    compile_domain_program,
    list_workflow_definitions,
    seed_action_catalog,
)


def test_seed_action_catalog_counts_actions() -> None:
    db = MagicMock()
    upsert_action = MagicMock()
    upsert_schema = MagicMock()
    body = {
        "catalog": {"actions": [{"action_name": "sample.methyl_qc", "capability": "methyl-qc"}]},
        "schemas": [
            {
                "action_name": "sample.methyl_qc",
                "direction": "input",
                "schema_json": {"type": "object"},
                "schema_id": "sample.methyl_qc",
            }
        ],
    }
    result = seed_action_catalog(
        db,
        body,
        upsert_workflow_action=upsert_action,
        upsert_action_schema=upsert_schema,
    )
    assert result["actions_upserted"] == 1
    assert result["schemas_upserted"] == 1
    upsert_action.assert_called_once()
    upsert_schema.assert_called_once()


def test_compile_domain_program_from_json(tmp_path: Path) -> None:
    project = tmp_path / "project.json"
    project.write_text("{}", encoding="utf-8")
    program_path = tmp_path / "program.json"
    program_path.write_text(
        json.dumps(
            {
                "programVersion": 2,
                "name": "MiniFlow",
                "projectPath": str(project),
                "body": [],
            }
        ),
        encoding="utf-8",
    )
    result = compile_domain_program({"program_path": str(program_path), "projectPath": str(project)})
    assert result["spec"]["name"] == "MiniFlow"


def test_list_workflow_definitions_forwards_source_filter() -> None:
    db = MagicMock()
    db.list_workflow_definitions.return_value = [{"name": "PortalFlow", "source": "portal"}]

    result = list_workflow_definitions(db, source="portal")

    db.list_workflow_definitions.assert_called_once_with(source_filter="portal")
    assert result["definitions"] == [{"name": "PortalFlow", "source": "portal"}]


def test_list_workflow_definitions_rejects_invalid_source() -> None:
    with pytest.raises(ValueError, match="source must be"):
        list_workflow_definitions(MagicMock(), source="invalid")
