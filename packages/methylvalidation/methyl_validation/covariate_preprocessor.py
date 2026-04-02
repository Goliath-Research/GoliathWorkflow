"""
Shared covariate loading and preprocessing for model backends.

Contract:
- Join key is sample basename (or caller-provided sample id list) matched against
  ``covariate_id_column`` in sidecar.
- Numeric columns are imputed then optionally standardized.
- Categorical columns are one-hot encoded with frozen vocab and ``__UNKNOWN__`` bucket.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


def _import_h5py_with_plugins():
    import hdf5plugin  # noqa: F401
    import h5py

    return h5py


def _load_covariate_table(covariates_path: str, covariate_id_column: str) -> pd.DataFrame:
    p = Path(covariates_path)
    if not p.is_file():
        raise FileNotFoundError(f"covariates_path not found: {p}")
    if p.suffix.lower() in (".csv", ".tsv"):
        sep = "\t" if p.suffix.lower() == ".tsv" else ","
        df = pd.read_csv(p, sep=sep)
    elif p.suffix.lower() in (".h5", ".hdf5"):
        h5py = _import_h5py_with_plugins()
        with h5py.File(p, "r") as f:
            if not all(k in f for k in ("sample_id", "values")):
                raise ValueError(f"Covariates HDF5 missing sample_id/values datasets: {p}")
            sids = np.asarray(f["sample_id"])
            if sids.dtype.kind == "S":
                sids = np.char.decode(sids, "utf-8")
            vals = np.asarray(f["values"], dtype=np.float32)
            cols = np.asarray(f["columns"]) if "columns" in f else np.array([f"cov_{i}" for i in range(vals.shape[1])])
            if cols.dtype.kind == "S":
                cols = np.char.decode(cols, "utf-8")
        df = pd.DataFrame(vals, columns=[str(c) for c in cols])
        df[covariate_id_column] = [str(x) for x in sids.tolist()]
    else:
        raise ValueError(f"Unsupported covariates sidecar format: {p.suffix}")
    if covariate_id_column not in df.columns:
        raise ValueError(f"Covariates table missing id column '{covariate_id_column}'")
    df = df.copy()
    df[covariate_id_column] = df[covariate_id_column].astype(str)
    return df


def _infer_column_roles(df: pd.DataFrame, candidate_cols: List[str]) -> Tuple[List[str], List[str]]:
    numeric: List[str] = []
    categorical: List[str] = []
    for col in candidate_cols:
        series = df[col]
        # treat as numeric if we can parse any non-null values
        parsed = pd.to_numeric(series, errors="coerce")
        non_null_original = int(series.notna().sum())
        non_null_numeric = int(parsed.notna().sum())
        if non_null_original > 0 and non_null_numeric > 0:
            numeric.append(col)
        else:
            categorical.append(col)
    return numeric, categorical


@dataclass
class CovariatePreprocessor:
    id_column: str
    numeric_columns: List[str]
    categorical_columns: List[str]
    numeric_fill_values: Dict[str, float]
    numeric_means: Dict[str, float]
    numeric_stds: Dict[str, float]
    categorical_levels: Dict[str, List[str]]
    output_columns: List[str]
    standardize_numeric: bool
    missing_numeric_strategy: str
    unknown_category_token: str = "__UNKNOWN__"
    missing_category_token: str = "__MISSING__"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id_column": self.id_column,
            "numeric_columns": list(self.numeric_columns),
            "categorical_columns": list(self.categorical_columns),
            "numeric_fill_values": {k: float(v) for k, v in self.numeric_fill_values.items()},
            "numeric_means": {k: float(v) for k, v in self.numeric_means.items()},
            "numeric_stds": {k: float(v) for k, v in self.numeric_stds.items()},
            "categorical_levels": {k: list(v) for k, v in self.categorical_levels.items()},
            "output_columns": list(self.output_columns),
            "standardize_numeric": bool(self.standardize_numeric),
            "missing_numeric_strategy": str(self.missing_numeric_strategy),
            "unknown_category_token": str(self.unknown_category_token),
            "missing_category_token": str(self.missing_category_token),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "CovariatePreprocessor":
        return cls(
            id_column=str(payload["id_column"]),
            numeric_columns=[str(x) for x in payload.get("numeric_columns", [])],
            categorical_columns=[str(x) for x in payload.get("categorical_columns", [])],
            numeric_fill_values={str(k): float(v) for k, v in (payload.get("numeric_fill_values") or {}).items()},
            numeric_means={str(k): float(v) for k, v in (payload.get("numeric_means") or {}).items()},
            numeric_stds={str(k): float(v) for k, v in (payload.get("numeric_stds") or {}).items()},
            categorical_levels={str(k): [str(x) for x in v] for k, v in (payload.get("categorical_levels") or {}).items()},
            output_columns=[str(x) for x in payload.get("output_columns", [])],
            standardize_numeric=bool(payload.get("standardize_numeric", True)),
            missing_numeric_strategy=str(payload.get("missing_numeric_strategy", "mean")),
            unknown_category_token=str(payload.get("unknown_category_token", "__UNKNOWN__")),
            missing_category_token=str(payload.get("missing_category_token", "__MISSING__")),
        )

    def save_json(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_json(cls, path: str | Path) -> "CovariatePreprocessor":
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        return cls.from_dict(payload)


def _ordered_covariate_rows(
    df: pd.DataFrame,
    sample_ids: Sequence[str],
    id_column: str,
    *,
    strict_join: bool,
) -> Tuple[pd.DataFrame, List[str]]:
    lookup = df.set_index(id_column)
    missing = [sid for sid in sample_ids if sid not in lookup.index]
    if strict_join and missing:
        preview = ", ".join(missing[:5])
        raise ValueError(f"Missing covariate rows for {len(missing)} sample ids (first: {preview})")
    aligned = lookup.reindex([str(s) for s in sample_ids]).copy()
    return aligned, missing


def fit_covariates(
    covariates_path: Optional[str],
    sample_ids: Sequence[str],
    *,
    covariate_id_column: str,
    strict_join: bool,
    numeric_columns: Optional[Sequence[str]] = None,
    categorical_columns: Optional[Sequence[str]] = None,
    missing_numeric_strategy: str = "mean",
    standardize_numeric: bool = True,
) -> Tuple[Optional[np.ndarray], Optional[CovariatePreprocessor], Dict[str, Any]]:
    if not covariates_path:
        return None, None, {"used": False}

    raw = _load_covariate_table(covariates_path, covariate_id_column)
    aligned, missing = _ordered_covariate_rows(
        raw,
        sample_ids,
        covariate_id_column,
        strict_join=strict_join,
    )
    candidate_cols = [c for c in aligned.columns.tolist() if c != covariate_id_column]
    if not candidate_cols:
        raise ValueError("Covariates table has no feature columns")

    if numeric_columns is not None:
        numeric = [str(c) for c in numeric_columns]
        unknown = sorted(set(numeric) - set(candidate_cols))
        if unknown:
            raise ValueError(f"Configured numeric covariate columns not found: {unknown}")
    else:
        numeric = []
    if categorical_columns is not None:
        categorical = [str(c) for c in categorical_columns]
        unknown = sorted(set(categorical) - set(candidate_cols))
        if unknown:
            raise ValueError(f"Configured categorical covariate columns not found: {unknown}")
    else:
        categorical = []

    if numeric_columns is None and categorical_columns is None:
        numeric, categorical = _infer_column_roles(aligned, candidate_cols)
    elif numeric_columns is None:
        numeric = [c for c in candidate_cols if c not in categorical]
    elif categorical_columns is None:
        categorical = [c for c in candidate_cols if c not in numeric]

    if not numeric and not categorical:
        raise ValueError("No usable covariate columns after role assignment")

    missing_numeric_strategy = str(missing_numeric_strategy).strip().lower()
    if missing_numeric_strategy not in {"mean", "median", "zero"}:
        raise ValueError("missing_numeric_strategy must be one of: mean, median, zero")

    out_parts: List[np.ndarray] = []
    output_columns: List[str] = []
    fill_vals: Dict[str, float] = {}
    means: Dict[str, float] = {}
    stds: Dict[str, float] = {}
    cat_levels: Dict[str, List[str]] = {}
    unknown_token = "__UNKNOWN__"
    missing_token = "__MISSING__"

    for col in numeric:
        vals = pd.to_numeric(aligned[col], errors="coerce").astype(float)
        if missing_numeric_strategy == "median":
            fill = float(np.nanmedian(vals.to_numpy(dtype=np.float64))) if vals.notna().any() else 0.0
        elif missing_numeric_strategy == "zero":
            fill = 0.0
        else:
            fill = float(np.nanmean(vals.to_numpy(dtype=np.float64))) if vals.notna().any() else 0.0
        x = vals.fillna(fill).to_numpy(dtype=np.float32)
        mu = float(np.mean(x, dtype=np.float64))
        sd = float(np.std(x, dtype=np.float64))
        if not np.isfinite(sd) or sd <= 0.0:
            sd = 1.0
        if standardize_numeric:
            x = ((x - mu) / sd).astype(np.float32)
        out_parts.append(x.reshape(-1, 1))
        output_columns.append(col)
        fill_vals[col] = float(fill)
        means[col] = mu
        stds[col] = sd

    for col in categorical:
        s = aligned[col].astype(object)
        s = s.where(pd.notna(s), missing_token).astype(str)
        levels = sorted(set(s.tolist()))
        if unknown_token not in levels:
            levels.append(unknown_token)
        cat_levels[col] = levels
        for lvl in levels:
            out_parts.append((s == lvl).to_numpy(dtype=np.float32).reshape(-1, 1))
            output_columns.append(f"{col}__{lvl}")

    matrix = np.concatenate(out_parts, axis=1).astype(np.float32) if out_parts else np.zeros((len(sample_ids), 0), dtype=np.float32)
    prep = CovariatePreprocessor(
        id_column=covariate_id_column,
        numeric_columns=numeric,
        categorical_columns=categorical,
        numeric_fill_values=fill_vals,
        numeric_means=means,
        numeric_stds=stds,
        categorical_levels=cat_levels,
        output_columns=output_columns,
        standardize_numeric=bool(standardize_numeric),
        missing_numeric_strategy=missing_numeric_strategy,
        unknown_category_token=unknown_token,
        missing_category_token=missing_token,
    )
    report = {
        "used": True,
        "n_rows_requested": int(len(sample_ids)),
        "n_rows_missing": int(len(missing)),
        "missing_sample_ids_preview": [str(x) for x in missing[:10]],
        "n_numeric_columns": int(len(numeric)),
        "n_categorical_columns": int(len(categorical)),
        "n_output_columns": int(matrix.shape[1]),
        "numeric_columns": list(numeric),
        "categorical_columns": list(categorical),
        "missing_numeric_strategy": missing_numeric_strategy,
        "standardize_numeric": bool(standardize_numeric),
    }
    return matrix, prep, report


def transform_covariates(
    covariates_path: Optional[str],
    sample_ids: Sequence[str],
    preprocessor: Optional[CovariatePreprocessor],
    *,
    strict_join: bool,
) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
    if preprocessor is None:
        return None, {"used": False}
    if not covariates_path:
        raise ValueError("Covariates were used for training but no covariates_path was provided for prediction.")

    raw = _load_covariate_table(covariates_path, preprocessor.id_column)
    aligned, missing = _ordered_covariate_rows(
        raw,
        sample_ids,
        preprocessor.id_column,
        strict_join=strict_join,
    )
    out_parts: List[np.ndarray] = []

    for col in preprocessor.numeric_columns:
        if col not in aligned.columns:
            vals = np.full((len(sample_ids),), preprocessor.numeric_fill_values.get(col, 0.0), dtype=np.float32)
        else:
            vals = pd.to_numeric(aligned[col], errors="coerce").astype(float).fillna(preprocessor.numeric_fill_values.get(col, 0.0)).to_numpy(dtype=np.float32)
        if preprocessor.standardize_numeric:
            mu = float(preprocessor.numeric_means.get(col, 0.0))
            sd = float(preprocessor.numeric_stds.get(col, 1.0))
            if not np.isfinite(sd) or sd <= 0.0:
                sd = 1.0
            vals = ((vals - mu) / sd).astype(np.float32)
        out_parts.append(vals.reshape(-1, 1))

    unknown_count = 0
    for col in preprocessor.categorical_columns:
        if col in aligned.columns:
            s = aligned[col].astype(object)
            s = s.where(pd.notna(s), preprocessor.missing_category_token).astype(str)
        else:
            s = pd.Series([preprocessor.missing_category_token] * len(sample_ids), index=aligned.index, dtype=str)
        levels = preprocessor.categorical_levels.get(col, [preprocessor.unknown_category_token])
        allowed = set(levels)
        mapped = []
        for v in s.tolist():
            if v in allowed:
                mapped.append(v)
            else:
                mapped.append(preprocessor.unknown_category_token)
                unknown_count += 1
        ms = pd.Series(mapped, dtype=str)
        for lvl in levels:
            out_parts.append((ms == lvl).to_numpy(dtype=np.float32).reshape(-1, 1))

    matrix = np.concatenate(out_parts, axis=1).astype(np.float32) if out_parts else np.zeros((len(sample_ids), 0), dtype=np.float32)
    if preprocessor.output_columns and matrix.shape[1] != len(preprocessor.output_columns):
        raise ValueError(
            "Covariate preprocessing output shape mismatch: "
            f"{matrix.shape[1]} != {len(preprocessor.output_columns)}"
        )
    report = {
        "used": True,
        "n_rows_requested": int(len(sample_ids)),
        "n_rows_missing": int(len(missing)),
        "missing_sample_ids_preview": [str(x) for x in missing[:10]],
        "unknown_categorical_values_mapped": int(unknown_count),
        "n_output_columns": int(matrix.shape[1]),
    }
    return matrix, report
