"""Validate workflow task input_json / output_json against registered Pydantic models."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel, ValidationError

from .task_schema_registry import resolve_task_schema_spec

TASK_VALIDATION_ERROR_CODE = 4001


class TaskValidationError(ValueError):
    def __init__(self, message: str, *, direction: str, action_name: str) -> None:
        super().__init__(message)
        self.direction = direction
        self.action_name = action_name


def _validate(model: type[BaseModel], payload: Dict[str, Any]) -> None:
    model.model_validate(payload)


def validate_task_input(
    action_name: str,
    capability: Optional[str],
    input_json: Dict[str, Any],
) -> None:
    spec = resolve_task_schema_spec(action_name, capability)
    if spec is None:
        return
    try:
        _validate(spec.load_input_model(), input_json)
    except ValidationError as exc:
        raise TaskValidationError(
            f"input_json failed schema validation for {action_name}: {exc}",
            direction="input",
            action_name=action_name,
        ) from exc


def validate_task_output(
    action_name: str,
    capability: Optional[str],
    output_json: Dict[str, Any],
) -> None:
    spec = resolve_task_schema_spec(action_name, capability)
    if spec is None:
        return
    try:
        _validate(spec.load_output_model(), output_json)
    except ValidationError as exc:
        raise TaskValidationError(
            f"output_json failed schema validation for {action_name}: {exc}",
            direction="output",
            action_name=action_name,
        ) from exc


def try_validate_task_input(
    action_name: str,
    capability: Optional[str],
    input_json: Dict[str, Any],
) -> Optional[str]:
    try:
        validate_task_input(action_name, capability, input_json)
        return None
    except TaskValidationError as exc:
        return str(exc)


def try_validate_task_output(
    action_name: str,
    capability: Optional[str],
    output_json: Dict[str, Any],
) -> Optional[str]:
    try:
        validate_task_output(action_name, capability, output_json)
        return None
    except TaskValidationError as exc:
        return str(exc)
