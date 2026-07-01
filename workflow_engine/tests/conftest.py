"""Shared fixtures for workflow_engine tests.

Provides a helper to decouple committed study projects from production ``/work``
sample CSVs so profile/compile tests do not depend on cluster-local data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


def _rewrite_sample_paths(node: Any, tmp_dir: Path, counter: dict, sample_names: list) -> None:
    """Recursively replace every ``sample_paths`` list with local temp CSVs.

    Each CSV lists two unique sample folder names (recorded in ``sample_names``) so
    the caller can materialize matching H5 evidence for sample QC.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "sample_paths" and isinstance(value, list):
                new_paths = []
                for _ in value:
                    counter["n"] += 1
                    a = f"SAMPLE_{counter['n']:03d}_A"
                    b = f"SAMPLE_{counter['n']:03d}_B"
                    sample_names.extend([a, b])
                    csv = tmp_dir / f"samples_{counter['n']:03d}.csv"
                    csv.write_text(f"sample\n{a}\n{b}\n", encoding="utf-8")
                    new_paths.append(str(csv))
                node[key] = new_paths
            else:
                _rewrite_sample_paths(value, tmp_dir, counter, sample_names)
    elif isinstance(node, list):
        for item in node:
            _rewrite_sample_paths(item, tmp_dir, counter, sample_names)


def _materialize_h5_evidence(
    samples_base: Path, sample_names: list, chromosomes: list, contexts: list
) -> None:
    """Create minimal ``{chrom}-{ctx}.h5`` files so sample QC marks samples eligible."""
    samples_base.mkdir(parents=True, exist_ok=True)
    for name in sample_names:
        sample_dir = samples_base / name
        sample_dir.mkdir(parents=True, exist_ok=True)
        for chrom in chromosomes:
            for ctx in contexts:
                (sample_dir / f"{chrom}-{ctx}.h5").write_bytes(b"h5")


def project_with_local_samples(src_project: Path, tmp_path: Path) -> Path:
    """Copy a committed project JSON, pointing all sample CSVs at local temp files.

    Keeps the real cohort/stage structure (so compile + enrich exercise the actual
    fixture) while removing the dependency on ``/work/projects/.../data/*.csv`` and
    ``/work/samples`` H5 evidence.
    """
    data = json.loads(Path(src_project).read_text(encoding="utf-8"))
    sample_dir = tmp_path / "data"
    sample_dir.mkdir(parents=True, exist_ok=True)
    sample_names: list = []
    _rewrite_sample_paths(data, sample_dir, {"n": 0}, sample_names)

    samples_base = tmp_path / "samples"
    data["samples_base_path"] = str(samples_base)

    chromosomes = data.get("chromosomes") or ["1"]
    contexts = data.get("contexts") or ["CG"]
    _materialize_h5_evidence(samples_base, sample_names, chromosomes, contexts)

    out = tmp_path / f"{Path(src_project).stem}.local.json"
    out.write_text(json.dumps(data), encoding="utf-8")
    return out


@pytest.fixture
def local_project(tmp_path: Path):
    """Factory fixture: decouple a committed project from /work sample CSVs."""

    def _factory(src_project: Path) -> Path:
        return project_with_local_samples(src_project, tmp_path)

    return _factory
