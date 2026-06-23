"""Admin-tier gateway handlers (catalog seed, compile, deploy)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from workflow_definition_spec import WorkflowDefinitionSpec


def seed_action_catalog(
    db: Any,
    body: Dict[str, Any],
    *,
    upsert_workflow_action: Callable[..., None],
    upsert_action_schema: Callable[..., None],
) -> Dict[str, Any]:
    catalog = body.get("catalog") if isinstance(body.get("catalog"), dict) else body
    actions: List[dict[str, Any]] = list(catalog.get("actions") or [])
    schemas: List[dict[str, Any]] = list(body.get("schemas") or [])

    action_count = 0
    errors: List[str] = []
    for action in actions:
        try:
            upsert_workflow_action(
                db,
                str(action["action_name"]),
                str(action.get("capability") or "") or None,
                str(action.get("schema_id") or action["action_name"]),
            )
            action_count += 1
        except Exception as exc:
            errors.append(f"{action.get('action_name')}: {exc}")

    schema_count = 0
    for item in schemas:
        try:
            upsert_action_schema(
                db,
                str(item["action_name"]),
                str(item["direction"]),
                dict(item["schema_json"]),
                str(item.get("schema_id") or item["action_name"]),
            )
            schema_count += 1
        except Exception as exc:
            errors.append(f"{item.get('action_name')}/{item.get('direction')}: {exc}")

    return {
        "actions_upserted": action_count,
        "schemas_upserted": schema_count,
        "errors": errors,
    }


def compile_domain_program(body: Dict[str, Any]) -> Dict[str, Any]:
    from .study_lifecycle import _compile_program_spec

    program_path = body.get("program_path")
    program = body.get("program")
    project_path = body.get("projectPath") or body.get("project_path")

    if program_path:
        spec = _compile_program_spec(Path(str(program_path)), project_path=project_path)
    elif program is not None:
        import tempfile

        tmp = Path(tempfile.mkdtemp()) / "program.json"
        tmp.write_text(json.dumps(program), encoding="utf-8")
        spec = _compile_program_spec(tmp, project_path=project_path)
    else:
        raise ValueError("program or program_path is required")

    return {"spec": spec}


def deploy_workflow_definition(
    db: Any,
    body: Dict[str, Any],
    *,
    create_workflow_definition: Callable[..., Dict[str, Any]],
    delete_workflow_definition: Callable[..., Dict[str, int]],
) -> Dict[str, Any]:
    replace = bool(body.get("replace", False))
    spec = body.get("spec")

    if spec is None and (body.get("program") is not None or body.get("program_path")):
        spec = compile_domain_program(body)["spec"]
    elif spec is None:
        spec = WorkflowDefinitionSpec.model_validate(body).to_db_spec()
    elif isinstance(spec, dict) and "nodes" in spec:
        spec = WorkflowDefinitionSpec.model_validate(spec).to_db_spec()
    else:
        raise ValueError("spec, program, or program_path is required")

    name = str(spec.get("name") or "")
    if not name:
        raise ValueError("workflow spec missing name")

    if replace:
        delete_workflow_definition(db, name, bool(body.get("delete_instances", True)))

    return create_workflow_definition(db, spec)


def list_workflow_definitions(db: Any) -> Dict[str, Any]:
    rows = db.list_workflow_definitions()
    return {"definitions": rows}


def get_workflow_definition_by_name(db: Any, name: str) -> Dict[str, Any]:
    return db.get_workflow_definition_by_name(name)
