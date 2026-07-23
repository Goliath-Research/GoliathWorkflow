"""Sample-scoped CAAS store under ``/work/samples/{sample_id}/.caas/``.

Phase 4 of universal CAAS: sample-prep actions write/read a per-sample store
instead of the study ``{project_root}/.caas/``. Destructive and control-flow
actions remain hard opt-outs.

Enable with ``METHYL_SAMPLE_CAAS_ENABLED=1`` (or task ``sampleCaasEnabled: true``).
Default remains off until operators opt in.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Optional, Set

# Hard opt-outs even when sample CAAS is enabled.
SAMPLE_CAAS_OPT_OUT: dict[str, str] = {
    "sample.delete_fastqs": "destructive",
    "sample.delete_bam": "destructive",
    "sample.archive_sample": "remote_upload_etag_only",
    "sample.qc_failed": "control_flow",
}

# Prefixes deferred to sample-scoped store (not study .caas).
SAMPLE_SCOPED_PREFIXES = ("sample.", "parabricks.", "proteomics.", "align.")


def sample_caas_env_enabled() -> bool:
    env = os.environ.get("METHYL_SAMPLE_CAAS_ENABLED", "").strip().lower()
    return env in {"1", "true", "yes", "on"}


def sample_caas_enabled(input_json: Optional[Mapping[str, Any]] = None) -> bool:
    if input_json is not None:
        if input_json.get("sampleCaasEnabled") is True:
            return True
        if input_json.get("sampleCaasEnabled") is False:
            return False
    return sample_caas_env_enabled()


def is_sample_scoped_action(action_name: str) -> bool:
    return action_name.startswith(SAMPLE_SCOPED_PREFIXES)


def sample_caas_opt_out_reason(action_name: str) -> Optional[str]:
    return SAMPLE_CAAS_OPT_OUT.get(action_name)


def sample_caas_enabled_for_action(
    action_name: str,
    input_json: Optional[Mapping[str, Any]] = None,
) -> bool:
    """True when this sample-scoped action may use CAAS skip/commit."""
    if not is_sample_scoped_action(action_name):
        return False
    if sample_caas_opt_out_reason(action_name) is not None:
        return False
    return sample_caas_enabled(input_json)


def resolve_sample_id(input_json: Mapping[str, Any]) -> Optional[str]:
    for key in ("sampleId", "sample_id", "domainSample"):
        raw = input_json.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    sample_dir = input_json.get("sampleDir") or input_json.get("outputDir")
    if sample_dir:
        name = Path(str(sample_dir)).expanduser().name
        if name and name not in {".", ".."}:
            return name
    return None


def samples_base_dir(input_json: Optional[Mapping[str, Any]] = None) -> Path:
    if input_json:
        explicit = input_json.get("samplesBasePath") or input_json.get("samples_base_path")
        if explicit:
            return Path(str(explicit)).expanduser().resolve()
    env = os.environ.get("METHYL_SAMPLES_BASE", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path("/work/samples")


def resolve_sample_caas_root(input_json: Mapping[str, Any]) -> Optional[Path]:
    """Return ``{samples_base}/{sample_id}`` — store lives at ``.caas/`` under this root."""
    sample_id = resolve_sample_id(input_json)
    if not sample_id:
        return None
    return samples_base_dir(input_json) / sample_id


def opted_out_sample_actions() -> Set[str]:
    return set(SAMPLE_CAAS_OPT_OUT)
