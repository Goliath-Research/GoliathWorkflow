"""
Shared covariate loading and preprocessing for model backends.

Contract:
- Join key is sample basename (or caller-provided sample id list) matched against
  ``covariate_id_column`` in sidecar.
- Numeric columns are imputed then optionally standardized.
- Ordinal columns are mapped to numeric codes while preserving user-defined order.
- Categorical columns are one-hot encoded with frozen vocab and ``__UNKNOWN__`` bucket.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _import_h5py_with_plugins():
    import hdf5plugin  # noqa: F401
    import h5py

    return h5py


def _load_single_covariate_table(path: Path, covariate_id_column: str) -> pd.DataFrame:
    p = Path(path)
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


def _load_covariate_table(
    covariates_path: Union[str, Sequence[str]],
    covariate_id_column: str,
) -> pd.DataFrame:
    if isinstance(covariates_path, (list, tuple)):
        paths = [Path(str(p)) for p in covariates_path if str(p).strip()]
        if not paths:
            raise ValueError("covariates_path list is empty")
        existing = [p for p in paths if p.is_file()]
        missing = [p for p in paths if not p.is_file()]
        if missing:
            logger.warning(
                "Skipping missing covariates_path entries: %s",
                ", ".join(str(p) for p in missing),
            )
        if not existing:
            raise FileNotFoundError(
                "covariates_path list has no existing files: "
                + ", ".join(str(p) for p in paths)
            )
        merged = _load_single_covariate_table(existing[0], covariate_id_column)
        for extra in existing[1:]:
            other = _load_single_covariate_table(extra, covariate_id_column)
            overlap = [
                c
                for c in other.columns
                if c != covariate_id_column and c in merged.columns
            ]
            if overlap:
                other = other.rename(columns={c: f"{c}__dup" for c in overlap})
            merged = merged.merge(other, on=covariate_id_column, how="outer")
        return merged
    return _load_single_covariate_table(Path(str(covariates_path)), covariate_id_column)


# Never auto-include as covariates (label leakage / non-feature metadata).
# Operators may still opt in by listing these in covariate_*_columns explicitly.
_AUTO_EXCLUDE_COVARIATE_COLUMNS = frozenset(
    {
        "group",
        "label",
        "y",
        "class",
        "expected_class",
        "phenotype",
        "disease",
        "disease_status",
        "qp_status",
        "n_markers_observed",
        "marker_fraction",
    }
)


def _filter_auto_candidate_columns(candidate_cols: Sequence[str]) -> Tuple[List[str], List[str]]:
    """Drop known label/diagnostic columns from auto-inference candidates."""
    kept: List[str] = []
    excluded: List[str] = []
    for col in candidate_cols:
        if str(col) in _AUTO_EXCLUDE_COVARIATE_COLUMNS:
            excluded.append(str(col))
        else:
            kept.append(str(col))
    return kept, excluded


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


_KNOWN_ORDINAL_MAPS: Dict[Tuple[str, ...], Dict[str, float]] = {
    ("low", "medium", "high"): {"low": 1.0, "medium": 2.0, "high": 3.0},
    ("very_low", "low", "medium", "high", "very_high"): {
        "very_low": 1.0,
        "low": 2.0,
        "medium": 3.0,
        "high": 4.0,
        "very_high": 5.0,
    },
}


def _auto_ordinal_map_for_series(values: Sequence[str]) -> Optional[Dict[str, float]]:
    observed = sorted({str(v).strip().lower() for v in values if str(v).strip()})
    for key, mapping in _KNOWN_ORDINAL_MAPS.items():
        if set(observed).issubset(set(key)):
            return {k: float(v) for k, v in mapping.items()}
    return None


@dataclass
class CovariatePreprocessor:
    id_column: str
    numeric_columns: List[str]
    ordinal_columns: List[str]
    categorical_columns: List[str]
    ordinal_maps: Dict[str, Dict[str, float]]
    ordinal_unknown_value: float
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
            "ordinal_columns": list(self.ordinal_columns),
            "categorical_columns": list(self.categorical_columns),
            "ordinal_maps": {
                str(k): {str(kk): float(vv) for kk, vv in vm.items()}
                for k, vm in self.ordinal_maps.items()
            },
            "ordinal_unknown_value": float(self.ordinal_unknown_value),
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
            ordinal_columns=[str(x) for x in payload.get("ordinal_columns", [])],
            categorical_columns=[str(x) for x in payload.get("categorical_columns", [])],
            ordinal_maps={
                str(k): {str(kk): float(vv) for kk, vv in vm.items()}
                for k, vm in (payload.get("ordinal_maps") or {}).items()
            },
            ordinal_unknown_value=float(payload.get("ordinal_unknown_value", 0.0)),
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
    covariates_path: Optional[Union[str, Sequence[str]]],
    sample_ids: Sequence[str],
    *,
    covariate_id_column: str,
    strict_join: bool,
    numeric_columns: Optional[Sequence[str]] = None,
    ordinal_columns: Optional[Sequence[str]] = None,
    ordinal_maps: Optional[Dict[str, Dict[str, float]]] = None,
    ordinal_unknown_value: float = 0.0,
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

    auto_excluded: List[str] = []
    if numeric_columns is not None:
        numeric = [str(c) for c in numeric_columns]
        unknown = sorted(set(numeric) - set(candidate_cols))
        if unknown:
            raise ValueError(f"Configured numeric covariate columns not found: {unknown}")
    else:
        numeric = []
    if ordinal_columns is not None:
        ordinal = [str(c) for c in ordinal_columns]
        unknown = sorted(set(ordinal) - set(candidate_cols))
        if unknown:
            raise ValueError(f"Configured ordinal covariate columns not found: {unknown}")
    else:
        ordinal = []
    if categorical_columns is not None:
        categorical = [str(c) for c in categorical_columns]
        unknown = sorted(set(categorical) - set(candidate_cols))
        if unknown:
            raise ValueError(f"Configured categorical covariate columns not found: {unknown}")
    else:
        categorical = []

    # Default inference only touches numeric/categorical. Ordinal must be explicit
    # or auto-discovered via known label sets for non-numeric columns.
    if numeric_columns is None and categorical_columns is None and ordinal_columns is None:
        infer_cols, auto_excluded = _filter_auto_candidate_columns(candidate_cols)
        if not infer_cols:
            raise ValueError(
                "No usable covariate columns after excluding label/diagnostic metadata "
                f"({auto_excluded}). Set covariate_numeric_columns explicitly if needed."
            )
        numeric, categorical = _infer_column_roles(aligned, infer_cols)
        auto_ord: List[str] = []
        for col in list(categorical):
            series_vals = aligned[col].astype(object)
            series_vals = series_vals.where(pd.notna(series_vals), "").astype(str).tolist()
            inferred = _auto_ordinal_map_for_series(series_vals)
            if inferred is not None:
                auto_ord.append(col)
        if auto_ord:
            categorical = [c for c in categorical if c not in auto_ord]
            ordinal = auto_ord
            if ordinal_maps is None:
                ordinal_maps = {}
            for col in auto_ord:
                series_vals = aligned[col].astype(object)
                series_vals = series_vals.where(pd.notna(series_vals), "").astype(str).tolist()
                inferred = _auto_ordinal_map_for_series(series_vals)
                if inferred is not None:
                    ordinal_maps[col] = inferred
    elif ordinal_columns is None:
        ordinal = []
    elif numeric_columns is None:
        numeric = [c for c in candidate_cols if c not in categorical and c not in ordinal]
    elif categorical_columns is None:
        categorical = [c for c in candidate_cols if c not in numeric and c not in ordinal]

    overlap = (set(numeric) & set(ordinal)) | (set(numeric) & set(categorical)) | (set(ordinal) & set(categorical))
    if overlap:
        raise ValueError(f"Covariate columns must have exactly one role, overlap found: {sorted(overlap)}")

    if not numeric and not ordinal and not categorical:
        raise ValueError("No usable covariate columns after role assignment")
    ord_maps_in = {
        str(k): {str(kk).strip().lower(): float(vv) for kk, vv in vm.items()}
        for k, vm in (ordinal_maps or {}).items()
    }
    ord_maps: Dict[str, Dict[str, float]] = {}
    unknown_ordinal_count = 0

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

    for col in ordinal:
        vals_obj = aligned[col].astype(object) if col in aligned.columns else pd.Series([""] * len(sample_ids), index=aligned.index, dtype=object)
        vals_str = vals_obj.where(pd.notna(vals_obj), "").astype(str)
        mapping = ord_maps_in.get(col)
        if mapping is None:
            inferred = _auto_ordinal_map_for_series(vals_str.tolist())
            if inferred is None:
                raise ValueError(
                    f"Ordinal column '{col}' requires covariate_ordinal_maps[{col!r}] "
                    "or values matching a known order (e.g. low/medium/high)."
                )
            mapping = inferred
        ord_maps[col] = mapping
        coded = np.full((len(sample_ids),), float(ordinal_unknown_value), dtype=np.float32)
        for i, raw in enumerate(vals_str.tolist()):
            key = str(raw).strip().lower()
            if key in mapping:
                coded[i] = float(mapping[key])
            else:
                unknown_ordinal_count += 1
        if standardize_numeric:
            mu = float(np.mean(coded, dtype=np.float64))
            sd = float(np.std(coded, dtype=np.float64))
            if not np.isfinite(sd) or sd <= 0.0:
                sd = 1.0
            coded = ((coded - mu) / sd).astype(np.float32)
            means[col] = mu
            stds[col] = sd
        else:
            means[col] = float(np.mean(coded, dtype=np.float64))
            stds[col] = float(np.std(coded, dtype=np.float64) or 1.0)
        fill_vals[col] = float(ordinal_unknown_value)
        out_parts.append(coded.reshape(-1, 1))
        output_columns.append(col)

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
        ordinal_columns=ordinal,
        categorical_columns=categorical,
        ordinal_maps=ord_maps,
        ordinal_unknown_value=float(ordinal_unknown_value),
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
        "n_ordinal_columns": int(len(ordinal)),
        "n_categorical_columns": int(len(categorical)),
        "n_output_columns": int(matrix.shape[1]),
        "numeric_columns": list(numeric),
        "ordinal_columns": list(ordinal),
        "categorical_columns": list(categorical),
        "auto_excluded_columns": list(auto_excluded),
        "unknown_ordinal_values_mapped": int(unknown_ordinal_count),
        "missing_numeric_strategy": missing_numeric_strategy,
        "standardize_numeric": bool(standardize_numeric),
    }
    return matrix, prep, report


def transform_covariates(
    covariates_path: Optional[Union[str, Sequence[str]]],
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

    unknown_ordinal_count = 0
    for col in preprocessor.ordinal_columns:
        if col in aligned.columns:
            vals_obj = aligned[col].astype(object)
            vals_str = vals_obj.where(pd.notna(vals_obj), "").astype(str)
        else:
            vals_str = pd.Series([""] * len(sample_ids), index=aligned.index, dtype=str)
        mapping = preprocessor.ordinal_maps.get(col, {})
        coded = np.full((len(sample_ids),), float(preprocessor.ordinal_unknown_value), dtype=np.float32)
        for i, raw in enumerate(vals_str.tolist()):
            key = str(raw).strip().lower()
            if key in mapping:
                coded[i] = float(mapping[key])
            else:
                unknown_ordinal_count += 1
        if preprocessor.standardize_numeric:
            mu = float(preprocessor.numeric_means.get(col, 0.0))
            sd = float(preprocessor.numeric_stds.get(col, 1.0))
            if not np.isfinite(sd) or sd <= 0.0:
                sd = 1.0
            coded = ((coded - mu) / sd).astype(np.float32)
        out_parts.append(coded.reshape(-1, 1))

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
        "unknown_ordinal_values_mapped": int(unknown_ordinal_count),
        "n_output_columns": int(matrix.shape[1]),
    }
    return matrix, report
