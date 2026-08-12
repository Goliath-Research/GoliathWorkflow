"""Catalog metadata on cfg.analyte documents + sync item discovery."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ANALYTES = REPO / "workflow_engine" / "domain" / "analytes"
SCHEMA = REPO / "schemas" / "config" / "analyte.schema.json"

_REQUIRED_CATALOG = ("title", "summary", "visibility", "lifecycle", "family")
_VIS = frozenset({"operator", "advanced", "hidden"})
_LIFE = frozenset({"active", "deprecated", "internal"})
_FAM = frozenset({"analyte", "specialty", "legacy"})
_EXPECTED = frozenset(
    {"cfdna", "buffy_coat", "plant_tissue", "combined", "tissue"}
)


def _assert_catalog(cat: object, *, where: str) -> dict:
    assert isinstance(cat, dict), f"{where}: catalog missing"
    for key in _REQUIRED_CATALOG:
        assert key in cat and str(cat[key]).strip(), f"{where}: catalog.{key}"
    assert cat["visibility"] in _VIS, where
    assert cat["lifecycle"] in _LIFE, where
    assert cat["family"] in _FAM, where
    return cat


@pytest.fixture(scope="module")
def catalog_helper():
    from cfg.process_pack_catalog import cfg_status_for_catalog, is_operator_catalog_row

    return cfg_status_for_catalog, is_operator_catalog_row


def test_analyte_schema_exists():
    assert SCHEMA.is_file()
    doc = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert "analyteCatalog" in doc.get("$defs", {})
    assert "name" in doc["required"]
    assert "catalog" in doc["required"]


def test_all_analytes_have_valid_catalog(catalog_helper):
    cfg_status_for_catalog, _ = catalog_helper
    paths = sorted(ANALYTES.glob("*.analyte.json"))
    assert paths, "expected analyte JSON files"
    names = set()
    for path in paths:
        doc = json.loads(path.read_text(encoding="utf-8"))
        name = str(doc.get("name") or "")
        names.add(name)
        assert name == path.name.replace(".analyte.json", ""), path.name
        assert str(doc.get("version") or "").strip(), path.name
        cat = _assert_catalog(doc.get("catalog"), where=path.name)
        status = cfg_status_for_catalog(cat)
        assert status in ("published", "retired")
        aliases = doc.get("aliases") or []
        assert isinstance(aliases, list), path.name
    assert _EXPECTED.issubset(names)


def test_operator_analytes_include_cfdna_and_buffy(catalog_helper):
    _, is_operator_catalog_row = catalog_helper
    for name in ("cfdna", "buffy_coat", "plant_tissue"):
        doc = json.loads((ANALYTES / f"{name}.analyte.json").read_text(encoding="utf-8"))
        assert is_operator_catalog_row(status="published", catalog=doc["catalog"])


def test_advanced_analytes(catalog_helper):
    cfg_status_for_catalog, is_operator_catalog_row = catalog_helper
    for name in ("combined", "tissue"):
        doc = json.loads((ANALYTES / f"{name}.analyte.json").read_text(encoding="utf-8"))
        assert doc["catalog"]["visibility"] == "advanced"
        assert cfg_status_for_catalog(doc["catalog"]) == "published"
        assert not is_operator_catalog_row(status="published", catalog=doc["catalog"])


def test_sync_analyte_items():
    script = REPO / "scripts" / "sync_cfg_profiles_and_action_catalog.py"
    spec = importlib.util.spec_from_file_location("sync_cfg_analyte_catalog", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    names = [n for n, *_ in mod._analyte_items()]
    assert "cfdna" in names
    assert "buffy_coat" in names
    assert set(names) >= _EXPECTED


def test_kind_analyte_registered():
    from cfg.kinds import CFG_KINDS, MATERIALIZABLE_KINDS

    assert "analyte" in CFG_KINDS
    assert "analyte" in MATERIALIZABLE_KINDS


def test_import_fs_upserts_analytes(tmp_path: Path):
    from cfg.import_fs import import_filesystem
    from cfg.store import FileConfigStore

    store = FileConfigStore(tmp_path / "cfg-store")
    result = import_filesystem(
        store,
        repo_root=REPO,
        publish=True,
        include_programs=False,
        include_profiles=True,
        include_site=False,
        include_studies=False,
        include_reference_assets=False,
    )
    imported = result.get("imported") or []
    assert any(str(x).startswith("analyte:cfdna") for x in imported)
    rec = store.get("analyte", "cfdna", version="1")
    assert rec is not None
    assert rec.status == "published"
    assert rec.document["catalog"]["title"]


def test_materialize_analyte(tmp_path: Path):
    from cfg.materialize import materialize_store
    from cfg.store import FileConfigStore

    store = FileConfigStore(tmp_path / "cfg-store")
    store.upsert(
        "analyte",
        "cfdna",
        {
            "name": "cfdna",
            "version": "1",
            "catalog": {
                "title": "cfDNA",
                "summary": "plasma",
                "visibility": "operator",
                "lifecycle": "active",
                "family": "analyte",
            },
        },
        status="published",
        version="1",
    )
    work = tmp_path / "work"
    out = materialize_store(store, work, kinds=["analyte"])
    written = " ".join(out.get("written") or [])
    assert "analyte:cfdna@" in written
    path = work / "epimethyl" / "current" / "runtime-bundle" / "domain" / "analytes" / "cfdna.analyte.json"
    assert path.is_file()
