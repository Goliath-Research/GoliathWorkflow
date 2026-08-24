"""Tests for site → reference_asset role linking (cfg.cfg_repo_link_site_asset)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

from cfg.import_fs import import_filesystem
from cfg.site_assets import (
    apply_site_asset_links_to_db,
    link_site_assets,
    plan_site_asset_links,
)
from cfg.store import FileConfigStore
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

_ASSETS = {
    "linear-grch38-ensembl-114": {
        "version": "1",
        "inventoryPrefix": "linear/GRCh38/ensembl-114",
    },
    "linear-grch38-ensembl-116": {
        "version": "1",
        "inventoryPrefix": "linear/GRCh38/ensembl-116",
    },
    "gencode-v49": {
        "version": "1",
        "inventoryPrefix": "annotation/gencode/v49",
    },
    "gencode-v50": {
        "version": "1",
        "inventoryPrefix": "annotation/gencode/v50",
    },
    "pangenome-grch38-d9-1.70": {
        "version": "1",
        "inventoryPrefix": "pangenome/GRCh38/d9/1.70",
    },
    "pangenome-grch38-d9-bs-1.70": {
        "version": "1",
        "inventoryPrefix": "pangenome/GRCh38/d9-bs/1.70",
    },
}


def test_plan_default_site_pin_is_ensembl_116() -> None:
    plan = plan_site_asset_links(
        {
            "reference_selection": {
                "linear": "linear/GRCh38/ensembl-116",
                "gene_annotation": "annotation/gencode/v50",
                "pangenome": "pangenome/GRCh38/d9/1.70",
                "pangenome_wgbs": "pangenome/GRCh38/d9-bs/1.70",
            }
        },
        _ASSETS,
    )
    roles = {row["asset_role"]: row["asset_name"] for row in plan["linked"]}
    assert roles == {
        "reference_genome": "linear-grch38-ensembl-116",
        "annotation_gtf": "gencode-v50",
        "pangenome_bundle": "pangenome-grch38-d9-1.70",
    }


def test_plan_skips_wgbs_when_stock_pangenome_pinned() -> None:
    plan = plan_site_asset_links(
        {
            "reference_selection": {
                "linear": "linear/GRCh38/ensembl-114",
                "gene_annotation": "annotation/gencode/v49",
                "pangenome": "pangenome/GRCh38/d9/1.70",
                "pangenome_wgbs": "pangenome/GRCh38/d9-bs/1.70",
            }
        },
        _ASSETS,
    )
    roles = {row["asset_role"]: row["asset_name"] for row in plan["linked"]}
    assert roles == {
        "reference_genome": "linear-grch38-ensembl-114",
        "annotation_gtf": "gencode-v49",
        "pangenome_bundle": "pangenome-grch38-d9-1.70",
    }
    assert len(plan["skipped"]) == 1
    assert plan["skipped"][0]["selection_key"] == "pangenome_wgbs"
    assert "ck_cfg_sra_role" in plan["skipped"][0]["reason"]


def test_plan_wgbs_only_uses_pangenome_bundle() -> None:
    plan = plan_site_asset_links(
        {
            "reference_selection": {
                "pangenome_wgbs": "pangenome/GRCh38/d9-bs/1.70",
            }
        },
        _ASSETS,
    )
    assert plan["linked"] == [
        {
            "selection_key": "pangenome_wgbs",
            "asset_name": "pangenome-grch38-d9-bs-1.70",
            "asset_version": "1",
            "asset_role": "pangenome_bundle",
        }
    ]
    assert plan["skipped"] == []


def test_import_fs_records_site_reference_assets(tmp_path: Path) -> None:
    store = FileConfigStore(tmp_path / "cfg-store")
    work = tmp_path / "work"
    result = import_filesystem(
        store,
        repo_root=REPO,
        work_root=work,
        publish=True,
        include_programs=False,
        include_profiles=False,
        include_studies=False,
    )
    assert any(item.startswith("site_reference_asset:") for item in result["imported"])
    site = store.get("site", "default")
    assert site is not None
    extra = site.extra.get("siteReferenceAssets") or {}
    linked = extra.get("linked") or []
    roles = {row["asset_role"] for row in linked}
    assert roles == {"reference_genome", "annotation_gtf", "pangenome_bundle"}
    skipped = extra.get("skipped") or []
    assert any(row.get("selection_key") == "pangenome_wgbs" for row in skipped)


def test_apply_calls_cfg_repo_link_site_asset() -> None:
    calls: List[Tuple[str, Tuple[Any, ...]]] = []

    def fetch_one(sql: str, params: Tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:
        calls.append((sql, params))
        if "cfg.site" in sql:
            return {"id": 11}
        if "cfg.reference_asset" in sql:
            return {"id": 22}
        return None

    def exec_proc(sql: str, params: Tuple[Any, ...] = ()) -> None:
        calls.append((sql, params))

    db = MagicMock()
    db.backend = "mssql"
    db._fetch_one.side_effect = fetch_one
    db._exec_proc.side_effect = exec_proc

    applied = apply_site_asset_links_to_db(
        db,
        site_name="default",
        site_version="1",
        linked=[
            {
                "asset_name": "linear-grch38-ensembl-114",
                "asset_version": "1",
                "asset_role": "reference_genome",
            }
        ],
    )
    assert applied == [
        {
            "site_id": 11,
            "reference_asset_id": 22,
            "asset_name": "linear-grch38-ensembl-114",
            "asset_role": "reference_genome",
        }
    ]
    exec_sql = [sql for sql, _ in calls if "cfg_repo_link_site_asset" in sql]
    assert exec_sql
    assert exec_sql[0].startswith("EXEC cfg.cfg_repo_link_site_asset")


def test_link_site_assets_without_db_skips_sql(tmp_path: Path) -> None:
    store = FileConfigStore(tmp_path / "cfg-store")
    import_filesystem(
        store,
        repo_root=REPO,
        work_root=tmp_path / "work",
        include_programs=False,
        include_profiles=False,
        include_studies=False,
    )
    result = link_site_assets(store, site_name="default", db=None)
    assert "db" not in result
    assert result["linked"]
