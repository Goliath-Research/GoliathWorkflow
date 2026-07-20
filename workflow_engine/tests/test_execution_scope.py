"""Tests for execution-scope REST helpers (formerly hyperparameter set)."""

from __future__ import annotations

from rest.execution_scope import (
    extract_execution_scope_payload,
    extract_resolved_config_slices,
)


def test_extract_resolved_config_slices() -> None:
    ctx = {
        "resolvedConfig__detection": {"alpha": 0.05},
        "resolvedConfig__validation": {"n_iterations": 10},
        "executionScopeId": "abc",
    }
    slices = extract_resolved_config_slices(ctx)
    assert slices == {
        "resolvedConfig__detection": {"alpha": 0.05},
        "resolvedConfig__validation": {"n_iterations": 10},
    }


def test_extract_execution_scope_payload_includes_name_and_config() -> None:
    ctx = {
        "executionScopeId": "deadbeef",
        "executionScopeName": "tier-a",
        "resolvedConfig__detection": {"alpha": 0.05},
    }
    payload = extract_execution_scope_payload(ctx)
    assert payload is not None
    assert payload["set_key"] == "deadbeef"
    assert payload["display_name"] == "tier-a"
    assert payload["config_json"]["resolvedConfig__detection"]["alpha"] == 0.05


def test_extract_execution_scope_payload_accepts_legacy_alias() -> None:
    ctx = {
        "hyperparamSetId": "legacy",
        "hyperparamSetName": "old-name",
        "resolvedConfig__detection": {"alpha": 0.05},
    }
    payload = extract_execution_scope_payload(ctx)
    assert payload is not None
    assert payload["set_key"] == "legacy"
    assert payload["display_name"] == "old-name"


def test_extract_execution_scope_payload_missing_id() -> None:
    assert extract_execution_scope_payload({"resolvedConfig__detection": {}}) is None
