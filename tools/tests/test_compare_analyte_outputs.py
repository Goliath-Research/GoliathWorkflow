"""Tests for compare_analyte_outputs DMP source selection."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from compare_analyte_outputs import DMP_SOURCE_PATTERNS, load_dmps


def test_load_dmps_discovery(tmp_path: Path) -> None:
    det = tmp_path / "detections" / "all" / "PCa"
    det.mkdir(parents=True)
    pd.DataFrame({"chromosome": ["1"], "position": [100], "delta_mean": [0.1]}).to_csv(
        det / "dmps-1-discovery.csv", index=False
    )
    df = load_dmps(det, "discovery")
    assert len(df) == 1


def test_load_dmps_classifier_excludes_extended(tmp_path: Path) -> None:
    det = tmp_path / "detections" / "all" / "PCa"
    det.mkdir(parents=True)
    pd.DataFrame({"chromosome": ["1"], "position": [100]}).to_csv(
        det / "dmps-1-classifier.csv", index=False
    )
    pd.DataFrame({"chromosome": ["2"], "position": [200]}).to_csv(
        det / "dmps-2-classifier-extended.csv", index=False
    )
    df = load_dmps(det, "classifier")
    assert len(df) == 1
    assert df.iloc[0]["position"] == 100


def test_load_dmps_classifier_extended(tmp_path: Path) -> None:
    det = tmp_path / "detections" / "all" / "PCa"
    det.mkdir(parents=True)
    pd.DataFrame({"chromosome": ["2"], "position": [200]}).to_csv(
        det / "dmps-2-classifier-extended.csv", index=False
    )
    df = load_dmps(det, "classifier-extended")
    assert len(df) == 1


def test_load_dmps_missing_raises(tmp_path: Path) -> None:
    det = tmp_path / "detections" / "all" / "PCa"
    det.mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="dmps-\\*-classifier.csv"):
        load_dmps(det, "classifier")


def test_dmp_source_patterns() -> None:
    assert "discovery" in DMP_SOURCE_PATTERNS
    assert DMP_SOURCE_PATTERNS["classifier"] == "dmps-*-classifier.csv"
