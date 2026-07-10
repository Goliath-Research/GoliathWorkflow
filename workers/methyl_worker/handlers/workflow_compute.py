"""In-process handlers for typed workflow.compute actions."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from methyl_worker.depends import Depends, get_logger
from methyl_worker.task_models.workflow_compute_models import (
    ConstBoolTaskInput,
    ConstBoolTaskOutput,
    ConstIntTaskInput,
    ConstIntTaskOutput,
    ConstPathTaskInput,
    ConstPathTaskOutput,
    ConstStringTaskInput,
    ConstStringTaskOutput,
    FsStatTaskInput,
    FsStatTaskOutput,
    JsonPathBoolTaskInput,
    JsonPathBoolTaskOutput,
    JsonPathIntTaskInput,
    JsonPathIntTaskOutput,
    JsonPathStringTaskInput,
    JsonPathStringTaskOutput,
)


def _resolve_json_path(document: Any, json_path: str) -> Any:
    path = json_path.strip()
    if path.startswith("$"):
        path = path[1:]
    if path.startswith("."):
        path = path[1:]
    if not path:
        return document
    cur: Any = document
    for part in path.split("."):
        if part == "":
            continue
        if isinstance(cur, dict):
            if part not in cur:
                raise KeyError(f"json path segment {part!r} missing")
            cur = cur[part]
        else:
            raise TypeError(f"cannot traverse {part!r} into non-object")
    return cur


def _load_json_file(path: str) -> Any:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"JSON document not found: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


def _as_model(input: BaseModel, cls: type[BaseModel]) -> BaseModel:
    if isinstance(input, cls):
        return input
    return cls.model_validate(input.model_dump(mode="json"))


def _handle_workflow_const_bool(
    _capability: str,
    _action_name: str,
    input: BaseModel,
    log: logging.Logger = Depends(get_logger),
) -> ConstBoolTaskOutput:
    inp = _as_model(input, ConstBoolTaskInput)
    assert isinstance(inp, ConstBoolTaskInput)
    log.debug("workflow.const_bool value=%s", inp.value)
    return ConstBoolTaskOutput(value=inp.value, result_code=0, exit_code=0, status="ok")


def _handle_workflow_const_int(
    _capability: str,
    _action_name: str,
    input: BaseModel,
    log: logging.Logger = Depends(get_logger),
) -> ConstIntTaskOutput:
    inp = _as_model(input, ConstIntTaskInput)
    assert isinstance(inp, ConstIntTaskInput)
    return ConstIntTaskOutput(value=inp.value, result_code=0, exit_code=0, status="ok")


def _handle_workflow_const_string(
    _capability: str,
    _action_name: str,
    input: BaseModel,
    log: logging.Logger = Depends(get_logger),
) -> ConstStringTaskOutput:
    inp = _as_model(input, ConstStringTaskInput)
    assert isinstance(inp, ConstStringTaskInput)
    return ConstStringTaskOutput(value=inp.value, result_code=0, exit_code=0, status="ok")


def _handle_workflow_const_path(
    _capability: str,
    _action_name: str,
    input: BaseModel,
    log: logging.Logger = Depends(get_logger),
) -> ConstPathTaskOutput:
    inp = _as_model(input, ConstPathTaskInput)
    assert isinstance(inp, ConstPathTaskInput)
    return ConstPathTaskOutput(value=inp.value, result_code=0, exit_code=0, status="ok")


def _handle_workflow_json_path_bool(
    _capability: str,
    _action_name: str,
    input: BaseModel,
    log: logging.Logger = Depends(get_logger),
) -> JsonPathBoolTaskOutput:
    inp = _as_model(input, JsonPathBoolTaskInput)
    assert isinstance(inp, JsonPathBoolTaskInput)
    raw = _resolve_json_path(_load_json_file(inp.documentPath), inp.jsonPath)
    if not isinstance(raw, bool):
        raise TypeError(f"json path {inp.jsonPath!r} expected bool, got {type(raw).__name__}")
    return JsonPathBoolTaskOutput(value=raw, result_code=0, exit_code=0, status="ok")


def _handle_workflow_json_path_int(
    _capability: str,
    _action_name: str,
    input: BaseModel,
    log: logging.Logger = Depends(get_logger),
) -> JsonPathIntTaskOutput:
    inp = _as_model(input, JsonPathIntTaskInput)
    assert isinstance(inp, JsonPathIntTaskInput)
    raw = _resolve_json_path(_load_json_file(inp.documentPath), inp.jsonPath)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TypeError(f"json path {inp.jsonPath!r} expected int, got {type(raw).__name__}")
    return JsonPathIntTaskOutput(value=raw, result_code=0, exit_code=0, status="ok")


def _handle_workflow_json_path_string(
    _capability: str,
    _action_name: str,
    input: BaseModel,
    log: logging.Logger = Depends(get_logger),
) -> JsonPathStringTaskOutput:
    inp = _as_model(input, JsonPathStringTaskInput)
    assert isinstance(inp, JsonPathStringTaskInput)
    raw = _resolve_json_path(_load_json_file(inp.documentPath), inp.jsonPath)
    if not isinstance(raw, str):
        raise TypeError(f"json path {inp.jsonPath!r} expected str, got {type(raw).__name__}")
    return JsonPathStringTaskOutput(value=raw, result_code=0, exit_code=0, status="ok")


def _handle_workflow_fs_stat(
    _capability: str,
    _action_name: str,
    input: BaseModel,
    log: logging.Logger = Depends(get_logger),
) -> FsStatTaskOutput:
    inp = _as_model(input, FsStatTaskInput)
    assert isinstance(inp, FsStatTaskInput)
    p = Path(inp.path)
    if not p.exists():
        return FsStatTaskOutput(
            exists=False, size=0, mtimeUtc=None, value=False, result_code=0, exit_code=0, status="ok"
        )
    st = p.stat()
    mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return FsStatTaskOutput(
        exists=True,
        size=int(st.st_size),
        mtimeUtc=mtime,
        value=True,
        result_code=0,
        exit_code=0,
        status="ok",
    )
