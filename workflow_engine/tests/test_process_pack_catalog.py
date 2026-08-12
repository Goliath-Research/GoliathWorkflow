"""Catalog metadata on profiles/procedures + cfg status mapping."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PROFILES = REPO / "workflow_engine" / "domain" / "profiles"
PROCS = PROFILES / "procedures"

_REQUIRED_CATALOG = ("title", "summary", "visibility", "lifecycle", "family")
_VIS = frozenset({"operator", "advanced", "hidden"})
_LIFE = frozenset({"active", "deprecated", "internal"})
_FAM = frozenset({"samd", "staged", "specialty", "legacy"})


def _assert_catalog(cat: object, *, where: str) -> dict:
    assert isinstance(cat, dict), f"{where}: catalog missing"
    for key in _REQUIRED_CATALOG:
        assert key in cat and str(cat[key]).strip(), f"{where}: catalog.{key}"
    assert cat["visibility"] in _VIS, where
    assert cat["lifecycle"] in _LIFE, where
    assert cat["family"] in _FAM, where
    if "researchModes" in cat:
        assert isinstance(cat["researchModes"], list), where
    return cat


@pytest.fixture(scope="module")
def catalog_helper():
    from cfg.process_pack_catalog import cfg_status_for_catalog, is_operator_catalog_row

    return cfg_status_for_catalog, is_operator_catalog_row


def test_all_profiles_have_valid_catalog(catalog_helper):
    cfg_status_for_catalog, _ = catalog_helper
    paths = sorted(PROFILES.glob("*.profile.json"))
    assert paths, "expected profile JSON files"
    for path in paths:
        doc = json.loads(path.read_text(encoding="utf-8"))
        cat = _assert_catalog(doc.get("catalog"), where=path.name)
        status = cfg_status_for_catalog(cat)
        assert status in ("published", "retired")


def test_all_procedures_have_valid_catalog(catalog_helper):
    cfg_status_for_catalog, _ = catalog_helper
    paths = sorted(PROCS.glob("*.procedure.json"))
    assert paths, "expected procedure JSON files"
    for path in paths:
        doc = json.loads(path.read_text(encoding="utf-8"))
        cat = _assert_catalog(doc.get("catalog"), where=path.name)
        assert cfg_status_for_catalog(cat) in ("published", "retired")


def test_samd_research_is_operator_published(catalog_helper):
    cfg_status_for_catalog, is_operator_catalog_row = catalog_helper
    doc = json.loads((PROFILES / "samd_research.profile.json").read_text(encoding="utf-8"))
    assert cfg_status_for_catalog(doc["catalog"]) == "published"
    assert is_operator_catalog_row(status="published", catalog=doc["catalog"])
    assert "dual_fc" in doc["catalog"]["researchModes"]


@pytest.mark.parametrize(
    "name",
    [
        "mc_dmp",
        "mc_dmp_fc",
        "mc_gene",
        "mc_gene_fc",
        "mc_dmp_gene_fc",
        "discovery_gene_featurecuts",
        "legacy_dual",
        "dmp_panel_stability",
        "gene_enricher_stability",
    ],
)
def test_deprecated_profiles_retire(catalog_helper, name: str):
    cfg_status_for_catalog, is_operator_catalog_row = catalog_helper
    path = PROFILES / f"{name}.profile.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["catalog"]["lifecycle"] == "deprecated"
    assert doc["catalog"]["visibility"] == "hidden"
    assert cfg_status_for_catalog(doc["catalog"]) == "retired"
    assert not is_operator_catalog_row(status="published", catalog=doc["catalog"])
    assert not is_operator_catalog_row(status="retired", catalog=doc["catalog"])


def test_sync_profile_items_exclude_modes():
    import importlib.util
    import sys

    script = REPO / "scripts" / "sync_cfg_profiles_and_action_catalog.py"
    spec = importlib.util.spec_from_file_location("sync_cfg_profiles_catalog", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    names = [n for n, *_ in mod._profile_items()]
    assert "samd_research" in names
    assert not any(n.startswith("mode_") for n in names)
    assert "mc_dmp" in names  # still synced, but as retired


def test_catalog_meta_for_profile():
    from pipeline_profiles import catalog_meta_for

    meta = catalog_meta_for("samd_research")
    assert meta["visibility"] == "operator"
    assert meta["family"] == "samd"


def test_operator_catalog_filter_excludes_advanced_and_deprecated(catalog_helper):
    _, is_operator_catalog_row = catalog_helper
    operator_names = []
    for path in PROFILES.glob("*.profile.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        status = "published" if doc["catalog"]["lifecycle"] == "active" else "retired"
        # mimic sync status for active/advanced
        from cfg.process_pack_catalog import cfg_status_for_catalog

        status = cfg_status_for_catalog(doc["catalog"]) or "retired"
        if is_operator_catalog_row(status=status, catalog=doc["catalog"]):
            operator_names.append(doc.get("pipelineProfile") or path.stem)
    assert "samd_research" in operator_names
    assert "samd_pivotal" in operator_names
    assert "mc_dmp" not in operator_names
    assert "cell_deconv" not in operator_names  # advanced
