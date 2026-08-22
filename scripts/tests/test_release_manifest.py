"""Validate epimethyl release manifest schema and helper script contracts."""

from __future__ import annotations

import json
import os
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
        "version": "2026.6.1",
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


def test_manifest_schema_accepts_components_block() -> None:
    stub = {
        "version": "2026.6.1",
        "components": {
            "methyl_pipeline": "2026.6.1",
            "methyl_extractor": "2026.5.2",
        },
        "python": "3.12",
        "parabricks_image": "nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1",
        "docker_data_root": "/work/epimethyl/docker",
        "requirements_lock": "requirements-worker.lock",
        "artifacts": {
            "aarch64": {
                "methyl_extractor": "methyl-extractor-linux-aarch64.tar.gz",
                "sha256": "abc",
            },
            "amd64": {
                "methyl_extractor": "methyl-extractor-linux-amd64.tar.gz",
                "sha256": "def",
            },
        },
    }
    required = _required_manifest_fields()
    assert not (required - stub.keys())


def test_assemble_release_local_smoke(tmp_path: Path) -> None:
    mp_dir = tmp_path / "mp"
    out = tmp_path / "bundle"
    wheels = mp_dir / "wheels"
    wheels.mkdir(parents=True)
    (wheels / "dummy.whl").write_text("", encoding="utf-8")
    (mp_dir / "requirements-worker.lock").write_text("# test\n", encoding="utf-8")
    (mp_dir / "manifest.json").write_text(
        json.dumps(
            {
                "version": "2026.6.1",
                "python": "3.12",
                "parabricks_image": "nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1",
                "docker_data_root": "/work/epimethyl/docker",
                "requirements_lock": "requirements-worker.lock",
                "artifacts": {
                    "aarch64": {"methyl_extractor": "methyl-extractor-linux-aarch64.tar.gz", "sha256": ""},
                    "amd64": {"methyl_extractor": "methyl-extractor-linux-amd64.tar.gz", "sha256": ""},
                },
            }
        ),
        encoding="utf-8",
    )
    out.mkdir()
    for arch in ("aarch64", "amd64"):
        (out / f"methyl-extractor-linux-{arch}.tar.gz").write_bytes(b"fake tarball")

    subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "scripts/assemble_release.sh"),
            "--release-version",
            "2026.6.1",
            "--methyl-pipeline-version",
            "2026.6.1",
            "--methyl-extractor-version",
            "2026.5.2",
            "--methyl-pipeline-dir",
            str(mp_dir),
            "--output",
            str(out),
            "--skip-methyl-extractor-download",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "2026.6.1"
    assert manifest["components"]["methyl_extractor"] == "2026.5.2"
    assert manifest["artifacts"]["aarch64"]["sha256"]


def test_assemble_release_preserves_tarballs_when_skip_download(tmp_path: Path) -> None:
    mp_dir = tmp_path / "mp"
    out = tmp_path / "bundle"
    wheels = mp_dir / "wheels"
    wheels.mkdir(parents=True)
    (wheels / "dummy.whl").write_text("", encoding="utf-8")
    (mp_dir / "requirements-worker.lock").write_text("# test\n", encoding="utf-8")
    (mp_dir / "manifest.json").write_text("{}", encoding="utf-8")
    out.mkdir()
    for arch in ("aarch64", "amd64"):
        (out / f"methyl-extractor-linux-{arch}.tar.gz").write_bytes(b"preplaced")

    subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "scripts/assemble_release.sh"),
            "--release-version",
            "2026.6.1",
            "--methyl-pipeline-version",
            "2026.6.1",
            "--methyl-extractor-version",
            "2026.5.2",
            "--methyl-pipeline-dir",
            str(mp_dir),
            "--output",
            str(out),
            "--skip-methyl-extractor-download",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    for arch in ("aarch64", "amd64"):
        assert (out / f"methyl-extractor-linux-{arch}.tar.gz").read_bytes() == b"preplaced"


def test_release_scripts_pass_bash_syntax_check() -> None:
    scripts = [
        "build_release.sh",
        "promote_release.sh",
        "install_release.sh",
        "write_worker_env.sh",
        "package_methyl_extractor.sh",
        "bootstrap_epimethyl.sh",
        "init_work_layout.sh",
        "verify_work_layout.sh",
        "preflight_worker_join.sh",
        "provision_worker_node.sh",
        "provision_gateway_node.sh",
        "bootstrap_distributed_workers.sh",
        "download_methyl_extractor_artifacts.sh",
        "assemble_release.sh",
    ]
    for name in scripts:
        path = REPO_ROOT / "scripts" / name
        subprocess.run(["bash", "-n", str(path)], check=True, capture_output=True)


def test_bootstrap_docker_data_root_default_only_in_release_mode() -> None:
    text = (REPO_ROOT / "scripts/bootstrap_epimethyl.sh").read_text(encoding="utf-8")
    default_line = 'DOCKER_DATA_ROOT="${DOCKER_DATA_ROOT:-$ROOT/docker}"'
    release_marker = 'if [[ -n "$RELEASE_DIR" ]]; then'
    pre_release = text.split(release_marker, 1)[0]
    assert default_line not in pre_release, "DOCKER_DATA_ROOT must not default before release-dir check"
    assert default_line in text.split(release_marker, 1)[1]


def test_release_version_rejects_leading_zeros() -> None:
    result = subprocess.run(
        ["bash", "-c", f"source {REPO_ROOT / 'scripts/detect_platform.sh'} && require_release_version 2026.06.1"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "2026.06.1" in result.stderr


def test_release_version_accepts_semver() -> None:
    result = subprocess.run(
        ["bash", "-c", f"source {REPO_ROOT / 'scripts/detect_platform.sh'} && require_release_version 2026.6.1"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_release_version_accepts_v_prefix_after_normalize() -> None:
    detect = REPO_ROOT / "scripts/detect_platform.sh"
    result = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{detect}" && v="$(normalize_release_version v2026.6.1)" && require_release_version "$v" "--version"',
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "2026.6.1" not in result.stderr


def test_build_release_rejects_invalid_version() -> None:
    result = subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "scripts/build_release.sh"),
            "--version",
            "2026.06.1",
            "--output",
            "/tmp/should-not-run",
            "--skip-wheels",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "2026.06.1" in result.stderr


def test_write_worker_env_from_manifest(tmp_path: Path) -> None:
    root = tmp_path / "epimethyl"
    release = root / "releases" / "2026.6.1"
    release.mkdir(parents=True)
    manifest = {
        "version": "2026.6.1",
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
    assert "EPIMETHYL_RELEASE=2026.6.1" in worker_env
    assert "WORKER_API_BASE=http://test/v1" in worker_env
    assert "TMPDIR=/var/tmp/methyl-samtools" in worker_env
    assert "METHYL_SAMPLE_CAAS_ENABLED=0" in worker_env
    assert "METHYL_PARABRICKS_IMAGE=nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1" in worker_env
    assert str(root / "venv-aarch64/bin") in worker_env


def test_write_worker_env_omits_api_base_when_unset(tmp_path: Path) -> None:
    root = tmp_path / "epimethyl"
    release = root / "releases" / "2026.6.1"
    release.mkdir(parents=True)
    manifest = {
        "version": "2026.6.1",
        "python": "3.12",
        "parabricks_image": "",
        "docker_data_root": "/work/epimethyl/docker",
        "requirements_lock": "requirements-worker.lock",
        "artifacts": {
            "aarch64": {"methyl_extractor": "x.tar.gz", "sha256": ""},
            "amd64": {"methyl_extractor": "x.tar.gz", "sha256": ""},
        },
    }
    (release / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "venv-aarch64" / "bin").mkdir(parents=True)
    (root / "venv-aarch64" / "bin" / "python").write_text("", encoding="utf-8")
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("WORKER_API_BASE", "METHYL_API_BASE")
    }
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
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    worker_env = (root / "env/worker.env").read_text(encoding="utf-8")
    assert "WORKER_API_BASE=" not in worker_env
    assert "gateway.example.com" not in worker_env
    assert "TMPDIR=/var/tmp/methyl-samtools" in worker_env


def test_write_worker_env_preserves_existing_api_base_on_promote(tmp_path: Path) -> None:
    root = tmp_path / "epimethyl"
    release = root / "releases" / "2026.6.2"
    release.mkdir(parents=True)
    manifest = {
        "version": "2026.6.2",
        "python": "3.12",
        "parabricks_image": "",
        "docker_data_root": "/work/epimethyl/docker",
        "requirements_lock": "requirements-worker.lock",
        "artifacts": {
            "aarch64": {"methyl_extractor": "x.tar.gz", "sha256": ""},
            "amd64": {"methyl_extractor": "x.tar.gz", "sha256": ""},
        },
    }
    (release / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "venv-aarch64" / "bin").mkdir(parents=True)
    (root / "venv-aarch64" / "bin" / "python").write_text("", encoding="utf-8")
    env_dir = root / "env"
    env_dir.mkdir()
    (env_dir / "worker.env").write_text(
        "EPIMETHYL_ROOT=/work/epimethyl\nWORKER_API_BASE=https://gw.prod.example/v1\n",
        encoding="utf-8",
    )
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("WORKER_API_BASE", "METHYL_API_BASE")
    }
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
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    worker_env = (env_dir / "worker.env").read_text(encoding="utf-8")
    assert "WORKER_API_BASE=https://gw.prod.example/v1" in worker_env
    assert "EPIMETHYL_RELEASE=2026.6.2" in worker_env
