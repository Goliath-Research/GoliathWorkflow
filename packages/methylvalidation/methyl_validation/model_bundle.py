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
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from methyl_utils import load_project

if TYPE_CHECKING:
    from methyl_utils import ComparisonSpec, ProjectConfig

BUNDLE_SCHEMA_VERSION = 2
BUNDLE_MANIFEST_NAME = "model_feature_bundle.json"
BUNDLE_H5_NAME = "model_feature_bundle.h5"
DETECTOR_POINTER_NAME = "detection_model_bundle.json"
MAPPER_ANNOTATION_NAME = "mapper_dmp_annotations.csv"


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
    classifier_dmps_csvs: List[str] = Field(default_factory=list)
    discovery_dmps_csvs: List[str] = Field(default_factory=list)


class ModelFeatureBundleManifest(BaseModel):
    schema_version: int = Field(default=BUNDLE_SCHEMA_VERSION)
    project_json: str
    project_name: str
    bundle_h5: str
    dmp_count: int
    classes: List[str]
    comparisons: List[BundleComparison]
    dmp_columns: List[str]
    feature_families: List[str] = Field(default_factory=lambda: ["dmp", "gene", "structural"])
    feature_contract_version: str = Field(default="hybrid_bundle_v1")
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


def _choose_detector_csvs(detection_dir: Path) -> Dict[str, List[Path]]:
    classifier = sorted(detection_dir.glob("dmps-*-classifier.csv"))
    discovery = sorted(detection_dir.glob("dmps-*-discovery.csv"))
    unified = sorted(
        p
        for p in detection_dir.glob("dmps-*.csv")
        if "-classifier" not in p.name and "-discovery" not in p.name
    )
    return {
        "classifier": classifier if classifier else unified,
        "discovery": discovery,
    }


def _normalize_chromosome(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower().startswith("chr"):
        text = text[3:]
    return text


def _normalize_context(value: Any, *, default: str = "CG") -> str:
    if value is None or pd.isna(value):
        return default
    text = str(value).strip().upper()
    return text if text else default


def _parse_dmp_name_locus(value: Any) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    text = str(value or "").strip()
    if not text:
        return None, None, None
    parts = text.split(":")
    if len(parts) < 3:
        return None, None, None
    chrom = _normalize_chromosome(parts[0])
    try:
        pos = int(str(parts[1]).strip())
    except Exception:
        return None, None, None
    ctx = _normalize_context(parts[2])
    if not chrom or pos < 0:
        return None, None, None
    return chrom, pos, ctx


def _safe_feature_text(value: Any, *, default: str = "unknown") -> str:
    text = str(value or "").strip()
    return text if text else default


def _normalize_mapper_intersections(
    mapper_df: pd.DataFrame,
    *,
    comparison_label: str,
    source_csv: Path,
) -> pd.DataFrame:
    work = mapper_df.copy()
    if work.empty:
        return pd.DataFrame()

    dmp_col = "dmp_name" if "dmp_name" in work.columns else None
    chrom_col = None
    for candidate in ("chromosome", "chrom", "feature_chrom"):
        if candidate in work.columns:
            chrom_col = candidate
            break
    pos_col = None
    for candidate in ("position", "pos"):
        if candidate in work.columns:
            pos_col = candidate
            break
    ctx_col = "context" if "context" in work.columns else None

    parsed = work[dmp_col].map(_parse_dmp_name_locus) if dmp_col is not None else None
    chrom_from_dmp = (
        parsed.map(lambda t: t[0]) if parsed is not None else pd.Series([None] * len(work))
    )
    pos_from_dmp = (
        parsed.map(lambda t: t[1]) if parsed is not None else pd.Series([None] * len(work))
    )
    ctx_from_dmp = (
        parsed.map(lambda t: t[2]) if parsed is not None else pd.Series([None] * len(work))
    )

    if chrom_col is not None:
        chrom_series = work[chrom_col].map(_normalize_chromosome).replace("", pd.NA)
        chrom_series = pd.Series(
            np.where(chrom_series.isna(), chrom_from_dmp, chrom_series),
            index=work.index,
            dtype="object",
        )
    else:
        chrom_series = chrom_from_dmp
    if pos_col is not None:
        pos_series = pd.to_numeric(work[pos_col], errors="coerce")
        pos_series = pos_series.combine_first(pd.to_numeric(pos_from_dmp, errors="coerce"))
    else:
        pos_series = pd.to_numeric(pos_from_dmp, errors="coerce")
    if ctx_col is not None:
        ctx_series = work[ctx_col].map(lambda v: _normalize_context(v, default="")).replace("", pd.NA)
        ctx_series = pd.Series(
            np.where(ctx_series.isna(), ctx_from_dmp, ctx_series),
            index=work.index,
            dtype="object",
        )
    else:
        ctx_series = ctx_from_dmp.map(_normalize_context)

    gene_col = None
    for candidate in ("gene_name", "gene", "gene_symbol", "symbol", "nearest_gene"):
        if candidate in work.columns:
            gene_col = candidate
            break
    feat_col = None
    for candidate in ("feature_type", "gene_feature", "region_type", "annotation_feature"):
        if candidate in work.columns:
            feat_col = candidate
            break

    region_weight_col = None
    for candidate in ("region_weight", "feature_weight"):
        if candidate in work.columns:
            region_weight_col = candidate
            break
    combined_weight_col = "combined_weight" if "combined_weight" in work.columns else None
    eff_col = "effect_size" if "effect_size" in work.columns else None

    out = pd.DataFrame(
        {
            "comparison_label": str(comparison_label),
            "chromosome": chrom_series.astype(str),
            "position": pd.to_numeric(pos_series, errors="coerce"),
            "context": ctx_series.map(_normalize_context),
            "gene_name": (
                work[gene_col].map(_safe_feature_text)
                if gene_col is not None
                else "unknown"
            ),
            "feature_type": (
                work[feat_col].map(_safe_feature_text)
                if feat_col is not None
                else "unknown"
            ),
            "region_weight": (
                pd.to_numeric(work[region_weight_col], errors="coerce")
                if region_weight_col is not None
                else np.nan
            ),
            "combined_weight": (
                pd.to_numeric(work[combined_weight_col], errors="coerce")
                if combined_weight_col is not None
                else np.nan
            ),
            "effect_size": (
                pd.to_numeric(work[eff_col], errors="coerce")
                if eff_col is not None
                else np.nan
            ),
            "mapper_source_csv": str(source_csv.absolute()),
        }
    )
    out["chromosome"] = out["chromosome"].map(_normalize_chromosome)
    out["position"] = pd.to_numeric(out["position"], errors="coerce")
    out = out[np.isfinite(out["position"])].copy()
    out["position"] = out["position"].astype(np.int64)
    out = out[(out["position"] >= 0) & (out["chromosome"].astype(str).str.len() > 0)].copy()
    out["region_weight"] = (
        pd.to_numeric(out["region_weight"], errors="coerce").fillna(1.0).astype(float)
    )
    out["combined_weight"] = pd.to_numeric(out["combined_weight"], errors="coerce")
    out["effect_size"] = pd.to_numeric(out["effect_size"], errors="coerce")
    return out


def _collapse_mapper_annotations(annotations: pd.DataFrame) -> pd.DataFrame:
    if annotations.empty:
        return annotations
    work = annotations.copy()
    work["_priority_combined"] = pd.to_numeric(work["combined_weight"], errors="coerce").fillna(-1.0)
    work["_priority_region"] = pd.to_numeric(work["region_weight"], errors="coerce").fillna(-1.0)
    work["_priority_effect"] = (
        np.abs(pd.to_numeric(work["effect_size"], errors="coerce").fillna(0.0))
    )
    work = work.sort_values(
        [
            "comparison_label",
            "chromosome",
            "position",
            "context",
            "_priority_combined",
            "_priority_region",
            "_priority_effect",
            "gene_name",
            "feature_type",
            "mapper_source_csv",
        ],
        ascending=[True, True, True, True, False, False, False, True, True, True],
    )
    work = work.drop_duplicates(
        subset=["comparison_label", "chromosome", "position", "context"],
        keep="first",
    ).reset_index(drop=True)
    return work[
        [
            "comparison_label",
            "chromosome",
            "position",
            "context",
            "gene_name",
            "feature_type",
            "region_weight",
            "mapper_source_csv",
        ]
    ].copy()


def _candidate_mapper_annotation_paths(
    *,
    project_json: Path,
    project: "ProjectConfig",
    bundle_dir: Path,
    explicit_path: Optional[str | Path],
) -> List[Path]:
    candidates: List[Path] = []
    if explicit_path is not None:
        p = Path(explicit_path)
        if not p.is_absolute():
            p = (project_json.parent / p).resolve()
        candidates.append(p)
    try:
        mb_cfg = project.get_step_config("model_bundle") or {}
    except Exception:
        mb_cfg = {}
    cfg_path = mb_cfg.get("mapper_annotation_csv")
    if cfg_path:
        p = Path(str(cfg_path))
        if not p.is_absolute():
            p = (project_json.parent / p).resolve()
        candidates.append(p)
    candidates.append(bundle_dir / MAPPER_ANNOTATION_NAME)
    candidates.append(project_json.parent / "model_bundle" / MAPPER_ANNOTATION_NAME)

    out: List[Path] = []
    seen: set[str] = set()
    for p in candidates:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def build_mapper_annotation_cache(
    *,
    project_json: str | Path,
    output_csv: str | Path,
) -> Dict[str, Any]:
    project_json_path = Path(project_json).absolute()
    with _project_cwd(project_json_path):
        project: "ProjectConfig" = load_project(project_json_path)

    comparisons = project.get_comparisons()
    rows: List[pd.DataFrame] = []
    source_files: List[str] = []

    for spec in comparisons:
        cmp_label = spec.comparison_label or spec.disease_group
        mapper_dir = Path(
            project.get_mapper_output_dir(spec.control_group, spec.disease_group)
        )
        if not mapper_dir.is_dir():
            continue
        csvs = sorted(mapper_dir.glob("*-intersections.csv"))
        for csv_path in csvs:
            try:
                df = pd.read_csv(csv_path)
            except Exception:
                continue
            source_files.append(str(csv_path.absolute()))
            normalized = _normalize_mapper_intersections(
                df,
                comparison_label=str(cmp_label),
                source_csv=csv_path,
            )
            if not normalized.empty:
                rows.append(normalized)

    if not rows:
        out_path = Path(output_csv).absolute()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            columns=[
                "comparison_label",
                "chromosome",
                "position",
                "context",
                "gene_name",
                "feature_type",
                "region_weight",
                "mapper_source_csv",
            ]
        ).to_csv(out_path, index=False)
        return {
            "path": str(out_path),
            "rows": 0,
            "unique_loci": 0,
            "source_files": sorted(set(source_files)),
            "comparisons": [str(spec.comparison_label or spec.disease_group) for spec in comparisons],
        }

    raw = pd.concat(rows, ignore_index=True)
    ann = _collapse_mapper_annotations(raw)
    out_path = Path(output_csv).absolute()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ann.to_csv(out_path, index=False)
    return {
        "path": str(out_path),
        "rows": int(len(ann)),
        "unique_loci": int(len(ann)),
        "source_files": sorted(set(source_files)),
        "comparisons": sorted(set(ann["comparison_label"].astype(str).tolist())),
    }


def _load_mapper_annotation_table(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if df.empty:
        return pd.DataFrame(
            columns=[
                "comparison_label",
                "chromosome",
                "position",
                "context",
                "gene_name",
                "feature_type",
                "region_weight",
                "mapper_source_csv",
            ]
        )
    required = {"comparison_label", "chromosome", "position", "context"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(
            f"Mapper annotation CSV missing required columns {missing}: {path}"
        )
    for c in ("gene_name", "feature_type", "mapper_source_csv"):
        if c not in df.columns:
            df[c] = "unknown" if c != "mapper_source_csv" else str(path)
    if "region_weight" not in df.columns:
        df["region_weight"] = 1.0
    if "combined_weight" not in df.columns:
        df["combined_weight"] = np.nan
    if "effect_size" not in df.columns:
        df["effect_size"] = np.nan
    df["comparison_label"] = df["comparison_label"].astype(str)
    df["chromosome"] = df["chromosome"].map(_normalize_chromosome).astype(str)
    df["position"] = pd.to_numeric(df["position"], errors="coerce")
    df = df[np.isfinite(df["position"])].copy()
    df["position"] = df["position"].astype(np.int64)
    df["context"] = df["context"].map(_normalize_context).astype(str)
    df["gene_name"] = df["gene_name"].map(_safe_feature_text)
    df["feature_type"] = df["feature_type"].map(_safe_feature_text)
    df["region_weight"] = (
        pd.to_numeric(df["region_weight"], errors="coerce").fillna(1.0).astype(float)
    )
    return _collapse_mapper_annotations(df)


def _merge_mapper_annotations(
    dmp_df: pd.DataFrame,
    ann_df: pd.DataFrame,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if ann_df.empty or dmp_df.empty:
        return dmp_df, {
            "n_loci": int(len(dmp_df)),
            "n_loci_with_mapper_match": 0,
            "n_gene_name_from_mapper": 0,
            "n_feature_type_from_mapper": 0,
        }
    work = dmp_df.copy()
    work["chromosome"] = work["chromosome"].map(_normalize_chromosome).astype(str)
    work["context"] = work["context"].map(_normalize_context).astype(str)
    work["position"] = pd.to_numeric(work["position"], errors="coerce").fillna(-1).astype(np.int64)
    merged = work.merge(
        ann_df,
        on=["comparison_label", "chromosome", "position", "context"],
        how="left",
        suffixes=("", "_mapper"),
    )

    gene_mapper = merged["gene_name_mapper"] if "gene_name_mapper" in merged.columns else pd.Series([None] * len(merged))
    feat_mapper = merged["feature_type_mapper"] if "feature_type_mapper" in merged.columns else pd.Series([None] * len(merged))
    rw_mapper = merged["region_weight_mapper"] if "region_weight_mapper" in merged.columns else pd.Series([np.nan] * len(merged))

    gene_valid = gene_mapper.notna() & (gene_mapper.astype(str).str.strip() != "")
    feat_valid = feat_mapper.notna() & (feat_mapper.astype(str).str.strip() != "")
    rw_valid = np.isfinite(pd.to_numeric(rw_mapper, errors="coerce"))

    merged.loc[gene_valid, "gene_name"] = gene_mapper[gene_valid].astype(str)
    merged.loc[feat_valid, "feature_type"] = feat_mapper[feat_valid].astype(str)
    merged.loc[rw_valid, "region_weight"] = pd.to_numeric(rw_mapper[rw_valid], errors="coerce").astype(float)
    merged["gene_name"] = merged["gene_name"].map(_safe_feature_text)
    merged["feature_type"] = merged["feature_type"].map(_safe_feature_text)
    merged["region_weight"] = pd.to_numeric(merged["region_weight"], errors="coerce").fillna(1.0).astype(float)

    stats = {
        "n_loci": int(len(merged)),
        "n_loci_with_mapper_match": int((gene_valid | feat_valid | rw_valid).sum()),
        "n_gene_name_from_mapper": int(gene_valid.sum()),
        "n_feature_type_from_mapper": int(feat_valid.sum()),
    }
    drop_cols = [c for c in ("gene_name_mapper", "feature_type_mapper", "region_weight_mapper") if c in merged.columns]
    if drop_cols:
        merged = merged.drop(columns=drop_cols)
    return merged, stats


def _load_dmps_table(
    csv_path: Path,
    comparison_label: str,
    weight_column: str = "effect_size",
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
    gene_col = None
    for candidate in ("gene_name", "gene", "gene_symbol", "symbol", "nearest_gene"):
        if candidate in df.columns:
            gene_col = candidate
            break
    dmr_col = None
    for candidate in ("dmr_region", "region_id", "dmr_id", "region", "dmr"):
        if candidate in df.columns:
            dmr_col = candidate
            break
    if "effect_size" not in df.columns:
        raise ValueError(
            f"DMP CSV missing required column ['effect_size']: {csv_path}"
        )
    # Keep the parameter for API compatibility, but canonicalize model weighting to effect_size.
    del weight_column
    effect_size = pd.to_numeric(df["effect_size"], errors="coerce").fillna(0.0).astype(float)
    feature_col = None
    for candidate in ("feature_type", "gene_feature", "region_type", "annotation_feature"):
        if candidate in df.columns:
            feature_col = candidate
            break
    region_weight_col = None
    for candidate in ("region_weight", "combined_weight", "feature_weight"):
        if candidate in df.columns:
            region_weight_col = candidate
            break
    out = pd.DataFrame(
        {
            "comparison_label": str(comparison_label),
            "chromosome": df["chromosome"].astype(str),
            "position": pd.to_numeric(df["position"], errors="coerce").fillna(-1).astype(np.int64),
            "context": df["context"].astype(str),
            "effect_size": effect_size,
            "weight": effect_size,
            "gene_name": (df[gene_col].astype(str) if gene_col is not None else "unknown"),
            "dmr_region": (df[dmr_col].astype(str) if dmr_col is not None else "unknown"),
            "feature_type": (df[feature_col].astype(str) if feature_col is not None else "unknown"),
            "region_weight": (
                pd.to_numeric(df[region_weight_col], errors="coerce").fillna(1.0).astype(float)
                if region_weight_col is not None
                else 1.0
            ),
            "source_csv": str(csv_path.absolute()),
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
        _h5_write_str(g, "gene_name", dmp_df["gene_name"].fillna("unknown").astype(str).tolist())
        _h5_write_str(g, "dmr_region", dmp_df["dmr_region"].fillna("unknown").astype(str).tolist())
        _h5_write_str(g, "feature_type", dmp_df["feature_type"].fillna("unknown").astype(str).tolist())
        g.create_dataset(
            "region_weight",
            data=dmp_df["region_weight"].fillna(1.0).astype(np.float32).values,
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
                "gene_name": (
                    _decode_bytes(np.asarray(g["gene_name"])).astype(str)
                    if "gene_name" in g
                    else np.asarray(["unknown"] * len(np.asarray(g["position"])), dtype=object)
                ),
                "dmr_region": (
                    _decode_bytes(np.asarray(g["dmr_region"])).astype(str)
                    if "dmr_region" in g
                    else np.asarray(["unknown"] * len(np.asarray(g["position"])), dtype=object)
                ),
                "feature_type": (
                    _decode_bytes(np.asarray(g["feature_type"])).astype(str)
                    if "feature_type" in g
                    else np.asarray(["unknown"] * len(np.asarray(g["position"])), dtype=object)
                ),
                "region_weight": (
                    np.asarray(g["region_weight"], dtype=np.float32)
                    if "region_weight" in g
                    else np.asarray([1.0] * len(np.asarray(g["position"])), dtype=np.float32)
                ),
                "source_csv": _decode_bytes(np.asarray(g["source_csv"])).astype(str),
            }
        )
    return df


def build_model_feature_bundle(
    project_json: str | Path,
    output_dir: str | Path,
    *,
    weight_column: str = "effect_size",
    feature_family_set: str = "dmp",
    mapper_annotation_csv: Optional[str | Path] = None,
    require_mapper_annotations: Optional[bool] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Path:
    project_json = Path(project_json).absolute()
    out_dir = Path(output_dir).absolute()
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
        classifier_csvs = [p for p in csvs["classifier"] if p.is_file()]
        discovery_csvs = [p for p in csvs["discovery"] if p.is_file()]
        cmp_items.append(
            BundleComparison(
                comparison_label=str(cmp_label),
                control_group=str(spec.control_group),
                disease_group=str(spec.disease_group),
                detection_dir=str(det_dir),
                classifier_dmps_csv=str(classifier_csvs[0].absolute()) if classifier_csvs else None,
                discovery_dmps_csv=str(discovery_csvs[0].absolute()) if discovery_csvs else None,
                classifier_dmps_csvs=[str(p.absolute()) for p in classifier_csvs],
                discovery_dmps_csvs=[str(p.absolute()) for p in discovery_csvs],
            )
        )
        detector_pointer["comparisons"].append(cmp_items[-1].model_dump(mode="json"))
        for csv_path in classifier_csvs:
            rows.append(_load_dmps_table(csv_path, str(cmp_label), weight_column=weight_column))

    # Flat projects or missing explicit comparisons: use root detection dir fallback.
    if not rows:
        det_dir = Path(paths.detection_dir)
        csvs = _choose_detector_csvs(det_dir)
        classifier_csvs = [p for p in csvs["classifier"] if p.is_file()]
        if classifier_csvs:
            for csv_path in classifier_csvs:
                rows.append(_load_dmps_table(csv_path, "default", weight_column=weight_column))
            cmp_items.append(
                BundleComparison(
                    comparison_label="default",
                    control_group="group1",
                    disease_group="group2",
                    detection_dir=str(det_dir),
                    classifier_dmps_csv=str(classifier_csvs[0].absolute()),
                    discovery_dmps_csv=None,
                    classifier_dmps_csvs=[str(p.absolute()) for p in classifier_csvs],
                    discovery_dmps_csvs=[],
                )
            )
            detector_pointer["comparisons"].append(cmp_items[-1].model_dump(mode="json"))

    if not rows:
        raise FileNotFoundError(
            "No detector DMP CSVs found for bundle build. Expected dmps-*-classifier.csv or dmps-*.csv under detection dirs."
        )

    family_token = str(feature_family_set or "dmp").strip().lower()
    strict_mapper = bool(require_mapper_annotations) if require_mapper_annotations is not None else (family_token != "dmp")
    mapper_ann_path: Optional[Path] = None
    mapper_ann_df = pd.DataFrame()
    mapper_lookup_stats: Dict[str, Any] = {
        "n_loci": 0,
        "n_loci_with_mapper_match": 0,
        "n_gene_name_from_mapper": 0,
        "n_feature_type_from_mapper": 0,
    }
    mapper_candidates = _candidate_mapper_annotation_paths(
        project_json=project_json,
        project=project,
        bundle_dir=out_dir,
        explicit_path=mapper_annotation_csv,
    )
    for p in mapper_candidates:
        if p.is_file():
            mapper_ann_path = p
            break
    if mapper_ann_path is not None:
        mapper_ann_df = _load_mapper_annotation_table(mapper_ann_path)
    elif strict_mapper:
        raise FileNotFoundError(
            "Mapper annotation cache is required for non-dmp feature families but was not found. "
            f"Searched: {[str(p) for p in mapper_candidates]}"
        )

    del weight_column
    dmp_df = pd.concat(rows, ignore_index=True)
    if mapper_ann_path is not None:
        dmp_df, mapper_lookup_stats = _merge_mapper_annotations(dmp_df, mapper_ann_df)
    dmp_df = dmp_df.sort_values(
        ["effect_size", "chromosome", "position", "comparison_label"],
        ascending=[False, True, True, True],
    ).reset_index(drop=True)

    includes_gene = family_token in {"gene", "dmp+gene", "hybrid-all"}
    includes_structural = family_token in {"structural", "dmp+structural", "hybrid-all"}
    gene_non_unknown = int((dmp_df["gene_name"].astype(str).str.strip().str.lower() != "unknown").sum())
    feat_non_unknown = int((dmp_df["feature_type"].astype(str).str.strip().str.lower() != "unknown").sum())
    if strict_mapper:
        if mapper_ann_path is None:
            raise FileNotFoundError("Mapper annotations are required but no annotation cache path was resolved.")
        if mapper_lookup_stats.get("n_loci_with_mapper_match", 0) <= 0:
            raise ValueError(
                "Mapper annotations were required but no detector loci matched mapper cache keys."
            )
        if includes_gene and gene_non_unknown <= 0:
            raise ValueError(
                "Mapper annotations were required for gene features but no non-'unknown' gene_name values were found."
            )
        if includes_structural and feat_non_unknown <= 0:
            raise ValueError(
                "Mapper annotations were required for structural features but no non-'unknown' feature_type values were found."
            )

    bundle_h5 = out_dir / BUNDLE_H5_NAME
    _write_bundle_h5(bundle_h5, dmp_df, classes)

    bundle_metadata: Dict[str, Any] = dict(extra_metadata or {})
    bundle_metadata.setdefault("feature_family_set", family_token)
    bundle_metadata.setdefault("strict_mapper_annotations", bool(strict_mapper))
    bundle_metadata.setdefault(
        "mapper_annotation",
        {
            "path": str(mapper_ann_path) if mapper_ann_path is not None else None,
            "n_rows": int(len(mapper_ann_df)) if mapper_ann_path is not None else 0,
            "n_loci_with_mapper_match": int(mapper_lookup_stats.get("n_loci_with_mapper_match", 0)),
            "n_gene_name_from_mapper": int(mapper_lookup_stats.get("n_gene_name_from_mapper", 0)),
            "n_feature_type_from_mapper": int(mapper_lookup_stats.get("n_feature_type_from_mapper", 0)),
            "n_gene_name_non_unknown": int(gene_non_unknown),
            "n_feature_type_non_unknown": int(feat_non_unknown),
            "gene_unknown_rate": float(
                1.0 - (gene_non_unknown / max(1, len(dmp_df)))
            ),
            "feature_unknown_rate": float(
                1.0 - (feat_non_unknown / max(1, len(dmp_df)))
            ),
        },
    )
    bundle_metadata.setdefault(
        "feature_aggregation",
        {
            "weight_column": "effect_size",
            "region_weight_column": "region_weight",
            "gene_column": "gene_name",
            "structural_column": "feature_type",
            "supported_structural_features": [
                "promoter",
                "exon",
                "intron",
                "gene_body",
                "terminator",
                "unknown",
            ],
            "effect_size_transform": "abs(effect_size) normalized",
        },
    )
    manifest = ModelFeatureBundleManifest(
        project_json=str(project_json),
        project_name=str(project.project_name),
        bundle_h5=str(bundle_h5),
        dmp_count=int(len(dmp_df)),
        classes=classes,
        comparisons=cmp_items,
        dmp_columns=[
            "comparison_label",
            "chromosome",
            "position",
            "context",
            "effect_size",
            "weight",
            "gene_name",
            "dmr_region",
            "feature_type",
            "region_weight",
            "source_csv",
        ],
        metadata=bundle_metadata,
    )
    manifest_path = out_dir / BUNDLE_MANIFEST_NAME
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest.model_dump(mode="json"), f, indent=2)

    pointer_path = out_dir / DETECTOR_POINTER_NAME
    with open(pointer_path, "w", encoding="utf-8") as f:
        json.dump(detector_pointer, f, indent=2)
    return manifest_path

