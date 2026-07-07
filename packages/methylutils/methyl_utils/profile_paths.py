"""Resolve pipeline profile JSON paths for dev, release bundle, and operator overrides."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Optional, Union

PROFILE_ENV = "METHYL_PROFILE"
PROFILE_DIR_ENV = "METHYL_PROFILE_DIR"
EPIMETHYL_ROOT_ENV = "EPIMETHYL_ROOT"
DEFAULT_EPIMETHYL_ROOT = "/work/epimethyl"


def profile_search_dirs(*, extra: Optional[Iterable[Union[str, Path]]] = None) -> List[Path]:
    """Ordered directories to search for ``<name>.profile.json``."""
    dirs: List[Path] = []
    if extra:
        for item in extra:
            dirs.append(Path(str(item)).expanduser())
    raw_dir = os.environ.get(PROFILE_DIR_ENV)
    if raw_dir:
        dirs.append(Path(raw_dir).expanduser())
    epimethyl_root = Path(os.environ.get(EPIMETHYL_ROOT_ENV, DEFAULT_EPIMETHYL_ROOT)).expanduser()
    dirs.append(epimethyl_root / "current" / "runtime-bundle" / "domain" / "profiles")
    # Editable / dev checkout adjacent to packages/
    repo_profiles = Path(__file__).resolve().parents[3] / "workflow_engine" / "domain" / "profiles"
    dirs.append(repo_profiles)
    # Same module layout when workflow_engine/domain is on sys.path
    sibling_profiles = Path(__file__).resolve().parents[3] / "domain" / "profiles"
    dirs.append(sibling_profiles)
    seen: set[Path] = set()
    out: List[Path] = []
    for d in dirs:
        resolved = d.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(resolved)
    return out


def resolve_profile_path(name_or_path: Union[str, Path]) -> Path:
    """
    Resolve a profile file path.

    Accepts an existing file path or a profile name / alias (``mc_gene_fc``).
    """
    p = Path(name_or_path).expanduser()
    if p.is_file():
        return p.resolve()

    key = str(name_or_path).strip()
    if not key:
        raise FileNotFoundError("Empty pipeline profile name")

    aliases = {
        "buffy_mc_gene_fc": "mc_dmp_gene_fc",
        "mc_dmp_discovery": "mc_dmp",
        "mc_dmp_featurecuts": "mc_dmp_fc",
        "mc_gene_mapper": "mc_gene",
        "mc_gene_featurecuts": "mc_gene_fc",
        "gene_enricher_stability": "mc_dmp",
        "dmp_panel_stability": "mc_dmp_fc",
        "discovery_gene_featurecuts": "mc_dmp_gene_fc",
    }
    candidates = [key]
    if key in aliases:
        candidates.append(aliases[key])

    for name in candidates:
        for directory in profile_search_dirs():
            candidate = directory / f"{name}.profile.json"
            if candidate.is_file():
                return candidate.resolve()

    searched = ", ".join(str(d) for d in profile_search_dirs())
    raise FileNotFoundError(
        f"Unknown pipeline profile: {name_or_path!r} (searched: {searched})"
    )
