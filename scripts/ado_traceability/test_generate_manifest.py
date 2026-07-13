"""Tests for ado_traceability generate_manifest README parsing."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ado_traceability"))

from generate_manifest import (  # noqa: E402
    DEFAULT_OUT,
    ROW_RE,
    build_manifest,
    parse_readme_feature_cell,
)


def test_parse_readme_feature_cell_ab_id() -> None:
    parsed = parse_readme_feature_cell("**AB#414**")
    assert parsed["ado_feature_id"] == 414
    assert parsed["legacy_ado_type"] == "Feature"


def test_parse_readme_feature_cell_legacy_epic() -> None:
    parsed = parse_readme_feature_cell("**Epic**")
    assert parsed["ado_feature_id"] is None
    assert parsed["legacy_ado_type"] == "Epic"


def test_parse_readme_feature_cell_meta() -> None:
    parsed = parse_readme_feature_cell("_(meta)_")
    assert parsed["legacy_ado_type"] == "Task"


def test_row_re_does_not_put_ab_into_type_slot() -> None:
    readme = (
        Path(ROOT) / "docs" / "plans" / "README.md"
    ).read_text(encoding="utf-8")
    m = next(ROW_RE.finditer(readme))
    parsed = parse_readme_feature_cell(m.group(2))
    assert parsed["legacy_ado_type"] in ("Epic", "Task", "Feature")
    assert not str(parsed["legacy_ado_type"]).startswith("AB#")
    assert parsed["ado_feature_id"] is not None or "meta" in m.group(2).lower()


def test_build_manifest_preserves_prior_legacy_types() -> None:
    manifest = build_manifest(prior_manifest=DEFAULT_OUT)
    types = {f["legacy_ado_type"] for f in manifest["features"]}
    assert types <= {"Epic", "Task", "Feature"}
    assert not any(
        str(f["legacy_ado_type"]).startswith("AB#") for f in manifest["features"]
    )
    # Prior committed YAML used Epic/Task; regen should keep those when present
    prior = yaml.safe_load(DEFAULT_OUT.read_text(encoding="utf-8"))
    prior_by_stem = {
        f["plan_stem"]: f["legacy_ado_type"] for f in prior["features"]
    }
    for feat in manifest["features"]:
        if feat["plan_stem"] in prior_by_stem:
            assert feat["legacy_ado_type"] == prior_by_stem[feat["plan_stem"]]
        if feat.get("ado_feature_id") is not None:
            assert isinstance(feat["ado_feature_id"], int)
