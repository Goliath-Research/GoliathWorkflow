"""Run Houseman cell deconvolution for all project samples."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import pandas as pd

from ..config import CellDeconvStepConfig
from .houseman import deconvolve_sample, load_seed_basis


def run_cell_deconv_for_samples(
    samples: Sequence[Tuple[str, str]],
    output_dir: Path,
    cfg: CellDeconvStepConfig,
) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    basis = load_seed_basis(cfg.seed_basis_path)
    contexts = [str(c) for c in (cfg.contexts or ["CG"])]
    min_cov = int(cfg.marker_min_coverage) if cfg.marker_min_coverage is not None else 1
    min_frac = float(cfg.min_marker_fraction) if cfg.min_marker_fraction is not None else 0.25
    id_col = str(cfg.sample_id_column or "sample_id")

    rows: List[Dict[str, Any]] = []
    for sample_id, sample_dir in samples:
        props = deconvolve_sample(
            sample_dir,
            basis,
            contexts=contexts,
            min_coverage=min_cov,
            min_marker_fraction=min_frac,
            use_gpu=cfg.use_gpu,
        )
        row = {id_col: str(sample_id)}
        for ct in basis.cell_types:
            row[ct] = props.get(ct)
        row["n_markers_observed"] = props.get("n_markers_observed")
        row["marker_fraction"] = props.get("marker_fraction")
        row["qp_status"] = props.get("qp_status")
        rows.append(row)

    df = pd.DataFrame(rows)
    # Stable column order: id, cell types, diagnostics
    ordered = [id_col, *list(basis.cell_types), "n_markers_observed", "marker_fraction", "qp_status"]
    df = df.reindex(columns=ordered)
    csv_path = output_dir / "cell_fractions.csv"
    df.to_csv(csv_path, index=False)

    n_ok = int((df["qp_status"] == "ok").sum()) if "qp_status" in df.columns else 0
    manifest: Dict[str, Any] = {
        "output_csv": str(csv_path.resolve()),
        "n_samples": int(len(rows)),
        "n_columns": int(len(df.columns)),
        "n_ok": n_ok,
        "contexts": contexts,
        "cell_types": list(basis.cell_types),
        "seed_basis": basis.provenance,
        "marker_min_coverage": min_cov,
        "min_marker_fraction": min_frac,
        "use_gpu": cfg.use_gpu,
    }
    manifest_path = output_dir / "cell_fractions.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
