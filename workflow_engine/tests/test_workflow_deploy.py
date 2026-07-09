"""Regression tests for ops.workflow_deploy (import path + callable signature)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

WF_ENGINE = Path(__file__).resolve().parents[1]
if str(WF_ENGINE) not in sys.path:
    sys.path.insert(0, str(WF_ENGINE))


def test_deploy_workflow_definition_imports_without_contract_preloaded() -> None:
    """Bug 1: module must load with only workflow_engine/ on sys.path."""
    # Drop contract/ if a prior import left it on the path.
    contract = str(WF_ENGINE / "contract")
    sys.path[:] = [p for p in sys.path if p != contract]
    sys.modules.pop("ops.workflow_deploy", None)
    sys.modules.pop("workflow_definition_spec", None)

    from ops.workflow_deploy import deploy_workflow_definition  # noqa: F401

    assert callable(deploy_workflow_definition)


def test_deploy_workflow_definition_passes_db_then_spec_to_wrappers() -> None:
    """Bug 2: callables must accept (db, spec) like rest.db_client wrappers."""
    from ops.workflow_deploy import deploy_workflow_definition

    db = MagicMock()
    created: list[tuple[object, object]] = []
    deleted: list[tuple[object, str, bool]] = []

    def create_workflow_definition(db_or_dsn, spec):
        created.append((db_or_dsn, spec))
        return {"workflow_version_id": 9, "name": spec["name"]}

    def delete_workflow_definition(db_or_dsn, name, delete_instances):
        deleted.append((db_or_dsn, name, delete_instances))
        return {"deleted_instance_count": 0, "deleted_version_count": 1}

    result = deploy_workflow_definition(
        db,
        {
            "spec": {
                "name": "SamplePrepPipeline",
                "root_node_key": "root",
                "nodes": [{"node_key": "root", "node_type": "SEQUENCE"}],
            },
            "replace": True,
            "delete_instances": False,
        },
        create_workflow_definition=create_workflow_definition,
        delete_workflow_definition=delete_workflow_definition,
    )

    assert result["workflow_version_id"] == 9
    assert deleted == [(db, "SamplePrepPipeline", False)]
    assert len(created) == 1
    assert created[0][0] is db
    assert created[0][1]["name"] == "SamplePrepPipeline"


def test_bound_db_methods_are_incompatible_with_deploy_signature() -> None:
    """Document why scripts must pass db_client wrappers, not bound methods."""
    from ops.workflow_deploy import deploy_workflow_definition

    db = MagicMock()
    db.create_workflow_definition = MagicMock(
        side_effect=lambda spec: {"workflow_version_id": 1, "name": spec["name"]}
    )
    db.delete_workflow_definition = MagicMock(
        side_effect=lambda name, delete_instances: {
            "deleted_instance_count": 0,
            "deleted_version_count": 1,
        }
    )

    body = {
        "spec": {
            "name": "X",
            "root_node_key": "root",
            "nodes": [{"node_key": "root", "node_type": "SEQUENCE"}],
        },
        "replace": True,
    }
    try:
        deploy_workflow_definition(
            db,
            body,
            create_workflow_definition=db.create_workflow_definition,
            delete_workflow_definition=db.delete_workflow_definition,
        )
        raised = False
    except TypeError:
        raised = True
    assert raised, "bound methods must not satisfy (db, spec) call convention"
