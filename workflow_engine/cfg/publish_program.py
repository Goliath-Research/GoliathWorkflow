"""Publish DomainProgram from cfg: compile + optional DB deploy + materialize IR."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .materialize import materialize_store
from .store import ConfigStore


def _ensure_paths(repo_root: Path) -> None:
    root = str(repo_root)
    we = str(repo_root / "workflow_engine")
    for p in (root, we, str(repo_root / "packages" / "methyldomain")):
        if p not in sys.path:
            sys.path.insert(0, p)


def publish_program(
    store: ConfigStore,
    name: str,
    *,
    version: str = "1",
    repo_root: Path | str,
    work_root: Path | str,
    deploy_db: bool = False,
    replace: bool = True,
    db: Any = None,
) -> Dict[str, Any]:
    """
    Compile DomainProgram IR from cfg, optionally deploy to ``wf``, materialize JSON.
    """
    repo_root = Path(repo_root)
    work_root = Path(work_root)
    _ensure_paths(repo_root)

    rec = store.get("domain_program", name, version=version, include_secret=False)
    if rec is None:
        raise KeyError(f"domain_program not found: {name}@{version}")

    from methyl_domain.program import DomainProgram

    # domain/ must be importable as top-level for compiler
    domain_dir = str(repo_root / "workflow_engine" / "domain")
    if domain_dir not in sys.path:
        sys.path.insert(0, domain_dir)
    from compiler import compile_domain_program

    program = DomainProgram.model_validate(rec.document)
    compiled = compile_domain_program(program)
    spec = compiled.workflow.model_dump(mode="json")

    # Persist compiled artifact under store extra + work env
    compiled_dir = work_root / "epimethyl" / "env" / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)
    compiled_path = compiled_dir / f"{name}.compiled.json"
    compiled_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")

    store.publish("domain_program", name, version)
    wf_version_id: Optional[int] = None
    deploy_result: Optional[Dict[str, Any]] = None

    if deploy_db:
        if db is None:
            raise ValueError("deploy_db=True requires a db client")
        from ops.workflow_deploy import deploy_workflow_definition
        from rest import db_client

        deploy_result = deploy_workflow_definition(
            db,
            {"spec": spec, "replace": replace},
            create_workflow_definition=db_client.create_workflow_definition,
            delete_workflow_definition=db_client.delete_workflow_definition,
        )
        wf_version_id = (
            deploy_result.get("workflow_version_id")
            or deploy_result.get("workflowVersionId")
            or deploy_result.get("id")
        )
        if wf_version_id is not None:
            store.set_extra(
                "domain_program",
                name,
                version,
                compiledWorkflowVersionId=wf_version_id,
            )

    mat = materialize_store(
        store,
        work_root,
        kinds=["domain_program"],
    )
    return {
        "name": name,
        "version": version,
        "compiledPath": str(compiled_path),
        "workflowVersionId": wf_version_id,
        "deploy": deploy_result,
        "materialize": mat,
    }
