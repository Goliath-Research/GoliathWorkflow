"""Tests for site reference_selection → concrete genome paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cfg.import_fs import import_filesystem
from cfg.provision import provision_asset, provision_selected_from_site
from cfg.reference_selection import (
    apply_reference_selection,
    asset_inventory_prefix,
    selected_asset_names,
    verify_selected_paths,
)
from cfg.store import FileConfigStore

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def store(tmp_path: Path) -> FileConfigStore:
    return FileConfigStore(tmp_path / "cfg-store")


def test_apply_reference_selection_fills_paths() -> None:
    doc = {
        "reference_selection": {
            "linear": "linear/GRCh38/ensembl-116",
            "gene_annotation": "annotation/gencode/v50",
            "pangenome": "pangenome/GRCh38/d9/1.70",
        }
    }
    out = apply_reference_selection(doc, work_root="/work", overwrite=True)
    assert out["reference_genome"]["fasta"].endswith(
        "linear/GRCh38/ensembl-116/Homo_sapiens.GRCh38.dna.primary_assembly.fa"
    )
    assert out["annotation"]["gtf"].endswith(
        "annotation/gencode/v50/gencode.v50.annotation.gtf"
    )
    assert "pangenome/GRCh38/d9/1.70/" in out["pangenome_genome"]["gbz"]
    assert out["pangenome_genome"]["linear_ref_fasta"] == out["reference_genome"]["fasta"]


def test_verify_selected_paths_ok(tmp_path: Path) -> None:
    work = tmp_path / "work"
    linear = work / "genomes" / "linear" / "GRCh38" / "ensembl-116"
    ann = work / "genomes" / "annotation" / "gencode" / "v50"
    pan = work / "genomes" / "pangenome" / "GRCh38" / "d9" / "1.70"
    for d in (linear, ann, pan):
        d.mkdir(parents=True)
    fasta = linear / "Homo_sapiens.GRCh38.dna.primary_assembly.fa"
    fasta.write_text(">1\nACGT\n")
    (Path(str(fasta) + ".C2T.fa")).write_text(">1\nATGT\n")
    pack = Path(str(fasta) + ".mojo_linear_k15")
    pack.mkdir()
    for name in ("meta.json", "kmers.bin", "offsets.bin", "postings.bin"):
        (pack / name).write_bytes(b"x")
    (ann / "gencode.v50.annotation.gtf").write_text("##gtf\n")
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
                "linear": "linear/GRCh38/ensembl-116",
                "gene_annotation": "annotation/gencode/v50",
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
    assert "linear-grch38-ensembl-116" in names
    assert "gencode-v49" in names
    assert "gencode-v50" in names
    assert "rna-grch38-star-ensembl-116" in names
    assert "rna-grch38-kallisto-gencode-v50" in names
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


def test_s3_sync_step_prefix_no_prefixbase_not_doubled(
    store: FileConfigStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Endpoint without prefixBase + step `prefix` must not double-apply the key."""
    from cfg import provision as provision_mod

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
    # No prefixBase on the endpoint — this is the case that triggered the bug.
    store.upsert(
        "storage_endpoint",
        "bare-bucket",
        {
            "type": "s3",
            "bucket": "epimethyl",
            "region": "us-east-1",
            "endpointUrl": "https://s3.us-east-1.myqnapcloud.io",
        },
        status="published",
        extra={"provider": "s3", "credentialName": "epimethyl-archive-keys"},
    )
    store.upsert(
        "reference_asset",
        "bare-asset",
        {
            "assetType": "linear_genome",
            "destRoot": str(tmp_path / "work" / "genomes" / "bare"),
            "recipe": {
                "steps": [
                    {
                        "op": "s3_sync",
                        "storageEndpoint": "bare-bucket",
                        "prefix": "linear/GRCh38/ensembl-114/",
                    }
                ]
            },
        },
        status="published",
    )

    captured: dict[str, str] = {}

    def _fake_run_aws_s3(args, *, loc, dry_run):  # noqa: ANN001
        # args = ["s3", "sync", <uri>, <dest>/]
        captured["uri"] = args[2]

    monkeypatch.setattr(provision_mod, "_run_aws_s3", _fake_run_aws_s3)

    provision_asset(store, "bare-asset", work_root=tmp_path / "work", dry_run=False)

    assert captured["uri"] == "s3://epimethyl/linear/GRCh38/ensembl-114/"


def test_selected_asset_names_matches_inventory_prefix() -> None:
    assets = {
        "linear-grch38-ensembl-114": {
            "inventoryPrefix": "linear/GRCh38/ensembl-114",
        },
        "gencode-v49": {
            "inventoryPrefix": "annotation/gencode/v49",
        },
        "other-linear": {
            "inventoryPrefix": "linear/GRCh38/ensembl-99",
        },
    }
    names = selected_asset_names(
        {
            "reference_selection": {
                "linear": "linear/GRCh38/ensembl-114",
                "gene_annotation": "annotation/gencode/v49",
            }
        },
        assets,
    )
    assert names == {
        "linear": "linear-grch38-ensembl-114",
        "gene_annotation": "gencode-v49",
    }


def test_selected_asset_names_miss_raises() -> None:
    with pytest.raises(ValueError, match="does not match any published"):
        selected_asset_names(
            {"reference_selection": {"linear": "linear/GRCh38/missing"}},
            {"linear-grch38-ensembl-114": {"inventoryPrefix": "linear/GRCh38/ensembl-114"}},
        )


def test_asset_inventory_prefix_from_recipe_key() -> None:
    assert (
        asset_inventory_prefix(
            {
                "recipe": {
                    "steps": [
                        {
                            "op": "s3_sync",
                            "key": "pangenome/GRCh38/d9/1.70/",
                        }
                    ]
                }
            }
        )
        == "pangenome/GRCh38/d9/1.70"
    )
    assert (
        asset_inventory_prefix(
            {
                "recipe": {
                    "steps": [
                        {
                            "op": "download",
                            "key": "linear/GRCh38/ensembl-114/marker.txt",
                        }
                    ]
                }
            }
        )
        == "linear/GRCh38/ensembl-114"
    )


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
    src = tmp_path / "src" / "linear" / "GRCh38" / "ensembl-116"
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
            "linear-grch38-ensembl-116",
            "linear/GRCh38/ensembl-116/marker.txt",
            "linear/GRCh38/ensembl-116/marker.txt",
        ),
    ):
        store.upsert(
            "reference_asset",
            name,
            {
                "inventoryPrefix": "linear/GRCh38/ensembl-116",
                "destRoot": str(tmp_path / "work" / "genomes" / "linear" / "GRCh38" / "ensembl-116"),
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
    site_doc["reference_selection"] = {"linear": "linear/GRCh38/ensembl-116"}
    store.upsert("site", "default", site_doc, status="published")
    result = provision_selected_from_site(
        store, work_root=tmp_path / "work", site_name="default", dry_run=False
    )
    assert len(result["results"]) == 1
    dest = Path(result["results"][0]["destRoot"]) / "marker.txt"
    assert dest.is_file()
