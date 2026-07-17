"""Tests for site reference_selection → concrete genome paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cfg.import_fs import import_filesystem
from cfg.provision import provision_asset, provision_selected_from_site
from cfg.reference_selection import apply_reference_selection, verify_selected_paths
from cfg.store import FileConfigStore

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def store(tmp_path: Path) -> FileConfigStore:
    return FileConfigStore(tmp_path / "cfg-store")


def test_apply_reference_selection_fills_paths() -> None:
    doc = {
        "reference_selection": {
            "linear": "linear/GRCh38/ensembl-114",
            "gene_annotation": "annotation/gencode/v49",
            "pangenome": "pangenome/GRCh38/d9/1.70",
        }
    }
    out = apply_reference_selection(doc, work_root="/work", overwrite=True)
    assert out["reference_genome"]["fasta"].endswith(
        "linear/GRCh38/ensembl-114/Homo_sapiens.GRCh38.dna.primary_assembly.fa"
    )
    assert out["annotation"]["gtf"].endswith(
        "annotation/gencode/v49/gencode.v49.annotation.gtf"
    )
    assert "pangenome/GRCh38/d9/1.70/" in out["pangenome_genome"]["gbz"]
    assert out["pangenome_genome"]["linear_ref_fasta"] == out["reference_genome"]["fasta"]


def test_verify_selected_paths_ok(tmp_path: Path) -> None:
    work = tmp_path / "work"
    linear = work / "genomes" / "linear" / "GRCh38" / "ensembl-114"
    ann = work / "genomes" / "annotation" / "gencode" / "v49"
    pan = work / "genomes" / "pangenome" / "GRCh38" / "d9" / "1.70"
    for d in (linear, ann, pan):
        d.mkdir(parents=True)
    (linear / "Homo_sapiens.GRCh38.dna.primary_assembly.fa").write_text(">1\nACGT\n")
    (ann / "gencode.v49.annotation.gtf").write_text("##gtf\n")
    for name in (
        "hprc-v1.1-mc-grch38.d9.gbz",
        "hprc-v1.1-mc-grch38.d9.autoindex.1.70.dist",
        "hprc-v1.1-mc-grch38.d9.autoindex.1.70.shortread.withzip.min",
        "hprc-v1.1-mc-grch38.d9.autoindex.1.70.shortread.zipcodes",
        "hprc-v1.1-mc-grch38.d9.paths.sub",
    ):
        (pan / name).write_text("x")
    doc = apply_reference_selection(
        {
            "reference_selection": {
                "linear": "linear/GRCh38/ensembl-114",
                "gene_annotation": "annotation/gencode/v49",
                "pangenome": "pangenome/GRCh38/d9/1.70",
            }
        },
        work_root=work,
        overwrite=True,
    )
    res = verify_selected_paths(doc, work_root=work)
    assert res["ok"] is True
    assert not res["missing"]


def test_import_reference_asset_fixtures(store: FileConfigStore) -> None:
    result = import_filesystem(
        store,
        repo_root=REPO,
        include_programs=False,
        include_profiles=False,
        include_site=False,
        include_studies=False,
        include_reference_assets=True,
        publish=True,
    )
    names = {r.name for r in store.list("reference_asset", published_only=True)}
    assert "linear-grch38-ensembl-114" in names
    assert "gencode-v49" in names
    assert "pangenome-grch38-d9-1.70" in names
    assert "epimethyl-genomes" in {
        r.name for r in store.list("storage_endpoint", published_only=True)
    }
    assert any("reference_asset:" in x for x in result["imported"])


def test_provision_s3_sync_dry_run(store: FileConfigStore, tmp_path: Path) -> None:
    store.upsert(
        "credential",
        "epimethyl-archive-keys",
        {
            "authMode": "explicit_keys",
            "accessKeyId": "AKIATEST",
            "secretAccessKey": "secret",
            "provider": "s3",
        },
        status="published",
        extra={"provider": "s3"},
    )
    store.upsert(
        "storage_endpoint",
        "epimethyl-genomes",
        {
            "type": "s3",
            "bucket": "epimethyl",
            "region": "us-east-1",
            "endpointUrl": "https://s3.us-east-1.myqnapcloud.io",
            "prefixBase": "genomes/",
        },
        status="published",
        extra={"provider": "s3", "credentialName": "epimethyl-archive-keys"},
    )
    store.upsert(
        "reference_asset",
        "linear-grch38-ensembl-114",
        {
            "assetType": "linear_genome",
            "destRoot": str(tmp_path / "work" / "genomes" / "linear" / "GRCh38" / "ensembl-114"),
            "recipe": {
                "steps": [
                    {"op": "mkdir"},
                    {
                        "op": "s3_sync",
                        "storageEndpoint": "epimethyl-genomes",
                        "key": "linear/GRCh38/ensembl-114/",
                    },
                ]
            },
        },
        status="published",
    )
    result = provision_asset(
        store,
        "linear-grch38-ensembl-114",
        work_root=tmp_path / "work",
        dry_run=True,
    )
    assert result["dryRun"] is True
    assert any("s3_sync" in line for line in result["log"])


def test_provision_selected_from_site(store: FileConfigStore, tmp_path: Path) -> None:
    import_filesystem(
        store,
        repo_root=REPO,
        include_programs=False,
        include_profiles=False,
        include_site=False,
        include_studies=False,
        include_reference_assets=True,
        publish=True,
    )
    site_doc = json.loads(
        (REPO / "tools/methyl-config-editor/configs/site_grch38.example.json").read_text()
    )
    store.upsert("site", "default", site_doc, status="published")
    # File endpoint override so selected provision does not need network
    src = tmp_path / "src" / "linear" / "GRCh38" / "ensembl-114"
    src.mkdir(parents=True)
    (src / "marker.txt").write_text("ok")
    store.upsert(
        "storage_endpoint",
        "epimethyl-genomes",
        {"type": "file", "basePath": str(tmp_path / "src")},
        status="published",
        version="1",
        # Clear credentialName merged from fixture import (file endpoints need none)
        extra={"provider": "file", "credentialName": None},
    )
    # Replace recipes with file downloads for unit test
    for name, key, dest_rel in (
        (
            "linear-grch38-ensembl-114",
            "linear/GRCh38/ensembl-114/marker.txt",
            "linear/GRCh38/ensembl-114/marker.txt",
        ),
    ):
        store.upsert(
            "reference_asset",
            name,
            {
                "destRoot": str(tmp_path / "work" / "genomes" / "linear" / "GRCh38" / "ensembl-114"),
                "recipe": {
                    "steps": [
                        {"op": "mkdir"},
                        {
                            "op": "download",
                            "storageEndpoint": "epimethyl-genomes",
                            "key": key,
                            "dest": Path(dest_rel).name,
                        },
                    ]
                },
            },
            status="published",
        )
    # Only provision linear in this unit test — shrink selection
    site_doc["reference_selection"] = {"linear": "linear/GRCh38/ensembl-114"}
    store.upsert("site", "default", site_doc, status="published")
    result = provision_selected_from_site(
        store, work_root=tmp_path / "work", site_name="default", dry_run=False
    )
    assert len(result["results"]) == 1
    dest = Path(result["results"][0]["destRoot"]) / "marker.txt"
    assert dest.is_file()
