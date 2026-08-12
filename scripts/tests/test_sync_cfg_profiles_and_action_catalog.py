"""Unit tests for scripts/sync_cfg_profiles_and_action_catalog.py verification."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "sync_cfg_profiles_and_action_catalog.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "sync_cfg_profiles_and_action_catalog", SCRIPT
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def sync_mod():
    return _load_mod()


def test_verify_profiles_fails_when_query_returns_no_rows(sync_mod, monkeypatch):
    monkeypatch.setenv("BACKEND_DB", "mssql")
    db = SimpleNamespace(_fetch_all=lambda *a, **k: [])
    with pytest.raises(SystemExit, match="missing from cfg.pipeline_profile"):
        sync_mod.verify_profiles(db, ["staged_ovr_mc", "staged_full_lifecycle"])


def test_verify_profiles_fails_when_subset_missing(sync_mod, monkeypatch):
    monkeypatch.setenv("BACKEND_DB", "mssql")
    db = SimpleNamespace(
        _fetch_all=lambda *a, **k: [
            {
                "name": "staged_ovr_mc",
                "has_removed": 0,
                "has_canonical": 1,
            }
        ]
    )
    with pytest.raises(SystemExit, match="staged_full_lifecycle"):
        sync_mod.verify_profiles(db, ["staged_ovr_mc", "staged_full_lifecycle"])


def test_verify_profiles_fails_on_empty_name_list(sync_mod):
    db = SimpleNamespace(_fetch_all=lambda *a, **k: [])
    with pytest.raises(SystemExit, match="no profile names"):
        sync_mod.verify_profiles(db, [])


def test_verify_profiles_ok_when_all_present_and_canonical(sync_mod, monkeypatch):
    monkeypatch.setenv("BACKEND_DB", "mssql")
    db = SimpleNamespace(
        _fetch_all=lambda *a, **k: [
            {"name": "staged_ovr_mc", "has_removed": 0, "has_canonical": 1},
            {"name": "staged_full_lifecycle", "has_removed": 0, "has_canonical": 1},
        ]
    )
    sync_mod.verify_profiles(db, ["staged_ovr_mc", "staged_full_lifecycle"])


def test_profile_items_exclude_mode_overlays(sync_mod):
    names = [n for n, *_ in sync_mod._profile_items()]
    assert "samd_research" in names
    assert not any(n.startswith("mode_") for n in names)


def test_cfg_status_from_stamped_docs(sync_mod):
    from cfg.process_pack_catalog import cfg_status_for_catalog

    for name, _version, _path, doc in sync_mod._profile_items():
        status = cfg_status_for_catalog(doc.get("catalog"))
        if doc.get("catalog", {}).get("lifecycle") == "deprecated":
            assert status == "retired", name
        elif doc.get("catalog", {}).get("visibility") == "operator":
            assert status == "published", name


def test_verify_catalog_status_fails_when_deprecated_still_published(sync_mod, monkeypatch):
    monkeypatch.setenv("BACKEND_DB", "mssql")
    db = SimpleNamespace(
        _fetch_all=lambda *a, **k: [
            {
                "name": "mc_dmp",
                "status": "published",
                "lifecycle": "deprecated",
                "visibility": "hidden",
            }
        ]
    )
    with pytest.raises(SystemExit, match="still published"):
        sync_mod.verify_catalog_status(db)


def test_verify_catalog_status_ok_when_retired(sync_mod, monkeypatch):
    monkeypatch.setenv("BACKEND_DB", "mssql")
    db = SimpleNamespace(
        _fetch_all=lambda *a, **k: [
            {
                "name": "mc_dmp",
                "status": "retired",
                "lifecycle": "deprecated",
                "visibility": "hidden",
            },
            {
                "name": "mode_dual_fc",
                "status": "retired",
                "lifecycle": None,
                "visibility": None,
            },
        ]
    )
    sync_mod.verify_catalog_status(db)


def test_procedure_items_present(sync_mod):
    names = [n for n, *_ in sync_mod._procedure_items()]
    assert "buffy_wgbs_pangenome_gene_fc" in names
    assert "cfdna_wgbs_plasma" in names
