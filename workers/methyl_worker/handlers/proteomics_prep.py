"""Proteomics sample-prep in-process handlers (DIA-NN, panel ingest, QC, register)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from pydantic import BaseModel

logger = logging.getLogger(__name__)


def _handle_diann(_capability: str, _action_name: str, input: BaseModel):
    from ..diann_runner import run_diann
    from ..sample_prep_log import append_sample_prep_log
    from ..task_models.proteomics_prep_models import DiannTaskOutput

    input_json: Dict[str, Any] = input.model_dump(mode="json")
    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.diann requires sampleDir and sampleId")
    site_path = input_json.get("siteConfigPath")
    result = run_diann(
        sample_id=str(sample_id),
        sample_dir=str(sample_dir),
        input_json=input_json,
        site_path=str(site_path) if site_path else None,
    )
    append_sample_prep_log(
        Path(str(sample_dir)),
        sample_id=str(sample_id),
        action="sample.diann",
        capability=_capability,
        attempt=int(input_json.get("qcAttempt") or 1),
        reason="DIA-NN GPU quantification",
        inputs={"ingestMode": "dia"},
        outputs=result,
        workflow_node_key=input_json.get("workflowNodeKey") or "diann",
    )
    return DiannTaskOutput(status="ok", sampleId=result.get("sampleId"), reportTsv=result.get("reportTsv"))


def _handle_sage(_capability: str, _action_name: str, input: BaseModel):
    from ..sage_runner import run_sage
    from ..sample_prep_log import append_sample_prep_log
    from ..task_models.proteomics_prep_models import SageTaskOutput

    input_json: Dict[str, Any] = input.model_dump(mode="json")
    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.sage requires sampleDir and sampleId")
    site_path = input_json.get("siteConfigPath")
    result = run_sage(
        sample_id=str(sample_id),
        sample_dir=str(sample_dir),
        input_json=input_json,
        site_path=str(site_path) if site_path else None,
    )
    append_sample_prep_log(
        Path(str(sample_dir)),
        sample_id=str(sample_id),
        action="sample.sage",
        capability=_capability,
        attempt=int(input_json.get("qcAttempt") or 1),
        reason="Sage DDA search + LFQ quant (CPU)",
        inputs={"ingestMode": "dda"},
        outputs=result,
        workflow_node_key=input_json.get("workflowNodeKey") or "sage",
    )
    return SageTaskOutput(
        status="ok",
        sampleId=result.get("sampleId"),
        reportTsv=result.get("reportTsv"),
        lfqTsv=result.get("lfqTsv"),
    )


def _handle_ingest_panel(_capability: str, _action_name: str, input: BaseModel):
    from proteomics_features.ingest import register_sample_abundance
    from ..sample_prep_log import append_sample_prep_log
    from ..task_models.proteomics_prep_models import AbundanceTaskOutput

    input_json: Dict[str, Any] = input.model_dump(mode="json")
    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.ingest_panel requires sampleDir and sampleId")

    from methyl_utils.action_config_resolver import resolve_from_task_input

    cfg = resolve_from_task_input("proteomics_quant", input_json)
    panel_path = input_json.get("panelPath") or cfg.get("panel_path")
    panel_format = input_json.get("panelFormat") or cfg.get("panel_format") or "open"
    if not panel_path:
        raise RuntimeError("sample.ingest_panel requires panelPath or actionConfig.proteomics_quant.panel_path")

    result = register_sample_abundance(
        sample_dir=str(sample_dir),
        sample_id=str(sample_id),
        source="panel",
        panel_path=str(panel_path),
        panel_format=str(panel_format),
    )
    append_sample_prep_log(
        Path(str(sample_dir)),
        sample_id=str(sample_id),
        action="sample.ingest_panel",
        capability=_capability,
        attempt=int(input_json.get("qcAttempt") or 1),
        reason=f"Panel ingest ({panel_format})",
        inputs={"ingestMode": "panel", "panelFormat": panel_format},
        outputs=result,
        workflow_node_key=input_json.get("workflowNodeKey") or "ingest_panel",
    )
    return AbundanceTaskOutput(status="ok", **result)


def _handle_register_abundance(_capability: str, _action_name: str, input: BaseModel):
    from proteomics_features.ingest import register_sample_abundance
    from ..sample_prep_log import append_sample_prep_log
    from ..task_models.proteomics_prep_models import AbundanceTaskOutput

    input_json: Dict[str, Any] = input.model_dump(mode="json")
    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.register_abundance requires sampleDir and sampleId")
    source = input_json.get("source") or "diann"
    result = register_sample_abundance(
        sample_dir=str(sample_dir),
        sample_id=str(sample_id),
        source=str(source),
    )
    append_sample_prep_log(
        Path(str(sample_dir)),
        sample_id=str(sample_id),
        action="sample.register_abundance",
        capability=_capability,
        attempt=int(input_json.get("qcAttempt") or 1),
        reason="Normalize proteomics quant to abundance.h5",
        inputs={"source": source},
        outputs=result,
        workflow_node_key=input_json.get("workflowNodeKey") or "register_abundance",
    )
    return AbundanceTaskOutput(status="ok", **result)


def _handle_dl_rescore(_capability: str, _action_name: str, input: BaseModel):
    from ..prosit_runner import run_prosit_rescore
    from ..task_models.proteomics_prep_models import DlRescoreTaskOutput

    input_json: Dict[str, Any] = input.model_dump(mode="json")
    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.dl_rescore requires sampleDir and sampleId")
    result = run_prosit_rescore(sample_id=str(sample_id), sample_dir=str(sample_dir), input_json=input_json)
    return DlRescoreTaskOutput(status="ok", sampleId=result.get("sampleId"), reportTsv=result.get("reportTsv"))


def _handle_casanovo(_capability: str, _action_name: str, input: BaseModel):
    from ..casanovo_runner import run_casanovo
    from ..task_models.proteomics_prep_models import CasanovoTaskOutput

    input_json: Dict[str, Any] = input.model_dump(mode="json")
    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.casanovo requires sampleDir and sampleId")
    result = run_casanovo(sample_id=str(sample_id), sample_dir=str(sample_dir), input_json=input_json)
    return CasanovoTaskOutput(status="ok", sampleId=result.get("sampleId"), peptidesCsv=result.get("peptidesCsv"))


def _handle_proteomics_qc(_capability: str, _action_name: str, input: BaseModel):
    from proteomics_qc.core import process_sample_proteomics_qc
    from ..handler_helpers import guardrails_from_payload
    from ..sample_prep_log import append_sample_prep_log
    from ..task_models.proteomics_prep_models import ProteomicsQcTaskOutput

    input_json: Dict[str, Any] = input.model_dump(mode="json")
    sample_dir = input_json.get("sampleDir")
    sample_id = input_json.get("sampleId")
    if not sample_dir or not sample_id:
        raise RuntimeError("sample.proteomics_qc requires sampleDir and sampleId")

    from methyl_utils.action_config_resolver import resolve_from_task_input

    qc_cfg = resolve_from_task_input("proteomics_qc", input_json)
    qc_path = process_sample_proteomics_qc(Path(str(sample_dir)), str(sample_id), config=qc_cfg)
    payload = json.loads(Path(qc_path).read_text(encoding="utf-8"))
    guardrails_raw = payload.get("guardrails") or {}
    guardrails = guardrails_from_payload(guardrails_raw if isinstance(guardrails_raw, dict) else {})
    append_sample_prep_log(
        Path(str(sample_dir)),
        sample_id=str(sample_id),
        action="sample.proteomics_qc",
        capability=_capability,
        attempt=int(input_json.get("qcAttempt") or 1),
        reason="Proteomics QC guardrails",
        inputs={},
        outputs={"qcPath": str(qc_path), "overallPass": guardrails.overall_pass},
        workflow_node_key=input_json.get("workflowNodeKey") or "proteomics_qc",
    )
    return ProteomicsQcTaskOutput(
        status="ok",
        sampleId=str(sample_id),
        qcPath=str(qc_path),
        guardrails=guardrails,
        proteomicsQcPass=guardrails.overall_pass,
    )
