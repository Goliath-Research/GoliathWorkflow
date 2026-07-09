"""Tests for deployment script reliability (documentation-and-deployment-reliability plan)."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_deploy_env_templates_exist() -> None:
    templates = [
        "deploy/env/gateway.postgres.env.example",
        "deploy/env/gateway.mssql.env.example",
        "deploy/env/gateway.security.env.example",
        "deploy/env/worker.env.example",
        "deploy/env/README.md",
    ]
    for rel in templates:
        assert (REPO_ROOT / rel).is_file(), rel


def test_systemd_units_use_placeholders() -> None:
    for rel in (
        "deploy/systemd/methyl-gateway.service",
        "deploy/systemd/methyl-worker.service",
        "deploy/systemd/methyl-worker@.service",
    ):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "__EPIMETHYL_VENV__" in text
        assert "venv-aarch64" not in text or "__EPIMETHYL_VENV__" in text


def test_build_release_resolves_workflow_engine_wheel() -> None:
    script = REPO_ROOT / "scripts" / "build_release.sh"
    text = script.read_text(encoding="utf-8")
    assert "_resolve_pkg_path" in text
    assert "workflow_engine" in (REPO_ROOT / "scripts" / "packages.list").read_text()


def test_verify_setup_fails_on_missing_canonical_doc(tmp_path: Path) -> None:
    proc = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "verify_setup.sh")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_install_worker_systemd_render_no_double_venv() -> None:
    unit = REPO_ROOT / "deploy" / "systemd" / "methyl-worker.service"
    rendered = unit.read_text(encoding="utf-8").replace(
        "__EPIMETHYL_VENV__", "/work/epimethyl/venv-aarch64"
    )
    assert "/work/epimethyl//work/epimethyl" not in rendered
    assert "venv-aarch64/bin/methyl-worker" in rendered
