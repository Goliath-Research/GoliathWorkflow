"""Admin-tier gateway handlers (catalog seed, deploy)."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from workflow_definition_spec import WorkflowDefinitionSpec


def _dispatch_fields(action: dict[str, Any]) -> dict[str, Any]:
    argv_map = action.get("argv_map")
    return {
        "execution_mode": action.get("execution_mode"),
        "cli_tool": action.get("cli_tool"),
        "in_process_handler": action.get("in_process_handler"),
        "argv_map": dict(argv_map) if isinstance(argv_map, dict) else None,
    }


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
                **_dispatch_fields(action),
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


def deploy_workflow_definition(
    db: Any,
    body: Dict[str, Any],
    *,
    create_workflow_definition: Callable[..., Dict[str, Any]],
    delete_workflow_definition: Callable[..., Dict[str, int]],
) -> Dict[str, Any]:
    replace = bool(body.get("replace", False))
    spec = body.get("spec")

    if spec is None:
        spec = WorkflowDefinitionSpec.model_validate(body).to_db_spec()
    elif isinstance(spec, dict) and "nodes" in spec:
        spec = WorkflowDefinitionSpec.model_validate(spec).to_db_spec()
    else:
        raise ValueError("spec is required (compiled WorkflowDefinitionSpec JSON)")

    name = str(spec.get("name") or "")
    if not name:
        raise ValueError("workflow spec missing name")

    if replace:
        delete_workflow_definition(db, name, bool(body.get("delete_instances", True)))

    return create_workflow_definition(db, spec)


def list_workflow_definitions(
    db: Any, *, source: Optional[str] = None
) -> Dict[str, Any]:
    if source is not None and source not in ("system", "portal"):
        raise ValueError("source must be 'system' or 'portal'")
    rows = db.list_workflow_definitions(source_filter=source)
    return {"definitions": rows}


def get_workflow_definition_by_name(db: Any, name: str) -> Dict[str, Any]:
    return db.get_workflow_definition_by_name(name)
