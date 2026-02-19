"""
Load sample CSVs, resolve paths with samples_base_path, and perform stratified train/val split.
"""

import csv
import random
from pathlib import Path
from typing import List, Tuple


def _resolve_entry(entry: str, base: Path) -> str:
    entry = entry.strip()
    if not entry:
        return ""
    if not _looks_like_absolute_path(entry):
        return str(base.resolve() / entry)
    return entry


def _looks_like_absolute_path(entry: str) -> bool:
    if not entry:
        return False
    e = entry.strip()
    return e.startswith("/") or (len(e) > 1 and e[1] == ":")


def load_and_resolve_sample_paths(csv_path: str | Path, base_path: str | Path) -> List[str]:
    """
    Load sample names/paths from a CSV (one column or header 'sample'/'path') and resolve
    with base_path (relative names -> base_path / name). Returns list of full paths.
    """
    base = Path(base_path).resolve()
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"Sample list file not found: {path}")
    out: List[str] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        first_row = next(reader, None)
        if first_row is None:
            return out
        # Header row?
        if first_row and first_row[0].strip().lower() in (
            "sample",
            "path",
            "sample_path",
            "name",
            "id",
        ):
            for row in reader:
                if len(row) > 0:
                    r = _resolve_entry(row[0], base)
                    if r:
                        out.append(r)
        else:
            if len(first_row) > 0:
                r = _resolve_entry(first_row[0], base)
                if r:
                    out.append(r)
            for row in reader:
                if len(row) > 0:
                    r = _resolve_entry(row[0], base)
                    if r:
                        out.append(r)
    return out


def stratified_split(
    control_paths: List[str],
    disease_paths: List[str],
    train_fraction: float,
    seed: int | None = None,
) -> Tuple[List[str], List[str], List[str], List[str]]:
    """
    Split control and disease samples into train and validation sets, keeping the same
    class proportion (stratified). Uses the same train_fraction for both classes.

    Returns:
        (train_control, train_disease, val_control, val_disease)
    """
    rng = random.Random(seed)
    n_control = len(control_paths)
    n_disease = len(disease_paths)
    if n_control == 0 or n_disease == 0:
        raise ValueError("Need at least one control and one disease sample for stratified split")

    control_shuffled = list(control_paths)
    disease_shuffled = list(disease_paths)
    rng.shuffle(control_shuffled)
    rng.shuffle(disease_shuffled)

    n_train_control = max(1, int(n_control * train_fraction))
    n_train_disease = max(1, int(n_disease * train_fraction))
    # Ensure we leave at least one for validation if possible
    if n_train_control >= n_control and n_control > 1:
        n_train_control = n_control - 1
    if n_train_disease >= n_disease and n_disease > 1:
        n_train_disease = n_disease - 1

    train_control = control_shuffled[:n_train_control]
    val_control = control_shuffled[n_train_control:]
    train_disease = disease_shuffled[:n_train_disease]
    val_disease = disease_shuffled[n_train_disease:]

    if not train_control or not train_disease:
        raise ValueError(
            "Stratified split produced empty train set: need at least one control and one disease for training"
        )
    if not val_control or not val_disease:
        raise ValueError(
            "Stratified split produced empty validation set: need at least one control and one disease for validation"
        )

    return train_control, train_disease, val_control, val_disease
