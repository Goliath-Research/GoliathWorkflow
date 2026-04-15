from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, List, Optional, Tuple

import numpy as np

from methyl_predictor.project_resolver import resolve_predictor_config
from methyl_utils import load_project


@contextmanager
def _project_cwd(project_json: str | Path):
    pj = Path(project_json).resolve()
    prev = Path.cwd()
    try:
        os.chdir(pj.parent)
        yield
    finally:
        os.chdir(prev)


def resolve_eval_paths_and_labels(
    project_json: str | Path,
    class_names: List[str],
    predictor_cfg: Optional[Any] = None,
    project_loader: Optional[Any] = None,
) -> Tuple[List[str], Optional[np.ndarray]]:
    """
    Resolve evaluation samples with unified precedence used by model backends.

    Precedence:
      1) test_group_paths
      2) holdout_group_paths
      3) train_group_paths
      4) binary holdout_control/disease (only for binary class_names)
      5) binary train_control/disease (only for binary class_names)
      6) binary test_control/disease (only for binary class_names)
      7) project.get_resolved_groups() fallback
    """
    if predictor_cfg is None:
        predictor_cfg = resolve_predictor_config(project_json)
    samples: List[str] = []
    y_true: List[int] = []

    test_group_paths = getattr(predictor_cfg, "test_group_paths", None)
    holdout_group_paths = getattr(predictor_cfg, "holdout_group_paths", None)
    train_group_paths = getattr(predictor_cfg, "train_group_paths", None)
    test_control_paths = list(getattr(predictor_cfg, "test_control_paths", []) or [])
    test_disease_paths = list(getattr(predictor_cfg, "test_disease_paths", []) or [])
    holdout_control_paths = list(getattr(predictor_cfg, "holdout_control_paths", []) or [])
    holdout_disease_paths = list(getattr(predictor_cfg, "holdout_disease_paths", []) or [])
    train_control_paths = list(getattr(predictor_cfg, "train_control_paths", []) or [])
    train_disease_paths = list(getattr(predictor_cfg, "train_disease_paths", []) or [])

    if test_group_paths:
        for idx, entry in enumerate(test_group_paths):
            cls_idx = int(entry.get("class_index", idx))
            paths = [str(p) for p in (entry.get("paths") or [])]
            for p in paths:
                samples.append(p)
                y_true.append(cls_idx)
        return samples, np.asarray(y_true, dtype=np.int32)

    if holdout_group_paths:
        for idx, entry in enumerate(holdout_group_paths):
            cls_idx = int(entry.get("class_index", idx))
            paths = [str(p) for p in (entry.get("paths") or [])]
            for p in paths:
                samples.append(p)
                y_true.append(cls_idx)
        if samples:
            return samples, np.asarray(y_true, dtype=np.int32)

    if train_group_paths:
        for idx, entry in enumerate(train_group_paths):
            cls_idx = int(entry.get("class_index", idx))
            paths = [str(p) for p in (entry.get("paths") or [])]
            for p in paths:
                samples.append(p)
                y_true.append(cls_idx)
        if samples:
            return samples, np.asarray(y_true, dtype=np.int32)

    if (holdout_control_paths or holdout_disease_paths) and len(class_names) <= 2:
        samples = holdout_control_paths + holdout_disease_paths
        y_true = [0] * len(holdout_control_paths) + [1] * len(holdout_disease_paths)
        return samples, np.asarray(y_true, dtype=np.int32)

    if (train_control_paths or train_disease_paths) and len(class_names) <= 2:
        samples = train_control_paths + train_disease_paths
        y_true = [0] * len(train_control_paths) + [1] * len(train_disease_paths)
        return samples, np.asarray(y_true, dtype=np.int32)

    if (test_control_paths or test_disease_paths) and len(class_names) <= 2:
        samples = test_control_paths + test_disease_paths
        y_true = [0] * len(test_control_paths) + [1] * len(test_disease_paths)
        return samples, np.asarray(y_true, dtype=np.int32)

    loader = project_loader or load_project
    with _project_cwd(project_json):
        project = loader(project_json)
    for cls_idx, (_label, paths) in enumerate(project.get_resolved_groups()):
        if cls_idx >= len(class_names):
            continue
        for p in paths:
            samples.append(str(p))
            y_true.append(cls_idx)
    if samples:
        return samples, np.asarray(y_true, dtype=np.int32)
    return [], None
