"""Scaffold client-side action stubs from the git action catalog (not cfg)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

_HANDLER_STUB = '''\
"""Scaffolded in-process handler for {action_name} — replace with real implementation."""

from __future__ import annotations

# from methyl_worker.task_models import {class_prefix}TaskInput, {class_prefix}TaskOutput


def handle_{slug}(
    _capability: str,
    _action_name: str,
    input: {class_prefix}TaskInput,
) -> {class_prefix}TaskOutput:
    """Wire into ACTION_CATALOG in_process_handler after implementing science logic."""
    raise NotImplementedError(
        "Action {action_name!r} was scaffolded; implement worker handler."
    )


# Catalog registration note (merge into workers/methyl_worker/action_catalog.py):
# in_process(
#     "{action_name}",
#     "{capability}",
#     in_process_handler="handle_{slug}",  # or handlers.<module>._handle_{slug}
#     action_config_key=None,
# )
'''

_CATALOG_STUB = '''\
# Scaffold entry for {action_name} — merge into action_catalog.ACTION_CATALOG
# action_name={action_name!r}
# capability={capability!r}
# schema_id={schema_id!r}
# execution_mode="in_process"  # or "cli"
# Next steps:
#   1. Fill Pydantic models under workers/methyl_worker/task_models/
#   2. Implement handler; set in_process_handler / register_cli_provider
#   3. methyl-export-action-catalog && methyl-export-task-schemas
#   4. methyl-cfg sync-actions   # seeds wf.workflow_action + wf.data_type
'''

_PYDANTIC_STUB = '''\
"""Scaffolded task I/O models for {action_name} — tighten fields from JSON Schema."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class {class_prefix}TaskInput(BaseModel):
    """Wire/identity fields only; tunables belong in resolvedConfig / actionConfig."""

    projectPath: Optional[str] = Field(
        default=None,
        description="Study project JSON path (identity / provenance).",
    )
    resolvedConfig: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Baked actionConfig slice; do not author science knobs on the wire.",
    )
    stepOverride: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Per-invocation overlay (program/MC); operator-set where applicable.",
    )


class {class_prefix}TaskOutput(BaseModel):
    status: str = Field(default="ok", description="Handler completion status.")
'''

_PROGRAM_SNIPPET = '''\
# DomainProgram step snippet for {action_name}
# Paste into a phase steps[] array (sample_prep / lifecycle / custom program):
#
# {{
#   "nodeKey": "{slug}",
#   "action": "{action_name}",
#   "with": {{
#     "projectPath": "${{var.projectPath}}"
#   }}
# }}
'''


def _slug(action_name: str) -> str:
    return action_name.replace(".", "_").replace("-", "_")


def _class_prefix(action_name: str) -> str:
    parts = [p.capitalize() for p in action_name.replace("-", "_").split(".")]
    return "".join(parts)


def _load_catalog_entry(repo_root: Path, action_name: str) -> Optional[Dict[str, Any]]:
    catalog_path = repo_root / "schemas" / "actions" / "catalog.json"
    if not catalog_path.is_file():
        return None
    doc = json.loads(catalog_path.read_text(encoding="utf-8"))
    actions = doc.get("actions") if isinstance(doc, dict) else None
    if isinstance(actions, list):
        for row in actions:
            if isinstance(row, dict) and row.get("action_name") == action_name:
                return row
    if isinstance(actions, dict) and action_name in actions:
        entry = actions[action_name]
        if isinstance(entry, dict):
            return {"action_name": action_name, **entry}
    return None


def define_scaffold_action(
    *,
    action_name: str,
    capability: str,
    input_schema: Optional[Dict[str, Any]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
    document: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return an in-memory action document used by scaffold (no cfg write)."""
    return {
        "action_name": action_name,
        "capability": capability,
        "schema_id": action_name.replace(".", "_"),
        "implementationStatus": "scaffolded",
        "input_schema": input_schema or {"type": "object"},
        "output_schema": output_schema or {"type": "object"},
        **(document or {}),
    }


# Back-compat alias — previously upserted cfg.action_definition.
def upsert_server_action(
    store: Any = None,
    *,
    action_name: str,
    capability: str,
    input_schema: Optional[Dict[str, Any]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
    document: Optional[Dict[str, Any]] = None,
    version: str = "1",
    publish: bool = True,
) -> Dict[str, Any]:
    del store, version, publish
    doc = define_scaffold_action(
        action_name=action_name,
        capability=capability,
        input_schema=input_schema,
        output_schema=output_schema,
        document=document,
    )
    return {"name": action_name, "version": "1", "status": "scaffolded", "document": doc}


def scaffold_action(
    store: Any = None,
    action_name: str = "",
    *,
    repo_root: Path | str,
    version: str = "1",
    force: bool = False,
    emit_pydantic: bool = True,
    emit_program_snippet: bool = True,
    document: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Emit task schema files, catalog note, handler stub, optional Pydantic models,
    and DomainProgram step snippet from the git catalog (or an explicit document).

    Actions and I/O types are seeded into wf via ``methyl-cfg sync-actions``;
    this helper does not write ``cfg.action_definition``.
    """
    del store, version
    repo_root = Path(repo_root)
    doc = document or _load_catalog_entry(repo_root, action_name) or {}
    if not doc:
        raise KeyError(
            f"action not found in schemas/actions/catalog.json: {action_name} "
            "(pass --define or add a catalog entry)"
        )
    slug = _slug(action_name)
    class_prefix = _class_prefix(action_name)
    schema_id = doc.get("schema_id") or slug
    capability = doc.get("capability") or action_name.split(".")[0]

    input_schema = doc.get("input_schema") or {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"{action_name}Input",
        "type": "object",
        "additionalProperties": True,
    }
    output_schema = doc.get("output_schema") or {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"{action_name}Output",
        "type": "object",
        "additionalProperties": True,
    }

    # Prefer committed task schemas when present
    tasks_dir = repo_root / "schemas" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    in_path = tasks_dir / f"{schema_id}.input.schema.json"
    out_path = tasks_dir / f"{schema_id}.output.schema.json"
    written = []
    for path, schema in ((in_path, input_schema), (out_path, output_schema)):
        if path.exists() and not force:
            written.append(f"skip:{path}")
        else:
            path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
            written.append(str(path))

    stub_dir = repo_root / "workers" / "methyl_worker" / "scaffolded"
    stub_dir.mkdir(parents=True, exist_ok=True)
    handler_path = stub_dir / f"{slug}.py"
    if handler_path.exists() and not force:
        written.append(f"skip:{handler_path}")
    else:
        handler_path.write_text(
            _HANDLER_STUB.format(
                action_name=action_name,
                slug=slug,
                capability=capability,
                class_prefix=class_prefix,
            ),
            encoding="utf-8",
        )
        written.append(str(handler_path))

    note_path = stub_dir / f"{slug}.catalog.txt"
    note_path.write_text(
        _CATALOG_STUB.format(
            action_name=action_name, capability=capability, schema_id=schema_id
        ),
        encoding="utf-8",
    )
    written.append(str(note_path))

    if emit_pydantic:
        models_dir = repo_root / "workers" / "methyl_worker" / "task_models"
        models_dir.mkdir(parents=True, exist_ok=True)
        model_path = models_dir / f"{slug}_scaffold.py"
        if model_path.exists() and not force:
            written.append(f"skip:{model_path}")
        else:
            model_path.write_text(
                _PYDANTIC_STUB.format(
                    action_name=action_name, class_prefix=class_prefix
                ),
                encoding="utf-8",
            )
            written.append(str(model_path))

    if emit_program_snippet:
        snip_path = stub_dir / f"{slug}.program_step.jsonc"
        if snip_path.exists() and not force:
            written.append(f"skip:{snip_path}")
        else:
            snip_path.write_text(
                _PROGRAM_SNIPPET.format(action_name=action_name, slug=slug),
                encoding="utf-8",
            )
            written.append(str(snip_path))

    return {
        "action": action_name,
        "written": written,
        "implementationStatus": doc.get("implementationStatus") or "scaffolded",
    }
