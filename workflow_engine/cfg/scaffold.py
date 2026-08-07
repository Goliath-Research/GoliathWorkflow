"""Scaffold client-side action stubs from cfg.action_definition (DB → client)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .store import ConfigStore

_HANDLER_STUB = '''\
"""Scaffolded in-process handler for {action_name} — replace with real implementation."""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel


def handle_{slug}(
    _capability: str,
    _action_name: str,
    input: BaseModel,
) -> BaseModel:
    """Wire into ACTION_CATALOG in_process_handler after implementing science logic."""
    raise NotImplementedError(
        "Action {action_name!r} was scaffolded from cfg; implement worker handler."
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
#   4. methyl-cfg sync-actions --seed-wf
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


def scaffold_action(
    store: ConfigStore,
    action_name: str,
    *,
    repo_root: Path | str,
    version: str = "1",
    force: bool = False,
    emit_pydantic: bool = True,
    emit_program_snippet: bool = True,
) -> Dict[str, Any]:
    """
    Emit task schema files, catalog note, handler stub, optional Pydantic models,
    and DomainProgram step snippet from a cfg action_definition.

    Marks implementation_status as ``scaffolded`` unless already ``present``.
    """
    repo_root = Path(repo_root)
    rec = store.get("action_definition", action_name, version=version)
    if rec is None:
        raise KeyError(f"action_definition not found: {action_name}@{version}")
    doc = rec.document
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
                action_name=action_name, slug=slug, capability=capability
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

    impl = rec.extra.get("implementationStatus") or doc.get("implementationStatus")
    if impl != "present":
        store.upsert(
            "action_definition",
            action_name,
            {**doc, "implementationStatus": "scaffolded"},
            version=version,
            status=rec.status,
            extra={"implementationStatus": "scaffolded"},
        )

    return {
        "action": action_name,
        "written": written,
        "implementationStatus": "scaffolded" if impl != "present" else "present",
    }


def upsert_server_action(
    store: ConfigStore,
    *,
    action_name: str,
    capability: str,
    input_schema: Optional[Dict[str, Any]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
    document: Optional[Dict[str, Any]] = None,
    version: str = "1",
    publish: bool = True,
) -> Dict[str, Any]:
    """Create/update an action_definition authored on the server side."""
    doc = {
        "action_name": action_name,
        "capability": capability,
        "schema_id": action_name.replace(".", "_"),
        "implementationStatus": "scaffolded",
        "input_schema": input_schema or {"type": "object"},
        "output_schema": output_schema or {"type": "object"},
        **(document or {}),
    }
    rec = store.upsert(
        "action_definition",
        action_name,
        doc,
        version=version,
        status="published" if publish else "draft",
        extra={"implementationStatus": "scaffolded"},
    )
    return {"name": rec.name, "version": rec.version, "status": rec.status}
