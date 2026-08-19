"""Paired FASTQ discovery shared by Align and fastp trim.

This module is aligner-agnostic. Clara ``trim_fastq`` imports from here so
FASTQ pairing does not load an aligner runner.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

logger = logging.getLogger(__name__)

FASTQ_SUFFIXES: Sequence[str] = (".fastq.gz", ".fq.gz", ".fastq", ".fq")
# {prefix}_1 / {prefix}_2 and Illumina {prefix}_R1[_001] / {prefix}_R2[_001]
# Capture separator and optional lane segment so sample_R1 ≠ sample_1 and
# _001 ≠ _002 (they are distinct pairs, not collisions on the same mate slot).
_FASTQ_MATE_RE = re.compile(
    r"^(?P<prefix>.+)(?P<sep>_R|_r|_)(?P<mate>[12])(?:_(?P<segment>[0-9]{3}))?$"
)
_FASTQ_BARE_R_RE = re.compile(
    r"^R(?P<mate>[12])(?:_(?P<segment>[0-9]{3}))?$", re.IGNORECASE
)
_SKIP_FASTQ_DIR_NAMES = frozenset({"tmp", ".caas"})


def _matches_fastq(path: Path) -> bool:
    name = path.name.lower()
    return any(name.endswith(suffix) for suffix in FASTQ_SUFFIXES)


def _fastq_stem(path: Path) -> str:
    name = path.name
    lower = name.lower()
    for suffix in FASTQ_SUFFIXES:
        if lower.endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def _mate_group(path: Path) -> Tuple[Tuple[str, str, str, str], str] | None:
    """Return ((parent, prefix, sep, segment), mate) or None if unparseable.

    ``sep`` and ``segment`` are part of the pair identity so ``sample_R1`` does
    not collide with ``sample_1``, and ``_R1_001`` does not collide with ``_R1_002``.
    """
    stem = _fastq_stem(path)
    match = _FASTQ_MATE_RE.match(stem)
    if match is None:
        match = _FASTQ_BARE_R_RE.match(stem)
        if match is None:
            return None
        prefix = "R"
        sep = "R"
    else:
        prefix = match.group("prefix")
        sep = match.group("sep")
    segment = match.group("segment") or ""
    parent = str(path.parent.resolve())
    return (parent, prefix, sep, segment), match.group("mate")


def _collect_fastqs(sample_dir: Path) -> List[Path]:
    found: List[Path] = []
    seen: set[Path] = set()
    for path in sample_dir.rglob("*"):
        if not path.is_file() or not _matches_fastq(path):
            continue
        rel_dirs = {part.lower() for part in path.relative_to(sample_dir).parts[:-1]}
        if rel_dirs & _SKIP_FASTQ_DIR_NAMES:
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        found.append(path)
    return sorted(found)


def canonical_trimmed_fastqs(sample_dir: Path, sample_id: str) -> Tuple[Path, Path]:
    """Remediation outputs that Align prefers: ``{id}_1.trimmed.fastq.gz`` / ``_2``."""
    root = Path(sample_dir)
    return (
        root / f"{sample_id}_1.trimmed.fastq.gz",
        root / f"{sample_id}_2.trimmed.fastq.gz",
    )


def _is_trimmed_fastq_name(path: Path) -> bool:
    return ".trimmed." in path.name.lower()


def resolve_paired_fastqs(
    sample_dir: Path,
    sample_id: str,
    *,
    prefer_trimmed: bool = True,
) -> List[Path]:
    """Return paired-end FASTQs (one or more pairs) for a sample.

    Aligners accept several R1/R2 pairs (multi-lane / multi-flowcell). An even
    count of mate-paired files is valid. Trimmed ``{id}_1.trimmed.fastq.gz`` /
    ``_2`` at *sample_dir* wins for Align (remediation). Trim must pass
    ``prefer_trimmed=False`` so it never feeds those outputs back into fastp.
    """
    trimmed = list(canonical_trimmed_fastqs(sample_dir, sample_id))
    if prefer_trimmed and all(p.is_file() for p in trimmed):
        return trimmed

    skip = {p.resolve() for p in trimmed}
    all_fastqs = _collect_fastqs(sample_dir)
    groups: Dict[Tuple[str, str, str, str], Dict[str, Path]] = {}
    leftovers: List[Path] = []
    for path in all_fastqs:
        if (not prefer_trimmed) and (
            path.resolve() in skip or _is_trimmed_fastq_name(path)
        ):
            continue
        parsed = _mate_group(path)
        if parsed is None:
            leftovers.append(path)
            continue
        key, mate = parsed
        mates = groups.setdefault(key, {})
        if mate in mates:
            existing = mates[mate]
            raise RuntimeError(
                f"Duplicate FASTQ mate {mate} under {sample_dir}: "
                f"{existing.relative_to(sample_dir)} and {path.relative_to(sample_dir)}"
            )
        mates[mate] = path

    pairs: List[Tuple[Path, Path]] = []
    for key in sorted(groups):
        mates = groups[key]
        if "1" in mates and "2" in mates:
            pairs.append((mates["1"], mates["2"]))
        else:
            leftovers.extend(mates.values())

    if not pairs:
        raise RuntimeError(
            f"Expected paired FASTQ files under {sample_dir}, found {len(all_fastqs)}"
            + (f": {', '.join(p.name for p in all_fastqs)}" if all_fastqs else "")
        )
    if leftovers:
        logger.warning(
            "Ignoring unpaired FASTQ(s) under %s: %s",
            sample_dir,
            ", ".join(str(p.relative_to(sample_dir)) for p in leftovers),
        )
    ordered: List[Path] = []
    for r1, r2 in pairs:
        ordered.extend((r1, r2))
    return ordered
