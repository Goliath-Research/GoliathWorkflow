"""Typed registry that identifies real reference samples used for testing.

This is *test-infrastructure* configuration, not tunable science configuration.
It names, per analyte (e.g. ``cfdna``, ``buffy_coat``), a single real reference
sample directory (containing extracted ``{chr}-{ctx}.h5`` files) plus optional
named groups of samples (e.g. ``healthy``, ``PCa``) for cohort-level tests.

Where operators set it (precedence, highest wins):

1. ``METHYL_TEST_DATA_CONFIG`` -> path to a standalone registry JSON.
2. Site manifest ``testing`` block (``METHYL_SITE_CONFIG`` / ``/work/site/methyl_site.json``).
3. Committed repo default (``tests/real_data/registry.json``) -> points at the
   small committed real-format fixture, when present.

Paths may be absolute (``/work/samples/...``) or repo-relative (resolved against
the repository root). Tests must skip cleanly when a referenced sample is not
mounted; see ``methyl_utils.testing.real_data``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

TEST_DATA_CONFIG_ENV = "METHYL_TEST_DATA_CONFIG"
SITE_CONFIG_ENV = "METHYL_SITE_CONFIG"
DEFAULT_SITE_PATH = Path("/work/site/methyl_site.json")


class TestSampleRef(BaseModel):
    """One designated real reference sample (a directory of ``{chr}-{ctx}.h5``)."""

    __test__ = False  # not a pytest test class despite the ``Test`` prefix

    model_config = ConfigDict(extra="forbid")

    sample_id: Optional[str] = Field(
        default=None, description="Stable identifier for the reference sample."
    )
    sample_dir: Optional[str] = Field(
        default=None,
        description="Directory holding extracted {chr}-{ctx}.h5 files. Absolute (e.g. "
        "/work/samples/<id>) or repo-relative (resolved from the repository root).",
    )
    analyte: Optional[str] = Field(
        default=None,
        description="Canonical analyte (cfdna, buffy_coat, combined, ...) this sample represents.",
    )
    chromosomes: Optional[List[str]] = Field(
        default=None, description="Chromosomes available for this reference sample (e.g. ['21'])."
    )
    contexts: Optional[List[str]] = Field(
        default=None, description="Methylation contexts available (e.g. ['CG'])."
    )
    description: Optional[str] = Field(
        default=None, description="Human-readable purpose/notes for the reference sample."
    )
    provenance: Optional[str] = Field(
        default=None,
        description="Source, consent basis, and producing MethylExtractor release for "
        "regulatory traceability (non-PHI sources only).",
    )


class TestSampleGroup(BaseModel):
    """A named cohort of real reference samples for cohort-level tests."""

    __test__ = False  # not a pytest test class despite the ``Test`` prefix

    model_config = ConfigDict(extra="forbid")

    label: Optional[str] = Field(
        default=None, description="Cohort label (e.g. healthy, PCa, PCa1)."
    )
    analyte: Optional[str] = Field(
        default=None, description="Canonical analyte for the group (cfdna, buffy_coat, ...)."
    )
    sample_dirs: Optional[List[str]] = Field(
        default=None,
        description="Sample directories in the group (absolute or repo-relative).",
    )
    description: Optional[str] = Field(
        default=None, description="Human-readable purpose/notes for the group."
    )


class TestDataRegistry(BaseModel):
    """Registry of real reference samples and groups used by ``real_data`` tests."""

    __test__ = False  # not a pytest test class despite the ``Test`` prefix

    model_config = ConfigDict(extra="forbid")

    committed_fixture_dir: Optional[str] = Field(
        default=None,
        description="Repo-relative directory holding the small committed real-format H5 "
        "fixture (runs on hosted CI). Absent/empty when only /work samples are used.",
    )
    samples: Optional[Dict[str, TestSampleRef]] = Field(
        default=None,
        description="Reference samples keyed by analyte or logical name "
        "(e.g. {'cfdna': {...}, 'buffy_coat': {...}}).",
    )
    groups: Optional[Dict[str, TestSampleGroup]] = Field(
        default=None,
        description="Named cohorts keyed by group name (e.g. {'healthy': {...}, 'PCa': {...}}).",
    )


def _load_json(path: Path) -> Dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def repo_root() -> Path:
    """Repository root (packages/methylutils/methyl_utils -> parents[3])."""
    return Path(__file__).resolve().parents[3]


def load_test_data_registry(path: Optional[str | Path] = None) -> TestDataRegistry:
    """Resolve the test-data registry from env, site manifest, or the repo default.

    Precedence (highest wins): explicit ``path`` -> ``METHYL_TEST_DATA_CONFIG`` ->
    site manifest ``testing`` block -> committed ``tests/real_data/registry.json`` ->
    empty registry.
    """
    explicit = path or os.environ.get(TEST_DATA_CONFIG_ENV)
    if explicit:
        p = Path(str(explicit)).expanduser()
        if p.is_file():
            return TestDataRegistry.model_validate(_load_json(p))

    site_raw = os.environ.get(SITE_CONFIG_ENV) or str(DEFAULT_SITE_PATH)
    site_path = Path(site_raw).expanduser()
    if site_path.is_file():
        site = _load_json(site_path)
        testing = site.get("testing")
        if isinstance(testing, dict):
            return TestDataRegistry.model_validate(testing)

    default_path = repo_root() / "tests" / "real_data" / "registry.json"
    if default_path.is_file():
        return TestDataRegistry.model_validate(_load_json(default_path))

    return TestDataRegistry()


def resolve_sample_dir(sample_dir: Optional[str]) -> Optional[Path]:
    """Resolve a registry ``sample_dir`` to an absolute path (repo-relative allowed)."""
    if not sample_dir:
        return None
    p = Path(sample_dir).expanduser()
    if p.is_absolute():
        return p
    return (repo_root() / p).resolve()


def sample_has_h5(sample_dir: Optional[Path]) -> bool:
    """True when the directory exists and holds at least one ``{chr}-{ctx}.h5`` file."""
    if sample_dir is None or not sample_dir.is_dir():
        return False
    return any(sample_dir.glob("*-*.h5"))
