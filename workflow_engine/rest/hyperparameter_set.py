"""Deprecated shim: use :mod:`rest.execution_scope`.

The wf engine renamed the process-agnostic "hyperparameter set" concept to
"execution scope". This module re-exports the new API under the legacy names for
one release; new code should import from ``rest.execution_scope`` directly.
"""

from __future__ import annotations

from .execution_scope import (
    extract_execution_scope_payload,
    extract_resolved_config_slices,
    sync_execution_scope_action_entry_after_submit,
)

# Legacy aliases (removed after one release).
extract_hyperparameter_set_payload = extract_execution_scope_payload
sync_hyperparameter_action_entry_after_submit = (
    sync_execution_scope_action_entry_after_submit
)

__all__ = [
    "extract_resolved_config_slices",
    "extract_execution_scope_payload",
    "extract_hyperparameter_set_payload",
    "sync_execution_scope_action_entry_after_submit",
    "sync_hyperparameter_action_entry_after_submit",
]
