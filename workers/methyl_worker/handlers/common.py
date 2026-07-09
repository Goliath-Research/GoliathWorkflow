"""Shared helpers for in-process action handlers."""

from __future__ import annotations

from typing import Any, Dict

from methyl_utils.action_config_resolver import resolve_from_task_input


def resolve_reference_fasta(input_json: Dict[str, Any]) -> str:
    project = input_json.get("projectPath") or input_json.get("project")
    regulatory: Dict[str, Any] = {}
    if project:
        from methyl_utils import load_project

        regulatory = load_project(str(project)).get_regulatory_config()
    alignment_cfg = resolve_from_task_input("alignment_qc", input_json, regulatory=regulatory)
    methyl_cfg = resolve_from_task_input("methyl_extract", input_json, regulatory=regulatory)
    reference_raw = methyl_cfg.get("reference_fasta") or alignment_cfg.get("genome_fasta")
    if not reference_raw:
        raise RuntimeError(
            "reference genome is required in site reference_genome.fasta or "
            "profile/site actionConfig.alignment_qc / methyl_extract"
        )
    return str(reference_raw)
