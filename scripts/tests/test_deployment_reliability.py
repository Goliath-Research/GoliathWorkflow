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
        "deploy/systemd/methyl-reclaim-leases.service",
    ):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "__GOLIATH_VENV__" in text
        if "methyl-gateway.service" in rel or "methyl-reclaim-leases.service" in rel:
            assert "__GOLIATH_ROOT__" in text
            assert "/work/goliath" not in text
    timer = (REPO_ROOT / "deploy/systemd/methyl-reclaim-leases.timer").read_text(
        encoding="utf-8"
    )
    assert "OnUnitActiveSec=" in timer
    assert (
        REPO_ROOT / "scripts" / "install_reclaim_leases_timer.sh"
    ).is_file()


def test_build_release_resolves_workflow_engine_wheel() -> None:
    script = REPO_ROOT / "scripts" / "build_release.sh"
    text = script.read_text(encoding="utf-8")
    assert "_resolve_pkg_path" in text
    assert "workflow_engine" in (REPO_ROOT / "scripts" / "packages.list").read_text()


def test_packages_list_includes_worker_path_deps_before_workers() -> None:
    """pip ignores [tool.uv.sources]; path deps must be installed before workers."""
    lines = [
        ln.strip()
        for ln in (REPO_ROOT / "scripts" / "packages.list").read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    required = (
        "rnaalignmentqc",
        "rnaexpress",
        "omicsfeatures",
        "proteomicsfeatures",
        "proteomicsqc",
    )
    assert "workers" in lines
    workers_idx = lines.index("workers")
    for name in required:
        assert name in lines, f"{name} missing from packages.list"
        assert lines.index(name) < workers_idx, f"{name} must precede workers"


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
        "__GOLIATH_VENV__", "/work/goliath/venv-aarch64"
    )
    assert "/work/goliath//work/goliath" not in rendered
    assert "venv-aarch64/bin/methyl-worker" in rendered
