"""
MethylCentroidExplorer: Inspect a MethylFrame (single H5, single JSON mixture, or folder of H5 files).
Identifies type (MethylSample, MethylBasicCentroid, MethylExtendedCentroid, MethylBetaBinomialCentroid,
MethylBetaMixtureCentroid), prints metadata, and optionally describes a range of positions in detail.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import h5py
except ImportError:
    h5py = None

import numpy as np
import pandas as pd


def _get_methyl_group(f) -> Any:
    """Return the group containing pos, mC, uC, tnc (methylation_data or root)."""
    if "methylation_data" in f and hasattr(f["methylation_data"], "keys"):
        return f["methylation_data"]
    return f


def _detect_type_from_keys(keys: List[str]) -> str:
    """Infer MethylFrame type from HDF5 dataset keys (without loading data)."""
    keys_set = set(keys)
    if "N" not in keys_set:
        return "MethylSample"
    if not {"Sx", "Sx2", "log_x_sum", "log_1_minus_x_sum"}.issubset(keys_set):
        return "MethylBasicCentroid"
    bb = {"sum_mC", "sum_uC", "sum_cov", "sum_cov2", "sum_mC2", "sum_uC2", "Sx3", "Sx4", "count_zero", "count_one"}
    if bb.issubset(keys_set):
        return "MethylBetaBinomialCentroid"
    return "MethylExtendedCentroid"


def _is_project_config(path: Path) -> bool:
    """Return True if the JSON file looks like a project config (not a MethylBetaMixtureCentroid)."""
    path = Path(path)
    if path.suffix.lower() != ".json" or not path.is_file():
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(data, dict):
        return False
    has_project = "project_name" in data
    has_project_keys = any(k in data for k in ("output_base", "controls", "diseases", "step_config"))
    return bool(has_project and has_project_keys)


def _get_mixture_info(path: Path) -> Tuple[str, int, Dict[str, Any], List[str]]:
    """Load MethylBetaMixtureCentroid from JSON. Returns (type_name, n_positions, metadata, column_names)."""
    path = Path(path)
    if _is_project_config(path):
        raise ValueError(
            f"{path} is a project config file, not a MethylFrame or mixture centroid. "
            "Point to a centroid output folder (containing .h5 files such as 1-CG.h5) or to a single .h5 file."
        )
    from methyl_utils.core.methyl_mixture_centroid import MethylBetaMixtureCentroid
    centroid = MethylBetaMixtureCentroid.from_json(path)
    df = centroid.df
    n_positions = len(df)
    metadata = dict(centroid.metadata)
    keys = list(df.columns)
    return "MethylBetaMixtureCentroid", n_positions, metadata, keys


def get_frame_info(path: Path) -> Tuple[str, int, Dict[str, Any], List[str]]:
    """
    Read HDF5 or JSON without loading full data. Returns (type_name, n_positions, metadata, dataset_keys).
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Not a file: {path}")
    if path.suffix.lower() == ".json":
        return _get_mixture_info(path)
    if not h5py:
        raise RuntimeError("h5py is required for MethylCentroidExplorer")
    with h5py.File(path, "r") as f:
        group = _get_methyl_group(f)
        if isinstance(group, h5py.Group):
            keys = list(group.keys())
        else:
            keys = list(f.keys())
        required = {"pos", "mC", "uC", "tnc"}
        if not required.issubset(set(keys)):
            raise ValueError(f"Missing required datasets {required - set(keys)} in {path}")
        pos_ds = group["pos"] if "pos" in group.keys() else f["pos"]
        n_positions = int(pos_ds.shape[0])
        type_name = _detect_type_from_keys(keys)
        metadata = {}
        for name, value in f.attrs.items():
            try:
                if isinstance(value, (bytes, str)):
                    s = value.decode("utf-8") if isinstance(value, bytes) else value
                    metadata[name] = json.loads(s)
                else:
                    metadata[name] = value
            except (json.JSONDecodeError, TypeError):
                metadata[name] = value
        return type_name, n_positions, metadata, keys


def get_positions_in_range(path: Path, pos_start: int, pos_end: int) -> np.ndarray:
    """Read pos/position dataset and return positions that fall in [pos_start, pos_end] (inclusive)."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        if _is_project_config(path):
            raise ValueError(
                f"{path} is a project config file, not a MethylFrame or mixture centroid. "
                "Point to a centroid output folder (containing .h5 files) or to a single .h5 file."
            )
        from methyl_utils.core.methyl_mixture_centroid import MethylBetaMixtureCentroid
        centroid = MethylBetaMixtureCentroid.from_json(path)
        pos = np.asarray(centroid.df["position"].values, dtype=np.uint32)
        mask = (pos >= pos_start) & (pos <= pos_end)
        return np.unique(pos[mask])
    if not h5py:
        raise RuntimeError("h5py is required")
    with h5py.File(path, "r") as f:
        group = _get_methyl_group(f)
        pos_ds = group["pos"]
        pos = np.asarray(pos_ds[:], dtype=np.uint32)
    mask = (pos >= pos_start) & (pos <= pos_end)
    return np.unique(pos[mask])


def load_frame(path: Path, positions: Optional[np.ndarray] = None):
    """Load a MethylFrame from H5 or MethylBetaMixtureCentroid from JSON; optionally filter by positions."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        if _is_project_config(path):
            raise ValueError(
                f"{path} is a project config file, not a MethylFrame or mixture centroid. "
                "Point to a centroid output folder (containing .h5 files) or to a single .h5 file."
            )
        from methyl_utils.core.methyl_mixture_centroid import MethylBetaMixtureCentroid
        centroid = MethylBetaMixtureCentroid.from_json(path)
        if positions is not None and len(positions) > 0:
            df = centroid.df
            mask = np.isin(np.asarray(df["position"].values, dtype=np.uint32), positions)
            subset = df.loc[mask].copy()
            return MethylBetaMixtureCentroid(subset, metadata=centroid.metadata)
        return centroid
    from methyl_utils.core.io import load_from_h5
    return load_from_h5(path, positions=positions)


# --- Mean/variance formulas per distribution (for position table) ---

def _mean_var_normal_from_sufficient(N: float, Sx: float, Sx2: float):
    """Normal (sample) mean and variance from sufficient stats: mean = Sx/N, var = (Sx2 - Sx²/N)/(N-1)."""
    if N is None or N < 1:
        return None, None
    mean = Sx / N
    if N <= 1:
        return mean, None
    var = (Sx2 - (Sx * Sx) / N) / (N - 1)
    var = max(0.0, var) if var is not None else None
    return mean, var


def _mean_var_normal_from_counts(mC: int, uC: int):
    """Normal (empirical proportion) mean and variance from counts: mean = mC/(mC+uC), var = p(1-p)/n."""
    cov = mC + uC
    if cov <= 0:
        return None, None
    mean = mC / cov
    var = (mean * (1 - mean) / cov) if cov > 0 else None
    return mean, var


def _mean_var_beta(alpha: float, beta: float):
    """Beta: mean = α/(α+β), var = αβ/((α+β)²(α+β+1))."""
    if alpha is None or beta is None or (alpha + beta) <= 0:
        return None, None
    s = alpha + beta
    mean = alpha / s
    var = (alpha * beta) / ((s * s) * (s + 1))
    return mean, var


def _mean_var_betamixture_row(weights: Any, alphas: Any, betas: Any):
    """Beta mixture for one row: mean = Σ w_j μ_j, var = Σ w_j(σ²_j + μ²_j) - mean²."""
    if weights is None or alphas is None or betas is None:
        return None, None
    w = np.asarray(weights if isinstance(weights, (list, np.ndarray)) else json.loads(weights) if isinstance(weights, str) else [])
    a = np.asarray(alphas if isinstance(alphas, (list, np.ndarray)) else json.loads(alphas) if isinstance(alphas, str) else [])
    b = np.asarray(betas if isinstance(betas, (list, np.ndarray)) else json.loads(betas) if isinstance(betas, str) else [])
    if len(w) == 0 or len(a) != len(w) or len(b) != len(w):
        return None, None
    a = np.maximum(np.asarray(a, dtype=np.float64), 1e-10)
    b = np.maximum(np.asarray(b, dtype=np.float64), 1e-10)
    comp_mean = a / (a + b)
    comp_var = (a * b) / ((a + b) ** 2 * (a + b + 1))
    mean = float(np.sum(w * comp_mean))
    var = float(np.sum(w * (comp_var + comp_mean ** 2)) - mean ** 2)
    var = max(0.0, var)
    return mean, var


def _safe_series_values(obj, name: str):
    """Get values from a DataFrame column or property; return list for JSON/print."""
    try:
        s = getattr(obj, name, None)
        if s is None and hasattr(obj, "_df") and name in obj._df.columns:
            s = obj._df[name]
        if s is not None:
            v = s.values if hasattr(s, "values") else np.asarray(s)
            return np.asarray(v).tolist()
    except Exception:
        pass
    return None


def _build_mixture_position_table(frame, pos_start: int, pos_end: int) -> pd.DataFrame:
    """Build per-position table for MethylBetaMixtureCentroid (position, context, k, weights, alphas, betas, mean_betamixture, var_betamixture, best_distribution, ...)."""
    df = frame._df.copy()
    if "position" not in df.columns:
        return pd.DataFrame()
    pos = np.asarray(df["position"], dtype=np.uint32)
    mask = (pos >= pos_start) & (pos <= pos_end)
    df = df.loc[mask].copy()
    if len(df) == 0:
        return pd.DataFrame()
    # Mean and variance for BetaMixture at each position
    mean_bmm = []
    var_bmm = []
    for _, row in df.iterrows():
        m, v = _mean_var_betamixture_row(
            row.get("weights"), row.get("alphas"), row.get("betas")
        )
        mean_bmm.append(m)
        var_bmm.append(v)
    out = df.copy()
    out["mean_betamixture"] = mean_bmm
    out["var_betamixture"] = var_bmm
    out["best_distribution"] = "BetaMixture"
    # mean and variance = best-distribution estimates (BetaMixture here)
    out["mean"] = mean_bmm
    out["variance"] = var_bmm
    # Count-based and other distribution columns N/A for mixture-only data (consistent table shape)
    out["mean_counts"] = None
    out["var_counts"] = None
    out["mean_normal"] = None
    out["var_normal"] = None
    out["mean_beta"] = None
    out["var_beta"] = None
    out["mean_betabinomial"] = None
    out["var_betabinomial"] = None
    # Serialize list columns for CSV/TSV (weights, alphas, betas)
    for col in ("weights", "alphas", "betas"):
        if col in out.columns:
            out[col] = out[col].apply(lambda x: json.dumps(x) if isinstance(x, (list, np.ndarray)) else x)
    return out


def build_position_table(frame, pos_start: int, pos_end: int) -> pd.DataFrame:
    """
    Build a per-position table with pos, mC, uC, coverage; mean_counts, var_counts (from counts);
    distribution-specific mean_* and var_* (Normal, Beta, BetaBinomial, BetaMixture, ECDF); best_distribution;
    and mean, variance as the best-distribution estimates (for MethylCentroidPair / MethylDetector).
    Also type-specific fields (N, Sx, Sx2, alpha, beta; BetaBinomial: Sx3, Sx4, count_zero, count_one, sum_*;
    BetaMixture: position, context, k, weights, alphas, betas, n_samples, converged, bic, loglik, status).
    """
    # MethylBetaMixtureCentroid: no "pos", has "position" and "weights"
    if hasattr(frame, "_df") and "position" in frame._df.columns and "weights" in frame._df.columns:
        return _build_mixture_position_table(frame, pos_start, pos_end)
    frame = frame.to_cpu()
    df = frame._df.copy()
    pos = np.asarray(df["pos"])
    mask = (pos >= pos_start) & (pos <= pos_end)
    df = df.loc[mask].copy()
    if len(df) == 0:
        return pd.DataFrame()
    # Trigger alpha/beta on the full frame so they are in _df, then copy to our slice
    if hasattr(frame, "alpha"):
        try:
            _ = frame.alpha
            _ = frame.beta
            if "alpha" in frame._df.columns and "beta" in frame._df.columns:
                df["alpha"] = frame._df.loc[df.index, "alpha"].values
                df["beta"] = frame._df.loc[df.index, "beta"].values
        except Exception:
            pass
    # Trigger alpha_bb/beta_bb for BetaBinomial centroids
    if hasattr(frame, "alpha_bb"):
        try:
            _ = frame.alpha_bb
            _ = frame.beta_bb
            if "alpha_bb" in frame._df.columns and "beta_bb" in frame._df.columns:
                df["alpha_bb"] = frame._df.loc[df.index, "alpha_bb"].values
                df["beta_bb"] = frame._df.loc[df.index, "beta_bb"].values
        except Exception:
            pass
    has_binned = (
        getattr(frame, "binned_stats", None) is not None
        and isinstance(getattr(frame, "binned_stats", None), dict)
        and "bin_edges" in getattr(frame, "binned_stats", {})
        and "bin_counts" in getattr(frame, "binned_stats", {})
    )
    max_n_ecdf = 30
    rows = []
    for _, row in df.iterrows():
        r = {"pos": int(row["pos"]), "mC": int(row["mC"]), "uC": int(row["uC"])}
        cov = int(row["mC"]) + int(row["uC"])
        r["coverage"] = cov
        if "N" in df.columns:
            r["N"] = int(row["N"])
        if "Sx" in df.columns:
            r["Sx"] = float(row["Sx"])
        if "Sx2" in df.columns:
            r["Sx2"] = float(row["Sx2"])
        if "log_x_sum" in df.columns:
            r["log_x_sum"] = float(row["log_x_sum"])
        if "log_1_minus_x_sum" in df.columns:
            r["log_1_minus_x_sum"] = float(row["log_1_minus_x_sum"])
        a = float(row["alpha"]) if "alpha" in df.columns else None
        b = float(row["beta"]) if "beta" in df.columns else None
        r["alpha"] = a
        r["beta"] = b
        # BetaBinomial sufficient statistics for parameter estimation
        for col in (
            "sum_mC", "sum_uC", "sum_cov", "sum_cov2", "sum_mC2", "sum_uC2",
            "Sx3", "Sx4", "count_zero", "count_one",
        ):
            if col in df.columns:
                val = row[col]
                r[col] = int(val) if isinstance(val, (np.integer, int)) else float(val) if isinstance(val, (np.floating, float)) else val

        # --- Count-based and distribution-specific mean/variance (all estimated parameters together) ---
        mean_counts, var_counts = _mean_var_normal_from_counts(int(row["mC"]), int(row["uC"]))
        r["mean_counts"] = mean_counts
        r["var_counts"] = var_counts
        # Normal: sample mean and variance (from sufficient stats or from counts)
        if "N" in df.columns and "Sx" in df.columns and "Sx2" in df.columns:
            mn, vn = _mean_var_normal_from_sufficient(
                float(row["N"]), float(row["Sx"]), float(row["Sx2"])
            )
        else:
            mn, vn = _mean_var_normal_from_counts(int(row["mC"]), int(row["uC"]))
        r["mean_normal"] = mn
        r["var_normal"] = vn
        # Beta: mean = α/(α+β), var = αβ/((α+β)²(α+β+1))
        mean_beta, var_beta = _mean_var_beta(a, b)
        r["mean_beta"] = mean_beta
        r["var_beta"] = var_beta
        # BetaBinomial: use same unbiased mean/variance as Normal/ECDF when sufficient stats exist (N>=2)
        a_bb = float(row["alpha_bb"]) if "alpha_bb" in df.columns else None
        b_bb = float(row["beta_bb"]) if "beta_bb" in df.columns else None
        if "N" in df.columns and "Sx" in df.columns and "Sx2" in df.columns and vn is not None:
            # Distribution-independent: mean = Sx/N, variance = (Sx2 - Sx²/N)/(N-1)
            r["mean_betabinomial"] = mn
            r["var_betabinomial"] = vn
        elif a_bb is not None and b_bb is not None:
            mean_bb, var_bb = _mean_var_beta(a_bb, b_bb)
            r["mean_betabinomial"] = mean_bb
            r["var_betabinomial"] = var_bb
        else:
            r["mean_betabinomial"] = None
            r["var_betabinomial"] = None
        # BetaMixture: not computed per position for HDF5 centroids (only in mixture table)
        r["mean_betamixture"] = None
        r["var_betamixture"] = None
        # ECDF: mean = Sx/N, variance = unbiased sample variance (Sx2 - Sx²/N)/(N-1), same as Normal/BetaBinomial
        if "N" in df.columns and "Sx" in df.columns and "Sx2" in df.columns:
            n_val = float(row["N"])
            sx_val = float(row["Sx"])
            sx2_val = float(row["Sx2"])
            mean_ecdf = sx_val / max(n_val, 1.0)
            # Unbiased sample variance, distribution-independent
            var_ecdf = (sx2_val - (sx_val ** 2) / max(n_val, 1.0)) / max(n_val - 1.0, 1.0)
            r["mean_ecdf"] = mean_ecdf
            r["var_ecdf"] = max(var_ecdf, 1e-12)
        else:
            r["mean_ecdf"] = None
            r["var_ecdf"] = None
        # Best distribution for this centroid type (ECDF when binned_stats and N < threshold)
        n_val = int(row["N"]) if "N" in df.columns else 0
        if has_binned and n_val < max_n_ecdf and r.get("mean_ecdf") is not None:
            r["best_distribution"] = "ECDF"
        elif a_bb is not None and b_bb is not None:
            r["best_distribution"] = "BetaBinomial"
        elif a is not None and b is not None:
            r["best_distribution"] = "Beta"
        else:
            r["best_distribution"] = "Normal"
        # mean and variance = best-distribution estimates (for MethylCentroidPair / MethylDetector)
        best = r["best_distribution"]
        if best == "ECDF":
            r["mean"] = r["mean_ecdf"]
            r["variance"] = r["var_ecdf"]
        else:
            r["mean"] = r.get("mean_betamixture") if best == "BetaMixture" else r.get("mean_betabinomial") if best == "BetaBinomial" else r.get("mean_beta") if best == "Beta" else r.get("mean_normal")
            r["variance"] = r.get("var_betamixture") if best == "BetaMixture" else r.get("var_betabinomial") if best == "BetaBinomial" else r.get("var_beta") if best == "Beta" else r.get("var_normal")
        rows.append(r)
    return pd.DataFrame(rows)


def list_h5_in_folder(folder: Path) -> List[Path]:
    """Return sorted list of .h5 files in folder (non-recursive)."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(folder.glob("*.h5"))


def _check_output_not_under_input(output_path: Path, input_path: Path) -> None:
    """Raise ValueError if output would be written under the read-only input path."""
    output_resolved = output_path.resolve()
    input_base = input_path.resolve() if input_path.is_dir() else input_path.resolve().parent
    try:
        output_resolved.resolve().relative_to(input_base)
        raise ValueError(
            f"Refusing to write under read-only input path. "
            f"Output would be inside {input_base}. Use a path outside the centroid or package (e.g. current directory)."
        )
    except ValueError as e:
        if "Refusing to write" in str(e):
            raise
        # relative_to raised: output is not under input, which is good
        pass


def _stem_to_chrom_context(stem: str) -> Tuple[str, str]:
    """Parse chrom and context from stem (e.g. '1-CG' -> ('1', 'CG'), '2-CHG' -> ('2', 'CHG'))."""
    parts = stem.split("-")
    return (parts[0], parts[1]) if len(parts) >= 2 else (stem, "")


def run_explorer(
    path: Path,
    *,
    file_filter: Optional[str] = None,
    chrom: Optional[str] = None,
    context: Optional[str] = None,
    pos_start: Optional[int] = None,
    pos_end: Optional[int] = None,
    max_positions: int = 10_000,
    json_metadata: bool = False,
    output: Optional[Path] = None,
    export_format: str = "csv",
    single_csv: bool = False,
    single_json: bool = False,
) -> None:
    """
    Main explorer logic: resolve path (file or folder), detect type, print metadata,
    optionally print position range detail.
    """
    path = Path(path).resolve()
    if path.is_file():
        target = path
    elif path.is_dir():
        h5_files = list_h5_in_folder(path)
        if not h5_files:
            print(f"No .h5 files in {path}", file=sys.stderr)
            return
        if file_filter:
            h5_files = [p for p in h5_files if file_filter in p.name]
        if chrom or context:
            # e.g. 1-CG.h5
            parts = []
            if chrom:
                parts.append(str(chrom))
            if context:
                parts.append(str(context))
            pattern = "-".join(parts)
            h5_files = [p for p in h5_files if pattern in p.name or p.name.startswith(pattern + "-")]
        if not h5_files:
            print("No matching .h5 file after filter.", file=sys.stderr)
            return
        # Process all matching .h5 files ({chrom}-{context}.h5)
        targets = [Path(p) if not isinstance(p, Path) else p for p in h5_files]
    else:
        print(f"Path not found: {path}", file=sys.stderr)
        return

    # Single file: path was a file
    if path.is_file():
        targets = [target]

    # Full range when only --max-positions is set; otherwise use --pos-start/--pos-end
    pos_start_val = pos_start if pos_start is not None else 0
    pos_end_val = pos_end if pos_end is not None else (1 << 32) - 1
    has_position_range = (pos_start is not None or pos_end is not None) or max_positions is not None
    combined_tables: List[pd.DataFrame] = []  # for --single-csv
    combined_metadata: Dict[str, Any] = {}   # for --single-json: stem -> {path, type, positions, datasets, metadata}

    for idx, target in enumerate(targets):
        if len(targets) > 1:
            print(f"\n--- {target.name} ({idx + 1}/{len(targets)}) ---")
        type_name, n_positions, metadata, keys = get_frame_info(target)
        if single_json:
            combined_metadata[target.stem] = {
                "path": str(target.resolve()),
                "type": type_name,
                "positions": n_positions,
                "datasets": sorted(keys),
                "metadata": metadata,
            }
        print(f"Path: {target}")
        print(f"Type: {type_name}")
        print(f"Positions: {n_positions:,}")
        print(f"Datasets: {', '.join(sorted(keys))}")
        if json_metadata:
            print("Metadata (JSON):")
            print(json.dumps(metadata, indent=2, default=str))
        else:
            print("Metadata:")
            for k, v in metadata.items():
                print(f"  {k}: {v}")

        if not has_position_range:
            continue

        positions_to_load = get_positions_in_range(target, pos_start_val, pos_end_val)
        if len(positions_to_load) == 0:
            print(f"No positions in range [{pos_start_val}, {pos_end_val}].", file=sys.stderr)
            continue
        if len(positions_to_load) > max_positions:
            print(f"Range has {len(positions_to_load):,} positions; capping to {max_positions} (use --max-positions to change).", file=sys.stderr)
            positions_to_load = positions_to_load[:max_positions]
        # When user gave only --max-positions (no pos-start/pos-end), use actual range for filename and table
        file_start = int(positions_to_load.min()) if pos_start is None and pos_end is None else pos_start_val
        file_end = int(positions_to_load.max()) if pos_start is None and pos_end is None else pos_end_val
        frame = load_frame(target, positions=positions_to_load)
        table = build_position_table(frame, file_start, file_end)
        if table is None or len(table) == 0:
            print("No rows in position table.")
            continue

        chrom_str, context_str = _stem_to_chrom_context(target.stem)

        if single_csv:
            # Prepend chromosome and context; accumulate for one CSV at the end
            out_df = table.copy()
            out_df.insert(0, "context", context_str)
            out_df.insert(0, "chromosome", chrom_str)
            combined_tables.append(out_df)
            print(f"Collected {len(table):,} rows for {target.name} (chromosome={chrom_str}, context={context_str})")
        else:
            # Export path: -o is output directory; same filename as default (e.g. 1-CG_positions_100000_200000.csv)
            basename = target.stem
            out_dir = Path(output).resolve() if output is not None else Path.cwd()
            if out_dir.suffix.lower() in (".csv", ".tsv", ".txt"):
                out_dir = out_dir.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{basename}_positions_{file_start}_{file_end}.{export_format}"
            fmt = export_format
            _check_output_not_under_input(out_path, path)

            if fmt == "csv":
                table.to_csv(out_path, index=False)
            else:
                table.to_csv(out_path, index=False, sep="\t")
            print(f"Exported {len(table):,} rows to {out_path} ({fmt.upper()})")

        pd.set_option("display.max_rows", None)
        pd.set_option("display.width", None)
        print("\nPosition detail (first rows):")
        print(table.head(500).to_string(index=False))
        if len(table) > 500:
            print(f"... and {len(table) - 500} more rows.")

    # Write single combined CSV when --single-csv was used
    if single_csv and combined_tables:
        out_dir = Path(output).resolve() if output is not None else Path.cwd()
        if out_dir.suffix.lower() in (".csv", ".tsv", ".txt"):
            out_dir = out_dir.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        combined = pd.concat(combined_tables, ignore_index=True)
        c_min, c_max = int(combined["pos"].min()), int(combined["pos"].max())
        out_path = out_dir / f"positions_{c_min}_{c_max}.{export_format}"
        _check_output_not_under_input(out_path, path)
        if export_format == "csv":
            combined.to_csv(out_path, index=False)
        else:
            combined.to_csv(out_path, index=False, sep="\t")
        print(f"\nExported single {export_format.upper()} with chromosome and context: {out_path} ({len(combined):,} rows)")

    # Write single JSON with metadata for all chrom-context .h5 when --single-json was used
    if single_json and combined_metadata:
        out_dir = Path(output).resolve() if output is not None else Path.cwd()
        if out_dir.suffix.lower() in (".csv", ".tsv", ".txt", ".json"):
            out_dir = out_dir.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "metadata.json"
        _check_output_not_under_input(out_path, path)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(combined_metadata, f, indent=2, default=str)
        print(f"\nExported single JSON with metadata for {len(combined_metadata)} file(s): {out_path}")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="MethylCentroidExplorer: Inspect a MethylFrame (folder or .h5 file) or MethylBetaMixtureCentroid (.json), detect type, print metadata, and optionally describe a range of positions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("path", type=Path, help="Path to a MethylFrame folder, a single .h5 file, or a MethylBetaMixtureCentroid .json file")
    parser.add_argument("--file", dest="file_filter", metavar="SUBSTR", help="If path is a folder, only consider .h5 files whose name contains SUBSTR (e.g. '1-CG')")
    parser.add_argument("--chrom", "-c", help="If path is a folder, filter to .h5 files for this chromosome (e.g. 1)")
    parser.add_argument("--context", "-x", choices=["CG", "CHG", "CHH"], help="If path is a folder, filter to this context")
    parser.add_argument("--pos-start", type=int, default=None, metavar="POS", help="Start of position range (inclusive) for per-position detail")
    parser.add_argument("--pos-end", type=int, default=None, metavar="POS", help="End of position range (inclusive) for per-position detail")
    parser.add_argument("--max-positions", type=int, default=10_000, metavar="N", help="Maximum number of positions to load. If only this is set (no --pos-start/--pos-end), uses the full range of each file capped at N (default 10000).")
    parser.add_argument("--json-metadata", action="store_true", help="Print metadata as JSON")
    parser.add_argument("--output", "-o", type=Path, default=None, metavar="DIR", help="Output directory for exported position tables. Files keep the same name (e.g. 1-CG_positions_START_END.csv). Default: current directory.")
    parser.add_argument("--single-csv", action="store_true", help="Export one CSV/TSV with chromosome and context as first two columns (combines all files when path is a folder).")
    parser.add_argument("--single-json", action="store_true", help="Export one valid JSON file with metadata for all chrom-context .h5 in the folder (keyed by stem, e.g. 1-CG).")
    parser.add_argument("--format", "-f", choices=["csv", "tsv", "txt"], default="csv", dest="export_format", help="Format when using default output path (default: csv). With --output, format is inferred from extension.")
    args = parser.parse_args()
    # Infer format from --output extension if provided
    export_format = args.export_format
    if args.output is not None and args.output.suffix.lower() in (".csv", ".tsv", ".txt"):
        export_format = args.output.suffix.lower().lstrip(".")
    run_explorer(
        args.path,
        file_filter=args.file_filter,
        chrom=args.chrom,
        context=args.context,
        pos_start=args.pos_start,
        pos_end=args.pos_end,
        max_positions=args.max_positions,
        json_metadata=args.json_metadata,
        output=args.output,
        export_format=export_format,
        single_csv=args.single_csv,
        single_json=args.single_json,
    )


if __name__ == "__main__":
    main()
