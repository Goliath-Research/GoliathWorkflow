"""Tests for scripts/render_diagrams.sh."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "render_diagrams.sh"
OUT = REPO_ROOT / "docs" / "diagrams" / "out"
SRC = REPO_ROOT / "docs" / "diagrams" / "src"


def test_render_diagrams_check_passes() -> None:
    proc = subprocess.run(
        ["bash", str(SCRIPT), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_all_mmd_sources_have_non_placeholder_svgs() -> None:
    for mmd in sorted(SRC.glob("*.mmd")):
        svg = OUT / f"{mmd.stem}.svg"
        assert svg.is_file(), f"missing SVG for {mmd.name}"
        text = svg.read_text(encoding="utf-8")
        assert "placeholder SVG" not in text, f"{svg.name} is still a placeholder"
        assert len(text) > 2000, f"{svg.name} looks too small to be a real diagram"
        hash_file = OUT / f"{mmd.stem}.mmd.sha256"
        assert hash_file.is_file(), f"missing source hash for {mmd.name}"
        expected = hash_file.read_text(encoding="utf-8").strip()
        actual = hashlib.sha256(mmd.read_bytes()).hexdigest()
        assert actual == expected, f"hash mismatch for {mmd.name}; run scripts/render_diagrams.sh"
