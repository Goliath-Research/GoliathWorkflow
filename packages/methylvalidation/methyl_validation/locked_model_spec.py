"""
Generate a locked-model specification artifact for auditability.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional


def _sha256(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def write_locked_model_spec(
    *,
    production_dir: Path,
    source_event: str,
    config: Optional[Any] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Emit `locked_model_spec.json/md` under production directory.
    """
    production_dir = Path(production_dir)
    production_dir.mkdir(parents=True, exist_ok=True)
    project_json = production_dir / "project.json"
    production_summary = _read_json(production_dir / "production_summary.json")
    selected_backend = _read_json(production_dir / "selected_backend.json")
    project_payload = _read_json(project_json)
    step_cfg = (project_payload.get("step_config") or {}) if isinstance(project_payload, dict) else {}
    val_cfg = (step_cfg.get("validation") or {}) if isinstance(step_cfg, dict) else {}
    reg_cfg = (val_cfg.get("regulatory") or {}) if isinstance(val_cfg, dict) else {}
    model_bundle_cfg = (step_cfg.get("model_bundle") or {}) if isinstance(step_cfg, dict) else {}

    stable_panel = Path(str(production_summary.get("fixed_dmp_panel") or production_dir / "stable_dmps_genomewide.csv"))
    mapper_ann = Path(str(model_bundle_cfg.get("mapper_annotation_csv") or ""))
    fixed_gene_panel = Path(str(model_bundle_cfg.get("fixed_gene_panel") or ""))
    fixed_gene_features = Path(str(model_bundle_cfg.get("fixed_gene_features") or ""))

    payload: Dict[str, Any] = {
        "spec_version": "locked_model_spec_v1",
        "source_event": source_event,
        "project_json": str(project_json),
        "regulatory": {
            "stage": reg_cfg.get("stage", "feasibility"),
            "allow_clinical_performance_claims": bool(
                reg_cfg.get("allow_clinical_performance_claims", False)
            ),
            "claim_boundary": reg_cfg.get(
                "claim_boundary",
                "Not pivotal-validation evidence unless lifecycle stage is pivotal_validation/fda_submission.",
            ),
            "intended_use_summary": reg_cfg.get("intended_use_summary"),
            "target_population": reg_cfg.get("target_population"),
            "sample_type": reg_cfg.get("sample_type"),
            "reference_standard": reg_cfg.get("reference_standard"),
        },
        "artifacts": {
            "fixed_dmp_panel": {
                "path": str(stable_panel) if stable_panel else None,
                "sha256": _sha256(stable_panel) if stable_panel else None,
            },
            "mapper_annotation_csv": {
                "path": str(mapper_ann) if mapper_ann else None,
                "sha256": _sha256(mapper_ann) if mapper_ann else None,
            },
            "fixed_gene_panel": {
                "path": str(fixed_gene_panel) if fixed_gene_panel else None,
                "sha256": _sha256(fixed_gene_panel) if fixed_gene_panel else None,
            },
            "fixed_gene_features": {
                "path": str(fixed_gene_features) if fixed_gene_features else None,
                "sha256": _sha256(fixed_gene_features) if fixed_gene_features else None,
            },
        },
        "selection": selected_backend or None,
        "runtime": {
            "model_backend": str(getattr(config, "model_backend", "")) if config is not None else None,
            "feature_mode": str(getattr(config, "feature_mode", "")) if config is not None else None,
            "feature_family_set": str(getattr(config, "feature_family_set", "")) if config is not None else None,
            "covariates_path": str(getattr(config, "covariates_path", "")) if config is not None else None,
            "validation_partitions": (
                getattr(getattr(config, "validation_partitions", None), "model_dump", lambda **_: None)(
                    mode="python", exclude_none=True
                )
                if config is not None and getattr(config, "validation_partitions", None) is not None
                else None
            ),
        },
    }
    if extra:
        payload["extra"] = extra

    json_path = production_dir / "locked_model_spec.json"
    md_path = production_dir / "locked_model_spec.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    lines = [
        "# Locked model specification",
        "",
        f"- source_event: `{source_event}`",
        f"- lifecycle stage: `{payload['regulatory'].get('stage')}`",
        f"- claims allowed: `{payload['regulatory'].get('allow_clinical_performance_claims')}`",
        f"- claim boundary: {payload['regulatory'].get('claim_boundary')}",
        "",
        "## Artifact hashes",
        "",
    ]
    for name, spec in (payload.get("artifacts") or {}).items():
        lines.append(f"- {name}: path=`{spec.get('path')}`, sha256=`{spec.get('sha256')}`")
    md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return {"json_path": str(json_path), "md_path": str(md_path), "payload": payload}

