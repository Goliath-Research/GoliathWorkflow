"""Validate epimethyl release manifest schema and helper script contracts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schemas/deployment/epimethyl_release_manifest.schema.json"


def _required_manifest_fields() -> set[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return set(schema.get("required", []))


def test_manifest_schema_accepts_build_release_stub() -> None:
    stub = {
        "version": "2026.06.1",
        "python": "3.12",
        "parabricks_image": "nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1",
        "parabricks_image_digest": "",
        "docker_data_root": "/work/epimethyl/docker",
        "min_driver_version": "",
        "requirements_lock": "requirements-worker.lock",
        "runtime_bundle": "runtime-bundle",
        "artifacts": {
            "aarch64": {
                "methyl_extractor": "methyl-extractor-linux-aarch64.tar.gz",
                "sha256": "abc123",
            },
            "amd64": {
                "methyl_extractor": "methyl-extractor-linux-amd64.tar.gz",
                "sha256": "def456",
            },
        },
    }
    required = _required_manifest_fields()
    missing = required - stub.keys()
    assert not missing, f"manifest stub missing required keys: {sorted(missing)}"
    assert stub["artifacts"]["aarch64"]["methyl_extractor"].endswith(".tar.gz")


def test_release_scripts_pass_bash_syntax_check() -> None:
    scripts = [
        "build_release.sh",
        "promote_release.sh",
        "install_release.sh",
        "write_worker_env.sh",
        "package_methyl_extractor.sh",
        "bootstrap_epimethyl.sh",
    ]
    for name in scripts:
        path = REPO_ROOT / "scripts" / name
        subprocess.run(["bash", "-n", str(path)], check=True, capture_output=True)


def test_write_worker_env_from_manifest(tmp_path: Path) -> None:
    root = tmp_path / "epimethyl"
    release = root / "releases" / "2026.06.1"
    release.mkdir(parents=True)
    manifest = {
        "version": "2026.06.1",
        "python": "3.12",
        "parabricks_image": "nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1",
        "docker_data_root": "/work/epimethyl/docker",
        "requirements_lock": "requirements-worker.lock",
        "artifacts": {
            "aarch64": {
                "methyl_extractor": "methyl-extractor-linux-aarch64.tar.gz",
                "sha256": "",
            },
            "amd64": {
                "methyl_extractor": "methyl-extractor-linux-amd64.tar.gz",
                "sha256": "",
            },
        },
    }
    (release / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    venv = root / "venv-aarch64" / "bin"
    venv.mkdir(parents=True)
    (venv / "python").write_text("", encoding="utf-8")

    subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "scripts/write_worker_env.sh"),
            "--root",
            str(root),
            "--manifest",
            str(release / "manifest.json"),
            "--arch",
            "aarch64",
            "--worker-api-base",
            "http://test/v1",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    worker_env = (root / "env/worker.env").read_text(encoding="utf-8")
    assert "EPIMETHYL_RELEASE=2026.06.1" in worker_env
    assert "WORKER_API_BASE=http://test/v1" in worker_env
    assert "METHYL_PARABRICKS_IMAGE=nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1" in worker_env
    assert str(root / "venv-aarch64/bin") in worker_env
