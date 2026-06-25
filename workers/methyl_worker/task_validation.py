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


def _validate_input_model(model: type[BaseModel], payload: Dict[str, Any]) -> None:
    model.model_validate(payload)


def _coerce_output_model(model: type[BaseModel], output: BaseModel) -> BaseModel:
    if isinstance(output, model):
        return output
    return model.model_validate(output)


def normalize_task_input(
    action_name: str,
    capability: Optional[str],
    input_json: Dict[str, Any],
) -> Dict[str, Any]:
    """Drop template fields not in the task input schema (e.g. projectPath)."""
    spec = resolve_task_schema_spec(action_name, capability)
    if spec is None:
        return input_json
    model = spec.load_input_model()
    allowed = set(model.model_fields.keys())
    filtered = {k: v for k, v in input_json.items() if k in allowed}
    return model.model_validate(filtered).model_dump(mode="python", exclude_none=True, exclude_unset=True)


def validate_task_input(
    action_name: str,
    capability: Optional[str],
    input_json: Dict[str, Any],
) -> None:
    spec = resolve_task_schema_spec(action_name, capability)
    if spec is None:
        return
    try:
        normalized = normalize_task_input(action_name, capability, input_json)
        _validate_input_model(spec.load_input_model(), normalized)
    except ValidationError as exc:
        raise TaskValidationError(
            f"input_json failed schema validation for {action_name}: {exc}",
            direction="input",
            action_name=action_name,
        ) from exc


def validate_task_output(
    action_name: str,
    capability: Optional[str],
    output: BaseModel,
) -> BaseModel:
    """Validate an ACTION output model; return the coerced registry output type."""
    spec = resolve_task_schema_spec(action_name, capability)
    if spec is None:
        return output
    try:
        return _coerce_output_model(spec.load_output_model(), output)
    except ValidationError as exc:
        raise TaskValidationError(
            f"output failed schema validation for {action_name}: {exc}",
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
    output: BaseModel,
) -> Optional[str]:
    try:
        validate_task_output(action_name, capability, output)
        return None
    except TaskValidationError as exc:
        return str(exc)
