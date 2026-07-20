"""Detect and validate worker capability sets for registration and dispatch."""

from __future__ import annotations

import logging
import os
import shutil
from typing import FrozenSet, Optional, Sequence

logger = logging.getLogger(__name__)

OMNIBUS_WILDCARD = "*"

# Capabilities that require a functional NVIDIA GPU at execute time (defense-in-depth).
GPU_REQUIRED_CAPABILITIES: FrozenSet[str] = frozenset(
    {
        "parabricks.fq2bam",
        "parabricks.giraffe",
        "parabricks.rna_fq2bam",
        "parabricks.kallisto",
        "methyl-centroid",
    }
)

# Probe kinds for catalog-derived auto-detection (not tunable science parameters).
_PROBE_ALWAYS = "always"
_PROBE_CLI = "cli"
_PROBE_PARABRICKS = "parabricks"
_PROBE_EXTRACTOR = "extractor"


def _capability_probe_kind(capability: str, *, execution_mode: str, cli_tool: Optional[str]) -> str:
    """Classify how auto-detect decides whether a catalog capability is available."""
    if capability in (
        "parabricks.fq2bam",
        "parabricks.giraffe",
        "parabricks.rna_fq2bam",
        "parabricks.kallisto",
    ):
        return _PROBE_PARABRICKS
    if capability == "methyl-extract":
        return _PROBE_EXTRACTOR
    if execution_mode == "cli" and cli_tool:
        return _PROBE_CLI
    return _PROBE_ALWAYS


def _catalog_capability_rows() -> list[tuple[str, str, Optional[str]]]:
    """Return (capability, probe_kind, cli_tool) derived from ACTION_CATALOG."""
    from .action_catalog import ACTION_CATALOG

    rows: list[tuple[str, str, Optional[str]]] = []
    seen: set[str] = set()
    for entry in ACTION_CATALOG:
        if entry.capability in seen:
            continue
        seen.add(entry.capability)
        kind = _capability_probe_kind(
            entry.capability,
            execution_mode=entry.execution_mode,
            cli_tool=entry.cli_tool,
        )
        rows.append((entry.capability, kind, entry.cli_tool))
    return rows


def _gpu_available() -> bool:
    try:
        from methyl_utils.gpu_detection import is_gpu_available

        return bool(is_gpu_available())
    except Exception:
        return shutil.which("nvidia-smi") is not None


def _parabricks_available() -> bool:
    if os.environ.get("METHYL_PARABRICKS_IMAGE", "").strip():
        return True
    if shutil.which("docker") is None:
        return False
    try:
        import subprocess

        proc = subprocess.run(
            ["docker", "images", "-q", "nvcr.io/nvidia/clara-parabricks"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return bool(proc.stdout.strip())
    except Exception:
        return False


def _extractor_available() -> bool:
    if os.environ.get("METHYL_EXTRACTOR_BIN", "").strip():
        return True
    return shutil.which("MethylExtractor") is not None


def _cli_on_path(binary: str) -> bool:
    return shutil.which(binary) is not None


def resolve_worker_capabilities(
    *,
    explicit: Optional[Sequence[str]] = None,
) -> list[str]:
    """
    Compute the capability set this node can serve.

    When ``explicit`` is provided, returns that set (deduplicated). A single ``*`` entry
    means omnibus (matches any task capability at dispatch).

    Otherwise probes GPU, Parabricks, extractor, and installed CLIs from the action catalog.
    """
    if explicit:
        normalized = [str(c).strip() for c in explicit if str(c).strip()]
        if OMNIBUS_WILDCARD in normalized:
            return [OMNIBUS_WILDCARD]
        return sorted(set(normalized))

    caps: set[str] = set()
    gpu = _gpu_available()
    parabricks_ok = _parabricks_available()
    extractor_ok = _extractor_available()

    for capability, kind, cli_tool in _catalog_capability_rows():
        if kind == _PROBE_ALWAYS:
            caps.add(capability)
            continue
        if kind == _PROBE_CLI:
            if not cli_tool or not _cli_on_path(cli_tool):
                continue
            if capability in GPU_REQUIRED_CAPABILITIES and not gpu:
                logger.debug("Skipping %s: GPU required but not available", capability)
                continue
            caps.add(capability)
            continue
        if kind == _PROBE_PARABRICKS:
            if parabricks_ok and gpu:
                caps.add(capability)
            elif parabricks_ok and not gpu:
                logger.warning(
                    "Parabricks image configured but no GPU; omitting %s", capability
                )
            continue
        if kind == _PROBE_EXTRACTOR:
            if extractor_ok:
                caps.add(capability)
            continue

    if not caps:
        logger.warning("resolve_worker_capabilities: no capabilities detected; registering omnibus")
        return [OMNIBUS_WILDCARD]

    return sorted(caps)


def capability_requires_gpu(capability: str) -> bool:
    return capability in GPU_REQUIRED_CAPABILITIES


def assert_node_can_serve_capability(capability: str) -> None:
    """Raise RuntimeError when WORKER_CAPABILITY targets hardware this node lacks."""
    if not capability or capability == OMNIBUS_WILDCARD:
        return
    if capability_requires_gpu(capability) and not _gpu_available():
        raise RuntimeError(
            f"Worker configured for capability {capability!r} but no functional GPU was detected. "
            "Install NVIDIA drivers/CuPy, verify nvidia-smi, or run a CPU-only capability unit."
        )
    if (
        capability
        in ("parabricks.fq2bam", "parabricks.giraffe", "parabricks.rna_fq2bam", "parabricks.kallisto")
        and not _parabricks_available()
    ):
        raise RuntimeError(
            f"Worker configured for capability {capability!r} but Parabricks is not available. "
            "Set METHYL_PARABRICKS_IMAGE or install the nvcr.io Parabricks image."
        )
    if capability == "methyl-extract" and not _extractor_available():
        raise RuntimeError(
            "Worker configured for methyl-extract but MethylExtractor is not on PATH. "
            "Set METHYL_EXTRACTOR_BIN or install MethylExtractor."
        )


def assert_execute_gpu_prereqs(capability: str, action_name: str) -> None:
    """Execute-time guard; should not trigger when dispatch is capability-based."""
    if not capability_requires_gpu(capability):
        return
    if _gpu_available():
        return
    raise RuntimeError(
        f"Action {action_name!r} (capability {capability!r}) requires a GPU but none is available. "
        "Re-register this worker with detected capabilities or move the task to a GPU pool."
    )
