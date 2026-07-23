"""Tests for scripts/check_package_install_contract.py."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_package_install_contract.py"


def test_install_contract_passes_on_repo() -> None:
    proc = subprocess.run(
        ["python", str(SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_detects_missing_readme_and_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("check_pkg", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    root = tmp_path / "repo"
    (root / "packages" / "libpkg").mkdir(parents=True)
    (root / "packages" / "apppkg").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "deploy" / "env").mkdir(parents=True)
    for name in mod.REQUIRED_ENV_EXAMPLES:
        (root / name).write_text("# example\n", encoding="utf-8")

    (root / "packages" / "libpkg" / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            name = "lib_pkg"
            version = "0.1.0"
            readme = "README.md"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    # Missing README on purpose.

    (root / "packages" / "apppkg" / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [build-system]
            requires = ["setuptools>=61"]
            build-backend = "setuptools.build_meta"

            [project]
            name = "app_pkg"
            version = "0.1.0"
            dependencies = ["lib_pkg"]
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (root / "scripts" / "packages.list").write_text("apppkg\nlibpkg\n", encoding="utf-8")

    errors = mod.check_package_install_contract(root)
    assert any("missing declared readme" in e for e in errors)
    assert any("must appear before" in e for e in errors)
