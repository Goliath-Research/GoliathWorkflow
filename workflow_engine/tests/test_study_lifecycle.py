"""Tests for study lifecycle admin helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

WF_ENGINE = Path(__file__).resolve().parents[1]
if str(WF_ENGINE) not in sys.path:
    sys.path.insert(0, str(WF_ENGINE))

from ops.study_lifecycle import (  # noqa: E402
    _apply_project_path_scope_default,
    compile_program_spec,
)


def test_apply_project_path_scope_default_replaces_circular_expr(tmp_path: Path) -> None:
    project = tmp_path / "project.json"
    project.write_text("{}", encoding="utf-8")
    spec = {
        "root_node_key": "root",
        "scope_defaults": [
            {
                "node_key": "root",
                "var_name": "projectPath",
                "default_expr": "${var.projectPath}",
            }
        ],
    }
    _apply_project_path_scope_default(spec, str(project))
    project_default = next(
        item for item in spec["scope_defaults"] if item["var_name"] == "projectPath"
    )
    assert project_default["default_expr"] == json.dumps(str(project.resolve()))
    assert "context_defaults" not in spec


def test_compile_program_spec_pins_body_project_path(tmp_path: Path) -> None:
    program_path = tmp_path / "lifecycle.program.json"
    project_in_program = tmp_path / "embedded.json"
    project_in_body = tmp_path / "override.json"
    project_in_program.write_text("{}", encoding="utf-8")
    project_in_body.write_text("{}", encoding="utf-8")
    program_path.write_text(
        json.dumps(
            {
                "programVersion": 2,
                "name": "TestLifecycle",
                "projectPath": str(project_in_program),
                "body": [],
            }
        ),
        encoding="utf-8",
    )

    spec = compile_program_spec(program_path, project_path=str(project_in_body))
    project_default = next(
        item for item in spec["scope_defaults"] if item["var_name"] == "projectPath"
    )
    assert project_default["default_expr"] == json.dumps(str(project_in_body.resolve()))
    chrom_binding = next(
        item for item in spec["collection_bindings"] if item["scope_var"] == "project"
    )
    assert chrom_binding["path_var"] == "projectPath"
