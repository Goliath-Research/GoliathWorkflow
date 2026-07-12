"""Tests for cfg registry: import → materialize → expand storage → scaffold."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "workflow_engine"))

from cfg.import_fs import import_filesystem
from cfg.materialize import materialize_store
from cfg.provision import provision_asset
from cfg.publish_program import publish_program
from cfg.scaffold import scaffold_action, upsert_server_action
from cfg.storage_expand import expand_storage_endpoint, expand_storage_profile
from cfg.store import FileConfigStore
from cfg.sync_actions import sync_actions_from_committed_json


@pytest.fixture
def store(tmp_path: Path) -> FileConfigStore:
    return FileConfigStore(tmp_path / "cfg-store")


def test_import_profiles_and_programs(store: FileConfigStore) -> None:
    result = import_filesystem(
        store,
        repo_root=REPO,
        work_root=None,
        publish=True,
        include_site=False,
        include_studies=False,
    )
    assert result["count"] > 0
    profiles = store.list("pipeline_profile", published_only=True)
    programs = store.list("domain_program", published_only=True)
    assert profiles
    assert programs
    assert any(p.name == "samd_research" for p in profiles) or len(profiles) >= 1


def test_roundtrip_materialize_site_and_profile(store: FileConfigStore, tmp_path: Path) -> None:
    site_doc = {
        "reference_genome": {"fasta": "/work/genomes/hg38.fa"},
        "annotation": {"gtf": "/work/genomes/hg38.gtf"},
    }
    store.upsert("site", "default", site_doc, status="published")
    store.upsert(
        "pipeline_profile",
        "samd_research",
        {"pipelineProfile": "samd_research", "actionConfig": {}},
        status="published",
    )
    work = tmp_path / "work"
    bundle = work / "epimethyl" / "current" / "runtime-bundle" / "domain"
    result = materialize_store(store, work, runtime_bundle_domain=bundle)
    assert (work / "site" / "methyl_site.json").is_file()
    loaded = json.loads((work / "site" / "methyl_site.json").read_text())
    assert loaded["reference_genome"]["fasta"] == "/work/genomes/hg38.fa"
    assert (bundle / "profiles" / "samd_research.profile.json").is_file()
    assert result["written"]

    # Simulate wipe + rematerialize
    (work / "site" / "methyl_site.json").unlink()
    materialize_store(store, work, runtime_bundle_domain=bundle)
    assert (work / "site" / "methyl_site.json").is_file()


def test_storage_endpoint_credentials_never_materialized(
    store: FileConfigStore, tmp_path: Path
) -> None:
    store.upsert(
        "credential",
        "lab-aws-keys",
        {
            "authMode": "explicit_keys",
            "accessKeyId": "AKIAEXAMPLE",
            "secretAccessKey": "secret-value",
            "provider": "s3",
        },
        status="published",
        secret={
            "authMode": "explicit_keys",
            "accessKeyId": "AKIAEXAMPLE",
            "secretAccessKey": "secret-value",
        },
        extra={"provider": "s3"},
    )
    store.upsert(
        "storage_endpoint",
        "lab-aws",
        {"type": "s3", "bucket": "cohort", "region": "us-east-1"},
        status="published",
        extra={"provider": "s3", "credentialName": "lab-aws-keys"},
    )
    work = tmp_path / "work"
    materialize_store(store, work)
    ep_path = work / "site" / "storage_endpoints" / "lab-aws.json"
    assert ep_path.is_file()
    text = ep_path.read_text()
    assert "secret-value" not in text
    assert "AKIAEXAMPLE" not in text

    expanded = expand_storage_endpoint(store, "lab-aws", prefix="plasma/S1/")
    assert expanded["type"] == "s3"
    assert expanded["prefix"] == "plasma/S1/"
    assert expanded["credentials"]["secretAccessKey"] == "secret-value"


def test_azure_sas_and_gcs_expand(store: FileConfigStore) -> None:
    store.upsert(
        "credential",
        "az-sas",
        {"authMode": "sas_url", "sasUrl": "https://acct.blob.core.windows.net/c?sig=x"},
        status="published",
        secret={
            "authMode": "sas_url",
            "sasUrl": "https://acct.blob.core.windows.net/c?sig=x",
        },
        extra={"provider": "azure_blob"},
    )
    store.upsert(
        "storage_endpoint",
        "lab-azure",
        {"type": "azure_blob", "account": "acct", "container": "c"},
        status="published",
        extra={"provider": "azure_blob", "credentialName": "az-sas"},
    )
    az = expand_storage_endpoint(store, "lab-azure", prefix="s1/")
    assert az["credentials"]["authMode"] == "sas_url"

    store.upsert(
        "credential",
        "gcs-adc",
        {"authMode": "application_default"},
        status="published",
        secret={"authMode": "application_default"},
        extra={"provider": "gcs"},
    )
    store.upsert(
        "storage_endpoint",
        "lab-gcs",
        {"type": "gcs", "bucket": "b", "projectId": "p"},
        status="published",
        extra={"provider": "gcs", "credentialName": "gcs-adc"},
    )
    gcs = expand_storage_endpoint(store, "lab-gcs")
    assert gcs["type"] == "gcs"
    assert gcs["credentials"]["authMode"] == "application_default"


def test_storage_profile_expand(store: FileConfigStore) -> None:
    store.upsert(
        "storage_endpoint",
        "ingress",
        {"type": "file", "basePath": "/data/fastq"},
        status="published",
        extra={"provider": "file"},
    )
    store.upsert(
        "storage_profile",
        "default-lab",
        {"fastqStorageEndpoint": "ingress"},
        status="published",
    )
    out = expand_storage_profile(store, "default-lab", sample_prefix="S1")
    assert out["fastqStorage"]["type"] == "file"
    assert out["fastqStorage"]["prefix"] == "S1"


def test_provision_file_download(store: FileConfigStore, tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "genome.fa").write_text(">chr1\nACGT\n", encoding="utf-8")
    store.upsert(
        "storage_endpoint",
        "local-ref",
        {"type": "file", "basePath": str(src_dir)},
        status="published",
        extra={"provider": "file"},
    )
    store.upsert(
        "reference_asset",
        "tiny-genome",
        {
            "assetType": "linear_genome",
            "destRoot": str(tmp_path / "work" / "genomes" / "tiny"),
            "recipe": {
                "steps": [
                    {"op": "mkdir"},
                    {
                        "op": "download",
                        "storageEndpoint": "local-ref",
                        "key": "genome.fa",
                        "dest": "genome.fa",
                    },
                ]
            },
        },
        status="published",
    )
    result = provision_asset(
        store, "tiny-genome", work_root=tmp_path / "work", dry_run=False
    )
    dest = Path(result["destRoot"]) / "genome.fa"
    assert dest.is_file()
    assert "ACGT" in dest.read_text()


def test_publish_program_compiles(store: FileConfigStore, tmp_path: Path) -> None:
    import_filesystem(
        store,
        repo_root=REPO,
        include_site=False,
        include_studies=False,
        include_profiles=False,
        include_programs=True,
        publish=True,
    )
    programs = store.list("domain_program", published_only=True)
    assert programs
    name = programs[0].name
    work = tmp_path / "work"
    result = publish_program(
        store,
        name,
        version=programs[0].version,
        repo_root=REPO,
        work_root=work,
        deploy_db=False,
    )
    assert Path(result["compiledPath"]).is_file()
    spec = json.loads(Path(result["compiledPath"]).read_text())
    assert "nodes" in spec or "name" in spec


def test_sync_and_scaffold_action(store: FileConfigStore, tmp_path: Path) -> None:
    # Use committed catalog if present; else define server-side
    catalog = REPO / "schemas" / "actions" / "catalog.json"
    if catalog.is_file():
        sync_actions_from_committed_json(store, repo_root=REPO, publish=True)
        assert store.list("action_definition", published_only=True)
    upsert_server_action(
        store,
        action_name="demo.echo",
        capability="demo",
        input_schema={"type": "object", "properties": {"msg": {"type": "string"}}},
        publish=True,
    )
    out_root = tmp_path / "scaffold_repo"
    (out_root / "schemas" / "tasks").mkdir(parents=True)
    (out_root / "workers" / "methyl_worker").mkdir(parents=True)
    result = scaffold_action(store, "demo.echo", repo_root=out_root, force=True)
    assert any("demo_echo.input.schema.json" in w or "schema" in w for w in result["written"])
    stub = out_root / "workers" / "methyl_worker" / "scaffolded" / "demo_echo.py"
    assert stub.is_file()
