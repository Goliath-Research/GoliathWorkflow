"""Helpers for building typed handler outputs from domain artifacts."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel

from .task_models.sample_prep_models import (
    GuardrailsOutput,
    QcHistoryEntry,
    ScreeningOutput,
)


def screening_from_payload(screening: Mapping[str, Any]) -> ScreeningOutput:
    return ScreeningOutput(
        disposition=screening.get("disposition"),
        trim_front1=int(screening.get("trim_front1") or 0),
        trim_tail1=int(screening.get("trim_tail1") or 0),
        trim_front2=int(screening.get("trim_front2") or 0),
        trim_tail2=int(screening.get("trim_tail2") or 0),
        message=screening.get("message"),
    )


def guardrails_from_payload(guardrails: Mapping[str, Any]) -> GuardrailsOutput:
    screening_raw = guardrails.get("screening") or {}
    screening = screening_from_payload(screening_raw if isinstance(screening_raw, dict) else {})
    return GuardrailsOutput(
        overall_pass=guardrails.get("overall_pass"),
        screening=screening,
    )


def qc_history_from_payload(history: List[Any]) -> List[QcHistoryEntry]:
    entries: List[QcHistoryEntry] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        screening_raw = item.get("screening") or {}
        entries.append(
            QcHistoryEntry(
                attempt=int(item.get("attempt") or 1),
                reason=str(item.get("reason") or ""),
                overall_pass=item.get("overall_pass"),
                disposition=(
                    screening_raw.get("disposition")
                    if isinstance(screening_raw, dict)
                    else item.get("disposition")
                ),
            )
        )
    return entries


def methyl_qc_result_code(*, remediate: bool, permanent_fail: bool = False) -> int:
    if permanent_fail:
        return 2
    if remediate:
        return 1
    return 0


def model_dump_subset(model: type[BaseModel], payload: Mapping[str, Any]) -> dict[str, Any]:
    return {k: payload[k] for k in model.model_fields if k in payload}
