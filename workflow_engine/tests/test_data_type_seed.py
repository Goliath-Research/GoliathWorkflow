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


def test_primitive_json_schema(seed) -> None:
    integer_schema = seed.primitive_json_schema("int")
    assert integer_schema["type"] == "integer"
    assert integer_schema["title"] == "int"
    dt = seed.primitive_json_schema("datetime")
    assert dt["type"] == "string"
    assert dt["format"] == "date-time"


def test_editor_schema_keeps_full_root_document(seed) -> None:
    root = {
        "title": "Foo",
        "type": "object",
        "properties": {"x": {"$ref": "#/$defs/Bar"}},
        "$defs": {"Bar": {"type": "object", "properties": {"n": {"type": "integer"}}}},
    }
    doc = seed.editor_schema_document(
        "Foo", root, defs=root["$defs"], root_document=root
    )
    assert doc["properties"]["x"]["$ref"] == "#/$defs/Bar"
    assert doc["$defs"]["Bar"]["type"] == "object"


def test_editor_schema_nested_def_includes_siblings(seed) -> None:
    root = {
        "$defs": {
            "A": {"type": "object", "properties": {}},
            "B": {"$ref": "#/$defs/A"},
        }
    }
    doc = seed.editor_schema_document("B", root["$defs"]["B"], defs=root["$defs"])
    assert doc["$ref"] == "#/$defs/A"
    assert doc["$defs"]["A"]["type"] == "object"
    assert doc["title"] == "B"


def test_array_and_enum_schemas(seed) -> None:
    arr = seed.array_json_schema("Foo.items.array", "Bar", defs={"Bar": {"type": "object"}})
    assert arr["type"] == "array"
    assert arr["items"]["$ref"] == "#/$defs/Bar"
    enum_doc = seed.enum_json_schema("Foo.kind", ["a", "b"], description="kind")
    assert enum_doc["enum"] == ["a", "b"]
    assert enum_doc["type"] == "string"


def test_config_guardrail_type_files_exist(seed) -> None:
    assert seed.CONFIG_DIR.is_dir()
    for type_name, filename in seed.CONFIG_GUARDRAIL_TYPES:
        path = seed.CONFIG_DIR / filename
        assert path.is_file(), path
        assert type_name in (
            "sample_prep_guardrails",
            "sample_prep_guardrails_overlay",
            "study_action_config_overlay",
        )


def test_action_definition_removed_from_kinds() -> None:
    from cfg.kinds import CFG_KINDS, MATERIALIZABLE_KINDS

    assert "action_definition" not in CFG_KINDS
    assert "action_definition" not in MATERIALIZABLE_KINDS
