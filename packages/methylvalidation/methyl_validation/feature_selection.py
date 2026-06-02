"""
Feature selection helpers for freeze artifacts and backend training.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


@dataclass
class RuntimeFeatureSelectionConfig:
    enabled: bool = False
    mode: str = "stability_filter"
    feature_families: Tuple[str, ...] = ("dmp", "gene", "structural", "gene_scored")
    max_features_total: int = 200
    max_features_per_sample_ratio: float = 5.0
    min_dmp_frequency: float = 0.8
    min_abs_effect_size: Optional[float] = None
    group_by_gene: bool = True
    redundancy_filter: str = "correlation"
    max_pairwise_correlation: float = 0.95
    embedded_selector: Optional[str] = None
    latent_projection: Optional[str] = None
    random_seed: int = 13


def normalize_runtime_feature_selection_config(payload: Optional[Dict[str, Any]]) -> RuntimeFeatureSelectionConfig:
    if not isinstance(payload, dict):
        return RuntimeFeatureSelectionConfig()
    families_raw = payload.get("feature_families", ("dmp", "gene", "structural"))
    if not isinstance(families_raw, (list, tuple)):
        families_raw = ("dmp", "gene", "structural")
    families: List[str] = []
    for item in families_raw:
        token = str(item).strip().lower()
        if token in {"dmp", "gene", "structural", "gene_scored"} and token not in families:
            families.append(token)
    if not families:
        families = ["dmp", "gene", "structural", "gene_scored"]
    return RuntimeFeatureSelectionConfig(
        enabled=bool(payload.get("enabled", False)),
        mode=str(payload.get("mode", "stability_filter")).strip().lower() or "stability_filter",
        feature_families=tuple(families),
        max_features_total=max(1, int(payload.get("max_features_total", 200))),
        max_features_per_sample_ratio=max(0.1, float(payload.get("max_features_per_sample_ratio", 5.0))),
        min_dmp_frequency=float(payload.get("min_dmp_frequency", 0.8)),
        min_abs_effect_size=(
            float(payload["min_abs_effect_size"])
            if payload.get("min_abs_effect_size") is not None
            else None
        ),
        group_by_gene=bool(payload.get("group_by_gene", True)),
        redundancy_filter=str(payload.get("redundancy_filter", "correlation")).strip().lower() or "correlation",
        max_pairwise_correlation=float(payload.get("max_pairwise_correlation", 0.95)),
        embedded_selector=(
            str(payload["embedded_selector"]).strip().lower()
            if payload.get("embedded_selector") is not None
            else None
        ),
        latent_projection=(
            str(payload["latent_projection"]).strip().lower()
            if payload.get("latent_projection") is not None
            else None
        ),
        random_seed=int(payload.get("random_seed", 13)),
    )


def _dmp_key_series(df: pd.DataFrame) -> pd.Series:
    chrom_col = df["chromosome"] if "chromosome" in df.columns else pd.Series([""] * len(df), index=df.index)
    pos_col = df["position"] if "position" in df.columns else pd.Series([-1] * len(df), index=df.index)
    ctx_col = df["context"] if "context" in df.columns else pd.Series(["CG"] * len(df), index=df.index)
    chrom = chrom_col.astype(str).str.replace("chr", "", regex=False)
    pos = pd.to_numeric(pos_col, errors="coerce").fillna(-1).astype(int).astype(str)
    ctx = ctx_col.astype(str).str.upper()
    return chrom.str.cat(pos, sep=":").str.cat(ctx, sep=":")


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _feature_family_from_name(name: str) -> str:
    token = str(name)
    if token.startswith("gene_directional_score__") or token.startswith("region_directional_score__"):
        return "gene_scored"
    if token.startswith("gene::"):
        return "gene"
    if token.startswith("struct::"):
        return "structural"
    return "dmp"


def _class_separation_score(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    # Simple between-class variance / within-class variance score.
    Xf = np.asarray(X, dtype=np.float32)
    yv = np.asarray(y, dtype=np.int32)
    n_features = int(Xf.shape[1])
    if Xf.shape[0] <= 1 or n_features == 0:
        return np.zeros((n_features,), dtype=np.float32)
    global_mean = np.nanmean(Xf, axis=0)
    global_var = np.nanvar(Xf, axis=0) + 1e-8
    labels = sorted(set(int(v) for v in yv.tolist()))
    between = np.zeros((n_features,), dtype=np.float64)
    for cls in labels:
        mask = yv == int(cls)
        if not np.any(mask):
            continue
        cls_mean = np.nanmean(Xf[mask], axis=0)
        between += float(np.sum(mask)) * np.square(cls_mean - global_mean)
    score = (between / max(1.0, float(Xf.shape[0]))) / global_var
    score = np.nan_to_num(score, nan=0.0, posinf=0.0, neginf=0.0)
    return score.astype(np.float32)


def _redundancy_prune(
    X: np.ndarray,
    ordered_indices: List[int],
    threshold: float,
) -> List[int]:
    if not ordered_indices:
        return []
    if len(ordered_indices) == 1:
        return ordered_indices
    Xf = np.asarray(X, dtype=np.float32)
    keep: List[int] = []
    for idx in ordered_indices:
        if not keep:
            keep.append(int(idx))
            continue
        col = Xf[:, int(idx)]
        col = np.nan_to_num(col, nan=float(np.nanmedian(col) if np.isfinite(col).any() else 0.0))
        redundant = False
        for kept in keep:
            base = Xf[:, int(kept)]
            base = np.nan_to_num(base, nan=float(np.nanmedian(base) if np.isfinite(base).any() else 0.0))
            if np.std(col) <= 1e-8 or np.std(base) <= 1e-8:
                continue
            corr = np.corrcoef(base, col)[0, 1]
            if np.isfinite(corr) and abs(float(corr)) >= float(threshold):
                redundant = True
                break
        if not redundant:
            keep.append(int(idx))
    return keep


def select_training_features(
    X: np.ndarray,
    y: Sequence[int],
    feature_names: Sequence[str],
    cfg: RuntimeFeatureSelectionConfig,
) -> Dict[str, Any]:
    names = [str(x) for x in feature_names]
    n_features = len(names)
    if not cfg.enabled or n_features == 0:
        return {
            "selected_indices": list(range(n_features)),
            "selected_feature_names": list(names),
            "report": {"enabled": False, "reason": "disabled_or_empty"},
        }
    Xf = np.asarray(X, dtype=np.float32)
    yv = np.asarray(y, dtype=np.int32)
    if Xf.ndim != 2 or Xf.shape[1] != n_features:
        raise ValueError("Feature matrix shape does not match feature_names.")

    separation = _class_separation_score(Xf, yv)
    variance = np.nanvar(Xf, axis=0)
    variance = np.nan_to_num(variance, nan=0.0, posinf=0.0, neginf=0.0)
    score = separation * (variance + 1e-6)
    valid = np.isfinite(score) & (score > 0.0)
    score = np.where(valid, score, 0.0)

    n_samples = int(Xf.shape[0])
    cap_by_samples = max(1, int(round(float(cfg.max_features_per_sample_ratio) * max(1, n_samples))))
    target_total = max(1, min(int(cfg.max_features_total), cap_by_samples, n_features))

    family_to_indices: Dict[str, List[int]] = {"dmp": [], "gene": [], "structural": [], "gene_scored": []}
    for idx, name in enumerate(names):
        fam = _feature_family_from_name(name)
        if fam in family_to_indices:
            family_to_indices[fam].append(idx)

    active_families = [f for f in cfg.feature_families if family_to_indices.get(f)]
    if not active_families:
        active_families = ["dmp", "gene", "structural", "gene_scored"]

    per_family_cap = max(1, target_total // max(1, len(active_families)))
    selected: List[int] = []
    for fam in active_families:
        fam_idx = family_to_indices.get(fam, [])
        if not fam_idx:
            continue
        ranked = sorted(fam_idx, key=lambda j: float(score[j]), reverse=True)
        fam_selected = ranked[:per_family_cap]
        selected.extend(fam_selected)
    # fill remainder globally
    if len(selected) < target_total:
        chosen = set(selected)
        ranked_all = sorted(range(n_features), key=lambda j: float(score[j]), reverse=True)
        for idx in ranked_all:
            if idx in chosen:
                continue
            selected.append(idx)
            chosen.add(idx)
            if len(selected) >= target_total:
                break
    selected = selected[:target_total]

    if cfg.redundancy_filter == "correlation" and len(selected) > 1:
        selected = _redundancy_prune(
            Xf,
            selected,
            threshold=float(max(0.0, min(0.9999, cfg.max_pairwise_correlation))),
        )

    if not selected:
        selected = [int(np.argmax(score))]
    selected_names = [names[i] for i in selected]
    return {
        "selected_indices": [int(i) for i in selected],
        "selected_feature_names": selected_names,
        "report": {
            "enabled": True,
            "mode": cfg.mode,
            "n_input_features": int(n_features),
            "n_selected_features": int(len(selected)),
            "target_total": int(target_total),
            "n_samples": int(n_samples),
            "families": list(cfg.feature_families),
            "redundancy_filter": cfg.redundancy_filter,
            "max_pairwise_correlation": float(cfg.max_pairwise_correlation),
        },
    }


def run_feature_selection_artifacts(
    *,
    production_dir: Path,
    config_payload: Optional[Dict[str, Any]],
    training_partition_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    cfg = normalize_runtime_feature_selection_config(config_payload)
    out_dir = Path(production_dir) / "feature_selection"
    out_dir.mkdir(parents=True, exist_ok=True)

    stable_dmps = _load_csv(Path(production_dir) / "stable_dmps_genomewide.csv")
    if stable_dmps.empty:
        stable_dmps = _load_csv(Path(production_dir) / "stable_dmps_production.csv")
    bundle_dir = Path(production_dir) / "model_bundle"
    mapper_ann = _load_csv(bundle_dir / "mapper_dmp_annotations.csv")
    frozen_genes = _load_csv(bundle_dir / "frozen_genes_production.csv")
    frozen_gene_features = _load_csv(bundle_dir / "frozen_gene_features.csv")
    dmp_frequency = _load_csv(Path(production_dir).parent / "stability" / "dmp_frequency.csv")

    if stable_dmps.empty:
        stable_dmps = pd.DataFrame(columns=["chromosome", "position", "context", "effect_size"])
    work_dmps = stable_dmps.copy()
    if "context" not in work_dmps.columns:
        work_dmps["context"] = "CG"
    if "effect_size" not in work_dmps.columns:
        work_dmps["effect_size"] = 0.0
    work_dmps["abs_effect_size"] = pd.to_numeric(work_dmps["effect_size"], errors="coerce").abs().fillna(0.0)
    work_dmps["dmp_key"] = _dmp_key_series(work_dmps)

    if not dmp_frequency.empty:
        freq = dmp_frequency.copy()
        if "dmp_name" in freq.columns and "dmp_key" not in freq.columns:
            parsed = freq["dmp_name"].astype(str).str.split(":", expand=True)
            if parsed.shape[1] >= 3:
                left = parsed[0].astype(str).str.replace("chr", "", regex=False)
                left = left.str.cat(parsed[1].astype(str), sep=":")
                freq["dmp_key"] = left.str.cat(parsed[2].astype(str).str.upper(), sep=":")
        if "frequency" in freq.columns and "dmp_key" in freq.columns:
            freq_small = freq[["dmp_key", "frequency"]].copy()
            freq_small["frequency"] = pd.to_numeric(freq_small["frequency"], errors="coerce").fillna(0.0)
            work_dmps = work_dmps.merge(freq_small, on="dmp_key", how="left")
        else:
            work_dmps["frequency"] = 1.0
    else:
        work_dmps["frequency"] = 1.0

    min_freq = float(max(0.0, min(1.0, cfg.min_dmp_frequency)))
    if cfg.min_abs_effect_size is not None:
        work_dmps = work_dmps[work_dmps["abs_effect_size"] >= float(cfg.min_abs_effect_size)].copy()
    work_dmps = work_dmps[work_dmps["frequency"] >= min_freq].copy()
    work_dmps = work_dmps.sort_values(["abs_effect_size", "frequency"], ascending=[False, False])

    # DMP caps from total budget.
    dmp_cap = int(max(1, min(len(work_dmps), cfg.max_features_total)))
    selected_dmps = work_dmps.head(dmp_cap).copy()

    if not mapper_ann.empty and "gene_name" in mapper_ann.columns and "dmp_key" not in mapper_ann.columns:
        mapper_ann["dmp_key"] = _dmp_key_series(mapper_ann)
    gene_scores = pd.DataFrame(columns=["gene_name", "gene_score"])
    if not mapper_ann.empty and "gene_name" in mapper_ann.columns:
        ann = mapper_ann.copy()
        ann = ann[ann["gene_name"].astype(str).str.strip().ne("")]
        ann = ann[ann["gene_name"].astype(str).str.lower().ne("unknown")]
        if not ann.empty:
            if "effect_size" in ann.columns:
                ann["abs_effect_size"] = pd.to_numeric(ann["effect_size"], errors="coerce").abs().fillna(0.0)
            else:
                ann["abs_effect_size"] = 0.0
            gene_scores = (
                ann.groupby("gene_name")["abs_effect_size"].mean().to_frame(name="gene_score").reset_index()
            )

    if not frozen_genes.empty and "gene_name" in frozen_genes.columns:
        fg = frozen_genes.copy()
        if "gene_importance" in fg.columns:
            fg["gene_importance"] = pd.to_numeric(fg["gene_importance"], errors="coerce").fillna(0.0)
        else:
            fg["gene_importance"] = 0.0
        frozen_score = (
            fg.groupby("gene_name")["gene_importance"].max().to_frame(name="gene_score_frozen").reset_index()
        )
        if gene_scores.empty:
            gene_scores = frozen_score.rename(columns={"gene_score_frozen": "gene_score"})
        else:
            gene_scores = gene_scores.merge(frozen_score, on="gene_name", how="outer")
            if "gene_score" not in gene_scores.columns:
                gene_scores["gene_score"] = 0.0
            if "gene_score_frozen" not in gene_scores.columns:
                gene_scores["gene_score_frozen"] = 0.0
            gene_scores["gene_score"] = (
                pd.to_numeric(gene_scores["gene_score"], errors="coerce").fillna(0.0)
                + pd.to_numeric(gene_scores["gene_score_frozen"], errors="coerce").fillna(0.0)
            )
            gene_scores = gene_scores[["gene_name", "gene_score"]]

    gene_cap = max(1, cfg.max_features_total // 2)
    selected_genes = gene_scores.sort_values("gene_score", ascending=False).head(gene_cap).copy()

    selected_gene_features = pd.DataFrame()
    if not frozen_gene_features.empty and "gene_name" in frozen_gene_features.columns:
        f = frozen_gene_features.copy()
        if not selected_genes.empty:
            f = f[f["gene_name"].astype(str).isin(set(selected_genes["gene_name"].astype(str)))].copy()
        if "feature_effect_compound" in f.columns:
            f["feature_score"] = pd.to_numeric(f["feature_effect_compound"], errors="coerce").abs().fillna(0.0)
        else:
            f["feature_score"] = 0.0
        if "n_dmps_in_feature" in f.columns:
            f["feature_score"] += pd.to_numeric(f["n_dmps_in_feature"], errors="coerce").fillna(0.0)
        selected_gene_features = f.sort_values("feature_score", ascending=False).head(gene_cap).copy()

    selected_dmps_out = out_dir / "selected_dmps.csv"
    selected_genes_out = out_dir / "selected_genes.csv"
    selected_gene_features_out = out_dir / "selected_gene_features.csv"
    selected_features_out = out_dir / "selected_features.csv"
    selected_dmps.to_csv(selected_dmps_out, index=False)
    selected_genes.to_csv(selected_genes_out, index=False)
    selected_gene_features.to_csv(selected_gene_features_out, index=False)

    feat_rows: List[Dict[str, Any]] = []
    for _, row in selected_dmps.iterrows():
        feat_rows.append(
            {
                "feature_family": "dmp",
                "feature_id": str(row.get("dmp_key", "")),
                "parent_gene": "",
                "score": float(row.get("abs_effect_size", 0.0)),
            }
        )
    for _, row in selected_genes.iterrows():
        feat_rows.append(
            {
                "feature_family": "gene",
                "feature_id": str(row.get("gene_name", "")),
                "parent_gene": str(row.get("gene_name", "")),
                "score": float(row.get("gene_score", 0.0)),
            }
        )
    if not selected_gene_features.empty:
        for _, row in selected_gene_features.iterrows():
            start_num = pd.to_numeric(pd.Series([row.get("feature_start", 0)]), errors="coerce").fillna(0).iloc[0]
            end_num = pd.to_numeric(pd.Series([row.get("feature_end", 0)]), errors="coerce").fillna(0).iloc[0]
            feature_id = (
                f"{row.get('gene_name','')}::{row.get('feature_type','unknown')}::"
                f"{int(start_num)}::{int(end_num)}"
            )
            feat_rows.append(
                {
                    "feature_family": "structural",
                    "feature_id": feature_id,
                    "parent_gene": str(row.get("gene_name", "")),
                    "score": float(row.get("feature_score", 0.0)),
                }
            )
    selected_features_df = pd.DataFrame(feat_rows)
    selected_features_df.to_csv(selected_features_out, index=False)

    manifest = {
        "schema_version": "feature_selection_v1",
        "mode": cfg.mode,
        "enabled": bool(cfg.enabled),
        "config": {
            "feature_families": list(cfg.feature_families),
            "max_features_total": int(cfg.max_features_total),
            "max_features_per_sample_ratio": float(cfg.max_features_per_sample_ratio),
            "min_dmp_frequency": float(cfg.min_dmp_frequency),
            "min_abs_effect_size": cfg.min_abs_effect_size,
            "group_by_gene": bool(cfg.group_by_gene),
            "redundancy_filter": cfg.redundancy_filter,
            "max_pairwise_correlation": float(cfg.max_pairwise_correlation),
            "embedded_selector": cfg.embedded_selector,
            "latent_projection": cfg.latent_projection,
        },
        "training_partition_identity": training_partition_ids or [],
        "input_artifacts": {
            "stable_dmps": str((Path(production_dir) / "stable_dmps_genomewide.csv")),
            "mapper_annotation_csv": str(bundle_dir / "mapper_dmp_annotations.csv"),
            "frozen_genes": str(bundle_dir / "frozen_genes_production.csv"),
            "frozen_gene_features": str(bundle_dir / "frozen_gene_features.csv"),
        },
        "output_artifacts": {
            "selected_features_csv": str(selected_features_out),
            "selected_dmps_csv": str(selected_dmps_out),
            "selected_genes_csv": str(selected_genes_out),
            "selected_gene_features_csv": str(selected_gene_features_out),
        },
        "counts": {
            "selected_dmps": int(len(selected_dmps)),
            "selected_genes": int(len(selected_genes)),
            "selected_gene_features": int(len(selected_gene_features)),
            "selected_features_total": int(len(selected_features_df)),
        },
        "group_relationships": {
            "group_by_gene": bool(cfg.group_by_gene),
            "has_gene_linked_dmps": bool(not mapper_ann.empty),
        },
        "latent_projection_used": bool(cfg.latent_projection is not None),
    }
    manifest_path = out_dir / "feature_selection_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    report_lines = [
        "# Feature Selection Report",
        "",
        f"- enabled: `{cfg.enabled}`",
        f"- mode: `{cfg.mode}`",
        f"- selected DMPs: `{len(selected_dmps)}`",
        f"- selected genes: `{len(selected_genes)}`",
        f"- selected gene features: `{len(selected_gene_features)}`",
        f"- selected total features: `{len(selected_features_df)}`",
        "",
        "## Notes",
        "- Selector is deterministic and interpretable.",
        "- Runtime fold-only pruning is applied during backend training when enabled.",
    ]
    report_path = out_dir / "feature_selection_report.md"
    report_path.write_text("\n".join(report_lines).strip() + "\n", encoding="utf-8")
    return {
        "output_dir": str(out_dir),
        "manifest_path": str(manifest_path),
        "report_path": str(report_path),
        "selected_features_path": str(selected_features_out),
        "selected_dmps_path": str(selected_dmps_out),
        "selected_genes_path": str(selected_genes_out),
        "selected_gene_features_path": str(selected_gene_features_out),
        "counts": manifest["counts"],
    }


def load_selected_dmp_keys(manifest_path: Optional[str | Path]) -> Optional[set[str]]:
    if manifest_path is None:
        return None
    p = Path(manifest_path)
    if not p.is_file():
        return None
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    out_art = obj.get("output_artifacts") if isinstance(obj, dict) else None
    selected_dmps_csv = out_art.get("selected_dmps_csv") if isinstance(out_art, dict) else None
    if not selected_dmps_csv:
        return None
    df = _load_csv(Path(str(selected_dmps_csv)))
    if df.empty:
        return set()
    if "dmp_key" in df.columns:
        return set(df["dmp_key"].astype(str).tolist())
    return set(_dmp_key_series(df).astype(str).tolist())

