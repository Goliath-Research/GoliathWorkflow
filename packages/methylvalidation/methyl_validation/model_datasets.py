"""Canonical train/test design-matrix exports under ``model_bundle/``.

Flat Option-A layout (backends already isolated per model-MC run)::

    model_bundle/train_dataset.parquet
    model_bundle/test_dataset.parquet   # omitted when no test split
    model_bundle/dataset_manifest.json

Identity columns (aligned across backends)::

    sample_id, class_index, class_label

followed by backend-specific feature columns.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np
import pandas as pd

TRAIN_DATASET_NAME = "train_dataset.parquet"
TEST_DATASET_NAME = "test_dataset.parquet"
DATASET_MANIFEST_NAME = "dataset_manifest.json"

IDENTITY_COLUMNS = ("sample_id", "class_index", "class_label")


def resolve_model_bundle_dir(
    bundle_dir: Optional[Union[str, Path]] = None,
    *,
    project_json: Optional[Union[str, Path]] = None,
) -> Path:
    """Resolve the run-local ``model_bundle`` directory."""
    if bundle_dir is not None:
        return Path(bundle_dir).expanduser().resolve()
    if project_json is not None:
        return Path(project_json).expanduser().resolve().parent / "model_bundle"
    raise ValueError("bundle_dir or project_json is required to resolve model_bundle")


def train_dataset_path(bundle_dir: Union[str, Path]) -> Path:
    return Path(bundle_dir) / TRAIN_DATASET_NAME


def test_dataset_path(bundle_dir: Union[str, Path]) -> Path:
    return Path(bundle_dir) / TEST_DATASET_NAME


def dataset_manifest_path(bundle_dir: Union[str, Path]) -> Path:
    return Path(bundle_dir) / DATASET_MANIFEST_NAME


def dataset_sidecar_meta_path(dataset_path: Path) -> Path:
    """Tabular cache fingerprint sidecar (``.parquet.meta.json``)."""
    return dataset_path.with_suffix(f"{dataset_path.suffix}.meta.json")


def write_dataset_frame(dataset_path: Path, frame: pd.DataFrame) -> None:
    """Write a design matrix. Canonical format is Parquet; suffix may override for tests."""
    dataset_path = Path(dataset_path)
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    ext = dataset_path.suffix.lower()
    if ext == ".parquet":
        frame.to_parquet(dataset_path, index=False)
    elif ext == ".tsv":
        frame.to_csv(dataset_path, sep="\t", index=False)
    else:
        frame.to_csv(dataset_path, index=False)


def read_dataset_frame(dataset_path: Path) -> pd.DataFrame:
    dataset_path = Path(dataset_path)
    ext = dataset_path.suffix.lower()
    if ext == ".parquet":
        return pd.read_parquet(dataset_path)
    if ext == ".tsv":
        return pd.read_csv(dataset_path, sep="\t")
    return pd.read_csv(dataset_path)


def build_identity_feature_frame(
    *,
    sample_ids: Sequence[str],
    class_index: Sequence[int] | np.ndarray,
    class_names: Sequence[str],
    feature_matrix: Optional[np.ndarray] = None,
    feature_names: Optional[Sequence[str]] = None,
    feature_frame: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Assemble ``sample_id`` / ``class_index`` / ``class_label`` + feature columns."""
    ids = [str(s) for s in sample_ids]
    y = np.asarray(class_index, dtype=np.int32)
    if len(ids) != int(y.shape[0]):
        raise ValueError(
            f"sample_ids length {len(ids)} != class_index length {int(y.shape[0])}"
        )
    labels = [str(class_names[int(i)]) if 0 <= int(i) < len(class_names) else str(int(i)) for i in y]
    data: Dict[str, Any] = {
        "sample_id": ids,
        "class_index": y.astype(int),
        "class_label": labels,
    }
    if feature_frame is not None:
        feats = feature_frame.reset_index(drop=True)
        if len(feats) != len(ids):
            raise ValueError(
                f"feature_frame rows {len(feats)} != sample_ids length {len(ids)}"
            )
        for col in feats.columns:
            name = str(col)
            if name in IDENTITY_COLUMNS:
                continue
            data[name] = feats[col].to_numpy()
    elif feature_matrix is not None:
        matrix = np.asarray(feature_matrix)
        names = [str(n) for n in (feature_names or [])]
        if matrix.ndim != 2:
            raise ValueError("feature_matrix must be 2-D")
        if matrix.shape[0] != len(ids):
            raise ValueError(
                f"feature_matrix rows {matrix.shape[0]} != sample_ids length {len(ids)}"
            )
        if names and len(names) != int(matrix.shape[1]):
            raise ValueError(
                f"feature_names length {len(names)} != matrix columns {matrix.shape[1]}"
            )
        if not names:
            names = [f"feature_{i}" for i in range(int(matrix.shape[1]))]
        for index, name in enumerate(names):
            data[name] = matrix[:, index]
    return pd.DataFrame(data)


def feature_columns_from_frame(frame: pd.DataFrame) -> List[str]:
    return [str(c) for c in frame.columns if str(c) not in IDENTITY_COLUMNS]


def write_dataset_manifest(
    bundle_dir: Union[str, Path],
    *,
    backend: str,
    train_path: Union[str, Path],
    test_path: Optional[Union[str, Path]] = None,
    feature_columns: Optional[Sequence[str]] = None,
    train_test_overlap_count: Optional[int] = None,
    overlapping_sample_ids: Optional[Sequence[str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Path:
    """Write ``dataset_manifest.json`` beside the Parquet datasets."""
    bundle = Path(bundle_dir)
    bundle.mkdir(parents=True, exist_ok=True)
    train_p = Path(train_path)
    test_p = Path(test_path) if test_path is not None else None
    train_df = read_dataset_frame(train_p)
    n_test: Optional[int] = None
    if test_p is not None and test_p.is_file():
        n_test = int(len(read_dataset_frame(test_p)))
    feats = (
        [str(c) for c in feature_columns]
        if feature_columns is not None
        else feature_columns_from_frame(train_df)
    )
    manifest: Dict[str, Any] = {
        "schema_version": 1,
        "backend": str(backend),
        "train_dataset": str(train_p),
        "test_dataset": str(test_p) if test_p is not None else None,
        "n_train_samples": int(len(train_df)),
        "n_test_samples": n_test,
        "train_test_overlap_count": (
            int(train_test_overlap_count) if train_test_overlap_count is not None else None
        ),
        "overlapping_sample_ids": [str(x) for x in (overlapping_sample_ids or [])],
        "feature_columns": feats,
        "identity_columns": list(IDENTITY_COLUMNS),
    }
    if extra:
        manifest.update(dict(extra))
    out = dataset_manifest_path(bundle)
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return out


def write_model_datasets(
    bundle_dir: Union[str, Path],
    *,
    backend: str,
    train_frame: pd.DataFrame,
    test_frame: Optional[pd.DataFrame] = None,
    extra_manifest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Write train (and optional test) Parquet plus ``dataset_manifest.json``."""
    bundle = Path(bundle_dir)
    bundle.mkdir(parents=True, exist_ok=True)
    missing = [c for c in IDENTITY_COLUMNS if c not in train_frame.columns]
    if missing:
        raise ValueError(f"train_frame missing identity columns: {missing}")
    train_path = train_dataset_path(bundle)
    write_dataset_frame(train_path, train_frame)

    test_path: Optional[Path] = None
    overlap: List[str] = []
    if test_frame is not None:
        missing_test = [c for c in IDENTITY_COLUMNS if c not in test_frame.columns]
        if missing_test:
            raise ValueError(f"test_frame missing identity columns: {missing_test}")
        test_path = test_dataset_path(bundle)
        write_dataset_frame(test_path, test_frame)
        overlap = sorted(
            set(train_frame["sample_id"].astype(str))
            & set(test_frame["sample_id"].astype(str))
        )

    manifest_path = write_dataset_manifest(
        bundle,
        backend=backend,
        train_path=train_path,
        test_path=test_path,
        feature_columns=feature_columns_from_frame(train_frame),
        train_test_overlap_count=int(len(overlap)) if test_frame is not None else None,
        overlapping_sample_ids=overlap,
        extra=extra_manifest,
    )
    return {
        "train_dataset": str(train_path),
        "test_dataset": str(test_path) if test_path is not None else None,
        "dataset_manifest_json": str(manifest_path),
        "train_test_overlap_count": int(len(overlap)) if test_frame is not None else None,
        "n_train_samples": int(len(train_frame)),
        "n_test_samples": int(len(test_frame)) if test_frame is not None else None,
        "feature_columns": feature_columns_from_frame(train_frame),
        "overlapping_sample_ids": overlap,
    }
