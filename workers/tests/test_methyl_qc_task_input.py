"""MethylQcTaskInput is extra=forbid; alignmentMode is a typed field, not getattr."""

from __future__ import annotations

import inspect

import pytest
from pydantic import ValidationError

from methyl_worker.action_catalog import find_catalog_entry
from methyl_worker.action_execution import validate_input
from methyl_worker.handlers import sample_prep as sample_prep_handlers
from methyl_worker.task_models.sample_prep_models import MethylQcTaskInput


def test_alignment_mode_is_declared_on_methyl_qc_input() -> None:
    assert "alignmentMode" in MethylQcTaskInput.model_fields
    assert MethylQcTaskInput.model_config.get("extra") == "forbid"


def test_methyl_qc_input_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="extra"):
        MethylQcTaskInput.model_validate(
            {
                "tool": "MethylAlignmentQc",
                "sampleId": "S1",
                "sampleDir": "/work/samples/S1",
                "notAField": True,
            }
        )


def test_validate_input_keeps_alignment_mode() -> None:
    entry = find_catalog_entry("sample.methyl_qc")
    assert entry is not None
    model = validate_input(
        entry,
        {
            "tool": "MethylAlignmentQc",
            "sampleId": "S1",
            "sampleDir": "/work/samples/S1",
            "alignmentMode": "linear",
        },
    )
    assert isinstance(model, MethylQcTaskInput)
    assert model.alignmentMode == "linear"


def test_qc_handler_reads_typed_alignment_mode() -> None:
    src = inspect.getsource(sample_prep_handlers._handle_methyl_qc)
    assert "getattr(input, \"alignmentMode\"" not in src
    assert "input.alignmentMode" in src
    assert 'resolvedConfig or {}).get("alignmentMode")' not in src
