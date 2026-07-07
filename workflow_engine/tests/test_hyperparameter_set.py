"""Tests for hyperparameter set REST helpers."""

from __future__ import annotations

from rest.hyperparameter_set import (
    extract_hyperparameter_set_payload,
    extract_resolved_config_slices,
)


def test_extract_resolved_config_slices() -> None:
    ctx = {
        "resolvedConfig__detection": {"alpha": 0.05},
        "resolvedConfig__validation": {"n_iterations": 10},
        "hyperparamSetId": "abc",
    }
    slices = extract_resolved_config_slices(ctx)
    assert slices == {
        "resolvedConfig__detection": {"alpha": 0.05},
        "resolvedConfig__validation": {"n_iterations": 10},
    }


def test_extract_hyperparameter_set_payload_includes_name_and_config() -> None:
    ctx = {
        "hyperparamSetId": "deadbeef",
        "hyperparamSetName": "tier-a",
        "resolvedConfig__detection": {"alpha": 0.05},
    }
    payload = extract_hyperparameter_set_payload(ctx)
    assert payload is not None
    assert payload["set_key"] == "deadbeef"
    assert payload["display_name"] == "tier-a"
    assert payload["config_json"]["resolvedConfig__detection"]["alpha"] == 0.05


def test_extract_hyperparameter_set_payload_missing_id() -> None:
    assert extract_hyperparameter_set_payload({"resolvedConfig__detection": {}}) is None
