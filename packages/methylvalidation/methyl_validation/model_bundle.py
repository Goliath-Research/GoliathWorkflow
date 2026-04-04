"""
Model feature bundle (v1) for production model backends.

The bundle is a lightweight manifest + HDF5 tables that centralize detector exports,
resolved class labels, and a canonical DMP index for downstream model training.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from methyl_utils import load_project

if TYPE_CHECKING:
    from methyl_utils import ComparisonSpec, ProjectConfig

BUNDLE_SCHEMA_VERSION = 1
BUNDLE_MANIFEST_NAME = "model_feature_bundle.json"
BUNDLE_H5_NAME = "model_feature_bundle.h5"
DETECTOR_POINTER_NAME = "detection_model_bundle.json"


@contextmanager
def _project_cwd(project_json: Path):
    """Temporarily use project file directory for relative list-path resolution."""
    prev = Path.cwd()
    try:
        os.chdir(project_json.parent)
        yield
    finally:
        os.chdir(prev)


class BundleComparison(BaseModel):
    comparison_label: str
    control_group: str
    disease_group: str
    detection_dir: str
    classifier_dmps_csv: Optional[str] = None
    discovery_dmps_csv: Optional[str] = None


class ModelFeatureBundleManifest(BaseModel):
    schema_version: int = Field(default=BUNDLE_SCHEMA_VERSION)
    project_json: str
    project_name: str
    bundle_h5: str
    dmp_count: int
    classes: List[str]
    comparisons: List[BundleComparison]
    dmp_columns: List[str]
    metadata: Dict[str, Any] = Field(default_factory=dict)


def _import_h5py_with_plugins():
    # Full HDF5 plugin filter support requires this import order.
    import hdf5plugin  # noqa: F401
    import h5py

    return h5py


def _decode_bytes(arr: np.ndarray) -> np.ndarray:
    if arr.dtype.kind == "S":
        return np.char.decode(arr, "utf-8")
    return arr


def _h5_write_str(g: Any, name: str, values: List[str]) -> None:
    data = np.asarray(values, dtype="S")
    g.create_dataset(name, data=data, compression="gzip", compression_opts=4)


def _choose_detector_csvs(detection_dir: Path) -> Dict[str, Optional[Path]]:
    classifier = sorted(detection_dir.glob("dmps-*-classifier.csv"))
    discovery = sorted(detection_dir.glob("dmps-*-discovery.csv"))
    unified = sorted(
        p
        for p in detection_dir.glob("dmps-*.csv")
        if "-classifier" not in p.name and "-discovery" not in p.name
    )
    return {
        "classifier": classifier[0] if classifier else (unified[0] if unified else None),
        "discovery": discovery[0] if discovery else None,
    }


def _load_dmps_table(
    csv_path: Path,
    comparison_label: str,
    weight_column: str = "weight",
) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    rename_map: Dict[str, str] = {}
    if "chrom" in df.columns and "chromosome" not in df.columns:
        rename_map["chrom"] = "chromosome"
    if "pos" in df.columns and "position" not in df.columns:
        rename_map["pos"] = "position"
    if rename_map:
        df = df.rename(columns=rename_map)
    required = {"chromosome", "position"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"DMP CSV missing required columns {missing}: {csv_path}")
    if "context" not in df.columns:
        df["context"] = "CG"
    if weight_column not in df.columns:
        if "effect_size" in df.columns:
            df[weight_column] = pd.to_numeric(df["effect_size"], errors="coerce").fillna(0.0)
        else:
            df[weight_column] = 1.0
    out = pd.DataFrame(
        {
            "comparison_label": str(comparison_label),
            "chromosome": df["chromosome"].astype(str),
            "position": pd.to_numeric(df["position"], errors="coerce").fillna(-1).astype(np.int64),
            "context": df["context"].astype(str),
            "effect_size": pd.to_numeric(df.get("effect_size", np.nan), errors="coerce").astype(float),
            "weight": pd.to_numeric(df[weight_column], errors="coerce").fillna(0.0).astype(float),
            "source_csv": str(csv_path.resolve()),
        }
    )
    out = out[out["position"] >= 0].copy()
    out["position"] = out["position"].astype(np.uint32)
    return out


def _write_bundle_h5(bundle_h5: Path, dmp_df: pd.DataFrame, class_names: List[str]) -> None:
    h5py = _import_h5py_with_plugins()
    bundle_h5.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(bundle_h5, "w") as f:
        f.attrs["schema_version"] = BUNDLE_SCHEMA_VERSION
        g = f.create_group("dmp_index")
        _h5_write_str(g, "comparison_label", dmp_df["comparison_label"].astype(str).tolist())
        _h5_write_str(g, "chromosome", dmp_df["chromosome"].astype(str).tolist())
        g.create_dataset(
            "position",
            data=dmp_df["position"].astype(np.uint32).values,
            compression="gzip",
            compression_opts=4,
        )
        _h5_write_str(g, "context", dmp_df["context"].astype(str).tolist())
        g.create_dataset(
            "effect_size",
            data=dmp_df["effect_size"].fillna(0.0).astype(np.float32).values,
            compression="gzip",
            compression_opts=4,
        )
        g.create_dataset(
            "weight",
            data=dmp_df["weight"].fillna(0.0).astype(np.float32).values,
            compression="gzip",
            compression_opts=4,
        )
        _h5_write_str(g, "source_csv", dmp_df["source_csv"].astype(str).tolist())
        _h5_write_str(f, "classes", [str(x) for x in class_names])


def load_bundle_dmp_index(bundle_h5: str | Path) -> pd.DataFrame:
    h5py = _import_h5py_with_plugins()
    path = Path(bundle_h5)
    with h5py.File(path, "r") as f:
        g = f["dmp_index"]
        df = pd.DataFrame(
            {
                "comparison_label": _decode_bytes(np.asarray(g["comparison_label"])).astype(str),
                "chromosome": _decode_bytes(np.asarray(g["chromosome"])).astype(str),
                "position": np.asarray(g["position"], dtype=np.uint32),
                "context": _decode_bytes(np.asarray(g["context"])).astype(str),
                "effect_size": np.asarray(g["effect_size"], dtype=np.float32),
                "weight": np.asarray(g["weight"], dtype=np.float32),
                "source_csv": _decode_bytes(np.asarray(g["source_csv"])).astype(str),
            }
        )
    return df


def build_model_feature_bundle(
    project_json: str | Path,
    output_dir: str | Path,
    *,
    weight_column: str = "weight",
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Path:
    project_json = Path(project_json).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    with _project_cwd(project_json):
        project: "ProjectConfig" = load_project(project_json)
    comparisons: List["ComparisonSpec"] = project.get_comparisons()
    paths = project.get_derived_paths()
    classes = [str(label) for label, _paths in project.get_resolved_groups()]

    rows: List[pd.DataFrame] = []
    cmp_items: List[BundleComparison] = []
    detector_pointer: Dict[str, Any] = {"comparisons": []}

    for spec in comparisons:
        cmp_label = spec.comparison_label or spec.disease_group
        det_dir = Path(project.get_detection_output_dir(spec.control_group, spec.disease_group))
        csvs = _choose_detector_csvs(det_dir)
        classifier_csv = csvs["classifier"]
        discovery_csv = csvs["discovery"]
        cmp_items.append(
            BundleComparison(
                comparison_label=str(cmp_label),
                control_group=str(spec.control_group),
                disease_group=str(spec.disease_group),
                detection_dir=str(det_dir),
                classifier_dmps_csv=str(classifier_csv.resolve()) if classifier_csv else None,
                discovery_dmps_csv=str(discovery_csv.resolve()) if discovery_csv else None,
            )
        )
        detector_pointer["comparisons"].append(cmp_items[-1].model_dump(mode="json"))
        if classifier_csv and classifier_csv.is_file():
            rows.append(_load_dmps_table(classifier_csv, str(cmp_label), weight_column=weight_column))

    # Flat projects or missing explicit comparisons: use root detection dir fallback.
    if not rows:
        det_dir = Path(paths.detection_dir)
        csvs = _choose_detector_csvs(det_dir)
        classifier_csv = csvs["classifier"]
        if classifier_csv and classifier_csv.is_file():
            rows.append(_load_dmps_table(classifier_csv, "default", weight_column=weight_column))
            cmp_items.append(
                BundleComparison(
                    comparison_label="default",
                    control_group="group1",
                    disease_group="group2",
                    detection_dir=str(det_dir),
                    classifier_dmps_csv=str(classifier_csv.resolve()),
                    discovery_dmps_csv=None,
                )
            )
            detector_pointer["comparisons"].append(cmp_items[-1].model_dump(mode="json"))

    if not rows:
        raise FileNotFoundError(
            "No detector DMP CSVs found for bundle build. Expected dmps-*-classifier.csv or dmps-*.csv under detection dirs."
        )

    dmp_df = pd.concat(rows, ignore_index=True)
    dmp_df = dmp_df.sort_values(
        ["weight", "effect_size", "chromosome", "position", "comparison_label"],
        ascending=[False, False, True, True, True],
    ).reset_index(drop=True)

    bundle_h5 = out_dir / BUNDLE_H5_NAME
    _write_bundle_h5(bundle_h5, dmp_df, classes)

    manifest = ModelFeatureBundleManifest(
        project_json=str(project_json),
        project_name=str(project.project_name),
        bundle_h5=str(bundle_h5),
        dmp_count=int(len(dmp_df)),
        classes=classes,
        comparisons=cmp_items,
        dmp_columns=["comparison_label", "chromosome", "position", "context", "effect_size", "weight", "source_csv"],
        metadata=extra_metadata or {},
    )
    manifest_path = out_dir / BUNDLE_MANIFEST_NAME
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest.model_dump(mode="json"), f, indent=2)

    pointer_path = out_dir / DETECTOR_POINTER_NAME
    with open(pointer_path, "w", encoding="utf-8") as f:
        json.dump(detector_pointer, f, indent=2)
    return manifest_path

