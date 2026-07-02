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
        "methyl-centroid",
    }
)

# Pipeline modeling capabilities available when the corresponding CLI is on PATH.
_MODELING_CLI_CAPABILITIES: tuple[tuple[str, str], ...] = (
    ("methyl-centroid", "methyl-centroid"),
    ("methyl-detector", "methyl-detector"),
    ("methyl-dmp-select", "methyl-dmp-select"),
    ("methyl-mapper", "methyl-mapper"),
    ("methyl-gene-select", "methyl-gene-select"),
    ("methyl-gene-feature-select", "methyl-gene-feature-select"),
    ("methyl-enricher", "methyl-enricher"),
    ("methyl-disease-progression", "methyl-disease-progression"),
    ("methyl-classifier", "methyl-classifier"),
    ("methyl-predictor", "methyl-predictor"),
    ("methyl-fragmentomics", "methyl-fragmentomics"),
)

# In-process / sample-prep capabilities when the worker package is installed.
_ALWAYS_AVAILABLE_CAPABILITIES: FrozenSet[str] = frozenset(
    {
        "sample.download-fastq",
        "sample.trim-fastq",
        "sample.delete-fastqs",
        "sample.delete-bam",
        "sample.archive-sample",
        "sample.mark-failed",
        "methyl-qc",
        "methyl-extraction-qc",
        "validation.plan-iterations",
        "validation.stability",
        "validation.biomarker-filter",
        "validation.prepare-freeze-project",
        "validation.stability-freeze-readiness",
        "validation.link-artifacts",
        "validation.model-bundle",
        "validation.model-train",
        "validation.model-predict",
        "validation.select-best-model",
        "validation.model-mc",
        "validation.post-model-validation",
    }
)


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

    Otherwise probes GPU, Parabricks, extractor, and installed CLIs on the local VM.
    """
    if explicit:
        normalized = [str(c).strip() for c in explicit if str(c).strip()]
        if OMNIBUS_WILDCARD in normalized:
            return [OMNIBUS_WILDCARD]
        return sorted(set(normalized))

    caps: set[str] = set(_ALWAYS_AVAILABLE_CAPABILITIES)
    gpu = _gpu_available()

    for capability, binary in _MODELING_CLI_CAPABILITIES:
        if not _cli_on_path(binary):
            continue
        if capability in GPU_REQUIRED_CAPABILITIES and not gpu:
            logger.debug("Skipping %s: GPU required but not available", capability)
            continue
        caps.add(capability)

    if _parabricks_available() and gpu:
        caps.add("parabricks.fq2bam")
        caps.add("parabricks.giraffe")
    elif _parabricks_available() and not gpu:
        logger.warning("Parabricks image configured but no GPU; omitting parabricks.fq2bam")

    if _extractor_available():
        caps.add("methyl-extract")

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
    if capability in ("parabricks.fq2bam", "parabricks.giraffe") and not _parabricks_available():
        raise RuntimeError(
            "Worker configured for parabricks.fq2bam but Parabricks is not available. "
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
