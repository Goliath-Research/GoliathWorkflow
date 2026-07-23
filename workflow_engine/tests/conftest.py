"""Shared fixtures for workflow_engine tests.

Provides a helper to decouple committed study projects from production ``/work``
sample CSVs so profile/compile tests do not depend on cluster-local data.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from local_project_support import project_with_local_samples

DOMAIN = Path(__file__).resolve().parents[1] / "domain"
REPO_PROFILES = DOMAIN / "profiles"


@pytest.fixture(autouse=True)
def repo_pipeline_profiles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prefer repo profile JSON over deployed /work/epimethyl bundles in tests."""
    monkeypatch.setenv("METHYL_PROFILE_DIR", str(REPO_PROFILES))


@pytest.fixture
def local_project(tmp_path: Path):
    """Factory fixture: decouple a committed project from /work sample CSVs."""

    def _factory(src_project: Path) -> Path:
        return project_with_local_samples(src_project, tmp_path)

    return _factory
