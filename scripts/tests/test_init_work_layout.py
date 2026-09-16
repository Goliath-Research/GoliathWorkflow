"""Tests for scripts/init_work_layout.sh (tmpdir only; does not touch /work)."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INIT = REPO_ROOT / "scripts" / "init_work_layout.sh"
VERIFY = REPO_ROOT / "scripts" / "verify_work_layout.sh"


def _mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def _run_init(work: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(INIT), "--work", str(work), "--skip-acl", *extra],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_init_work_layout_creates_access_modes(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    proc = _run_init(work)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    for name in ("samples", "projects", "cache"):
        path = work / name
        assert path.is_dir(), name
        assert _mode(path) == 0o777, f"{name} mode {oct(_mode(path))}"

    for name in ("genomes", "site", "epimethyl"):
        path = work / name
        assert path.is_dir(), name
        assert _mode(path) == 0o755, f"{name} mode {oct(_mode(path))}"
        assert not (_mode(path) & stat.S_IWOTH), name


def test_init_work_layout_does_not_recurse(tmp_path: Path) -> None:
    work = tmp_path / "work"
    child = work / "samples" / "S1" / "align.linear.parabricks"
    child.mkdir(parents=True)
    os.chmod(child, 0o700)
    proc = _run_init(work)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _mode(work / "samples") == 0o777
    assert _mode(child) == 0o700


def test_init_work_layout_fails_when_work_missing(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-mount"
    proc = _run_init(missing)
    assert proc.returncode != 0
    assert "Work mount missing" in proc.stderr


def test_verify_work_layout_fails_when_samples_not_other_writable(
    tmp_path: Path,
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    assert _run_init(work).returncode == 0
    os.chmod(work / "samples", 0o755)
    env = os.environ.copy()
    env["WORK_ROOT"] = str(work)
    env["METHYL_WORK_ROOT"] = str(work)
    env["METHYL_SITE_CONFIG"] = str(work / "site" / "methyl_site.json")
    proc = subprocess.run(
        ["bash", str(VERIFY)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert proc.returncode != 0
    assert "Samples root not other-writable" in proc.stderr


def test_init_and_verify_work_layout_pass(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    assert _run_init(work).returncode == 0
    env = os.environ.copy()
    env["WORK_ROOT"] = str(work)
    env["METHYL_WORK_ROOT"] = str(work)
    env["METHYL_SITE_CONFIG"] = str(work / "site" / "methyl_site.json")
    proc = subprocess.run(
        ["bash", str(VERIFY)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Samples root other-writable" in proc.stdout
    assert "Genomes root worker-readable" in proc.stdout
    assert "GoliathOmics root worker-readable" in proc.stdout
