"""Config registry object kinds."""

from __future__ import annotations

from typing import Literal

Kind = Literal[
    "site",
    "pipeline_profile",
    "domain_program",
    "study",
    "credential",
    "storage_endpoint",
    "storage_profile",
    "reference_asset",
    "action_definition",
    "enrichment_library_preset",
]

CFG_KINDS: tuple[Kind, ...] = (
    "site",
    "pipeline_profile",
    "domain_program",
    "study",
    "credential",
    "storage_endpoint",
    "storage_profile",
    "reference_asset",
    "action_definition",
    "enrichment_library_preset",
)

# Kinds whose document may be written under /work (never credential).
MATERIALIZABLE_KINDS: tuple[Kind, ...] = (
    "site",
    "pipeline_profile",
    "domain_program",
    "study",
    "storage_endpoint",
    "storage_profile",
    "reference_asset",
    "action_definition",
    "enrichment_library_preset",
)
