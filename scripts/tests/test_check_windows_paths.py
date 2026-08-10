"""Tests for scripts/check_windows_paths.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "scripts" / "check_windows_paths.py"

_spec = importlib.util.spec_from_file_location("check_windows_paths", _MODULE_PATH)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
path_issues = _mod.path_issues


def test_valid_paths_pass() -> None:
    assert path_issues("docs/usage/index.md") == []
    assert path_issues("packages/methylcentroid/docs/IMPLEMENTATION.md") == []


def test_control_characters_fail() -> None:
    bad = "\x01\xD0[W\x04@\x85\x01\x12L\xD0"
    issues = path_issues(bad)
    assert any("control" in i for i in issues)


def test_invalid_characters_fail() -> None:
    assert path_issues("docs/theory/index?.qmd")
    assert any("invalid" in i for i in path_issues("docs/theory/index?.qmd"))


def test_trailing_space_fails() -> None:
    issues = path_issues("docs/trailing /bar.md")
    assert any("trailing" in i for i in issues)


def test_reserved_name_fails() -> None:
    issues = path_issues("tools/CON.txt")
    assert any("reserved" in i for i in issues)
