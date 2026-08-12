"""Unit tests for wf.data_type seed flatten helpers (no DB)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SEED_PATH = REPO / "workflow_engine" / "sql_mssql" / "seed_data_types.py"


def _load_seed_module():
    spec = importlib.util.spec_from_file_location("seed_data_types", SEED_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def seed():
    return _load_seed_module()


def test_json_type_to_kind_primitives(seed) -> None:
    assert seed._json_type_to_kind({"type": "string"}) == ("string", None)
    assert seed._json_type_to_kind({"type": "integer"}) == ("int", None)
    assert seed._json_type_to_kind({"type": "number"}) == ("number", None)
    assert seed._json_type_to_kind({"type": "boolean"}) == ("bool", None)
    assert seed._json_type_to_kind({"type": "string", "format": "date-time"}) == (
        "datetime",
        None,
    )


def test_json_type_to_kind_enum_and_ref(seed) -> None:
    assert seed._json_type_to_kind({"type": "string", "enum": ["a", "b"]}) == (
        "enum",
        None,
    )
    assert seed._json_type_to_kind({"$ref": "#/$defs/MethylSampleRef"}) == (
        "object",
        "MethylSampleRef",
    )


def test_json_type_to_kind_nullable_union(seed) -> None:
    kind, _ = seed._json_type_to_kind(
        {"anyOf": [{"type": "string"}, {"type": "null"}]}
    )
    assert kind == "string"


def test_json_type_to_kind_array(seed) -> None:
    kind, ref = seed._json_type_to_kind(
        {"type": "array", "items": {"$ref": "#/$defs/Foo"}}
    )
    assert kind == "array"
    assert ref == "Foo"


def test_action_definition_removed_from_kinds() -> None:
    from cfg.kinds import CFG_KINDS, MATERIALIZABLE_KINDS

    assert "action_definition" not in CFG_KINDS
    assert "action_definition" not in MATERIALIZABLE_KINDS
